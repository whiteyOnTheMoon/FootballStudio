# FS-004a – LLM-Anbieterbewertung und Kostenleitplanken

**Stand:** 10.11.2026 · **Status:** Recherche/technischer Vorschlag; **10 USD externes API-Monatsbudget durch Product Owner bestätigt**; Anbieter und Filmgrenze noch offen.  
**Issue:** [#8](https://github.com/whiteyOnTheMoon/FootballStudio/issues/8) · **Roadmap:** M0/FS-004 · **Architektur:** [ADR-0001](../architecture/ADR-0001-mvp-stack.md) und [Pipeline-Verträge](../architecture/pipeline-contracts.md).

## Kontext

Für FootballStudio brauchen wir eine preiswerte, belegorientierte LLM-Unterstützung für **drei Titelvorschläge**, **englisches Drehbuch**, ggf. **Szenenplanung** und kurze Überarbeitungsschleifen für einen **zur Laufzeit über Land → Liga → Verein ausgewählten Club**. Die KI darf **keine unbelegten Fakten erfinden**: Recherchequellen und Faktendossier werden von getrennten Modulen geliefert.

Der erste Film dauert 8–10 Minuten; nur Englisch im M2-MVP. Der gesamte Stack läuft in Docker Compose. Externe KI-Aufrufe erfolgen serverseitig im dafür vorgesehenen Web-/Worker-Kontext, nicht im Browser.

## Aktuelle Vergleichswerte – USD, Stand 10.11.2026

Alle Preise sind **öffentliche Anbieterangaben, keine ausgeführten API-Messungen**. Sie können sich ändern. In/Out = Preis je **1 Million Eingabe-/Ausgabetokens**, Standard-API ohne Batch-/Cache-/Rabattvorteile:

| Anbieter / Modell | Input | Output | Rechenbeispiel 100.000 Input + 20.000 Output | Einordnung |
| --- | ---: | ---: | ---: | --- |
| OpenAI `gpt-6-luna` | $0.10 | $0.50 | **$0.020** | **Preiswerter Ersttest-Kandidat**, an Qualitäts-Gates messen |
| Google `gemini-2.5-flash-lite` | $0.10 | $0.40 | **$0.018** | Kostengünstige Alternative, API-/Ausgabequalität noch testen |
| OpenAI `gpt-5.4-mini` | $0.75 | $4.50 | **$0.165** | Leistungsfähigere Alternative bei Qualitätsproblemen; teurer |
| Anthropic `claude-haiku-4-5` | $1.00 | $5.00 | **$0.200** | Vergleichsoption, nicht als MVP-Standard vorgeschlagen |

**Quellen (Anbieter, jeweils Preisangaben vom Abrufdatum):**
- OpenAI Luna: https://developers.openai.com/api/docs/models/gpt-6-luna
- OpenAI GPT-5.4 Mini: https://developers.openai.com/api/docs/models/gpt-5.4-mini
- Google Gemini API: https://ai.google.dev/gemini-api/docs/pricing
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing

**Rechenformel:** `(input_tokens / 1_000_000 × input_rate) + (output_tokens / 1_000_000 × output_rate)`. `100k/20k` ist ein **fiktives Volumenszenario pro Filmjob**, nicht gemessene Nutzung. Tatsächliche Skriptlänge, Wiederholungen, etwaige versteckte Denk-/Output-Tokens, Web-Suche/Tools, Providerzuschläge und Limits beeinflussen die Rechnung. TTS, Render, VPS, Daten und Bild-/Medienkosten sind **nicht** eingeschlossen.

### Beispiel mit Luna

- 100.000 Eingabetokens zu $0.10/1M → $0.010.
- 20.000 Ausgabetokens zu $0.50/1M → $0.010.
- **$0.020 LLM-Textgenerierung in diesem Beispiel**.
- Dieses Beispiel ist **keine Zusage** für realen Output, Qualität oder Kostendeckel.

## Technischer Vorschlag (noch keine kostenpflichtige Nutzung)

1. **Primärer Testkandidat**: OpenAI `gpt-6-luna` für Titel, Drehbuch, Szenen, vorbehaltlich tatsächlicher Qualität bei belegtem Testdossier.
2. **Alternativprovider**: Google `gemini-2.5-flash-lite` als Austausch-Kandidat. Wenn Sprachqualität / Faktentreue / Strukturausgabe schwach sind, einen stärkeren Modellkandidaten vergleichen, z. B. `gpt-5.4-mini`.
3. **Keine KI als Belegquelle**: Nur Fakten verwenden, die durch `Fact → Evidence → SourceReference` gestützt sind. Fehlende/widersprüchliche Fakten kennzeichnen und betroffene Aussagen auslassen.
4. **Drei Titelvorschläge** basieren möglichst auf einem vorhandenen Dossier und dürfen übersprungen werden, falls Nutzer manuell einen Titel eingibt.
5. Anbieter-/Modellwechsel ohne Codeänderung über Konfiguration, inklusive zentralem Token-/Kostenprotokoll.
6. Das **Monatsbudget von 10 USD** ist bestätigt. **Vor dem ersten kostenpflichtigen API-Aufruf** außerdem konkreten Provider freigeben und funktionsfähige Budgetkontrolle sowie sichere Anbieterabrechnung prüfen.

## API-/Datenschutz-Leitplanken

- Provider-Schlüssel ausschließlich über Secret-/Umgebungskonfiguration im Docker-Stack; nie in Git, Dashboard oder Logs ausgeben.
- **Nur benötigte, öffentliche, geprüfte Vereins-/Quelleninformationen** an externe LLMs senden; möglichst keine personenbezogenen Nutzer-/Sitzungsdaten.
- Quellen-URLs, Dossier-Version, Modellkennung, Prompt-Version, Tokenverbrauch, tatsächliche Kosten und Zeitpunkt je Call speichern – ohne API-Schlüssel oder unnötige personenbezogene Inhalte.
- OpenAI gibt an, API-Eingaben und -Ausgaben standardmäßig **nicht für Modelltraining** zu verwenden (außer Opt-in). Reguläre Abuse-Monitoring-Logs können bis zu 30 Tage gespeichert werden; endpoint-spezifische Speicherung ist getrennt zu prüfen. Quelle: https://developers.openai.com/api/docs/guides/your-data
- Bei Google Gemini unterscheiden sich freie und kostenpflichtige Tiers beim Datenverwendungs-Hinweis. Vor einem Produktionspilot prüfen, ob der gewählte Tarif für den geplanten Einsatzzweck geeignet ist. Quelle: https://ai.google.dev/gemini-api/docs/pricing
- Externe Quellen-/Suchdienste können eigene Preise, Quotas und Nutzungsbedingungen haben. Keine kostenpflichtige Suche stillschweigend aktivieren.

## Budgetschutz: **10 USD pro Monat genehmigt**, Filmgrenze offen

**Entscheidungsstand:** Die Monatsgrenze wurde am 10.11.2026 bestätigt. Eine eigene Filmgrenze und ein konkreter Anbieter sind noch nicht freigegeben. Details in [verbindlicher Budgetentscheidung](api-monthly-budget.md).

| Größe | Unverbindlicher M0-Vorschlag | Zweck |
| --- | ---: | --- |
| Maximale **externe KI-/TTS-API-Kosten pro vollständigem Filmjob** | **$0.50 – nur Vorschlag, nicht beschlossen** | Filmbezogene Grenze ist noch offen; nicht als aktive Vorgabe verwenden |
| Maximale **externe API-Kosten pro Kalendermonat** | **$10.00 – bestätigt** | Gemeinsames Budget über alle kostenpflichtigen externen APIs, nicht je Anbieter; neue Requests bei fehlender Reserve blockieren |
| Warnschwelle | **80 % des Monatsbudgets = $8.00** | Technische Voreinstellung; Dashboard-/Logwarnung, keine automatische Budgeterhöhung |
| Max. automatisch kostenwirksame Wiederholungen | **1** pro Schritt nach vorübergehendem Fehler | Endlosschleifen vermeiden; erneute Freigabe bei Mehrkosten |
| `DRY_RUN` / Fixture-Testmodus | **$0 externe API-Ausgaben** | UI/Jobs/Status/Fehler/Fallback ohne LLM/TTS-Kosten testen |

**Nicht enthalten:** VPS-/Internet-/Storage-/Rendering-Stromkosten sowie nicht ausdrücklich freigegebene feste Abogebühren. Kostenpflichtige externe Bild- und Such-APIs **zählen zur bestätigten 10-USD-Gesamtgrenze**, sofern solche Anbieter später ausdrücklich aktiviert werden. Die Grenze ist eine **geplante Anwendungskontrolle**, keine garantierte harte Anbieter-Rechnungsobergrenze; parallele Calls, Nachberechnung und Provider-Rundung können abweichen. Zusätzlich möglichst anbieterseitige Kostenwarnungen und Limits konfigurieren.

**Technische Regeln für Kostenkontrolle (M2-Umsetzung, noch nicht gebaut):**
- Vor jedem API-Call Budgetreserve anhand Schätzung und bestehenden Ausgaben verlangen (`fail closed`, wenn Budget nicht belastbar kalkulierbar).
- Maximale Tokens, Zeitouts, Request-/Retry-Zähler je Schritt begrenzen.
- Tatsächliche Token-/Audio-Nutzung und geschätzte wie bestätigte Kosten getrennt speichern, inkl. Währung und Preisversion.
- Bei Warnung aufhören oder bewusste Freigabe statt stillschweigende Eskalation; gescheiterte Schritte behalten alte erfolgreiche Artefakte.
- Pro Anbieter/Monat sowie Job aggregieren; Kostenlimits werden per Konfiguration und nicht durch fest codierte Werte vorgegeben.

## Qualitätstests vor der Modellwahl

Mit **demselben belegten Faktendossier** und identischen Akzeptanzkriterien mindestens zwei Kandidaten vergleichen:
- [ ] Drei Titelvorschläge; keine falschen oder nicht belegbaren Versprechen im Titel.
- [ ] Englisches Skript mit kohärentem Erzählbogen und Zielwortzahl für 8–10 Minuten.
- [ ] Zentrale Namen, Jahreszahlen, Rekorde und Ergebnisse gegen gespeicherte Quellen prüfen.
- [ ] Quellbindung: jede wesentliche Behauptung auf gespeicherten Fakt/Beleg verweisbar.
- [ ] Strukturierte Ausgaben syntaktisch gültig; Fehlfälle und Dossier mit schwacher Quellenlage testen.
- [ ] Tatsächlichen Tokenverbrauch, Fehler, Wiederholungen, Geschwindigkeit und Gebühren vergleichen.
- [ ] Keine Ausgabe eines unbelegten Vereinsfakts als sicher bei absichtlich unvollständigem Dossier.

**Bis APIs wirklich angebunden und getestet sind, ist kein Qualitätsvergleich bestanden.** Kandidat `gpt-6-luna` ist eine Planungshypothese, keine Qualitätsgarantie.

## Offene Entscheidungen / Definition of Done

- [x] Adapter- und Konfigurationspflicht sowie Quellenbindung dokumentiert.
- [x] Öffentliche Anbieterpreise samt Rechenbeispiel, Datenschutz- und Qualitätsrisiken verglichen.
- [x] **10 USD monatliches API-Gesamtbudget** durch Product Owner bestätigt und dokumentiert; Kosten-/Warn-/Dry-Run-Mechanik als Implementierungsplan festgehalten.
- [ ] **Product Owner bestätigt einen LLM-Kandidaten sowie ggf. eine separate Filmgrenze.** Das 10-USD-Monatsbudget ist bereits entschieden.
- [ ] Vor bezahlter Nutzung aktuellen Tarif, Zugangsberechtigung und tatsächlich anfallende Gebühren verifizieren.

**Folge-Issues:** TTS und Stimme [#9](https://github.com/whiteyOnTheMoon/FootballStudio/issues/9), Modelladapter [#34](https://github.com/whiteyOnTheMoon/FootballStudio/issues/34), Kostenlogging [#59](https://github.com/whiteyOnTheMoon/FootballStudio/issues/59).
