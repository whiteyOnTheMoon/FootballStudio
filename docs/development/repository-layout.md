# FS-006a – Repository-Struktur und Entwicklungsstart

**Status:** Strukturentwurf, **noch keine** implementierte Web-App.  
**Issue:** [#12](https://github.com/whiteyOnTheMoon/FootballStudio/issues/12) · **Architektur:** [ADR-0001](../architecture/ADR-0001-mvp-stack.md).

## Zielstruktur nach M1/M2

```text
FootballStudio/
├── README.md
├── CONTRIBUTING.md                     # GitHub-Arbeitsregeln (FS-006b)
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── docs/
│   ├── architecture/                    # ADRs und Pipeline-Verträge
│   ├── data/                            # Fakten-, Quellen-, Medienverträge
│   ├── development/                     # Arbeitsweise und Einstieg
│   ├── mvp/                             # Produktanforderungen und Abnahme
│   └── ops/                             # VPS, Docker, Betrieb und Backups
├── app/                                 # Django-Web-App (FS-007a, M1)
│   ├── config/                          # Einstellungen, URL-Routing und ASGI/WSGI
│   ├── accounts/                        # Login, Session, Berechtigungen
│   ├── clubs/                           # Land → Liga → Verein / manuelle Anlage
│   ├── production/                      # Job-/Artefaktmodell und Dashboard
│   └── templates/                       # Django/HTMX-Ansichten
├── pipeline/                            # getrennte, testbare Produktionsmodule (M2)
│   ├── catalog/                         # Club-Katalogadapter
│   ├── research/                        # Quellen & FactDossier
│   ├── story/                           # Titel, Skript, Szenen
│   ├── media/                           # Assets, Rechte und Fallback
│   ├── audio/                           # TTS, Dauern, Untertitel
│   └── render/                          # FFmpeg, QA und MP4-Export
├── tests/                               # Unit- und Integrations-/E2E-Tests
├── compose.yaml                         # Container web/db/worker (M1/M2)
├── Dockerfile                            # versioniertes Web-/Worker-Image (M1)
└── .env.example                         # ohne echte Geheimnisse (M1)
```

**Wichtig:** Der Baum ist eine **Planung**. Noch nicht existierende Dateien und Ordner werden erst durch ihre jeweiligen GitHub-Issues erstellt. Keine leeren Verzeichnisse als erledigte Features darstellen.

## Verantwortlichkeiten und Modulgrenzen

- **`app/`**: Authentifizierung, Dateneingabe und sichere Auslieferung von Ergebnissen; **keine** langsamen Renderjobs im HTTP-Request.
- **`pipeline/`**: testbare Dienste mit auswechselbaren Providern (Vereinsdaten, LLM, TTS, Wikimedia/Quellen); keine Web-View-Logik.
- **`tests/`**: die echten Tests für dynamische Clubwahl, Session-Sicherheit, Faktendossier, Medienfallback, Retry und 8–10-minütigen MP4-Export.
- **`docs/`**: fachliche Entscheidungen und Abnahmeprüfungen bleiben auch ohne lauffähige App lesbar.
- **`compose.yaml`**: in M1 Web/PostgreSQL als getrennte Container, in M2 zusätzlich separater Worker.
- **Persistente Artefakte** (Videos, Ton, temporäre Dateien, DB-Daten) gehören in Docker-Volumes bzw. private Datenpfade, **nicht** nach Git.

## Geplanter Entwickler-Workflow (erst nach Implementierung)

1. Repository klonen, passendes GitHub-Issue auswählen.
2. Ab M1 `.env.example` in `.env` kopieren; **`.env` niemals einchecken**.
3. Mit `docker compose up -d --build` starten; einzelne Dienste mit `docker compose ps` und `docker compose logs` prüfen.
4. Datenbankmigrationen und Tests mit später dokumentierten Django-/Compose-Befehlen ausführen. Die konkreten Services/Kommandos werden in **FS-007/008** ergänzt.
5. Branch, PR, Prüfprotokoll, Review und erst dann Merge.
6. Nicht automatisch auf dem produktiven VPS deployen; Änderungen an DNS/Proxy/Secrets haben eigene Issues.

Derzeit sind **nur die Dokumentationsschritte** nutzbar. Die ausführbaren Docker-Befehle sind eine **geplante Schnittstelle**, nicht bereits als getestet markiert.

## GitHub-Konventionen

- **Issue-Titel:** `M1 / FS-007a · Django-Grundprojekt erstellen`.
- **Branches:** `docs/fs-...-`, `feat/fs-...-`, `fix/fs-...-`, `infra/fs-...-` in Kleinbuchstaben mit Bindestrichen.
- **Commit:** kurz, fachlich, mit Issue-Referenz.
- **PR:** Ziel und Abgrenzung, zugehöriges Issue, Testbefund, Sicherheits-/Kosten-/Medienaspekte.
- **Status:** Backlog → Ready → In Progress → Review / Test → Done.
- **Labels geplant:** `type:feature`, `type:docs`, `type:security` etc.; `priority:P0..P3`, `area:web/backend/... `. Physische GitHub-Labels/Milestones/Board gehören zu **FS-006c / #14** und sind durch dieses Dokument nicht automatisch eingerichtet.
- **Keine Secret-/Rohdatenfreigabe:** nie private Zugangsdaten, Rohvideo, personenbezogene Testdaten oder urheberrechtlich unklare Medien in öffentlichen Issues.

## Definition of Done – FS-006a

- [x] Einstieg und aktueller Status im README dokumentiert.
- [x] Geplante Ordner für Web-App, Produktionspipeline, Tests, Betrieb und Dokumentation beschrieben.
- [x] Roadmap und Implementierungsabfolge eindeutig verlinkt.
- [x] Branch-/PR-/Test-Grundkonventionen aufgenommen.
- [x] Geplante lokale Docker-Schritte von bereits ausführbaren Befehlen ausdrücklich unterschieden.

**Folge-Issues:** [#13](https://github.com/whiteyOnTheMoon/FootballStudio/issues/13) für Templates, [#14](https://github.com/whiteyOnTheMoon/FootballStudio/issues/14) für Milestones/Labels/Board und [#15–#16](https://github.com/whiteyOnTheMoon/FootballStudio/issues/15) für realen App-/Docker-Code.
