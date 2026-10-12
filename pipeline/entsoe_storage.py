"""Storage checks and guarded Spark writes for the local Cassandra flow table.

The course's Spark Cassandra connector remains the data reader/writer. Docker
commands only inspect readiness and allocated disk use; they never prune data.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import shutil
import subprocess

KEYSPACE = 'ind320_energy'
TABLE = 'cross_border_intervals'
PARTITION = ['connection', 'year', 'month', 'direction']
KEY = PARTITION + ['start_utc']
COLUMNS = KEY + ['end_utc', 'power_mw', 'duration_hours', 'energy_mwh']
# Conservative admission allowance, not a prediction of on-disk row size.
BYTES_PER_NEW_ROW = 8192
WORKING_RESERVE = 64 * 1024**2


class StorageStopped(RuntimeError):
    """A failed check prevents database writes; limits are never increased."""


def _docker(*arguments):
    try:
        return subprocess.run(['docker', *arguments], check=True, capture_output=True,
                              text=True, timeout=45).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise StorageStopped('Cannot inspect local Cassandra. Check Docker/container access; no write allowed.') from None


def measure_storage(project_root):
    details = json.loads(_docker('inspect', 'cassandra'))[0]
    if not details['State']['Running']:
        raise StorageStopped('Cassandra container is not running.')
    mounts = [m for m in details['Mounts'] if m['Destination'] == '/var/lib/cassandra']
    if len(mounts) != 1 or not mounts[0].get('RW'):
        raise StorageStopped('Expected one writable persistent Cassandra data mount.')
    if _docker('exec', 'cassandra', 'nodetool', 'statusbinary').lower() != 'running':
        raise StorageStopped('Cassandra native transport is not ready.')
    used = _docker('exec', 'cassandra', 'du', '-sk', '/var/lib/cassandra').split()[0]
    disk = _docker('exec', 'cassandra', 'df', '-Pk', '/var/lib/cassandra').splitlines()[-1].split()
    try:
        volume_bytes, docker_free_bytes = int(used) * 1024, int(disk[3]) * 1024
        if volume_bytes < 0 or docker_free_bytes < 0:
            raise ValueError
    except (ValueError, IndexError):
        raise StorageStopped('Unrecognised Docker disk report; no write allowed.') from None
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'volume_allocated_bytes': volume_bytes,
            'docker_free_bytes': docker_free_bytes,
            'host_free_bytes': shutil.disk_usage(project_root).free,
            'mount_type': mounts[0]['Type']}


def check_capacity(snapshot, *, current_rows, new_rows, batch_rows, limits):
    counts = (current_rows, new_rows, batch_rows)
    if any(type(n) is not int or n < 0 for n in counts) or new_rows > batch_rows:
        raise StorageStopped('Invalid row counts; no write allowed.')
    if batch_rows > limits['max_rows_per_spark_write']:
        raise StorageStopped('Spark batch exceeds the row limit.')
    if current_rows + new_rows > limits['max_raw_rows']:
        raise StorageStopped('Total raw-row limit would be exceeded.')
    used = snapshot['volume_allocated_bytes']
    if used >= limits['max_cassandra_volume_bytes']:
        raise StorageStopped('Cassandra volume has reached its project limit.')
    # Allow for incoming rows, transient files and an extra copy of current data.
    reservation = WORKING_RESERVE + new_rows * BYTES_PER_NEW_ROW + used if new_rows else 0
    if used + reservation > limits['max_cassandra_volume_bytes']:
        raise StorageStopped('Insufficient Cassandra headroom for the proposed batch.')
    for field in ('host_free_bytes', 'docker_free_bytes'):
        if snapshot[field] < limits['min_host_free_bytes'] + reservation:
            raise StorageStopped(f'Insufficient free space: {field}.')
    return {'current_rows': current_rows, 'new_rows': new_rows,
            'projected_rows': current_rows + new_rows, 'batch_rows': batch_rows,
            'reserved_bytes': reservation, **snapshot}


@contextmanager
def storage_lock(project_root):
    path = Path(project_root) / 'no_sync/entsoe_storage.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StorageStopped('Another guarded Cassandra operation is active.') from None
        yield


def _table(spark):
    return (spark.read.format('org.apache.spark.sql.cassandra')
            .options(keyspace=KEYSPACE, table=TABLE).load().select(*COLUMNS))


def check_snapshot(existing, incoming):
    """Allow unchanged cached rows and resuming a partial identical write.

    Incoming must contain complete intended partitions. A changed value or stale
    key in an affected partition requires explicit source-revision handling.
    """
    partitions = incoming.select(*PARTITION).distinct()
    affected = existing.join(partitions, PARTITION, 'inner').select(*COLUMNS)
    if affected.exceptAll(incoming.select(*COLUMNS)).limit(1).count():
        raise StorageStopped('An affected partition differs from this snapshot; review revisions before writing.')
    return incoming.select(*COLUMNS).exceptAll(affected)


def validate_incoming(incoming, plan):
    from pyspark.sql import functions as F
    count = incoming.limit(plan['planned_limits']['max_rows_per_spark_write'] + 1).count()
    if count > plan['planned_limits']['max_rows_per_spark_write']:
        raise StorageStopped('Spark batch exceeds the row limit; use complete smaller partitions.')
    if not count:
        raise StorageStopped('Empty incoming batch.')
    if incoming.select(*KEY).distinct().count() != count:
        raise StorageStopped('Duplicate primary keys in incoming rows.')
    nulls = F.lit(False)
    for column in COLUMNS:
        nulls = nulls | F.col(column).isNull()
    local_start = F.from_utc_timestamp('start_utc', 'Europe/Oslo')
    invalid = (nulls | ~F.col('connection').isin([c['connection'] for c in plan['connections']])
        | ~F.col('direction').isin('import', 'export')
        | (F.col('year') != F.year(local_start)) | (F.col('month') != F.month(local_start))
        | (F.col('start_utc') >= F.col('end_utc'))
        | (F.col('start_utc') < F.lit(datetime.fromisoformat(plan['period']['start_inclusive'])))
        | (F.col('end_utc') > F.lit(datetime.fromisoformat(plan['period']['end_exclusive'])))
        | (F.col('power_mw') < 0) | (F.col('duration_hours') <= 0) | (F.col('energy_mwh') < 0))
    for col in ['power_mw', 'duration_hours', 'energy_mwh']:
        invalid = invalid | F.isnan(col) | (F.abs(F.col(col)) == float('inf'))
    hours = (F.col('end_utc').cast('double') - F.col('start_utc').cast('double')) / 3600
    invalid = invalid | (F.abs(F.col('duration_hours') - hours) > 1e-8)
    invalid = invalid | (F.abs(F.col('energy_mwh') - F.col('power_mw') * hours) > 1e-6)
    if incoming.filter(invalid).limit(1).count():
        raise StorageStopped('Incoming rows contain invalid fields, dates or energy calculations.')
    return count


def guarded_spark_write(spark, incoming, project_root, *, dry_run=True):
    """Validate actual counts/disk and reject conflicting snapshots before writing.

    Defaults to read-only. All writers in this project must use this entry point.
    Other applications writing Cassandra concurrently are outside this lock.
    """
    root = Path(project_root)
    plan = json.loads((root / 'entsoe_plan.json').read_text())
    limits = plan['planned_limits']
    incoming = incoming.select(*COLUMNS).cache()
    existing = None
    try:
        with storage_lock(root):
            batch_rows = validate_incoming(incoming, plan)
            existing = _table(spark).cache()
            current_rows = existing.limit(limits['max_raw_rows'] + 1).count()
            if current_rows > limits['max_raw_rows']:
                raise StorageStopped('Existing table exceeds the raw-row limit.')
            missing = check_snapshot(existing, incoming).cache()
            try:
                new_rows = missing.count()
                report = check_capacity(measure_storage(root), current_rows=current_rows,
                                        new_rows=new_rows, batch_rows=batch_rows, limits=limits)
                report.update(dry_run=dry_run, rows_written=0)
                if not dry_run and new_rows:
                    (missing.write.format('org.apache.spark.sql.cassandra')
                     .options(keyspace=KEYSPACE, table=TABLE).mode('append').save())
                    _docker('exec', 'cassandra', 'nodetool', 'flush', KEYSPACE, TABLE)
                    # Remove the cached logical plan before taking a fresh read.
                    existing.unpersist(blocking=True)
                    fresh = _table(spark)
                    affected = fresh.join(incoming.select(*PARTITION).distinct(), PARTITION, 'inner').select(*COLUMNS)
                    if (incoming.exceptAll(affected).limit(1).count()
                            or affected.exceptAll(incoming).limit(1).count()):
                        raise StorageStopped('Post-write snapshot verification failed; stop before the next batch.')
                    after_count = fresh.limit(limits['max_raw_rows'] + 1).count()
                    after = check_capacity(measure_storage(root), current_rows=after_count,
                                           new_rows=0, batch_rows=0, limits=limits)
                    report.update(rows_written=new_rows, after_write=after)
                from pipeline.entsoe_budget import _save_json
                _save_json(root / 'no_sync/entsoe_storage_audit.json', report)
                return report
            finally:
                missing.unpersist()
    finally:
        incoming.unpersist()
        if existing is not None:
            existing.unpersist()
