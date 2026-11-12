# FS-004b – TTS-Anbieter, Stimmtest und Kostenplan

**Stand:** 10.11.2026 · **Status:** Recherche und Kandidatenvorschlag, **kein Anbieter kostenpflichtig aktiviert**, **keine Stimme hörend getestet**, **10 USD monatliches API-Gesamtbudget freigegeben; TTS-Anbieter und separate Filmgrenze weiter offen**.  
**Issue:** [#9](https://github.com/whiteyOnTheMoon/FootballStudio/issues/9) · **Abhängigkeit:** [LLM-/Budgetvorschlag #8](llm-and-budget.md) · **Roadmap:** FS-004b / M0.

## Produktbedarf

FootballStudio erzeugt nach Auswahl eines **beliebigen Vereins über Land → Liga → Verein** eine **englische Erzählstimme** für 8–10 Minuten Video. Im M1-Docker-Prototyp kann ein kostenloser Fixture-/Stummtest den Jobfluss prüfen; ab M2 wird eine tatsächlich verständliche, durchgängig konsistente englische Sprecherstimme verlangt. TTS läuft im eigenen `worker`-Service und wird je Szene/Abschnitt als wiederverwendbare Audiodatei abgelegt.

## Drei Kandidaten und aktuelle Preisreferenzen

Preise in USD, **kein Testverbrauch**, Tarifstand 10.11.2026. Werden oft nach Textzeichen, Audio-/Texttokens oder in Creditpaketen berechnet; diese Werte sind **nicht** direkt ohne Annahmen vergleichbar.

| Kandidat | Öffentlicher Preis / Kostenmechanik | Eignung / Einschränkung |
| --- | --- | --- |
| **Google Gemini 3.8 Flash-Lite TTS** `gemini-3.8-flash-lite-tts` | Bis **31.12.2026** $0.50/1M Texttokens + $6/1M Audiotokens, ab **01.01.2027** $1/1M Texttokens + $12/1M Audiotokens (Standard Paid); Preisseite bezeichnet Angebot als Preview | **Vorschlag für den Ersttest**: günstige erzählte Szenen, Stimmenauswahl; Verfügbarkeit/Qualität und die Preisänderung beachten |
| **Google Cloud Neural2** (z. B. `en-US-Neural2-D`) | 1 Mio. Zeichen/Monat in ausgewiesener freier Stufe, danach **$16/1M Zeichen**, Abrechnung muss eingerichtet sein | Fallback innerhalb der Google-Cloud-TTS-Familie; Charakterkosten statt Audio-Token, Qualitätsvergleich nötig |
| **ElevenLabs** | Starter laut öffentlicher Preisseite **$6/Monat mit 30.000 Credits**; Credits je Modell/Zeichen unterschiedlich (oft 0.5–1 Credit/Zeichen) | Alternative für gewünschte Klangqualität, aber Abo-/Creditmodell und Nutzungsrechte vor Aktivierung prüfen |

**Anbieterquellen:**
- Google Cloud TTS-Preise: https://cloud.google.com/text-to-speech/pricing
- Gemini TTS-API, Modelle und Stimmen: https://ai.google.dev/gemini-api/docs/speech-generation
- Google Cloud Neural2-Sprachliste: https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types
- ElevenLabs-Preise: https://elevenlabs.io/pricing

**Hinweis:** Die aufgeführten Anbieter- und Modellnamen sind **nur Kandidaten**; ein späterer API-Test kann einen anderen Anbieter nötig machen.

## Beispiel: 10 Minuten Audio

Google listet für Gemini-TTS **25 Audio-Tokens pro Sekunde**. Daraus folgt bei 10 Minuten:
- `600 Sekunden × 25 = 15.000 Audio-Tokens`.
- Bis 31.12.2026 bei Flash-Lite `15.000 × $6 / 1.000.000 = $0.09` **reine Audioausgabe**.
- Ab 01.01.2027 bei `$12/1M` wären es **$0.18** reine Audioausgabe.
- **Text-Eingabetokens sind zusätzlich kostenpflichtig**, ebenso eventuelle Wiederholungen; gerundete finale Kosten hängen von tatsächlichen Token-Statistiken, Tarifen und Antwortlänge ab.
- Google Cloud Neural2: angenommen **9.000 Zeichen** → bei $16/1M wären das **$0.144** vor ggf. noch verfügbarer monatlicher freier Stufe, wenn die Abrechnung diese Nutzung so verbucht.
- ElevenLabs ist nicht als festes Filmpreisversprechen berechenbar, weil Plan, Verbrauch/Zeichen, Credits und Restkontingent variieren.

**Nicht enthalten:** LLM-Fakten-/Skript-Generierung, Medien, Suchtools, VPS, FFmpeg, Backups und eventuelle andere Google-Cloud-Ressourcen.

## Vorschlag für die erste englische Stimme

- **Primärkandidat:** Gemini 3.8 Flash-Lite TTS, **`Charon`** (von Google als *Informative* beschrieben): Passend als Testhypothese für sachlich erzählte Vereinsdokumentationen, **noch nicht gehört/abgenommen**.
- **Vergleichsstimme:** `Rasalgethi` (ebenfalls *Informative*) oder `Iapetus` (*Clear*). Im Test anhand derselben kurzen Passage vergleichen.
- **Fallback:** Google Cloud Neural2 `en-US-Neural2-D`; tatsächliche Klangqualität, Kontingente und Berechtigungen prüfen.
- **Nicht als neuer Kernadapter wählen:** OpenAI `gpt-4o-mini-tts` / `tts-1` / `tts-1-hd` sind laut aktueller API-Dokumentation zur Abschaltung am **06.01.2027** vorgesehen; eine Neuimplementierung direkt darauf wäre ein kurzfristiges Migrationsrisiko. Quelle: https://developers.openai.com/api/docs/guides/text-to-speech

**Wichtig:** Gesprochene Texte müssen **Originalskripte aus dem eigenen Projekt** sein. Keine fremden Stimmen imitieren oder Stimmen realer Personen ohne zulässige Zustimmung replizieren. Keine Sprecheraussage als menschliche Originalaufnahme ausgeben.

## Stimmtest-Plan (erst nach Providerfreigabe und aktivierter Kostenkontrolle)

1. **Kostenloser lokaler Fixture-Job**: Web-/Worker-/Status-/Dauer-Workflow mit vorher bereitgestelltem Test-Audio oder eindeutig als Demo markierter Platzhalterdatei prüfen – **nicht** als fertigen Film ausgeben.
2. **Kurze Probe (ca. 20–30 Sekunden)**: eigenes englisches Demo-Skript für Club-Geschichte und Namen, dieselbe Textpassage mit zwei Stimmen; Rückmeldungen zu Verständlichkeit, Aussprache, Tonalität, Tempo, Störgeräuschen.
3. **Mittellanger Test (60–90 Sekunden)**: segmentweise Synthese und Verkettung prüfen; Audio-Dauer messen, ein Fehler-/Retry-Szenario prüfen.
4. **Vollständiges Audio erst nach bestandenem Kurztest**: 8–10 Minuten erstellen, tatsächliche Länge und Kosten protokollieren; aus fertiger Audio-Dauer Szenen und Untertitel timen.
5. **Reproduzierbarkeit:** Audiodateien + Checksummen/Stimmen-ID, Modell, Prompt-/Skriptversion, Segment-Index, Dauer und Preis je API-Call speichern. Bei reinem Renderfehler keine neue TTS-Abrechnung auslösen.

Die M1-/M2-Testaufgaben für die Implementierung bleiben in [#41](https://github.com/whiteyOnTheMoon/FootballStudio/issues/41) (TTS), [#42](https://github.com/whiteyOnTheMoon/FootballStudio/issues/42) (Timing) und [#50](https://github.com/whiteyOnTheMoon/FootballStudio/issues/50) (End-to-End).

## Datenschutz, Nutzungsrechte und Betrieb

- **Nicht nur „technisch verfügbar“ heißt „kommerziell freigegeben“**. Vor späterer Veröffentlichung die zu diesem konkreten Tarif geltenden Nutzungsrechte der generierten Audiodateien prüfen und dokumentieren; Quelltext/Prompts dürfen keine ungeklärten fremden Texte enthalten.
- Gemini API-Freitier kann laut Preistabelle zur Produktverbesserung verwendete Daten umfassen, bezahlte Standardtier-Angaben unterscheiden sich davon. Bei Auswahl das aktive Tier und Datenschutzbestimmungen prüfen. Quelle: https://ai.google.dev/gemini-api/docs/pricing
- Schlüssel und Nutzungsdaten nie ins öffentliche GitHub-Repo, Video-URL oder Fehlerlogs. Secrets über Docker-Umgebungs-/Secret-Verwaltung; Ausgaben in privaten persistierten Volumes.
- Nutzer sollen später über KI-generierte Sprecherstimme informiert werden; keine Verwechslung mit Originalton von interviewten Personen.
- Grenzen für Voice-API-Aufrufe, Textsegmente, Rate-Limit, Timeouts und wiederholungsbedingte Mehrkosten werden erst in M2-Implementierung verbindlich erprobt.

## Vorgesehener technischer Adapter

`TTSProvider.synthesize(segments, voice_id, language_code, options)` → `AudioArtifact[]` und `usage`, `status`, `duration_seconds`, `provider_model`, `input_hash`.

`voice_id`, `provider_model`, `tts_provider` und `segment_size` bleiben per Konfiguration austauschbar; beim Providerwechsel wird nur betroffene Audio-/Captions-/Renderausgabe invalidiert, nicht das Faktendossier. Langer Text wird in robust wiederholbare Segmente geteilt (genaue API-Grenzen bei Implementierung verifizieren). Parallelrender mehrerer Videos bleibt außerhalb des MVP.

## Budget und Entscheidung – Monatsbudget genehmigt, Anbieter offen

**Am 10.11.2026 bestätigte der Product Owner 10 USD pro Monat** als gemeinsame Obergrenze für kostenpflichtige externe APIs. Die zuvor vorgeschlagenen **$0.50 pro Film sind nicht genehmigt**; auch der konkrete TTS-Anbieter und die Stimme sind noch nicht verbindlich gewählt. **80 % des Monatsbudgets ($8)** ist die technische Warnschwelle; Dry-Run bleibt kostenlos. Die Anwendungskontrolle ist keine garantierte Hard-Cap auf Anbieterrechnungen. Details: [Budgetentscheidung](api-monthly-budget.md).

- [x] Drei TTS-Kandidaten und öffentliche Kostengrundlagen verglichen.
- [x] Englischer Stimmentest-Kandidat `Charon` und Fallback benannt.
- [x] Testmodus mit kleinen Audio-Proben vor Vollrender spezifiziert.
- [x] Datenschutz-, Rechte-, API-Budget- und Docker-Leitplanken dokumentiert.
- [x] **10 USD monatliches Gesamtbudget** ausdrücklich freigegeben und dokumentiert.
- [ ] **Product Owner bestätigt später den konkreten TTS-Erstkandidaten** und gegebenenfalls ein separates Filmkostenlimit.
- [ ] Echte Stimme und kommerzielle Nutzungsrechte je ausgewähltem Vertrag geprüft, bevor extern veröffentlicht wird.
- [ ] Kurztest und tatsächlicher API-Verbrauch erst nach Freigabe und Implementierung ausgeführt.

**FS-004b / #9 bleibt wegen offener Anbieter-/Stimmwahl und ausstehender Nutzungsrechteprüfung offen.**


## Aktualisierung 13.11.2026 — Gemini als favorisierten Kandidaten prüfen

Der Product Owner hat **Gemini als bevorzugten TTS-Prüfkandidaten genannt**.
Dies ist **keine Freigabe** eines kostenpflichtigen API-Zugangs, einer Stimme,
eines Modells oder eines konkreten Tarifplans. Vorherige Anbieter-/Stimmwahl
bleibt nur ein Testvorschlag; Issue #9 bleibt offen.

**Aktuelle öffentliche Produktunterlagen (13.11.2026):** Google listet
Gemini 3.8 Flash-Lite TTS (`gemini-3.8-flash-lite-tts`) und Flash TTS als
spezialisierte Sprachmodelle; die Gemini-TTS-Dokumentation beschreibt
englische Single-Speaker-Ausgabe. Die Preisübersicht nennt für Flash-Lite
beim Paid-Standardtarif bis 31.12.2026 **$0.50/1M Texttokens und
$6/1M Audiotokens**, ab 01.01.2027 **$1/1M Texttokens und
$12/1M Audiotokens**. Dies sind veröffentlichte Tarife, **keine
verbindliche individuelle Kostenzusage**; Abrechnung, Rate-Limits,
Verfügbarkeit, Lizenzrechte und Voice-Qualität müssen vor einer konkreten
Providerfreigabe erneut geprüft werden.

Wichtig zur Nutzungsberechtigung: Die Gemini Developer API Additional Terms
(effective 23.03.2026) nennen ein **Mindestalter von 18 Jahren** und
untersagen die Bereitstellung über an Minderjährige gerichtete API-Clients.
Vor einer künftigen API-Anbindung muss ein berechtigter Verantwortlicher
die Nutzungsberechtigung und die jeweiligen Vertragsbedingungen prüfen.
**Keine Kontoerstellung, Schlüsselvergabe, Provideraktivierung oder
echter Testcall im Rahmen dieses Arbeitspakets.**

Quellen (Google, abgerufen am 13.11.2026):
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/speech-generation
- https://ai.google.dev/gemini-api/terms

**Implementierungsschritt #41:** Neuer rein lokaler
`app.production.tts_offline`-Vertrag mit injizierbarem, vertrauenswürdigem
Testbackend und atomar gespeicherter, als `demo_only` gekennzeichneter
PCM-WAV-Datei pro Segment. Er verlangt 24-kHz, Mono, 16-Bit-Audio,
prüft Eingabewerte/Dateigröße/Audiodauer, berechnet Prüfsummen
und berührt **weder** Netzwerke **noch** bezahlte Provider/Budgetreservierungen.
Die Daten sind **Demo-Artefakte ohne echte Sprache**. 
Eine reale TTS-Implementierung, Längen-Synchronisierung und
Providerkosten-Abrechnung bleiben offene Folgearbeiten.
