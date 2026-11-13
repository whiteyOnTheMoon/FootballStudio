# FS-016a / #36 – Quellengebundener Offline-Drehbuchentwurf

**Status:** implementierter, rein lokaler Review-Entwurf. **Kein**
vollständiges 8–10-Minuten-Drehbuch, keine KI, kein Render, kein TTS und
keine externen API-Aufrufe. Die vollständigen Meilensteine FS-016b/c
(Länge/Szenen) und ein veröffentlichungsfähiger Film bleiben offen.

## Datenfluss

`load_job_script_draft(owner, job_id, version)` prüft die Rechte an der
konkreten ProductionJob-Instanz, verlangt `language=en`, lädt genau die
angeforderte Version des zugehörigen Faktendossiers über
`load_fact_dossier` und erstellt einen JSON-serialisierbaren Entwurf.
Ohne menschlich überprüfte, belegte Fakten erfolgt **kein** Aufbau
eines Drehbuchs.

`build_script_draft(snapshot, club_name, selected_title)` ist eine
deterministische Pure Function ohne Datenbank- oder Netzzugriff und baut
auf `prepare_script_preview` auf. Deren strenge Sicherheitsregeln
entscheiden, ob ein strukturierter Sachverhalt tatsächlich verwendbar
ist: geprüfte Reviewentscheidung, zugängliche Quelle, konkrete
Evidenzverknüpfung, passende Jahre/Saisons, keine Widersprüche und
kein ungeprüfter Freitext.

Das Ergebnis enthält die drei geordneten Abschnitte
`opening`, `main`, `closing`, einen zusammengefügten
`voiceover_text`, je Sachsegment `fact_id` und
`evidence_refs` mit URL/Source-ID, sowie separate rein strukturelle
`unresolved`- und `excluded`-Einträge mit Fehlercodes.
Unbelegte Jahreszahlen, Webseitentexte, Quellen-Summaries,
Reviewnotizen, Nutzer-Schätzungen und ungeprüfte Behauptungen
werden **niemals** in Sprechertext übernommen. Einstieg und Schluss
sind feste, faktenneutrale englische Formulierungen. Der manuelle
Titel wird nur als `selected_title_for_review` dokumentiert,
nicht ungeprüft vorgelesen.

`input_fingerprint_sha256` ist ein stabiler SHA-256-Fingerabdruck
des gesamten strukturierten Ausgabestandards inklusive Titel,
Version, Quellen-URLs und Segmente und kann später zur selektiven
Invalidierung verwendet werden. Die Implementierung persistiert
**keine** neue Artefaktdatei und fügt keine öffentliche Route hinzu.
Sie markiert jeden Entwurf mit
`editorial_review_required=True` und `ready_for_tts=False`.

## Tests

`python manage.py test app.production.test_script_draft`

Offline-Regressionen prüfen Erzählstruktur, Quellenlinks,
unveränderten Fingerabdruck, Titelfingerabdruck, verweigerte
Null-Fakten-Dossiers, unbestätigte/strittige/abgelehnte Fakten,
Prompt-Injections in Review- und Quellenfeldern, mehrfach vergebene
Fact-IDs, Owner-Isolation und selektive Dossierversion.
CI prüft zusätzlich PostgreSQL/Docker Compose, den Offline-Katalog
und Cloudflare-Konfiguration.

## Noch offen

- Längenplanung 8–10 Minuten inklusive Wortzahl-/Timing-Guard: #37.
- Szenenplanung mit Medienbedarf und Quellenbindungen: #38.
- Gespeicherte Artefaktversionen/Worker-Lebenszyklus und Redaktions-UI.
- Menschliche inhaltliche Qualitätsprüfung und erst danach TTS.
- Echte generative KI erfordert gesonderte Anbieter-/Budgetfreigabe.
