# FS-016b.1 / #115 – Offline-Wortzahl und Längenprüfung

**Ziel:** Verbindliche Berechnungslogik für 8–10 Minuten englisches
Sprecher-Audio, ohne TTS, LLM oder kostenpflichtige APIs. Teilvorarbeit
für [#37](https://github.com/whiteyOnTheMoon/FootballStudio/issues/37).
Die tatsächliche TTS-/Worker-Einbindung in #37 bleibt offen.

## Reine Funktionen

`app.production.script_length.plan_spoken_text(text, words_per_minute=145)`
liefert Wortzahl, angenommene Dauer, konfigurierbares Sprechtempo,
Zielwortzahl und die 8–10-Minuten-Grenzen. Standard ist
**145 Wörter/Minute**; erlaubt sind ganze Zahlen von **100 bis 200**
Wörtern/Minute. Bool, Fließkomma, fehlende Werte und unsinnige Raten
werden mit sicheren Fehlercodes abgewiesen.

Bei der Standardeinstellung sind die Grenzen
**1.160–1.450 gesprochene Wörter**; Zielmitte ist
**1.305 Wörter** (9 Minuten). Die Dauer ist eine **Schätzung**
ohne Sprechpausen, emotionale Betonung oder Modellunterschiede;
erst das tatsächliche TTS-Audio gibt die Laufzeit sicher an.
Die Entscheidung wird **vor der Rundung** der angezeigten
Schätzung anhand ganzzahliger Wortgrenzen getroffen.

`plan_script_draft_length(draft, words_per_minute=145)`
prüft den internen FS-016a-Draft, das englische Schema,
den redaktionellen Prüfstatus, die drei Erzählabschnitte,
die Übereinstimmung von Segmenten und durchgehendem
Voiceover-Text und den vorhandenen SHA-256-Fingerprint
auf Konsistenz. Der Fingerprint ist **keine Authentisierung**;
der Draft muss weiterhin aus vertrauenswürdigem,
zuvor owner-scoped geladenem Code stammen.
Eine Veränderung an Text oder Quellenverweisen nach
dem Erstellen macht den alten Fingerprint ungültig.
Er liefert außerdem Wortzahlen je Abschnitt.

`require_script_length_before_tts(draft, ...)` ist die
künftige interne Guard-Schnittstelle: bei `too_short` oder
`too_long` wird **fail-closed** abgebrochen. Das Bestehen
der Längenprüfung ist **keine** eigenständige Freigabe für TTS:
`ready_for_tts=False` bleibt selbst bei erreichter Zielwortzahl
bestehen, da Faktenprüfung, redaktionelle Freigabe, Provider-
Nutzungsberechtigung und das gemeinsame API-Budget gesondert
geprüft werden müssen.

## Redaktionshinweise

- `too_short`: `add_source_reviewed_content` + genaue
  Mindestzahl fehlender Wörter. **Keine** automatische
  Ausschmückung, falsche Behauptung oder Blindauffüllung.
  Neue Fakten brauchen Quellen und menschliche Prüfung.
- `within_target`: `editorial_review` erforderlich; die
  geschätzte Wortzahl allein macht den Film nicht fertig.
- `too_long`: `edit_down_preserving_evidence` +
  Zahl der zu entfernenden Wörter. Quellbindung bewahren.

Unicode-Vereinsnamen und zusammengesetzte englische Wörter
werden vom dokumentierten, deterministischen Wort-Tokenizer
unterstützt. Saisonbezeichnungen wie `2025/26` zählen als
zwei Wort-Tokens. Reale Sprechdauer muss später
in [FS-018b / #42](https://github.com/whiteyOnTheMoon/FootballStudio/issues/42)
gemessen werden.

## Offline-Abnahme

`python manage.py test app.production.test_script_length`

Tests decken Wortgrenzen inkl. ±1 Wort, WPM-Variation,
nicht-ganzzahlige/ungültige Sprechgeschwindigkeit,
Unicode und Saisons, invalide/zu lange Texte,
stabile Resultate, bestehende FS-016a-Drafts, manipulierte
oder überholte Fingerprints, explizite Vor-TTS-Sperre
und fehlende Netzwerkzugriffe ab.

**Kein** neues Datenbankschema, API-Key, SDK, Provider-Aufruf,
Audiofile, UI-Änderung oder Worker. Production-Paid-APIs
bleiben deaktiviert.
