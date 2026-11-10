# Docker-Entwicklungsstart – FootballStudio M1

**Lokal, nicht auf dem ungeprüften VPS.** Stand der Anwendung: Django, PostgreSQL, passwortgeschützte Startseite, **Offline-Auswahl Konföderation → Land/Verband → Liga → Verein**, optionales manuelles Ergänzen und gespeicherte M1-Testjobs. Es wird **noch kein Video gerendert**.

## Starten auf eigener Testmaschine

Voraussetzungen: Docker Engine und Docker Compose Plugin. In einer nicht versionierten Datei `.env` eigene, **starke** Werte für Django Secret und PostgreSQL-Passwort setzen:

```sh
cp .env.example .env
# .env mit zwei unabhängigen starken Geheimwerten vervollständigen.
docker compose config
docker compose up -d --build
docker compose ps
curl -f http://127.0.0.1:8000/healthz/
```

Das Web-Container-Startkommando führt **Django-Migrationen und den lokalen Katalogimport automatisch** vor Gunicorn aus. Alle Inhalte kommen aus den im Repository versionierten JSON-Dateien – **keine Live-API-Abfrage**. Die App ist standardmäßig nur über die Loopback-Schnittstelle des Hosts erreichbar; PostgreSQL veröffentlicht keinen Port.

Falls der Start aufgrund fehlender Berechtigungen/Migrationsdaten scheitert, zuerst die Logs untersuchen, nicht das Datenbank-Volume löschen: `docker compose logs --tail=100 web`.

Ein Admin-Login wird in einer autorisierten lokalen Umgebung angelegt mit:

```sh
docker compose exec web python manage.py createsuperuser
```

Die Django-Oberfläche ist auf `http://127.0.0.1:8000/accounts/login/` erreichbar. Für einen **rein lokalen HTTP-Browsertest** muss `DJANGO_LOCAL_HTTP=1` in `.env` gesetzt und der Web-Container neu erstellt werden. Diese Ausnahme wird bei fremden Allowed-Hosts oder aktiviertem Proxy-Trust von Django abgelehnt. Für öffentlichen HTTPS-Betrieb bleibt `DJANGO_LOCAL_HTTP=0`.

## Offline-Katalog und Datenpflege

Nachträglichen Katalogstand bewusst einspielen:

```sh
docker compose exec web python manage.py seed_world_catalog
```

Die Dateien `app/clubs/data/world_catalog.json` und `teams-2026-27.json` enthalten die sechs Konföderationen, **55 UEFA-Verbände**, weitere Länder und die derzeit tatsächlich belegten Vereinslisten. Alle anderen Ligen sind als Namensreferenz kenntlich gemacht, **nicht als vollständige Vereinsliste**. Länder ohne eigene zweite Liga bekommen keine künstlichen Wettbewerbe. 2026/27-Snapshots werden bei Saisonwechsel **nicht automatisch aktualisiert**.

Der Import ist idempotent und löscht keine manuell angelegten Clubs und keine Jobs. Neue Offline-Daten brauchen ein geprüftes Repository-Update, dann einen erneuten Import – **keinen periodischen Anbieterabruf**. Mehr dazu: [Weltkatalog und Abdeckungsgrenzen](../data/offline-world-catalog.md).

## M1-Testjob und Tests

Nach Auswahl des Vereins kann ein Arbeitstitel gespeichert werden. Der Testjob bleibt bewusst mit Status `queued` stehen: **keine KI-, TTS- oder FFmpeg-Produktion in M1**. Die letzten Jobs und Fehler sind nur für den jeweiligen eingeloggten Nutzer sichtbar.

```sh
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test
docker compose stop
```

Vor Änderungen am Stack einen tatsächlichen Backup-/Restore-Test durchführen:

```sh
archive="$(bash scripts/postgres_backup.sh)"
bash scripts/verify_postgres_backup.sh "$archive"
```

Das Restore-Skript erzeugt ausschließlich eine temporäre Datenbank, keine Live-Änderung. Details zu Berechtigungen, Speicherbedarf und Aufbewahrung: [PostgreSQL-Backup und Restore](../ops/postgres-backup-restore.md).

Das Docker-Datenbank-Volume bleibt nach `docker compose stop` oder `docker compose down` erhalten. **Niemals unüberlegt `docker compose down -v` auf einer Datenbank mit Nutzerdaten ausführen.**

Das aktuelle GitHub Actions CI prüft Django-Tests, Migrationen, Containerstart, PostgreSQL-Persistenz und **Offline-Import ohne Netzwerkzugriff**. Die tatsächliche VPS-Einrichtung, HTTPS/TLS, Reverse-Proxy-Header, Backups und der Filmworker sind eigene noch offene Aufgaben.
