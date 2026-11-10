# M1 – Django- und Docker-Compose-Grundstruktur

**Issues:** [#15](https://github.com/whiteyOnTheMoon/FootballStudio/issues/15) · [#16](https://github.com/whiteyOnTheMoon/FootballStudio/issues/16) · [#17](https://github.com/whiteyOnTheMoon/FootballStudio/issues/17)

## Stand

Das Grundprojekt stellt eine öffentlich erreichbare **neutrale Startseite** und einen Datenbank-Readiness-Check unter `/healthz/` bereit. Es enthält noch **keine aktive Nutzeranmeldung**, **keine echte Land → Liga → Verein-Auswahl** und **keine Filmproduktion**; diese sind zwingende Folgearbeiten (#20–#26 und M2).

Die Web-App läuft als eigener Container, PostgreSQL als separater Container. Der Datenbank-Port wird **nicht veröffentlicht**; die Web-App ist standardmäßig ausschließlich an die Loopback-Adresse des Hosts gebunden. Ein Reverse Proxy und HTTPS für `studio2.ap-pixels.com` werden **erst nach der VPS-Inventur** in #27/#28 eingerichtet. Dies ist kein öffentliches Deployment.

## Lokaler Einstieg mit Docker Compose

Voraussetzung: Docker Engine und das Compose-Plugin auf einer **autorisierten lokalen Testmaschine**, nicht auf dem bisher ungeprüften Produktiv-VPS.

1. `cp .env.example .env` und in der **nicht versionierten** `.env` die Felder `DJANGO_SECRET_KEY` und `POSTGRES_PASSWORD` mit **separaten starken Zufallswerten** füllen. Zum Erzeugen z. B. `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`. Der PostgreSQL-Wert sollte für die URL-Zusammensetzung aus URL-sicheren Zeichen bestehen.
2. `docker compose config` zum Prüfen der Konfiguration.
3. `docker compose up -d --build` für die getrennten Container `web` und `db`.
4. `docker compose ps` und `docker compose logs --tail=100 web` zur Gesundheitskontrolle.
5. `docker compose exec web python manage.py migrate --noinput` für die **Django-Standardmigrationen**. Die fachlichen Länder-/Vereins-/Job-Migrationen folgen erst in #18/#22/#23.
6. `curl -f http://127.0.0.1:8000/` für **HTTP 200** der Startseite; `curl -f http://127.0.0.1:8000/healthz/` für eine **echte Datenbankverbindung**.
7. `docker compose exec web python manage.py test` führt Django-Tests gegen eine temporäre PostgreSQL-Testdatenbank aus.
8. `docker compose stop` zum Pausieren oder `docker compose down` zum Entfernen der Container. Das DB-Volume bleibt bestehen. **`docker compose down -v` löscht das Volumen – nur bewusst in einer Wegwerf-Testumgebung verwenden!**

## Nachweise und Grenzen

- `POSTGRES_PASSWORD` und Django Secret müssen vor dem Start gesetzt sein. Der Arbeitsstand enthält **keine** produktiven Secrets.
- Das PostgreSQL-Volume `postgres_data` ist persistent; die App selbst speichert hier noch keine Produktionsmedien. Worker- und Video-Volumes kommen in M2.
- Der Docker-Webprozess läuft unter einem nicht privilegierten Benutzer mit Gunicorn. Der Datenbank-Container bleibt auf dem internen Compose-Netz.
- `DATABASE_URL` wird ausschließlich aus Compose-Umgebungsvariablen zusammengesetzt. Die SQLite-Fallback-Einstellung `DJANGO_ALLOW_SQLITE=1` ist **nur** für lokale Unit-Tests ohne Docker vorgesehen und wird nicht in Compose gesetzt.
- `DJANGO_DEBUG=0` ist der Standard. SSL-/Proxy- und Session-Sicherheitskonfiguration müssen vor produktiver Bereitstellung geprüft werden (M1 #21, #27–#29).
- Die Tests prüfen Startseite (HTTP 200), Django-Systemcheck, Datenbank-Readiness, Migration und (im GitHub-Runner) Containerstart und Datenpersistenz. Eine erfolgreiche CI-Prüfung ist **keine VPS-Abnahme**.

## Versionswahl

Python 3.12 und Django 5.2 LTS (gepinnter Patchstand) mit PostgreSQL 17, Gunicorn und psycopg 3.3. Die Bibliotheken sind im `requirements.txt` versioniert. Änderungen erfordern Review/PR und erneute Tests.

Offizielle Referenzen: [Django-LTS-Unterstützung](https://www.djangoproject.com/download/), [Docker Compose Service-Healthy](https://docs.docker.com/reference/compose-file/services/).

**Nächste Issues:** Anmelde- und Sessionfunktionen #20/#21, Länder-/Liga-/Vereinsmodelle #22, das Katalog-/Dropdown-UI #24/#25 und ein frei gewählter Verein im Testjob #26. Der MVP ist **nicht auf einen Pilotclub beschränkt**.
