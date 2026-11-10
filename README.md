# FootballStudio

**Football Stories Studio** – eine geschützte Web-App, mit der sich ein Fußballverein zur Laufzeit über **Land → Liga → Verein** auswählen lässt (oder manuell anlegen lässt) und anschließend eine englischsprachige, etwa **8–10 Minuten lange Vereinsdokumentation** inklusive Quellen, Drehbuch, Untertiteln und MP4 generiert wird. Kein fest vorgegebener Pilotverein.

**Ziel-Domain:** `studio2.ap-pixels.com` · **Roadmap:** *Football Stories Studio / Projektroadmap*, v1.0 vom 09.11.2026.

## Projektstatus

**M0 – Planung.** Es gibt bislang **noch keine lauffähige Django-Web-App** und kein fertiges Docker-Deployment. Die Architektur und MVP-Anforderungen sind dokumentiert; die technische Implementierung beginnt in M1/M2. Etwaige ausgefüllte Dokumentationsprüfungen sind **keine** bestandenen Integrationstests.

## Architektur in Kürze

- **Web:** Python/Django, Templates, HTMX (kaskadierende Land-/Liga-/Vereins-Auswahl).
- **Daten:** PostgreSQL mit persistentem Docker-Volume.
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
| [Medien und Rechte](docs/data/media-and-rights.md) | Lizenzmetadaten, Fallback und Publikationsgrenzen |
| [VPS-Inventur](docs/ops/vps-inventory.md) | Lesender Prüfplan; tatsächliche Serverwerte noch offen |
| [Repository-Struktur](docs/development/repository-layout.md) | Geplante Verzeichnisse, lokaler Einstieg und Konventionen |

## Lokal starten – erst nach M1-Implementierung

Der geplante Entwicklungsstart mit Docker Compose lautet nach Fertigstellung von FS-007a/b und FS-008a:

```sh
# Diese Befehle funktionieren erst, wenn Compose-Datei, Images und env-Beispiel in M1 umgesetzt sind.
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 web
```

**Aktuell sind die benötigten Dateien/Services noch nicht erstellt.** Dies ist ein vorgesehener Ablauf, **keine** schon ausführbare Installationsanleitung. Echte Zugangsdaten gehören ausschließlich in sichere, nicht versionierte Konfiguration.

## GitHub-Arbeitsprozess

1. **Vor jeder technischen Arbeit ein Issue** mit Ziel, Nicht-Zielen, Abhängigkeiten, Priorität und prüfbaren Kriterien anlegen.
2. Branch vom aktuellen `main` erstellen (z. B. `docs/fs-006a-repository-guide`).
3. Änderungen mit Test-/Prüfnachweis und Issue-Verweis als Pull Request öffnen.
4. Review und relevante Prüfungen dokumentieren; erst dann mergen und das Issue schließen.
5. Produktscope/Budget/öffentliche Veröffentlichung entscheidet der Product Owner; technische Umsetzung und Dokumentation folgen dem Backlog.

[Offene GitHub-Issues](https://github.com/whiteyOnTheMoon/FootballStudio/issues) · [Pull Requests](https://github.com/whiteyOnTheMoon/FootballStudio/pulls)

> Jede Änderung am Scope wird als Issue-Änderung oder neue Aufgabe nachvollziehbar gemacht.
