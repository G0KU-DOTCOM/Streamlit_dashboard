"""Resume the frozen two-year ENTSO-E plan through guarded Spark writes.

Run without --execute to inspect the saved report. Credentials are read only by
DownloadBudget. No MongoDB connection or write is part of this stage.
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd

from entsoe_budget import DownloadBudget, _save_json
from entsoe_data import flow_intervals, coverage_summary, EntsoeDataError
from entsoe_storage import guarded_spark_write, measure_storage, check_capacity, StorageStopped, _table

SCHEMA = ('connection string, year int, month int, direction string, '
          'start_utc timestamp, end_utc timestamp, power_mw double, '
          'duration_hours double, energy_mwh double')


def segments(plan):
    start = pd.Timestamp(plan['period']['start_inclusive']).tz_convert('Europe/Oslo')
    end = pd.Timestamp(plan['period']['end_exclusive']).tz_convert('Europe/Oslo')
    windows = []
    current = start
    while current < end:
        finish = min(end, pd.Timestamp(year=current.year + 1, month=1, day=1, tz='Europe/Oslo'))
        windows.append((current, finish))
        current = finish
    for connection in plan['connections']:
        for begin, finish in windows:
            for direction in plan['directions']:
                origin, destination = connection['norwegian_eic'], connection['foreign_eic']
                if direction == 'import':
                    origin, destination = destination, origin
                stem = connection['connection'].replace('-', '_')
                # Reuse the original full-2025 NO2/DK1 responses.
                full_year = begin.month == begin.day == 1 and finish == pd.Timestamp(year=begin.year+1,month=1,day=1,tz='Europe/Oslo')
                dates = str(begin.year) if full_year else f'{begin:%Y-%m-%d}_{finish:%Y-%m-%d}'
                yield {'id': f"{connection['connection']}|{begin:%Y-%m-%d}|{finish:%Y-%m-%d}|{direction}",
                       'connection': connection['connection'], 'direction': direction,
                       'origin': origin, 'destination': destination,
                       'start': begin.isoformat(), 'end': finish.isoformat(),
                       'cache_name': f'{stem}_{dates}_{direction}.xml'}


def spark_frame(spark, intervals, segment):
    local = intervals['start_utc'].dt.tz_convert('Europe/Oslo')
    rows = [(segment['connection'], int(year), int(month), segment['direction'],
             r.start_utc.to_pydatetime(), r.end_utc.to_pydatetime(),
             float(r.power_mw), float(r.hours), float(r.energy_mwh))
            for r, year, month in zip(intervals.itertuples(index=False),local.dt.year,local.dt.month)]
    return spark.createDataFrame(rows, SCHEMA)


def start_spark(root):
    from pyspark.sql import SparkSession
    os.environ['JAVA_HOME'] = subprocess.check_output(['/usr/libexec/java_home', '-v', '17'],text=True).strip()
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable
    os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
    spark = (SparkSession.builder.master('local[2]').appName('IND320-Two-Year-Flows')
        .config('spark.jars.packages','com.datastax.spark:spark-cassandra-connector_2.12:3.5.1')
        .config('spark.jars.ivy',str(root/'no_sync/spark_ivy'))
        .config('spark.cassandra.connection.host','127.0.0.1')
        .config('spark.cassandra.connection.port','9042')
        .config('spark.sql.extensions','com.datastax.spark.connector.CassandraSparkExtensions')
        .config('spark.sql.catalog.mycatalog','com.datastax.spark.connector.datasource.CassandraCatalog')
        .config('spark.sql.session.timeZone','UTC').config('spark.sql.shuffle.partitions','2')
        .config('spark.cassandra.output.concurrent.writes','2')
        .config('spark.cassandra.output.throughputMBPerSec','1')
        .config('spark.ui.enabled','false').getOrCreate())
    spark.sparkContext.setLogLevel('ERROR')
    return spark


def final_verification(spark, report, plan, root):
    from pyspark.sql import functions as F, Window
    stored = _table(spark).cache()
    try:
        actual_count = stored.limit(plan['planned_limits']['max_raw_rows']+1).count()
        expected_count = sum(r['rows'] for r in report['segments'].values())
        if actual_count != expected_count:
            raise StorageStopped('Final row count differs from validated segment totals.')
        window = Window.partitionBy('connection','direction').orderBy('start_utc')
        if (stored.withColumn('previous_end',F.lag('end_utc').over(window))
                .filter(F.col('previous_end').isNotNull() & (F.col('previous_end') != F.col('start_utc'))).limit(1).count()):
            raise StorageStopped('Final stored data contains gaps or overlaps across segment boundaries.')
        summary = (stored.groupBy('connection','direction').agg(
            F.count('*').alias('rows'), F.sum('duration_hours').alias('hours'),
            F.sum('energy_mwh').alias('energy_mwh'),F.min('start_utc').cast('long').alias('start'),
            F.max('end_utc').cast('long').alias('end')).orderBy('connection','direction').collect())
        if len(summary) != len(plan['connections'])*2:
            raise StorageStopped('Final set of borders/directions is incomplete.')
        expected_hours = (pd.Timestamp(plan['period']['end_exclusive'])-pd.Timestamp(plan['period']['start_inclusive'])).total_seconds()/3600
        result = []
        for row in summary:
            expected_energy = sum(s['energy_mwh'] for s in report['segments'].values()
                                  if s['connection']==row.connection and s['direction']==row.direction)
            if abs(row.hours-expected_hours)>1e-7 or abs(row.energy_mwh-expected_energy)>max(1e-5,abs(expected_energy)*1e-10):
                raise StorageStopped('Final stored hours or MWh differ from validated API totals.')
            for field,expected in [('start',plan['period']['start_inclusive']),('end',plan['period']['end_exclusive'])]:
                if pd.Timestamp(row[field],unit='s',tz='UTC') != pd.Timestamp(expected):
                    raise StorageStopped('Final stored date boundaries differ from the plan.')
            result.append({'connection':row.connection,'direction':row.direction,'rows':row.rows,
                           'covered_hours':row.hours,'energy_mwh':row.energy_mwh})
        report['verification'] = {'rows':actual_count,'directions':result,
            'storage':check_capacity(measure_storage(root),current_rows=actual_count,new_rows=0,batch_rows=0,limits=plan['planned_limits'])}
    finally:
        stored.unpersist()


def run(root):
    root = Path(root)
    budget = DownloadBudget(root)
    plan = budget.plan
    jobs = list(segments(plan))
    digest = hashlib.sha256(json.dumps(jobs,sort_keys=True).encode()).hexdigest()
    report_path = root/'no_sync/entsoe_bulk_report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {
        'plan_hash':digest,'status':'pending','segments':{},'period':plan['period']}
    if report['plan_hash'] != digest:
        raise StorageStopped('Saved bulk run belongs to a different plan; review before continuing.')
    with (root/'no_sync/entsoe_bulk.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise StorageStopped('Another bulk run is active.') from None
        spark = None
        current_id = None
        try:
            # Check readiness and space before starting any API downloads.
            check_capacity(measure_storage(root),current_rows=0,new_rows=0,batch_rows=0,limits=plan['planned_limits'])
            spark = start_spark(root)
            count = _table(spark).limit(plan['planned_limits']['max_raw_rows']+1).count()
            check_capacity(measure_storage(root),current_rows=count,new_rows=0,batch_rows=0,limits=plan['planned_limits'])
            for number,job in enumerate(jobs,1):
                current_id = job['id']
                cached = report['segments'].get(current_id)
                cache_path = budget.cache/job['cache_name']
                if cached and cached['status']=='verified':
                    if not cache_path.exists() or hashlib.sha256(cache_path.read_bytes()).hexdigest()!=cached['sha256']:
                        raise StorageStopped('A verified cache snapshot is missing or changed.')
                    print(f"[{number}/{len(jobs)}] Reuse verified {current_id}",flush=True)
                    continue
                print(f"[{number}/{len(jobs)}] Validate {current_id}",flush=True)
                start,end = pd.Timestamp(job['start']),pd.Timestamp(job['end'])
                body,downloaded = budget.load(job['origin'],job['destination'],start,end,job['cache_name'])
                frame = flow_intervals(body,job['origin'],job['destination'],start,end)
                coverage = coverage_summary(frame,start,end)
                entry = {**job,'status':'validated' if coverage['complete'] else 'incomplete',
                         'rows':len(frame),'energy_mwh':float(frame.energy_mwh.sum()),
                         **coverage,'sha256':hashlib.sha256(body).hexdigest(),'downloaded_bytes':(cached or {}).get('downloaded_bytes',0)+downloaded}
                report['segments'][current_id]=entry
                _save_json(report_path,report)
                if not coverage['complete']:
                    raise StorageStopped('Incomplete API coverage; no rows written for this segment.')
                if len(frame)>plan['planned_limits']['max_rows_per_spark_write']:
                    raise StorageStopped('Segment exceeds batch limit; review partition batching.')
                audit=guarded_spark_write(spark,spark_frame(spark,frame,job),root,dry_run=False)
                entry.update(status='verified',write_audit=audit)
                report.update(status='in_progress',updated_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
                _save_json(report_path,report)
                print(f"  Verified {len(frame):,} intervals; {audit['rows_written']:,} new rows; {downloaded:,} new bytes",flush=True)
            final_verification(spark,report,plan,root)
            report.pop('safe_reason',None)
            report.pop('error_code',None)
            report.pop('stopped_at_segment',None)
            report.update(status='complete',download_ledger=budget.snapshot(),completed_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
            _save_json(report_path,report)
            print(f"COMPLETE: {report['verification']['rows']:,} rows; 18 directions; no MongoDB writes.",flush=True)
        except Exception as exc:
            report.update(status='stopped',stopped_at_segment=current_id,
                          error_code=getattr(exc,'code',type(exc).__name__))
            # Only our own fixed diagnostics are persisted; no generic exception URLs.
            if isinstance(exc,(StorageStopped,EntsoeDataError)):
                report['safe_reason']=str(exc)
            _save_json(report_path,report)
            raise
        finally:
            if spark is not None:
                spark.stop()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if args.execute:
        try:run(root)
        except Exception as exc:
            print('STOPPED:',str(exc) if isinstance(exc,(StorageStopped,EntsoeDataError)) else type(exc).__name__,flush=True)
            sys.exit(1)
    else:
        path=root/'no_sync/entsoe_bulk_report.json'
        if path.exists():
            report=json.loads(path.read_text())
            print(report['status'],sum(s['status']=='verified' for s in report['segments'].values()),'verified segments')
        else:
            print('Not started. Use --execute for bounded downloads and guarded local Cassandra writes.')
