# FS-005b – Medienmetadaten, Lizenzstatus und Grafik-Fallback

**Status:** M0-Datenvertrags-Spezifikation; keine implementierte Lizenzautomatik und keine Rechtsfreigabe.  
**Issue:** [#11](https://github.com/whiteyOnTheMoon/FootballStudio/issues/11) · **Roadmap:** FS-005 / M0, Medienstrategie (Seite 3), Qualitäts-/Rechtephase M3 (Seite 5).  
**Abhängigkeit:** [Fakten- und Quellenmodell](facts-and-sources.md), [Pipeline-Verträge](../architecture/pipeline-contracts.md).

## Zweck und Leitplanken

In der M2-Pipeline werden externe Fotos/Illustrationen möglichst aus offen lizenzierten oder ausdrücklich zur Nutzung erlaubten Quellen (Start: Wikimedia Commons) ausgewählt. **Jedes verwendete externe Asset** benötigt nachvollziehbare Quelle, Urheber, Lizenzstatus und beabsichtigten Einsatz. Die bloße Verfügbarkeit eines Bildes im Internet oder einer API ist **keine Erlaubnis zur Nutzung**.

**Unklarer Status = kein automatischer Einbau in ein freizugebendes Video.** Für den Prototypen bevorzugen wir ausreichend geklärte Medien oder eigene Karten, Texttafeln, Zeitleisten und Datengrafiken. Auch interne Prototypennutzung ist keine generelle Urheberrechtsausnahme.

## Logisches Datenmodell

### `MediaAsset`

| Feld | Pflicht | Bedeutung |
| --- | --- | --- |
| `id` | ja | stabile interne Referenz |
| `source_url` | ja, externe Medien | Seite mit Quell-/Lizenzinformationen, nicht nur direkte Bild-URL |
| `original_file_url` | falls verfügbar | Adresse der Originaldatei |
| `source_platform` | ja | z. B. `wikimedia_commons`, `own_generated`, `licensed_supplier`, `other` |
| `creator_name` | bei externen Medien soweit auffindbar | Urheber/Autorenangabe oder ausdrücklich `unknown` |
| `title` | optional | Werk- oder Dateititel |
| `license_identifier` | ja | exakte gefundene Lizenzangabe (z. B. SPDX-/Creative-Commons-Code), `custom_permission` oder `unknown` |
| `license_url` | falls vorhanden | Link zu vollständigen Lizenzbedingungen |
| `license_statement_url` | wenn vorhanden | konkrete Seite / Dokumentation der Rechteangabe zum Werk |
| `rights_status` | ja | Klassifikation nach Tabelle unten; noch keine pauschale Rechtsgarantie |
| `attribution_text` | ja bei erforderlicher Attribution | darstellbare Urheber-/Lizenznennung inkl. Link, sofern verlangt |
| `attribution_required` | ja | `yes`, `no`, `unknown` |
| `intended_use` | ja | Einsatz in Szene, Intro/Outro, Thumbnail, Vorschau, Export etc. |
| `scene_id` | optional | zugehörige Produktionsszene(n) |
| `file_storage_ref` | bei Abruf | interner geschützter Pfad/Datei-ID im persistenten Volume |
| `checksum`, `mime_type`, `pixel_size` | bei lokalem Medium | technischer Nachweis und Eignungsprüfung |
| `retrieved_at` | ja | tatsächlicher Abrufzeitpunkt als ISO-8601-Zeitstempel |
| `rights_checked_at` | optional | Zeitpunkt einer tatsächlichen Rechteprüfung |
| `rights_review_note` | optional | konkrete Einschränkungen, Prüfung, Unsicherheit |
| `public_release_approved_at` | optional | Zeitstempel einer **ausdrücklichen** Publikationsfreigabe (erst M3) |
| `public_release_approved_by` | optional | prüfende Person/Instanz (erst M3) |
| `job_id`, `asset_version` | ja | Job- und Artefaktzuordnung für Re-Render und Audit |

Felder sind **fachliche Verträge**. Die konkrete Django-/PostgreSQL-Implementierung erfolgt in M1/M2, nicht in diesem Dokument.

### `MediaUse` (verwendungsbezogen)

Ein Asset kann in mehreren Szenen und Formaten verwendet werden. Für jede Verwendung separat festhalten:

- `media_asset_id`, `job_id`, `scene_id`, `use_type` (z. B. background, still, overlay, thumbnail)
- `transformation` (Beschnitt, Farbe, Textüberlagerung, Animation)
- `planned_duration_seconds`, `position` (soweit technisch relevant)
- `required_attribution_display` und tatsächlicher `attribution_output_ref`
- `use_review_state`: `not_reviewed`, `allowed_for_this_use`, `blocked`, `unknown`
- `release_gate_state` (erst M3): `pending`, `approved`, `rejected`

**Warum trennen?** Eine Lizenz kann je nach Bearbeitung, Format oder Veröffentlichung unterschiedliche Bedingungen haben; eine Freigabe für eine konkrete Nutzung gilt nicht pauschal für jede andere Verwendung.

## Rechte- und Freigabestatus

| `rights_status` | Auslegung | Automatische Pipeline-Entscheidung |
| --- | --- | --- |
| `own_created` | eigene Grafik/Text-/Kartenkomposition; verwendete Bestandteile müssen ebenfalls zulässig sein | prinzipiell bevorzugen; Rechte weiterer Bestandteile prüfen |
| `open_license_to_review` | Lizenzangabe weist eine offene Lizenz aus, konkrete Bedingungen noch zu prüfen | **nicht** als vollständig publikationsfrei behandeln; Nutzungsbedingungen kontrollieren |
| `documented_permission` | ausdrückliche Erlaubnis liegt vor, mit dokumentierten Nutzungsbedingungen | nur für den erlaubten Umfang einsetzen |
| `public_domain_claimed` | Quelle behauptet Gemeinfreiheit | Schutzdauer, Ursprungsland und zusätzliche Rechte soweit relevant prüfen |
| `unknown` | Urheber, Lizenz oder Erlaubnis unklar | durch eigene Grafik ersetzen; keine stillschweigende Freigabe |
| `restricted_or_disallowed` | nach bekannten Bedingungen nicht einsetzbar | nicht auswählen; Fallback |

**Zusätzlicher Prüfpunkt:** Marken-/Logo-Rechte, Persönlichkeitsrechte und Rechte an abgebildeten Motiven können unabhängig vom fotografischen Copyright bestehen. Ein Wikimedia-Label allein genügt deshalb nicht als pauschaler Freigabenachweis. Kommerzielle Nutzung, Bearbeitung, Share-Alike und Namensnennung müssen bei Bedarf gesondert geprüft werden.

**MVP vs. M3:** Im M2-Prototyp werden diese Informationen **erfasst** und unklare Assets durch eigene Grafiken ersetzt. In M3 ergänzen wir systematisierte Lizenz- und Attributionsprüfung sowie eine formale Veröffentlichungssperre/-freigabe. Es erfolgt im MVP **kein automatischer YouTube-Upload**.

## Speicherung im Docker-Prototyp

Die Web-App, PostgreSQL und der M2-Worker laufen als getrennte **Docker-Compose-Services**. Mediendateien, Attributionsexporte und das Job-Medienmanifest liegen in einem **persistenten, nicht öffentlich freigegebenen Volume**; Metadaten und Zuordnungen liegen in PostgreSQL. Die Web-App gewährt Zugriff auf verwendete Medien und Begleitdaten erst nach Authentifizierung und Berechtigungsprüfung. Das Volume darf nicht als freier Webserver-Pfad offengelegt werden.

## Auswahl- und Fallback-Ablauf

1. **Szenenbedarf** aus dem Szenenplan bestimmen; der Club wird aus dem Job übernommen, **nicht hardcodiert**.
2. MediaProvider sucht potenzielle Kandidaten, beispielsweise in Wikimedia Commons. Er hält die echte Quellseite und dort verfügbare Metadaten fest.
3. Herkunft, Urheber, konkrete Lizenz und Einschränkungen werden **soweit tatsächlich feststellbar** dokumentiert; unbekannte Felder bleiben explizit `unknown`.
4. Nur **für die vorgesehene Nutzung hinreichend geklärte** Medien verwenden; erforderliche Attribution für Export/Begleitdaten erzeugen und erhalten.
5. Bei fehlendem Bild, widersprüchlichen Rechten, abgelehntem Einsatz oder API-Ausfall wird eine **eigene Karten-/Text-/Zeitleistenszene** aus belegten Vereinsdaten erzeugt.
6. Der Renderer speichert das konkrete Medienmanifest pro Jobversion. Ändert sich ein Asset oder dessen Nutzungsstatus, werden die davon abhängigen Render/QA-Artefakte invalidiert, **nicht** automatisch das Faktendossier und TTS.
7. Vor jeder **öffentlichen** Veröffentlichung muss die spätere formale Freigabe in M3 bestanden sein.

**Wichtig:** Auch eigene Ersatzgrafiken dürfen keine ungeklärten Fremdlogos, Clubwappen, Fotos oder Kartenelemente übernehmen. Für Karten verwendete Daten-/Kachelquellen müssen getrennt beachtet werden.

## Beispiel-Medienmanifest (rein fiktiv)

Alle Namen, URLs und Zustände sind **Dummydaten**, keine geprüften Rechte oder tatsächlich verfügbaren Dateien:

```json
{
  "job_id": "demo-job",
  "scene_id": "scene-03",
  "asset": {
    "id": "media-03",
    "source_url": "https://example.com/illustration",
    "original_file_url": "https://example.com/illustration.png",
    "source_platform": "other",
    "creator_name": "unknown",
    "license_identifier": "unknown",
    "rights_status": "unknown",
    "attribution_required": "unknown",
    "intended_use": "scene_background",
    "retrieved_at": "2026-11-10T12:00:00Z"
  },
  "selection_decision": "fallback_required",
  "fallback": {
    "type": "own_text_card",
    "uses_confirmed_facts_only": true
  }
}
```

**Erwartung:** Das Dummy-Asset wird **nicht** als erlaubtes Foto gerendert; der Renderer verwendet eine selbst erzeugte, inhaltlich belegte Textgrafik.

## Testfälle für M2/M3

- [ ] Jede verwendete externe Datei hat eine Originalquelle, Urheber-/Unbekannt-Vermerk, Lizenzstatus, Verwendungszweck und tatsächlichen Abrufzeitpunkt.
- [ ] Lizenzbedingungen und erforderliche Attribution sind, soweit ermittelt, im Manifest und Quellenexport nachvollziehbar.
- [ ] `unknown` / `restricted_or_disallowed` führt zu Ersatzgrafik oder blockiert den Einsatz; keine stille Freigabe.
- [ ] Ein bereits belegter Fakt darf ohne verfügbares Foto als eigene Text- oder Zeitleistenszene gerendert werden.
- [ ] Das Ersatzbild nutzt keine ungeklärten Fremdlogos.
- [ ] Geänderte Medienauswahl erzeugt einen neuen Render, ohne automatisch erneute Recherche/TTS auszulösen.
- [ ] Unerlaubter Zugriff auf interne Assets über eine öffentliche URL ist ausgeschlossen.
- [ ] **M3:** Formales Veröffentlichungsgate verweigert Freigabe für ungeprüftes/rechtlich ungeklärtes Material.

Die Tests sind hier **geplant, nicht ausgeführt**. Implementierungsissues: [#39–#40](https://github.com/whiteyOnTheMoon/FootballStudio/issues/39) (Medien), [#54–#55](https://github.com/whiteyOnTheMoon/FootballStudio/issues/54) (Lizenzprüfung/Freigabe).

## Definition of Done – M0-Dokument

- [x] URL, Urheber, Lizenzstatus, Attribution, Verwendungszweck und Review-Flags spezifiziert.
- [x] Ungeklärte Rechte und tatsächliche Publikationsfreigabe ausdrücklich voneinander getrennt.
- [x] Eigene Ersatzgrafiken statt ungeklärter Medien als Fallback festgelegt.
- [x] Quellenexport, Rechte- und Sicherheitshinweise, Beispielmanifest und technische Folgeprüfungen dokumentiert.
