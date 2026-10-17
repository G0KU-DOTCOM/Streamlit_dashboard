# Saved submission evidence

These selected reports describe completed checks on 13 October 2026. They contain public energy observations, counts, timestamps and size measurements; no credentials, connection strings, local paths or runtime locks. They are historical evidence, not a live database audit.

The Part 2 notebook reads the bulk and hourly snapshots here, so its report-display cells work after cloning without private `no_sync/` files. These snapshots are never used as an app fallback or uploader progress ledger.

To regenerate evidence, install `requirements-notebook.txt`, configure your own local secrets and run the documented bulk collection, hourly curation and MongoDB upload workflows in order (see the project README). Those workflows require the specified services and explicitly download/write data; they create full operational reports under ignored `no_sync/`. After successful verification, review and export only the public summary fields used here. Do not copy credentials, whole runtime ledgers or private connection settings into this folder.
