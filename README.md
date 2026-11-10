# FootballStudio

**Football Stories Studio** – eine geschützte Web-App, mit der sich ein Fußballverein zur Laufzeit über **Verband → Land → Liga → Verein** auswählen lässt (oder manuell anlegen lässt) und anschließend eine englischsprachige, etwa **8–10 Minuten lange Vereinsdokumentation** inklusive Quellen, Drehbuch, Untertiteln und MP4 generiert wird. Kein fest vorgegebener Pilotverein.

**Ziel-Domain:** `studio2.ap-pixels.com` · **Roadmap:** *Football Stories Studio / Projektroadmap*, v1.0 vom 09.11.2026.

## Projektstatus

**M1 – technische Grundlage im Aufbau.** Django, Docker Compose, PostgreSQL und E-Mail-Authentifizierung sind umgesetzt. Die neue **Verband → Land → Liga → Verein**-Auswahl ist als Offline-M1-Weboberfläche mit 6 Konföderationen, **allen 211 FIFA-Mitgliedsverbänden** (darunter 55 UEFA-Verbände) und lokalen Vereins-Snapshots implementiert. **Die 211 Verbandsnamen sind vollständig, die Ligadaten und aktuellen Vereinslisten weltweit jedoch nicht.** Die **manuelle Vereinsanlage innerhalb einer ausgewählten Liga** ist ebenfalls umgesetzt. Der **M1-Testjob** speichert bereits den zur Laufzeit gewählten Club und einen Titel; er führt **keinen Videorender** aus. **Noch keine produktive VPS-Bereitstellung und keine echte Videopipeline.** Diese werden in weiteren M1-/M2-Issues umgesetzt.

## Architektur in Kürze

- **Web:** Python/Django, Templates und lokale JavaScript-Dropdowns (Verband → Land → Liga → Verein); kein Frontend-CDN.
- **Daten:** PostgreSQL mit persistentem Docker-Volume; versionierte Offline-Referenz- und Vereinssnapshots ohne regelmäßige Katalog-API-Aufrufe.
- **Produktion:** separater Hintergrund-Worker mit Recherche-, LLM-, Medien-, TTS- und FFmpeg-Modulen; Zwischenergebnisse/Retry.
- **Betrieb:** Docker Compose mit getrennten Services `web`, `db` und ab M2 `worker`; Reverse Proxy + TLS am bestehenden VPS.
- **Sprache:** `en` zuerst; Architektur für `de`, `fr`, `it`, `es`, `pt`.
- **Sicherheit:** Anmeldung, private Produktionsdateien, keine Secrets im Repository; keine automatische YouTube-Veröffentlichung im MVP.

## Dokumentation

| Dokument | Inhalt |
| --- | --- |
| [MVP-Nutzerfluss](docs/mvp/user-flow.md) | Login, Land → Liga → Verein, Titelwahl, Jobs und Downloads |
| [MVP-Abnahme](docs/mvp/acceptance-criteria.md) | Messbare Gates, Tests und Nicht-Ziele |
| [Frei wählbare Vereine & Tests](docs/mvp/pilot-clubs.md) | Keine feste Clubauswahl; optionale Testbeispiele |
| [ADR-0001](docs/architecture/ADR-0001-mvp-stack.md) | Stack, Container-Topologie und Architekturentscheidungen |
| [Pipeline-Verträge](docs/architecture/pipeline-contracts.md) | Module, Artefakte, Fehler und Wiederaufnahme |
| [Fakten und Quellen](docs/data/facts-and-sources.md) | Belegbare Aussagen, Unsicherheit und Quellenverknüpfungen |
| [Offline-Weltkatalog](docs/data/offline-world-catalog.md) | 6 Verbände, alle UEFA-Verbände, Clublisten-Stand, Ausnahmefälle und Lücken |
| [Medien und Rechte](docs/data/media-and-rights.md) | Lizenzmetadaten, Fallback und Publikationsgrenzen |
| [VPS-Inventur](docs/ops/vps-inventory.md) | Lesender Prüfplan; tatsächliche Serverwerte noch offen |
| [Repository-Struktur](docs/development/repository-layout.md) | Geplante Verzeichnisse, lokaler Einstieg und Konventionen |
| [Django- und Docker-Grundlage](docs/development/docker-local.md) | Aktueller lokaler Start, sichere Konfiguration, Tests und Grenzen |

## Lokale M1-Basis starten (nur auf einem eigenen Testrechner)

Das Projekt enthält jetzt Dockerfile und Compose für **Django `web` + PostgreSQL `db`**. Voraussetzung: Docker Engine, Docker Compose und zwei selbst erzeugte, starke Zugangswerte in einer **nicht eingecheckten** `.env`:

```sh
cp .env.example .env
# In .env die Felder DJANGO_SECRET_KEY und POSTGRES_PASSWORD setzen.
# Beide Werte unabhängig mit einem lokalen Passwortgenerator erzeugen.
docker compose config
docker compose up -d --build
docker compose exec web python manage.py migrate --noinput
curl -f http://127.0.0.1:8000/
curl -f http://127.0.0.1:8000/healthz/
docker compose exec web python manage.py test app.studio
```

**Wichtig:** Standardmäßig ist die Web-App nur über die lokale Loopback-Adresse erreichbar; keine öffentliche VPS-Bereitstellung. Die Anmeldung und die dynamische Vereinsauswahl sind implementiert; die manuelle Vereinsanlage und Job-Oberflächen folgen noch. [Vollständige Anleitung](docs/development/docker-local.md).

## GitHub-Arbeitsprozess

1. **Vor jeder technischen Arbeit ein Issue** mit Ziel, Nicht-Zielen, Abhängigkeiten, Priorität und prüfbaren Kriterien anlegen.
2. Branch vom aktuellen `main` erstellen (z. B. `docs/fs-006a-repository-guide`).
3. Änderungen mit Test-/Prüfnachweis und Issue-Verweis als Pull Request öffnen.
4. Review und relevante Prüfungen dokumentieren; erst dann mergen und das Issue schließen.
5. Produktscope/Budget/öffentliche Veröffentlichung entscheidet der Product Owner; technische Umsetzung und Dokumentation folgen dem Backlog.

[Offene GitHub-Issues](https://github.com/whiteyOnTheMoon/FootballStudio/issues) · [Pull Requests](https://github.com/whiteyOnTheMoon/FootballStudio/pulls)

> Jede Änderung am Scope wird als Issue-Änderung oder neue Aufgabe nachvollziehbar gemacht.
