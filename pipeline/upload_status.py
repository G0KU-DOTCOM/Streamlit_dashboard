"""Show saved MongoDB upload progress locally, without network or credentials."""
import fcntl
import json
from pathlib import Path


def writer_active(root):
    """Check the uploader's existing lock; a stale 'running' report is insufficient."""
    path = root / 'no_sync/entsoe_mongo.lock'
    if not path.exists():
        return False
    with path.open('r') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / 'no_sync/entsoe_mongo_progress.json'
    if not path.exists():
        print('No saved upload progress yet.')
        return
    progress = json.loads(path.read_text())
    plan = json.loads((root / 'entsoe_plan.json').read_text())
    target = plan['curation']['measured_documents']
    verified = progress.get('verified_documents', 0)
    active = writer_active(root)
    complete = (progress.get('status') == 'complete'
                and progress.get('final_verified_documents') == target)
    if complete:
        status = 'COMPLETE: final remote read-back verified'
    elif active:
        status = 'RUNNING: a project upload/audit holds the lock'
    else:
        status = 'NOT RUNNING: partial progress is saved; inspect the log before resuming'
    print(status)
    print(f'Verified documents: {verified:,} / {target:,} ({verified / target:.1%})')
    storage = progress.get('latest_storage', {})
    for key, title, limit in [
        ('project_bytes', 'Project data + indexes', 'max_mongo_project_data_plus_indexes_bytes'),
        ('cluster_bytes', 'User databases combined', 'max_mongo_cluster_data_plus_indexes_bytes'),
    ]:
        if key in storage:
            print(f'{title}: {storage[key] / 1024**2:.2f} / {plan["planned_limits"][limit] / 1024**2:.0f} MiB')
    print('Last saved storage check (UTC):', storage.get('checked_at_utc', 'unknown'))
    # A historical error can remain in the report while a resumed run is active.
    if not active and not complete and progress.get('error_type'):
        print('Saved error type:', progress['error_type'])
    launch = root / 'no_sync/mongo_upload_process.json'
    if launch.exists():
        print('Upload log:', json.loads(launch.read_text())['log_path'])
    print('Local status only; this command makes no database requests or writes.')


if __name__ == '__main__':
    main()
