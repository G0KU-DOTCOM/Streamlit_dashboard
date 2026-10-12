"""Conservative Atlas uploader: audit, pilot, then resumable bounded writes.

Only ind320_energy.hourly_flows is written. No deletes, upgrades or automatic
retries. Credentials and server errors are never persisted or printed.
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import time
import tomllib

from bson import BSON, decode_file_iter
from bson.codec_options import CodecOptions
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi

from pipeline.entsoe_budget import _save_json

DATABASE='ind320_energy'
COLLECTION='hourly_flows'
BATCH_SIZE=40
PILOT_DOCUMENTS=200
RESERVE_BYTES=4*1024**2
MAX_WRITE_ATTEMPTS=160000
CODEC=CodecOptions(tz_aware=True, tzinfo=timezone.utc)


class UploadStopped(RuntimeError):
    pass


def number(mapping,key):
    value=mapping.get(key)
    if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise UploadStopped('Missing or invalid storage statistics; no upload allowed.')
    return int(value)


def connect(root):
    try:
        with (Path(root)/'.streamlit/secrets.toml').open('rb') as handle:
            uri=tomllib.load(handle)['mongo']['uri']
        client=MongoClient(uri,server_api=ServerApi('1'),maxPoolSize=2,
            serverSelectionTimeoutMS=10000,connectTimeoutMS=10000,socketTimeoutMS=15000,
            retryWrites=False,retryReads=False,w='majority',wTimeoutMS=10000,
            tz_aware=True,tzinfo=timezone.utc)
        del uri
        client.admin.command('ping')
        return client
    except Exception:
        if 'client' in locals():client.close()
        raise UploadStopped('Atlas connection failed; connection details hidden.') from None


def audit(client):
    # False avoids silently listing only the databases this user can access.
    names=[d['name'] for d in client.admin.command(
        {'listDatabases':1,'nameOnly':True,'authorizedDatabases':False})['databases']
        if d['name'] not in ('admin','local','config')]
    total=project=0
    for name in names:
        stats=client[name].command('dbStats',scale=1,maxTimeMS=10000)
        size=number(stats,'dataSize')+number(stats,'indexSize')
        total+=size
        if name==DATABASE:project=size
    db=client[DATABASE]
    if COLLECTION in db.list_collection_names():
        s=db.command('collStats',COLLECTION,scale=1,maxTimeMS=10000)
        collection={'documents':number(s,'count'),'data_bytes':number(s,'size'),
                    'index_bytes':number(s,'totalIndexSize')}
    else:
        collection={'documents':0,'data_bytes':0,'index_bytes':0}
    return {'checked_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'cluster_bytes':total,'project_bytes':project,'collection':collection}


def admit(stats,limits,*,remaining_bytes,batch_bytes=0,new_documents=0):
    c=stats['collection']
    if remaining_bytes<0 or batch_bytes<0 or new_documents<0:
        raise UploadStopped('Invalid upload budget inputs.')
    if c['documents']+new_documents>limits['max_mongo_documents']:
        raise UploadStopped('Document-count limit would be exceeded.')
    # Reserve twice all remaining BSON for future data+indexes, plus 4 MiB.
    # A separate four-times-batch allowance protects each next small mutation.
    extra=RESERVE_BYTES+max(2*remaining_bytes,4*batch_bytes)
    if stats['project_bytes']+extra>limits['max_mongo_project_data_plus_indexes_bytes']:
        raise UploadStopped('Project data/index headroom is insufficient; upload stopped.')
    if stats['cluster_bytes']+extra>limits['max_mongo_cluster_data_plus_indexes_bytes']:
        raise UploadStopped('Whole-cluster headroom is insufficient; upload stopped.')
    return {'reserved_headroom_bytes':extra,
            'projected_project_bytes':stats['project_bytes']+extra,
            'projected_cluster_bytes':stats['cluster_bytes']+extra}


def artifact(root):
    report=json.loads((root/'no_sync/entsoe_hourly_report.json').read_text())
    plan=json.loads((root/'entsoe_plan.json').read_text())
    path=root/'no_sync/entsoe_curated/hourly_flows.bson'
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024**2),b''):digest.update(chunk)
    if digest.hexdigest()!=report['sha256'] or path.stat().st_size!=report['bson_bytes']:
        raise UploadStopped('Curated file differs from the verified artifact.')
    if report['documents']>plan['planned_limits']['max_mongo_documents']:
        raise UploadStopped('Artifact exceeds document limit.')
    return report,plan,path


def documents(path):
    with path.open('rb') as handle:
        yield from decode_file_iter(handle,codec_options=CODEC)


def verify_local(path,report):
    count=0;previous=None;size=0
    start=datetime.fromisoformat(report['period']['start_inclusive'])
    end=datetime.fromisoformat(report['period']['end_exclusive'])
    totals={}
    for d in documents(path):
        stamp=d['time_utc'];key=f"{d['connection']}|{stamp:%Y%m%dT%H%MZ}"
        if d['_id']!=key or (previous is not None and key<=previous):
            raise UploadStopped('Local IDs are duplicated, unsorted or invalid.')
        if not start<=stamp<end or stamp.minute or stamp.second or stamp.microsecond:
            raise UploadStopped('Invalid UTC hour in local artifact.')
        for direction in ('import','export'):
            energy=d[f'{direction}_mwh']
            if not isinstance(energy,(int,float)) or not math.isfinite(energy) or energy<0 or d[f'{direction}_coverage_minutes']!=60:
                raise UploadStopped('Invalid energy or incomplete local coverage.')
            pair=(d['connection'],direction);totals[pair]=totals.get(pair,0.0)+energy
        previous=key;count+=1;size+=len(BSON.encode(d))
    if count!=report['documents'] or size!=report['bson_bytes']:
        raise UploadStopped('Local file count/size mismatch.')
    for expected in report['energy_checks']:
        value=totals.pop((expected['connection'],expected['direction']),None)
        if value is None or abs(value-expected['raw_mwh'])>max(1e-5,abs(expected['raw_mwh'])*1e-10):
            raise UploadStopped('Local energy differs from raw totals.')
    if totals:raise UploadStopped('Unexpected connection/direction in local file.')


def split_batches(iterator,size=BATCH_SIZE):
    batch=[]
    for document in iterator:
        batch.append(document)
        if len(batch)==size:
            yield batch;batch=[]
    if batch:yield batch


def missing_documents(collection,batch):
    found={d['_id']:d for d in collection.find({'_id':{'$in':[d['_id'] for d in batch]}},max_time_ms=10000).limit(len(batch)+1)}
    missing=[]
    for d in batch:
        if d['_id'] not in found:missing.append(d)
        elif found[d['_id']]!=d:
            raise UploadStopped('Existing document differs; no overwrite or delete performed.')
    return missing


def ensure_index(collection):
    expected=[('connection',1),('time_utc',1)]
    indexes=list(collection.list_indexes())
    for index in indexes:
        if index['name']=='_id_':continue
        if list(index['key'].items())!=expected or not index.get('unique'):
            raise UploadStopped('Unexpected existing index; review storage before continuing.')
    if len(indexes)==1:
        collection.create_index(expected,name='connection_time_utc',unique=True)


def run(root,mode):
    root=Path(root);source,plan,path=artifact(root);limits=plan['planned_limits']
    verify_local(path,source)
    progress_path=root/'no_sync/entsoe_mongo_progress.json'
    with (root/'no_sync/entsoe_mongo.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise UploadStopped('Another MongoDB upload is active.') from None
        progress=json.loads(progress_path.read_text()) if progress_path.exists() else {
            'source_sha256':source['sha256'],'status':'not_started','verified_documents':0,
            'verified_bson_bytes':0,'write_attempts':0,'last_write_at':0,'checkpoints':[]}
        if progress['source_sha256']!=source['sha256']:
            raise UploadStopped('A different artifact owns this upload progress file.')
        client=None
        try:
            client=connect(root);stats=audit(client)
            remaining=max(0,source['bson_bytes']-progress['verified_bson_bytes'])
            admit(stats,limits,remaining_bytes=remaining)
            progress['latest_storage']=stats
            if mode=='audit':
                _save_json(root/'no_sync/mongo_preupload_audit.json',stats)
                print(json.dumps({'mode':'read_only','storage':stats,'full_bson_bytes':source['bson_bytes']}),flush=True)
                return
            if progress['status']=='complete':
                print('Upload already complete. No writes repeated.',flush=True);return
            db=client[DATABASE];collection=db[COLLECTION]
            if COLLECTION not in db.list_collection_names():db.create_collection(COLLECTION)
            ensure_index(collection)
            progress.update(status='running',target=f'{DATABASE}.{COLLECTION}')
            _save_json(progress_path,progress)
            limit=PILOT_DOCUMENTS if mode=='pilot' else source['documents']
            processed=0;verified_bytes=0;last_log=0
            for batch in split_batches(documents(path)):
                if processed>=limit:break
                if processed+len(batch)>limit:batch=batch[:limit-processed]
                processed+=len(batch)
                batch_bytes=sum(len(BSON.encode(d)) for d in batch)
                # Checkpointed prefix was read back before saving. Final verification
                # rechecks the entire collection, including any resumed prefix.
                if processed<=progress['verified_documents']:
                    verified_bytes+=batch_bytes
                    continue
                missing=missing_documents(collection,batch)
                stats=audit(client)
                remaining=source['bson_bytes']-verified_bytes
                admit(stats,limits,remaining_bytes=remaining,batch_bytes=sum(len(BSON.encode(d)) for d in missing),new_documents=len(missing))
                if missing:
                    if progress['write_attempts']+len(missing)>MAX_WRITE_ATTEMPTS:
                        raise UploadStopped('Persistent write-attempt limit reached; no automatic retries.')
                    spacing=BATCH_SIZE/limits['max_mongo_document_writes_per_second']
                    wait=spacing-(time.time()-progress['last_write_at'])
                    if wait>0:time.sleep(wait)
                    progress['write_attempts']+=len(missing);progress['last_write_at']=time.time()
                    _save_json(progress_path,progress)  # Reserve before mutation.
                    operations=[UpdateOne({'_id':d['_id']},{'$setOnInsert':d},upsert=True) for d in missing]
                    collection.bulk_write(operations,ordered=True)
                if missing_documents(collection,batch):raise UploadStopped('Batch read-back is incomplete.')
                verified_bytes+=batch_bytes
                after=audit(client)
                admit(after,limits,remaining_bytes=source['bson_bytes']-verified_bytes)
                progress.update(verified_documents=processed,verified_bson_bytes=verified_bytes,latest_storage=after)
                now=time.time()
                if now-last_log>=60 or processed==limit:
                    checkpoint={'documents':processed,'data_plus_indexes_bytes':after['project_bytes'],'checked_at_utc':after['checked_at_utc']}
                    progress['checkpoints'].append(checkpoint)
                    print(f"Verified {processed:,}/{source['documents']:,}; project data + indexes {after['project_bytes']/1024**2:.2f} MiB / 64 MiB",flush=True)
                    last_log=now
                _save_json(progress_path,progress)
            if progress['verified_documents']==source['documents']:
                # Indexed, bounded cursor; compare every document with local BSON.
                cursor=collection.find({},max_time_ms=300000).sort([('connection',1),('time_utc',1)]).batch_size(200)
                compared=0
                try:
                    for expected,actual in zip(documents(path),cursor):
                        if expected!=actual:raise UploadStopped('Final remote document differs from local BSON.')
                        compared+=1
                    if compared!=source['documents'] or next(cursor,None) is not None:
                        raise UploadStopped('Final remote document count mismatch.')
                finally:cursor.close()
                after=audit(client)
                if after['collection']['documents']!=source['documents']:raise UploadStopped('Unexpected documents in target collection.')
                admit(after,limits,remaining_bytes=0)
                progress.update(status='complete',final_verified_documents=compared,latest_storage=after,
                    completed_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
            else:progress['status']='pilot_verified'
            progress.pop('error_type',None)
            _save_json(progress_path,progress)
            print('STATUS:',progress['status'],flush=True)
        except Exception as exc:
            progress.update(status='stopped',error_type=type(exc).__name__)
            _save_json(progress_path,progress)
            if isinstance(exc,UploadStopped):raise
            raise UploadStopped('Atlas operation failed; stopped without automatic retry. Connection details hidden.') from None
        finally:
            if client is not None:client.close()


if __name__=='__main__':
    import argparse,sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['audit','pilot','upload'],default='audit')
    args=parser.parse_args()
    try:run(Path(__file__).resolve().parents[1],args.mode)
    except UploadStopped as exc:
        print('STOPPED:',exc,flush=True);sys.exit(1)
