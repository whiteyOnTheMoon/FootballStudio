# ADR-0001 – MVP-Technologiestack und Betriebsarchitektur

**Status:** Angenommen als technischer Startpunkt für M1/M2; konkrete Anbieter- und Betriebsparameter bleiben offenen Issues vorbehalten.  
**Datum:** 10.11.2026  
**Issue:** [FS-002a / #4](https://github.com/whiteyOnTheMoon/FootballStudio/issues/4)  
**Grundlage:** *Football Stories Studio / Projektroadmap*, Version 1.0 (09.11.2026), vor allem Abschnitt 02 / Seite 3; bestätigte Produktanforderungen zu Docker und freier Vereinsauswahl.  
**Verwandte Dokumente:** [MVP-Nutzerfluss](../mvp/user-flow.md), [MVP-Abnahme](../mvp/acceptance-criteria.md), [Testfälle](../mvp/pilot-clubs.md).

## Kontext und Entscheidungsziele

FootballStudio soll auf dem bestehenden VPS als **passwortgeschützte Web-App** unter `studio2.ap-pixels.com` laufen. Der Nutzer wählt **zur Laufzeit** über **Land → Liga → Verein** oder manuell einen Verein aus, bestimmt einen Titel und startet eine englische Dokumentation von 8–10 Minuten. Eine feste Clubauswahl oder hart codierte Pilotverein-ID sind ausgeschlossen.

Die Architektur muss:
- Mit **Docker Compose** auf einem VPS einsetzbar und kostengünstig bleiben.
- Eine **M1-Demo mit echter dynamischer Vereinsauswahl** und einfachem Testjob erlauben.
- In M2 die Produktion (Recherche → Fakten → Skript → Szenen → Medien → TTS → Untertitel → FFmpeg → MP4) im Hintergrund ermöglichen.
- Für jeden Job Zwischenergebnisse, Quellen, Medienherkunft, Fehler und Ergebnisse speichern, sodass ein Render-Retry nicht erneut recherchieren muss.
- Anbieter für LLM, TTS und Vereins-/Ligadaten austauschbar halten und später sechs Sprachen unterstützen.
- Secrets, personenbezogene Daten und nicht freigegebene Produktionsmedien schützen.

## Entscheidung

| Bereich | Entscheidung für M1/M2 | Begründung |
| --- | --- | --- |
| Server-/Web-Framework | **Python + Django**, zunächst serverseitige Django-Templates | Wenig Infrastrukturaufwand; Authentifizierung, ORM, Admin und Formulare sind bereits Bestandteil des Frameworks |
| Interaktive UI | **HTMX** auf Django-Views; progressive Verbesserung | Abhängige Land-, Liga- und Vereins-Dropdowns ohne getrennte SPA/API-Anwendung |
| Datenhaltung | **PostgreSQL** als separater Compose-Service mit persistentem Volume | Strukturierte Beziehungen und transaktionale Speicherung von Vereinen, Quellen, Jobs, Szenen, Ergebnissen |
| Render | **FFmpeg** im Produktions-Worker-Container | Reproduzierbarer Audio-/Videomix, Bildszenen, Untertitel und MP4-Export ohne teure Video-SaaS-Grundpflicht |
| Hintergrundaufgaben | **Ein separater Worker-Prozess im eigenen Docker-Compose-Service**, zunächst nur ein Worker | Langsame Recherche/TTS/Renderarbeit blockiert keine Web-Requests. Konkrete Queue-/Claim-Technik wird in FS-002b/FS-020a beschrieben; **Redis/Celery ist keine MVP-Pflicht** |
| LLM | **Anbieteradapter** mit konfigurierbarem Modell und Kostenprotokoll | Anbieter und Budget werden separat in FS-004a entschieden, kein Anbieter wird hier festgelegt |
| TTS | **Anbieteradapter** mit englischem Testmodus | Stimme, Nutzungslizenz und Budget werden in FS-004b entschieden |
| Rechercheschnittstellen | **Wikidata / Wikipedia / Wikimedia Commons** zuerst; zusätzliche Quellen bei Bedarf | In der Roadmap vorgesehene Startquellen; Aussagen und Medien-Metadaten bleiben belegbar |
| Land-/Liga-/Vereinsdaten | **Separater austauschbarer Katalogadapter** (möglichst freie API), plus **manuelle Vereinsanlage** | Verfügbare Länder/Ligen nicht hart codieren; konkrete Datenquelle, Abdeckung und Limits werden in FS-011a geprüft |
| Deployment | **Docker Compose**, Reverse Proxy, HTTPS, Umgebungsvariablen/Secret-Verwaltung, Backup- und Logkonzept | Ein VPS, klar trennbare Prozesse, einfacher Betrieb; TLS-Details erst nach VPS-Inventur festlegen |
| Mediendateien und Exporte | **Persistentes, nicht öffentlich gemountetes Ausgabevolume**; Auslieferung nur durch authentifizierte App | MP4, Audiospuren, Quellenexporte und Zwischenstände überleben Container-Neustarts; keine öffentliche Rohdatei-URL |
| Sprache | Fakten/Vereine möglichst **sprachneutral**, generierte Artefakte je Sprachcode getrennt; zunächst nur **`en`** | `de`, `fr`, `it`, `es`, `pt` sind für M5 vorgesehen, nicht im MVP auszuführen |

### Geplanter Compose-Zuschnitt

```text
Browser (HTTPS) → Reverse Proxy → web (Django + Templates/HTMX)
                                      │
                                      ├── db (PostgreSQL, persistent)
                                      │
                                      └── Produktionsjob in DB
                                                  │
                                          worker (Python + FFmpeg)
                                                  │
                                          geschütztes Ausgabevolume
                                                  │
                                      Web-App: Vorschau / Download
```

- **M1:** `web` + `db` laufen in getrennten Containern; Reverse Proxy und HTTPS für die Ziel-Domain sind Teil von M1.
- **M2:** zusätzlich `worker` als eigener Compose-Service. Die Jobausführung bleibt auf **einen Worker** begrenzt, bis M6 Skalierung begründet.
- **Keine „Alles in einem Container“-Konstruktion:** Die Anforderung „Docker“ bedeutet einen gemeinsamen, per Compose gestarteten Betriebsverbund, nicht die Kopplung von Datenbank und Webprozess in ein Image.
- Entwicklungs- und Produktionskonfiguration können Compose-Overrides nutzen; Images/Quellcode bleiben versioniert.
- Der genaue Reverse Proxy (bestehende VPS-Infrastruktur, Ports, Zertifikatsverwaltung) wird **nach FS-003a** in M1 entschieden, nicht ohne Bestandsprüfung.
- Keine behauptete Betriebsbereitschaft: Die Compose-Dateien und Container werden erst in M1/M2 implementiert und getestet.

## Laufzeitmodell und Modulgrenzen

**M1-Auswahlfluss**
1. Authentifizierter Nutzer öffnet das Django-Dashboard.
2. Land-Liste wird vom Katalogadapter geladen/gecached; Länderabdeckung wird dokumentiert.
3. HTMX lädt abhängig vom gewählten Land die Ligen, abhängig von der Liga die Vereine.
4. Bei jeder übergeordneten Änderung werden veraltete abhängige Auswahlen zurückgesetzt.
5. Das System validiert und speichert die Club-Zuordnung für den Job. Falls ein Club fehlt, kann er manuell angelegt werden.
6. Die Web-App erstellt einen Testjob und zeigt dessen Status. Kein Club wird für die App fest vorgegeben.

**M2-Verarbeitung**
1. Die Web-App legt einen Produktionsjob mit Sprache, ausgewähltem Verein und Titel an und antwortet rasch.
2. Der Worker übernimmt Jobs kontrolliert; persistiert **Stufenstatus, Fehler und Zwischenergebnisse**.
3. Ein Recherche-Adapter speichert ein Quellen-/Faktendossier. Der Skriptgenerator arbeitet auf diesem Dossier, nicht auf unbelegten Modellbehauptungen.
4. Szenenplanung, Medienadapter und TTS liefern unabhängige, versionierbare Artefakte.
5. FFmpeg rendert MP4, Untertitel und Audio; das Ergebnis wird technisch geprüft und nur für angemeldete Nutzer bereitgestellt.
6. Wiederholung einer fehlerhaften späten Stufe verwendet gespeicherte frühere Ergebnisse. Die genaue Transaktions-/Retry-Semantik wird in **FS-002b / #5** und **FS-020a/b** spezifiziert.

**Schnittstellenverträge (logisch, noch nicht implementiert):**
- `ClubCatalogProvider`: `countries()`, `leagues(country)`, `clubs(league)`, Umgang mit Abdeckung und API-Fehlern.
- `ResearchProvider`: `build_fact_dossier(club)` mit Quellenverweisen und Unsicherheiten.
- `LLMProvider`: `suggest_titles(dossier)`, `generate_script(dossier, title, language)`; Modell/Kosten konfigurierbar.
- `TTSProvider`: `synthesize(script, voice, language)` mit Audio-/Dauer-Metadaten.
- `MediaProvider`: `find_media(scene)` mit URL, Urheber, Lizenz/Status und Verwendung.
- `RenderService`: `render(job, scenes, audio, captions)` mit MP4-Pfad, Laufzeit, Auflösung und Fehlermeldungen.

Dies sind **fachliche Grenzen**, keine verfrühte Festlegung auf konkrete Python-Klassennamen, Bibliotheken oder API-Responses. Das Detaildesign erfolgt in #5 und den zugehörigen Implementierungsissues.

## Sicherheit, Rechte und Betrieb

- **Django-Login/Session**, Zugriffsschutz für Jobstatus, Skript, Quellen und Medien; sichere Cookies, CSRF und Passwort-Hashing.
- **Keine API-Schlüssel, Passwörter oder personenbezogenen Produktionsdaten im Git-Repository oder Image.** Stattdessen Umgebungsvariablen und sichere Secret-Verwaltung gemäß M1 #29.
- DB nur im erforderlichen Container-Netz, keine unnötige öffentliche DB-Portfreigabe; Healthchecks, strukturierte Logs und Backup-/Restore-Test.
- Medien und Quelldaten mit Herkunft/Lizenzstatus archivieren; **interner Download ist keine automatische Veröffentlichungsfreigabe**. Öffentliche Publikation erst nach Rechteprüfung.
- Datenbank- und Ausgabevolumes getrennt persistent sichern; Umfang und Rotation nach VPS-Inventur (FS-003a, FS-008c).
- **Budget:** API-/TTS-Nutzung bei allen Generierungsschritten protokollierbar; tatsächliche Limits und Providerwahl in FS-004a/b.

## Alternativen und bewusst nicht gewählte MVP-Optionen

| Alternative | Warum jetzt nicht? |
| --- | --- |
| React/Vue als separate SPA plus REST-Backend | Zusätzliches Build-, Auth- und Hosting-Setup ohne notwendige MVP-Anforderung; UI bleibt erweiterbar |
| FastAPI/Flask anstelle Django | Mehr eigene Infrastruktur für Login, Admin, ORM und Sessions bei ähnlichem Produktumfang |
| SQLite für Produktionsdaten | Für getrennte Web-/Worker-Prozesse und langlebige relationale Produktionsdaten ist PostgreSQL als Basis geeigneter |
| Cloud Video Rendering / generative Videodienste als Kern | Kosten und Anbieterbindung widersprechen dem Low-Budget-FFmpeg-Prototyp |
| Sofort Redis/Celery und mehrere Worker | Zusätzliche Betriebsdienste; Umfang des MVP erfordert nur einen kontrollierten Worker. Nach Skalierungsbedarf neu prüfen |
| Komplett automatischer YouTube-Upload | In der Roadmap explizit erst nach interner MVP-Phase und Rechtefreigabe |
| Alle sechs Sprachpipelines in M2 | M5-Aufgabe; Datenmodell wird nur vorbereitet |

## Nachteile, Risiken und Gegenmaßnahmen

1. **HTMX/Server-Rendering** ist für einen späteren komplexen Timeline-Editor begrenzt → vor einer anspruchsvollen M4/M6-Bedienoberfläche neu bewerten.
2. **Ein Worker** führt zu Wartezeiten → Jobstatus und Fehlermeldungen anzeigen; Queue-Ausbau erst M6.
3. **Externe APIs und Quellen** können unvollständig/instabil sein → Provideradapter, Caching soweit rechtlich zulässig, manuelle Vereinsanlage und eindeutige Fehlermeldungen; Abdeckungsumfang dokumentieren.
4. **VPS-RAM und Renderzeit** unbekannt → M0 FS-003a/b prüfen, zunächst 720p-Test und ein Worker.
5. **Urheber- und Bildrechte** nicht immer eindeutig → Lizenzmetadaten speichern, Fallback auf eigene Grafiken und Freigabe vor öffentlicher Publikation.
6. **Secrets und Rohmedien** können durch Fehlkonfiguration öffentlich werden → geschützte Volumes/Downloads, Rechtechecks und Deployment-Review.

## Verbleibende, ausdrücklich offene Entscheidungen

| Frage | Nächstes Issue |
| --- | --- |
| Konkrete Pipeline-Datenverträge, Jobstatus und Retry-/Queue-Mechanik | FS-002b / [#5](https://github.com/whiteyOnTheMoon/FootballStudio/issues/5) |
| VPS-Spezifikation und Infrastruktur-/Reverse-Proxy-Bestand | FS-003a/b / [#6](https://github.com/whiteyOnTheMoon/FootballStudio/issues/6), [#7](https://github.com/whiteyOnTheMoon/FootballStudio/issues/7) |
| LLM-Modell, Provider, Kostenlimit und Fallback | FS-004a / [#8](https://github.com/whiteyOnTheMoon/FootballStudio/issues/8) |
| Englische TTS-Stimme und Anbieter | FS-004b / [#9](https://github.com/whiteyOnTheMoon/FootballStudio/issues/9) |
| Fakt-/Lizenzfelder | FS-005a/b / [#10](https://github.com/whiteyOnTheMoon/FootballStudio/issues/10), [#11](https://github.com/whiteyOnTheMoon/FootballStudio/issues/11) |
| Freie Länder-/Ligen-/Clubs-API und Abdeckung | FS-011a / [#24](https://github.com/whiteyOnTheMoon/FootballStudio/issues/24) |
| Exakte Docker-/Deployment-Implementierung | FS-007b / [#16](https://github.com/whiteyOnTheMoon/FootballStudio/issues/16), M1-Deployment #27–#30 |

**Änderungsverfahren:** Wird eine Architekturentscheidung später revidiert, muss die Abweichung in einem neuen oder ergänzten ADR und GitHub-Issue begründet werden.

## Abnahme dieser Dokumentationsaufgabe

- [x] Python/Django, HTMX, PostgreSQL, FFmpeg und Docker Compose samt Zweck und Trennung dokumentiert.
- [x] LLM-/TTS-Adapter und Konfigurierbarkeit von Anbietern/Modellen beschrieben.
- [x] Alternativen, technische Risiken, Sicherheit und bewusst ausgeschlossene MVP-Features notiert.
- [x] Frei wählbare Clubs bereits in M1 und Docker-Worker ab M2 ausdrücklich berücksichtigt.
- [x] Technische Detailfragen als Folge-Issues ausgewiesen; keine nicht getestete Implementierung als fertig behauptet.
