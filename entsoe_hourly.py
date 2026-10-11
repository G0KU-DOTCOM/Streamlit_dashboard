"""Curate local Cassandra intervals with Spark; measure BSON without uploading."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil

from bson import BSON

from entsoe_budget import _save_json
from entsoe_bulk import start_spark, final_verification
from entsoe_storage import _table, StorageStopped, storage_lock


def hourly_flows(raw, start, end, connections):
    """Split MW blocks at UTC hour boundaries, retain missing energy as null.

    The caller verifies the source snapshot; overlap is also rejected here so
    coverage sums cannot silently double count. Each full UTC hour is one row
    with both directions. DST only affects display, never this UTC key.
    """
    from pyspark.sql import functions as F, Window
    start_s, end_s = int(start.timestamp()), int(end.timestamp())
    if start.tzinfo is None or end.tzinfo is None or start_s % 3600 or end_s % 3600 or end_s <= start_s:
        raise StorageStopped('Curation needs a positive window with whole UTC-hour boundaries.')
    if not connections or len(connections) != len(set(connections)):
        raise StorageStopped('Expected unique connections.')
    raw = raw.select('connection','direction','start_utc','end_utc','power_mw')
    bad = (F.col('start_utc').isNull() | F.col('end_utc').isNull() | F.col('power_mw').isNull()
           | F.col('connection').isNull() | F.col('direction').isNull()
           | ~F.col('connection').isin(connections) | ~F.col('direction').isin('import','export')
           | (F.col('end_utc') <= F.col('start_utc')) | (F.col('power_mw') < 0)
           | F.isnan('power_mw') | (F.abs('power_mw') == float('inf')))
    if raw.filter(bad).limit(1).count():
        raise StorageStopped('Invalid source flow interval.')
    window = Window.partitionBy('connection','direction').orderBy('start_utc','end_utc')
    # Running maximum also detects intervals nested inside an earlier long block.
    prior_end = F.max('end_utc').over(window.rowsBetween(Window.unboundedPreceding,-1))
    if raw.withColumn('prior_end',prior_end).filter(F.col('start_utc') < F.col('prior_end')).limit(1).count():
        raise StorageStopped('Overlapping intervals would double count hourly energy.')
    clipped = (raw.withColumn('start_utc',F.greatest('start_utc',F.lit(start)))
               .withColumn('end_utc',F.least('end_utc',F.lit(end)))
               .filter(F.col('start_utc') < F.col('end_utc')))
    pieces = (clipped.withColumn('hour_utc',F.explode(F.sequence(
        F.date_trunc('hour','start_utc'),
        F.date_trunc('hour',F.expr('end_utc - INTERVAL 1 MICROSECOND')),
        F.expr('INTERVAL 1 HOUR')))))
    seconds = (F.least('end_utc',F.expr('hour_utc + INTERVAL 1 HOUR')).cast('double')
               - F.greatest('start_utc','hour_utc').cast('double'))
    pieces = pieces.withColumn('piece_mwh',F.col('power_mw')*seconds/3600).withColumn('piece_minutes',seconds/60)
    paired = (pieces.groupBy('connection','hour_utc').pivot('direction',['import','export'])
              .agg(F.sum('piece_mwh').alias('mwh'),F.sum('piece_minutes').alias('coverage_minutes')))
    spark = raw.sparkSession
    hours = spark.range((end_s-start_s)//3600).select((F.col('id')*3600+start_s).cast('timestamp').alias('hour_utc'))
    borders = spark.createDataFrame([(c,) for c in connections],'connection string')
    result = borders.crossJoin(hours).join(paired,['connection','hour_utc'],'left')
    for direction in ('import','export'):
        result=result.withColumn(f'{direction}_coverage_minutes',F.coalesce(f'{direction}_coverage_minutes',F.lit(0.0)))
    return result.select('connection','hour_utc','import_mwh','export_mwh','import_coverage_minutes','export_coverage_minutes')


def document_from_row(row):
    timestamp = datetime.fromtimestamp(row['hour_epoch'],timezone.utc)
    document={'_id':f"{row['connection']}|{timestamp:%Y%m%dT%H%MZ}",
              'connection':row['connection'],'time_utc':timestamp}
    for direction in ('import','export'):
        energy=row[f'{direction}_mwh'];coverage=float(row[f'{direction}_coverage_minutes'])
        if (energy is not None and (not math.isfinite(energy) or energy < 0)
                or not math.isfinite(coverage) or coverage < 0 or coverage > 60+1e-7):
            raise StorageStopped('Invalid curated energy or coverage.')
        document[f'{direction}_mwh']=None if energy is None else float(energy)
        document[f'{direction}_coverage_minutes']=coverage
    return document


def write_bson(rows, path, *, max_documents, max_bytes):
    """Write concatenated BSON atomically; no partial file replaces a valid one."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    count=size=0;digest=hashlib.sha256();sample=[]
    try:
        with temp.open('wb') as handle:
            for row in rows:
                document=document_from_row(row);encoded=BSON.encode(document)
                if count+1>max_documents or size+len(encoded)>max_bytes:
                    raise StorageStopped('Curated document or BSON-byte budget exceeded.')
                handle.write(encoded);digest.update(encoded);count+=1;size+=len(encoded)
                if len(sample)<5:
                    sample.append({**document,'time_utc':document['time_utc'].isoformat()})
        temp.replace(path)
    finally:
        if temp.exists():temp.unlink()
    return {'documents':count,'bson_bytes':size,'sha256':digest.hexdigest(),'sample_documents':sample}


