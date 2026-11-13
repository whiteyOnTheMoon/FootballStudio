# FS-016c / #38 – Offline-Szenenplan mit Quellenbindung

**Teilumsetzung:** Eine deterministische reine Funktion erzeugt aus dem
bestehenden, vom berechtigten Job-Eigentümer geladenen
FS-016a-Drehbuchentwurf eine chronologisch geordnete Szenenliste.
Noch **kein** vollständig produzierbarer Szenenplan, kein Worker und
keine Medien-/TTS-API. Persistente PostgreSQL-Snapshots sind inzwischen
als separater, bewusst kleiner Schritt hinzugekommen (siehe unten).

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

**Offen innerhalb #38:** echte Medienbedarfe je Szene, Zusammenführung
mit Medien-/Renderpipeline und End-to-End-Abnahme. Das vorhandene
$10-API-Monatsbudget und alle Default-OFF-Schalter bleiben
unverändert.


### Ergänzung 13.11.2026 – PostgreSQL-Snapshots (Migration 0011)

Der neue additive `ScenePlanSnapshot` speichert einen kleinen
JSON-Szenenplan direkt in der bereits persistenten PostgreSQL-Datenbank.
Damit gehen Daten beim Austausch des Web-Containers nicht verloren.
Eine unveränderliche Zuordnung `(job, dossier_version, words_per_minute)`
mit Unique-Constraint erlaubt parallele, klar getrennte Varianten:
neuer Dossierstand oder geänderte Sprechgeschwindigkeit → anderes Artefakt.
Es werden **keine** großen Audio-/Video-Dateien in der Datenbank abgelegt.

`app.production.scene_snapshots.save_scene_plan_snapshot(owner=..., job_id=..., dossier_version=..., words_per_minute=145)`
lädt über den bestehenden owner-scoped Django-Pfad den aktuellen
faktengeprüften Drehbuchentwurf, baut die Szenen mit
`build_scene_plan()` und legt unter Job-Row-Lock höchstens einmal
eine unveränderliche Version ab. Ein identischer erneuter Aufruf
liefert denselben DB-Datensatz; eine Abweichung bei gleichbleibender
Dossierversion und WPM wird mit `stale_scene_snapshot`
**abgelehnt**, nicht überschrieben. Für eine inhaltliche neue Version
ist ein neuer Dossierstand erforderlich.

`load_scene_plan_snapshot(owner=..., job_id=..., dossier_version=..., words_per_minute=145)`
verlangt dieselbe Besitzerprüfung, verifiziert die gespeicherten
Metadaten und den SHA-256-Fingerprint und vergleicht den Snapshot
erneut mit der **aktuellen geprüften** Eingabe. Es gibt keine
öffentliche Download-Route oder fremde Job-ID-Abfrage. Ein geänderter
Titel oder überarbeiteter Fakt bei derselben Dossierversion wird
nicht still als aktueller Plan ausgegeben. Fingerprints dienen
**nur** der Konsistenz, nicht der Authentisierung fremder Daten.
Maximale JSON-Nutzlast: 512 KiB.

Der gespeicherte Plan behält `ready_for_tts=False`,
`ready_for_render=False`, `rights_cleared=False`.
Die echten Medienrechte, die Audio-Länge und eine fachliche
Redaktionsfreigabe müssen später separat erfolgen.

Tests: `python manage.py test app.production.test_scene_snapshots`

**VPS-Deployment mit neuer Migration:** Zuerst PostgreSQL-Backup
erstellen und in einer Wegwerf-Datenbank verifiziert restaurieren,
dann Pull/Compose-Build und `showmigrations production`,
`migrate --noinput`, `check`, `show_paid_api_budget`,
Containerstatus und HTTPS-Healthcheck prüfen.
Die auf dem VPS bestehende gemeinsame Paid-API-Monatsgrenze
steht derzeit auf `UNCONFIGURED`; bezahlte Aufrufe bleiben
durch `PAID_API_CALLS_ENABLED=0` vollständig gesperrt.
