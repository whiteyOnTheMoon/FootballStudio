# FS-002b – Pipeline-Module, Artefakte und Wiederaufnahme

**Status:** Architekturspezifikation für M0, noch keine Implementierung.  
**Datum:** 10.11.2026 · **Issue:** [#5](https://github.com/whiteyOnTheMoon/FootballStudio/issues/5) · **Roadmap:** FS-002 / M0, Abschnitt 02 und M2 (Version 1.0, 09.11.2026).  
**Rahmen:** [ADR-0001](ADR-0001-mvp-stack.md), [MVP-Nutzerfluss](../mvp/user-flow.md) und [MVP-Abnahme](../mvp/acceptance-criteria.md).

## 1. Ziel und verbindliche Grenzen

FootballStudio verarbeitet für einen **zur Laufzeit selbst gewählten Verein** englische Dokumentationsprojekte in einer **Django-Web-App**. Die App läuft über **Docker Compose** mit getrenntem `web`-, `db`- und ab M2 `worker`-Service. Der Nutzer wählt das Land, danach die Liga, danach den Verein (oder legt ihn manuell an), wählt einen Titel und startet die Filmproduktion.

Jede aufwendige Produktionsstufe:
- bekommt **strukturierte Eingaben** aus dem vorherigen Stand;
- legt ein **eigenständiges, wiederlesbares Artefakt** und einen Datenbank-Status ab;
- hält **Quellen, Modell-/Providerparameter und Kosteninformationen** fest, soweit betroffen;
- kann bei Fehlern **gezielt** neu gestartet werden; erfolgreiche frühere Schritte bleiben erhalten;
- speichert **keine echten Secrets** in Artefakten, Logs oder dem Repository.

Ein Fehler beim finalen Rendern darf **weder Recherche noch Skript noch TTS** unnötig erneut auslösen.

## 2. Modulkarte mit Ein-/Ausgaben

| Reihenfolge | Modul | Eingang | Persistiertes Ergebnis | Fehler/Fallback |
| --- | --- | --- | --- | --- |
| 0 | **ClubCatalog** (außerhalb Renderpipeline) | Land, Liga, Such-/manuelle Clubauswahl | gewählte Club-ID, Name, Land, Liga, Herkunft/Adapter, Zeitpunkt | Freie Datenquelle nicht verfügbar → manueller Verein, keine fest codierte Club-ID |
| 1 | **ClubProfile** | ausgewählter Club, externe Kennungen soweit vorhanden | normalisiertes Vereinsprofil, IDs/Quellen | Unbekannte Daten als offen markieren |
| 2 | **SourceResearch** | Vereinsprofil, Quelladapter | Abrufe und datierte Quellenreferenzen mit Original-URLs | Unzugängliche Quelle dokumentieren |
| 3 | **FactDossier** | Rohquellen, Profil | Fakten mit Beleg-Verweisen, Unsicherheit und evtl. Konflikten | Ungesicherte Aussage nicht als sicher verwenden |
| 4 | **TitlePlanning** (optional vor Generierung) | Vereinsprofil + belegte Fakten, ggf. gewählter Ton | drei Titelvorschläge **oder** manuell erfasster Titel | Bei KI-Fehler manueller Titel; keine erfundenen Behauptungen |
| 5 | **Script** | Faktendossier, bestätigter Titel, Sprache `en`, Ziel-Laufzeit | englisches Drehbuch mit Quellenbindungen und Erzählbogen | Unsicherheit kennzeichnen; bei zu wenigen Fakten nicht halluzinieren |
| 6 | **ScenePlanning** | Drehbuch, Faktendossier | nummerierte Szenen, Sprecherabschnitte, Medienbedarf und geplante Dauer | Ersatz für medienarme Szenen angeben |
| 7 | **MediaSelection** | Szenen, Club-Kontext, Quellen | ausgewählte Medien samt URL, Urheber, Lizenzstatus, Verwendungszweck, lokale Dateien | Fehlendes/unklares Medium → eigene Karten-/Textszene |
| 8 | **TTS** | sprachbezogene Sprecherabschnitte, Stimmkonfiguration | Audio-Dateien, Dauern, Anbieter-/Kosteninfos | Anbieterfehler pro Szene, gezielter Retry |
| 9 | **Captions** | Sprecherabschnitte und tatsächliche TTS-Dauern | zeitcodierte englische Untertitel | Synchronisation prüfen und ggf. neu erstellen |
| 10 | **Render** | Szenenplan, Medien, TTS, Captions, Template-Einstellungen | gerenderte MP4 im geschützten Volume, FFmpeg-Ausgabe/Exitcode | Wiederholung **nur Render**, falls Inputs unverändert |
| 11 | **QualityExport** | MP4, Skript, Quellen, Medienmetadaten | Laufzeit-/Auflösungsprüfung, Ausgabe-Metadaten, Skript-/Quellenexport | Fehlendes/defektes MP4 als Fehler; nach Korrektur erneut prüfen |

Die Reihenfolge ist **logisch**, nicht zwingend eine starre Schleife. Insbesondere Medienabruf und TTS können nach vorliegendem Szenenplan unabhängig vorbereitet werden; parallele Render-Worker sind **nicht** Teil des MVP.

## 3. Titelvorschläge vor dem Generieren

Der festgelegte Nutzerfluss ist **Verein → Titel → „Generieren“**. Gleichzeitig benötigen belegbare KI-Titel möglicherweise bereits Rechercheergebnisse. Das wird wie folgt vereinbar gemacht:

1. **Manueller Titel:** Der Nutzer kann sofort einen Titel eingeben; eine kostenpflichtige KI-Recherche **vor dem Jobstart ist dafür nicht erforderlich**.
2. **Drei KI-Vorschläge:** Ein **optionaler Vorbereitungs-/Preflight-Schritt** lädt vorhandene, möglichst belegte Vereinsinformationen und schlägt drei Titel vor. Benötigt er Recherche, werden das Dossier und der Zwischenstand gespeichert.
3. **„Generieren“:** Aus dem bestätigten Titel und ausgewählten Verein wird der eigentliche Filmjob gestartet. Gültige bereits gespeicherte Preflight-Recherche wird **wiederverwendet**, statt automatisch doppelt bezahlt/geladen zu werden.
4. Die Oberfläche kennzeichnet bei KI-Titelwünschen den Vorbereitungsstatus und erlaubt bei Fehlern weiterhin einen manuellen Titel.

Eine technische Trennung von `Project`, `PreparationJob` und `ProductionJob` wird erst in den Modell-/Worker-Issues im Detail umgesetzt. Es genügt, wenn gespeicherte Vorbereitungsartefakte eindeutig einer ausgewählten Club-Konfiguration zugeordnet sind.

## 4. Zu speichernde Daten

### 4.1 Datenbank (PostgreSQL)

Logische Entitäten; die endgültigen Django-Modellfelder folgen in FS-005a/b, FS-010a/b und M2:

- **Club**: ID, Name, Land, Liga, Quelle/externe ID oder manuell erfasst.
- **ProductionJob**: ID, Benutzerbezug, Club-ID, Titel, Sprache, Zielparameter, Status, Zeiten, Fehler- und Kostenübersicht.
- **PipelineStepRun**: Job, Schrittname, Versuch, Status, Beginn/Ende, Eingabe-Fingerprint, Ergebnispfad/-ID, Fehlertyp und ggf. Kosten.
- **SourceReference / Fact**: Quellen-URL, Abrufdatum, Zuordnung zu einer belegbaren Aussage, Unsicherheits-/Konfliktstatus.
- **MediaAsset**: Original-URL, Urheber, Lizenz und Status, Attribution, Nutzungszweck, gespeicherte Datei-ID.
- **Script / Scene / LanguageVariant**: Versionen bzw. strukturierte Texte mit Quellbezug; zunächst nur `en`.
- **ProductionArtifact**: Job-ID, Schritt, Version, Dateityp, Speicherpfad, Prüfsumme, Größe, Metadaten, Erzeugungszeit.

Das Datenbankschema wird **nicht** ohne zugehörige Implementierungsissues festgelegt. Die Entitäten beschreiben Anforderungen an Speicherung und Wiederholbarkeit.

### 4.2 Artefakte in persistentem Dateivolume

Empfohlener **logischer** Speicheraufbau (kein öffentliches statisches Webverzeichnis):

```text
production-data/
  jobs/<job-id>/
    profile/profile.json
    research/sources.json
    research/facts.json
    title/selection.json
    script/en/v1.json
    scenes/en/v1.json
    media/manifest.json
    media/files/...
    audio/en/...
    captions/en/subtitles.srt
    render/en/documentary.mp4
    export/en/script.txt
    export/en/sources.json
    qa/en/report.json
    manifest.json
```

- Die App liefert Downloads **nur nach Login und Berechtigungsprüfung** aus. Nicht direkt öffentlich als Nginx-Static-Directory bereitstellen.
- Zur Fehlerresistenz zunächst in eine temporäre Datei schreiben, dann nach erfolgreichem Abschluss atomar übernehmen, wenn das Volume das unterstützt.
- **PostgreSQL speichert Jobstatus und Artefaktverweise**; große Medien-/Videodateien gehören nicht als BLOB in die DB.
- Löschen/Archivieren und Backup-Aufbewahrung werden nach Kenntnis von VPS-Platz und Budget bestimmt.

### 4.3 Metadaten pro Artefakt

Mindestens: `job_id`, `stage`, `schema_version`, `attempt`, `language` soweit relevant, `created_at`, `status`, `input_fingerprint`, `artifact_path`, `checksum`, `size` und referenzierte Quellen/Medien. Für KI/TTS zusätzlich `provider`, `model_or_voice`, geeignete Nutzungs-/Kostenangaben und Status. Zugangsdaten dürfen nicht persistiert werden.

**Wichtig:** Versionierung meint **nachvollziehbare Inputs und Outputs**, nicht garantierte bitidentische Neugenerierung bei veränderlichen externen APIs oder KI-Modellen.

## 5. Statusmodell

**Produktionsjob:**
```text
draft → queued → running → completed
                  └────→ failed → queued (nach bewusstem Retry)
```

- `draft`: Titel/Club-Kontext vorbereitet, Job noch nicht endgültig gestartet.
- `queued`: zur Verarbeitung angenommen.
- `running`: Worker führt einen Schritt aus.
- `completed`: MP4/Exports sind erstellt und technische Mindestprüfungen erfolgreich.
- `failed`: konkrete Stufe und Fehlermeldung gespeichert; Nutzer sieht Fehler und kann ggf. wiederholen.
- `cancelled` ist **keine notwendige MVP-UI-Funktion**; wird später bei Bedarf spezifiziert.

**Einzelne Pipeline-Stufen:** `pending` → `running` → `completed` oder `failed`. Nicht betroffene Stufen bleiben `completed`. Pro Wiederholung entsteht ein neuer **Attempt-Datensatz**, statt alte Fehlerhistorie zu überschreiben.

**Arbeitsweise:** Ein Worker bearbeitet im MVP höchstens einen Filmjob zur selben Zeit. Jobübernahme/Timeout und Erholung nach Absturz müssen transaktionssicher sein; konkrete Datenbank-Locking-/Leasing-Technik wird in FS-020a/b implementiert. Ein HTTP-Request rendert **nicht** selbst das Video.

## 6. Wiederholung, Invalidierung und Idempotenz

| Änderung/Fehler | Erneut erzeugen | Weiterhin verwenden |
| --- | --- | --- |
| FFmpeg-Render schlägt fehl | Render, danach QA/Export | Clubprofil, Quellen, Faktendossier, Titel, Skript, Szenen, Medien, TTS, Captions |
| QA findet beschädigten Export | Nur betroffenen Render-/QA-Teil | Alle unveränderten vorgelagerten Artefakte |
| TTS-Fehler in einer Szene | betroffene TTS-Ausgabe, Dauer/Captions, Render/QA | Recherche, Fakten, Skript, übrige Szenen soweit unverändert |
| Stimme oder TTS-Parameter ändern | betroffenes Audio, Untertitel-Zeitpunkte, Render/QA | Faktendossier, Skript, Quellen |
| Medienauswahl/Lizenzstatus ändern | betroffene Medienstufe, Render/QA | Dossier, Skript, TTS, wenn unverändert |
| Drehbuchtext ändern | Skriptversion, abhängige Szenen/TTS/Captions/Render/QA | Quellen/Faktendossier und Verein |
| Titel ändern | Titelauswahl, Skript und alle davon abhängigen Stufen | Quellen und Faktendossier (sofern weiterhin passend) |
| Verein ändern | **Neuer Projekt-/Jobkontext** und zugehörige Recherche/alle abhängigen Stufen | Nur ausdrücklich universelle, nicht vereinsbezogene Konfiguration |
| Quellen erneuern / geändertes Dossier | Dossier und alle darauf basierenden Inhalte | Unabhängige Basisdaten, soweit validiert |

**Umsetzung:** Für jedes Ergebnis einen **Input-Fingerprint** aus den tatsächlich verwendeten Vorgängerständen/Parametern ableiten. Ein gültiger `completed`-Zwischenstand mit passendem Fingerprint kann wiederverwendet werden. Bei Änderungen werden **nur abhängige** Stufen ungültig. Ein Retry prüft existierende Dateien/Checksummen, markiert verwaiste oder halbfertige Ergebnisse als ungültig und erzeugt einen neuen Versuch.

**Sicherheits- und Kostenregel:** Automatisches Retry nur für geeignete **vorübergehende** Fehler in begrenztem Umfang; bei permanenten API-, Daten-, Lizenz- oder Konfigurationsfehlern klar abbrechen. Doppelte LLM-/TTS-Aufrufe sind nicht immer vollständig vermeidbar; Kosten werden pro tatsächlichem Versuch nachvollziehbar erfasst.

## 7. Fehlerklassen und UI

- **Externe Daten/Quelle:** Timeout, Rate-Limit, fehlende Club-ID oder unbrauchbare Quellen → spezifische Fehlermeldung; manuelle Vereinsanlage möglich, aber keine erfundenen Fakten.
- **KI/Text:** JSON-Formatfehler, unzureichende Belege, Modelllimit oder ungeeignete Länge → Schrittfehler und gezielte Korrektur.
- **Medien/Rechte:** keine geeigneten Medien → eigene Karten/Textgrafiken; nicht geklärte Rechte nicht automatisch freigeben.
- **TTS/FFmpeg:** Anbieter-/Codec-/Ressourcenfehler → Fehlerphase protokollieren; betroffene Stufe neu ansetzen.
- **Sicherheit/Download:** unerlaubte Zugriffe werden abgewiesen; Rohdatenpfade oder Secrets werden Nutzern nicht als Fehlermeldung gezeigt.

Die Web-App zeigt mindestens **Job-ID, Club, Titel, Sprache, aktuelle Phase, Status und Fehlerzusammenfassung**. Versions-/Kosten-/Rohdiagnose können zunächst im Admin/Log sichtbar sein, müssen aber für die technische Fehlersuche nachvollziehbar gespeichert werden.

## 8. Docker- und Qualitäts-Nachweise

- [ ] In M1 startet `docker compose up -d --build` Web + Datenbank; persistente DB-Daten überstehen Container-Neustarts.
- [ ] Im M1-Dashboard werden **zwei verschiedene API-Clubs** und ein **manuell angelegter Club** jeweils für einen Testjob ausgewählt.
- [ ] In M2 läuft die Pipeline im **separaten Worker-Container**, nicht im Web-Request.
- [ ] Ein M2-Renderfehler wird reproduziert; erneuter Render verwendet dieselben Dossier-/Skript-/TTS-Artefakte.
- [ ] Aus dem ausgewählten Club entsteht eine **8–10 Minuten lange englische MP4** in 16:9 mit Skript, Quellen, Untertiteln und internem Download.
- [ ] Kein unautorisierter Abruf von Produktionsdateien möglich.

Diese Kriterien sind **noch nicht ausgeführt**. Reale Abnahme in M1/M2, insbesondere [#50](https://github.com/whiteyOnTheMoon/FootballStudio/issues/50) und [#51](https://github.com/whiteyOnTheMoon/FootballStudio/issues/51).

## 9. Abgrenzung und verbleibende Details

- **Dieses Issue #5 spezifiziert**, implementiert noch keinen Job-Worker, kein Datenbankschema und keinen Render.
- Die Django-Modelle folgen in [#22](https://github.com/whiteyOnTheMoon/FootballStudio/issues/22) / [#23](https://github.com/whiteyOnTheMoon/FootballStudio/issues/23); Quellenfelder in [#10](https://github.com/whiteyOnTheMoon/FootballStudio/issues/10), Medien-/Lizenzfelder in [#11](https://github.com/whiteyOnTheMoon/FootballStudio/issues/11).
- Die genaue Queue-Übernahme, Retry-Implementierung und Web-Statusansicht folgen in [#46](https://github.com/whiteyOnTheMoon/FootballStudio/issues/46) und [#47](https://github.com/whiteyOnTheMoon/FootballStudio/issues/47).
- Echte API-, TTS- und LLM-Anbieter/Preise werden separat entschieden. Keine neuen SaaS-Verpflichtungen aus diesem Design.
- Kein YouTube-Autoupload, keine parallelen Render-Worker, keine komplexe Timeline-Bedienung und keine fünf weiteren Sprachproduktionen im MVP.

## 10. Dokumentations-Review für FS-002b

- [x] Pipeline-Module mit Eingaben, Ausgaben und Fallbacks beschrieben.
- [x] Datenbankeinträge, separate Artefakte, Metadaten und Speicherort festgehalten.
- [x] Statusmodell, Fehlerklassen und wiederholbare Schritte definiert.
- [x] Ein fehlgeschlagener Render führt **nicht** zu erneuter Recherche.
- [x] Anforderungen für freie Vereinswahl und Docker Compose beibehalten.
- [x] Implementierung und technische Tests ausdrücklich als noch offen gekennzeichnet.