def run(root):
    from pyspark.sql import functions as F
    root=Path(root);plan=json.loads((root/'entsoe_plan.json').read_text())
    limits=plan['planned_limits']
    bulk=json.loads((root/'no_sync/entsoe_bulk_report.json').read_text())
    if bulk['status']!='complete':raise StorageStopped('Complete verified raw collection first.')
    start=datetime.fromisoformat(plan['period']['start_inclusive']);end=datetime.fromisoformat(plan['period']['end_exclusive'])
    connections=[c['connection'] for c in plan['connections']]
    expected_documents=int((end-start).total_seconds()/3600)*len(connections)
    if expected_documents>limits['max_mongo_documents']:raise StorageStopped('Expected hourly document count exceeds the plan.')
    # Reserve a full maximum-sized local artifact while preserving host headroom.
    if shutil.disk_usage(root).free < limits['min_host_free_bytes']+limits['max_mongo_project_data_plus_indexes_bytes']:
        raise StorageStopped('Insufficient host space to prepare curated data.')
    spark=raw=hourly=None
    with storage_lock(root):
        try:
            spark=start_spark(root)
            final_verification(spark,bulk,plan,root)  # Fresh read-only source check.
            raw=_table(spark).cache()
            hourly=hourly_flows(raw,start,end,connections).cache()
            count=hourly.count()
            if count!=expected_documents:raise StorageStopped('Unexpected hourly document count.')
            invalid=F.lit(False)
            for direction in ('import','export'):
                invalid=invalid | F.col(f'{direction}_mwh').isNull() | (F.abs(F.col(f'{direction}_coverage_minutes')-60)>1e-7)
            if hourly.filter(invalid).limit(1).count():raise StorageStopped('Incomplete hourly coverage; review before preparing upload.')
            # Compare all 18 direction totals, not just the national grand total.
            aggregates=hourly.groupBy('connection').agg(*[
                F.sum(f'{d}_mwh').alias(d) for d in ('import','export')]).collect()
            expected={(r['connection'],r['direction']):r['energy_mwh'] for r in bulk['verification']['directions']}
            comparisons=[]
            for row in aggregates:
                for d in ('import','export'):
                    raw_energy=expected[(row.connection,d)];hourly_energy=row[d]
                    difference=hourly_energy-raw_energy
                    if abs(difference)>max(1e-5,abs(raw_energy)*1e-10):raise StorageStopped('Hourly energy does not match raw energy.')
                    comparisons.append({'connection':row.connection,'direction':d,'raw_mwh':raw_energy,
                                        'hourly_mwh':hourly_energy,'difference_mwh':difference})
            # Unix seconds avoid converting a naive Spark datetime in the host timezone.
            rows=(hourly.orderBy('connection','hour_utc').select('connection',F.col('hour_utc').cast('long').alias('hour_epoch'),
                'import_mwh','export_mwh','import_coverage_minutes','export_coverage_minutes').toLocalIterator())
            result=write_bson(rows,root/'no_sync/entsoe_curated/hourly_flows.bson',
                max_documents=limits['max_mongo_documents'],max_bytes=limits['max_mongo_project_data_plus_indexes_bytes'])
            result.update(status='prepared_locally_not_uploaded',created_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                period=plan['period'],raw_rows=bulk['verification']['rows'],energy_checks=sorted(comparisons,key=lambda r:(r['connection'],r['direction'])),
                source_plan_hash=bulk['plan_hash'],index_headroom_scenario_bytes=2*result['bson_bytes'],mongo_writes=0)
            if 2*result['bson_bytes']>limits['max_mongo_project_data_plus_indexes_bytes']:
                raise StorageStopped('BSON plus index planning allowance exceeds the project limit.')
            _save_json(root/'no_sync/entsoe_hourly_report.json',result)
            print(f"Prepared {result['documents']:,} documents; {result['bson_bytes']/1024**2:.2f} MiB BSON; no database writes.",flush=True)
        finally:
            if hourly is not None:hourly.unpersist()
            if raw is not None:raw.unpersist()
            if spark is not None:spark.stop()


if __name__=='__main__':
    import sys
    try:run(Path(__file__).resolve().parent)
    except Exception as exc:
        print('STOPPED:',str(exc) if isinstance(exc,StorageStopped) else type(exc).__name__)
        sys.exit(1)
