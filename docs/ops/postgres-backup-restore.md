# PostgreSQL-Backup und Restore-Test (FS-008c / #19)

**Status:** wiederholbar in Docker Compose und GitHub CI; der reale VPS ist weiterhin nicht inventarisiert bzw. gesichert.

## Backup

Der `db`-Container enthält PostgreSQL 17, `pg_dump` und `pg_restore`. Die DB ist vom Host aus nicht öffentlich erreichbar. Voraussetzung ist ein gestarteter Compose-Stack mit eigener `.env`.

```bash
docker compose up -d --wait
bash scripts/postgres_backup.sh
# Oder mit eigenem geschützten Speicherort:
bash scripts/postgres_backup.sh /private/footballstudio-backups
```

Das Skript erstellt eine komprimierte PostgreSQL-*Custom*-Sicherung als `PGDMP`-Datei, validiert Header und Archivinhalt, schreibt zunächst atomar in eine temporäre Datei und gibt auf **stdout ausschließlich den absoluten Sicherungspfad** zurück. Die Datei wird mit Rechten **0600** angelegt, das Standardverzeichnis `backups/` mit privater Umask. Datenbank-Passwörter bleiben im `db`-Container und werden weder geparst noch ausgegeben. Bei Fehlern wird der unvollständige Dump entfernt.

Dumps enthalten möglicherweise persönliche Daten (E-Mail-Adressen und Metadaten). Sie sind vom Git-Repository und Docker-Image ausgeschlossen. Ein benutzerdefiniertes Zielverzeichnis muss durch den Betreiber zusätzlich vor fremdem Zugriff geschützt sein. **Nie** Backups, Zugangsdaten oder die `.env` in Issues, öffentliche CI-Artefakte oder unverschlüsselte Cloud-Speicher hochladen.

## Isolierte Wiederherstellung verifizieren

```bash
archive="$(bash scripts/postgres_backup.sh)"
bash scripts/verify_postgres_backup.sh "$archive"
# Optional eine bestimmte Tabelle und Mindestanzahl an Zeilen prüfen:
bash scripts/verify_postgres_backup.sh "$archive" django_migrations 1
```

Die Restore-Probe legt eine **separate, eindeutig benannte temporäre Datenbank**
`fs_restore_…` im laufenden Container an. Der Dump wird mit
`pg_restore --exit-on-error --single-transaction --no-owner --no-acl`
restauriert. Danach werden die Anzahl öffentlicher Tabellen sowie die
Zeilen der geforderten Tabelle abgefragt. Die temporäre DB wird im
EXIT-Trap wieder gelöscht; die **Produktivdatenbank wird nie als
Restore-Ziel angeboten**.

**Speicherwarnung:** Die Prüfung benötigt freie Kapazität für eine
weitere restaurierte Datenbank **im gleichen PostgreSQL-Volume**.
Produktive Restore-Tests daher nur nach Größenprüfung oder in einer
isolierten Testumgebung ausführen.

## Automatisierte CI

Im Compose-Job des GitHub-Actions-Workflows wird die reale Testdatenbank
um eine Tabelle `fs_m1_backup_restore_probe` (Wert `42`) ergänzt,
ein Custom-Dump erstellt und in eine temporäre Datenbank restauriert.
Der Restore bestätigt, dass die Testtabelle enthalten ist, und
anschließend wird der Originaldatensatz in der Live-Testdatenbank
erneut geprüft. CI-Dumps und -Volumes werden nach dem Lauf entfernt.
**Das ersetzt kein tatsächlich eingerichtetes VPS-Backup.**

## Aufbewahrung und Platzbedarf

Nach realer VPS-Inventur als **Betriebsvorschlag**: sieben tägliche,
vier wöchentliche und drei monatliche Sicherungen, zusätzlich
verschlüsselte Kopien außerhalb des Servers. Ein automatisches
Löschverfahren wird bewusst **noch nicht** aktiv geschaltet, da
Speicherort, Verantwortlichkeit, Monitoring und Verschlüsselung
erst festgelegt werden müssen.

Auf dem autorisierten Host vor Planung die tatsächlichen Größen ermitteln:

```bash
docker compose exec -T db sh -c 'psql -X -A -t -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT pg_size_pretty(pg_database_size(current_database()));"'
du -h backups/*.dump
df -h backups
```

Für Speicherung den beobachteten Dumpumfang mal Retentionsanzahl
kalkulieren, zuzüglich Platz für einen parallelen Dump und für
die vollständig restaurierte Testdatenbank. `pg_dump` sichert
**nur** PostgreSQL: spätere Medien- und Render-Dateien sowie
die sichere Verwaltung von Secrets brauchen eigene Prozesse.

## Wiederanlauf auf einem tatsächlichen Server

Nur nach ausdrücklich freigegebenem Betriebswechsel: zunächst
die bestehende Datenbank und Schreibzugriffe unangetastet lassen,
einen verifizierten Dump auf ein **neues, leeres Ziel** restaurieren,
Schema, Nutzerzugriff und Healthchecks prüfen, dann bewusst auf
die wiederhergestellte Datenbank umschalten. Ein Rollback erfolgt
durch Rückkehr zur unveränderten alten Datenbank. Keines der
bereitgestellten Skripte überschreibt oder löscht die aktive
Anwendungsdatenbank. Der VPS-/Live-Restore muss separat geprüft
werden, sobald #6 (Serverinventur) durchgeführt ist.
