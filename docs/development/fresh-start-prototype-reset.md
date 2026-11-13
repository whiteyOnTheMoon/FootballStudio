# Fresh-start test: deleting old prototype jobs safely

FootballStudio supports **explicit removal of old M1 prototype test jobs**
when the operator wants to test the complete one-click research flow from scratch.

The new `reset_prototype_jobs` command is **read-only by default**.
It never runs automatically as part of server startup, migrations, release,
health check, ordinary browser navigation, or GitHub CI.

## 1. Before any deletion: create and restore-verify a DB backup

Run these on the Ubuntu server, not on your laptop:

```bash
cd /home/ap/www/footballstudio
archive="$(bash scripts/postgres_backup.sh)" &&
bash scripts/verify_postgres_backup.sh "$archive"
```

The second script restores the dump into a disposable PostgreSQL database,
checks its tables/migrations and removes the disposable database.
If either command fails, **STOP**. Do not attempt the delete.

Keep the backup archive safely. The reset can only be undone using
a DB restore; it does not undo filesystem artifacts or external API actions.

## 2. See exactly which jobs would be removed

```bash
docker compose -f compose.yaml -f compose.tunnel.yaml \
  exec -T web python manage.py reset_prototype_jobs
```

The preview lists IDs, owners, status and the number of matching
`ProductionJob.kind=prototype` rows. Film jobs are excluded.

The command explicitly **refuses** to delete:
- more than 200 prototype jobs at once;
- any collection containing a prototype job with a paid-API ledger row;
- any collection containing a currently running official research request.

To delete only one owner's prototype jobs, add `--owner-id=<id>`.
The default with no owner filter targets **all prototype jobs from all owners**.

## 3. Explicitly delete the previewed test jobs

**Only after a successful backup restore-verification** and an acceptable
dry-run preview:

```bash
docker compose -f compose.yaml -f compose.tunnel.yaml \
  exec -T web python manage.py reset_prototype_jobs \
  --execute --backup-verified \
  --confirm=DELETE_PROTOTYPE_TEST_JOBS
```

`--backup-verified` is the **operator's attestation**, not an independent
check performed by the command. Never pass it if you did not verify the
archive with `scripts/verify_postgres_backup.sh`.

Under a single database transaction, the command deletes the test jobs
and their associated dossier versions, source references, confirmations,
facts, evidence, reviews, research-request metadata and offline scene plans.
Before deleting source rows it deletes related evidence links explicitly
because Evidence.source uses PROTECT. The command re-checks paid-ledger and
running-research guards after obtaining row locks.

**Preserved:** authentication accounts/users, country/league/club catalog,
`kind=film` jobs and their data, paid-API budget lock/ledger, migrations,
PostgreSQL schema, application configuration and credentials.

Django/PostgreSQL **do not reset ID sequences**. A new first test job
may be Job #9 or #20 rather than Job #1, which is correct.

## 4. Check that the prototype list is empty

```bash
docker compose -f compose.yaml -f compose.tunnel.yaml \
  exec -T web python manage.py reset_prototype_jobs
```

Expected: `matching test jobs: 0`.
Then open `https://studio2.ap-pixels.com/` and create a
**new test job** using country → league → club and an English film title.

On the new job's research page:
- Click **Automatische Recherche starten / fortsetzen** once.
- Wikidata club identity, current stadium and P54 player candidates
  may be gathered automatically, provided the upstream data is suitable.
- **Official** club legends and league title chronicles require
  previously confirmed official club and league URLs for this **new**
  job. The old job's manual confirmations are intentionally deleted
  with the old job; the autopilot will **pause**, not silently invent
  approval, until new source confirmations exist.
- If the club has ambiguous/missing source data, the research stops
  safely with a message and retains earlier successful dossier versions.
- Source discovery, human FactReview, voiceover and final rendering
  are **not yet end-to-end automatic**. The 9-minute English beat sheet
  is a research map, not a finished narrated film.

This is a destructive **operator maintenance command**, intentionally
not a web UI delete button. It does not make or authorize any paid API
requests.

## Tests

`python manage.py test app.production.test_reset_prototype_jobs`

Coverage includes default dry run, confirmation/backup gate, owner scope,
paid-ledger protection, cascade of sourced test dossiers and human reviews,
preservation of real film jobs/catalog/accounts, and repeatable cleanup.
