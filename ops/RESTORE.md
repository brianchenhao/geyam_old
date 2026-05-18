# Geyam — restore runbook

Recovering the production database from a Cloudflare R2 backup. For the
*automated* drill that runs weekly, see `ops/restore-drill.sh`. This document
covers the **manual disaster** path — a human reading this is recovering from a
data-loss or corruption incident.

All paths assume the VPS layout: `/opt/geyam/` with `ops/`, container
`geyam-db`, rclone configured at `/root/.config/rclone/rclone.conf`.

---

## 1. Triage — decide whether to restore

A backup restore is destructive. Before running it:

- Confirm the live DB is actually unrecoverable. Read the logs of whatever
  caused the incident; if the cause is a botched single-table update,
  selective `pg_restore -t <table>` is safer than wholesale restore.
- Take a final dump of the *current* (broken) state so you can compare later:
  ```bash
  sudo bash -c 'docker exec geyam-db pg_dump -U pos_user --no-owner -Fc geyam \
      > /tmp/pre-restore-$(date +%Y-%m-%d-%H%M%S).dump'
  ```
- Put the API into maintenance mode if it's serving traffic (Phase 4 introduces
  this). For Phase 3 (no app yet) just stop further writes manually.

## 2. Pick a backup

```bash
sudo rclone ls r2:geyam-backups | sort -k2
```

Filenames embed timestamps in `geyam-YYYY-MM-DD-HHMMSS.dump` form. Pick the
most recent **good** dump — i.e. one taken *before* the corruption.

## 3. Pull the dump locally

```bash
sudo rclone copy r2:geyam-backups/<chosen-filename>.dump /tmp/
ls -la /tmp/<chosen-filename>.dump
```

## 4. Drop and recreate the live database

> **Destructive.** Anything still in `geyam` at this point will be lost.

```bash
sudo docker exec geyam-db psql -U pos_user -d postgres \
    -c "DROP DATABASE IF EXISTS geyam;"
sudo docker exec geyam-db psql -U pos_user -d postgres \
    -c "CREATE DATABASE geyam;"
```

## 5. Restore

```bash
sudo docker cp /tmp/<chosen-filename>.dump geyam-db:/tmp/restore.dump
sudo docker exec geyam-db pg_restore -U pos_user --no-owner \
    -d geyam /tmp/restore.dump
sudo docker exec geyam-db rm /tmp/restore.dump
```

## 6. Post-restore checks

Verify the schema is at the expected alembic revision:

```bash
sudo docker exec geyam-db psql -U pos_user -d geyam \
    -c "SELECT version_num FROM alembic_version;"
```

Spot-check row counts on the busiest tables:

```bash
sudo docker exec geyam-db psql -U pos_user -d geyam -c "
  SELECT 'tenants' AS t, COUNT(*) FROM tenants UNION ALL
  SELECT 'users', COUNT(*) FROM users UNION ALL
  SELECT 'transactions', COUNT(*) FROM transactions UNION ALL
  SELECT 'audit_logs', COUNT(*) FROM audit_logs
  ORDER BY t;"
```

If alembic head is *older* than the codebase expects (e.g. you restored a
dump from before a recent migration), run `./ops/run-migrations.sh` to bring
the schema forward. Backwards is harder — coordinate with the codebase deploy.

## 7. Restore to laptop (cold-recovery scenario)

If the VPS itself is gone, you can pull a backup and restore into the laptop
dev DB:

```bash
# On the laptop, given you have rclone configured with the R2 token:
rclone copy r2:geyam-backups/<chosen-filename>.dump $TEMP/
docker cp $TEMP/<chosen-filename>.dump geyam-db-1:/tmp/restore.dump
docker exec geyam-db-1 psql -U pos_user -d postgres \
    -c "DROP DATABASE IF EXISTS geyam;"
docker exec geyam-db-1 psql -U pos_user -d postgres \
    -c "CREATE DATABASE geyam;"
docker exec geyam-db-1 pg_restore -U pos_user --no-owner \
    -d geyam /tmp/restore.dump
```

This is also the cold-DR test: rebuild from R2 alone, no other VPS artifacts
required.

## 8. After the incident

- Note the cause + the dump filename used in a post-incident note.
- Run `ops/restore-drill.sh` once successfully to re-confirm the new live DB
  state matches a fresh round-trip through R2.
- If a backup was *missed* during the incident window, run `ops/backup.sh`
  manually to capture the post-restore state outside the 02:00 cron schedule.
