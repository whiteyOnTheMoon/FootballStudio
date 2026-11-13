# FS-016c / #38 – Offline-Szenenplan mit Quellenbindung

**Teilumsetzung:** Eine deterministische reine Funktion erzeugt aus dem
bestehenden, vom berechtigten Job-Eigentümer geladenen
FS-016a-Drehbuchentwurf eine chronologisch geordnete Szenenliste.
Noch **kein** vollständig produzierbarer Szenenplan, keine gespeicherte
Datenbank- oder Dateiversion, kein Worker und keine Medien-/TTS-API.

`app.production.scene_plan.build_scene_plan(draft, words_per_minute=145)`
verwendet den bestehenden FS-016b-Längenplaner einschließlich
Schema-, Status-, Narrations- und Fingerprint-Prüfungen. Der Draft
muss über den owner-scoped Backendpfad entstanden sein; sein
SHA-256-Fingerprint beweist nur Konsistenz, **nicht** Autorisierung,
Korrektheit oder Freigabe für die Veröffentlichung.

Jeder Sprecherabschnitt wird genau eine Szene mit fortlaufender
`scene_number`, unverändertem englischen `narration`,
`segment_id`, `section` (opening/main/closing), `fact_id`
und `evidence_refs` für geprüfte Quellen. Opening/Closing
enthalten keine Tatsachenbehauptungen und entsprechend keine
Fakten-/Quellen-IDs. Die Liste `unresolved_fact_ids` enthält
unbestätigte, im Sprechertext ausgesparte Sachverhalte zur
späteren redaktionellen Prüfung.

### Zeitplanung

Der Plan verwendet die gleiche konfigurierbare
Sprechgeschwindigkeit wie FS-016b (Standard 145 WPM,
zulässig 100–200). Die kumulative Gesamtwortzahl wird in
Millisekunden umgerechnet und **erst je kumulativem
Endzeitpunkt** gerundet; aufeinanderfolgende Szenen
haben dadurch keine rechnerischen Lücken/Überlappungen.
Diese Werte heißen absichtlich `start_ms_estimate`,
`end_ms_estimate`, `duration_ms_estimate`.
Tatsächliche Szenendauern sind nach echtem TTS-Audio
neu zu vermessen (FS-018b/#42); der Plan darf nicht
als exakte Untertitel-Timeline verwendet werden.

### Medienbedarf und Rechte

Die `visual`-Metadaten sind für jede Szene ausdrücklich
**nur ein Original-Textkarten-Platzhalter**:
`kind=original_text_card_placeholder`,
`external_media_selected=False`, `rights_cleared=False`,
`requires_editorial_review=True`. Es werden keine Fotos,
Videos oder Websites abgerufen. Für Bilder müssen später
Urheber, Lizenz und Nutzungszweck separat überprüft werden.
Kein Platzhalter ist ein angeblich rechtlich freigegebenes Medium.

Die gesamte Ausgabe trägt
`editorial_review_required=True`,
`ready_for_tts=False`, `ready_for_render=False` und
einen reproduzierbaren `plan_fingerprint_sha256`
einschließlich der Quellen, geschätzten Zeiten und Stimmrate.
Auch ein Drehbuch unter acht Minuten kann für die Redaktion
visualisiert werden – es ist **nie** als render- oder
TTS-fähig freigegeben.

### Tests

`python manage.py test app.production.test_scene_plan`

Geprüft werden Szenenreihenfolge und Zeitkontinuität,
exakte Weitergabe der Quellenlinks, Anpassung der Schätzzeiten
an WPM, fehlende Medienfreigabe, kurze Skripte, kaputte
Fingerprint-/Dossierdaten, manipulierte Segment-IDs und
vollständig fehlende externe Netzwerkanfragen.

**Offen innerhalb #38:** Persistierte versionierte Szenenpläne
und erneutes Laden, echte Medienbedarfe je Szene, Zusammenführung
mit Medien-/Renderpipeline und End-to-End-Abnahme. Das vorhandene
$10-API-Monatsbudget und alle Default-OFF-Schalter bleiben
unverändert.
