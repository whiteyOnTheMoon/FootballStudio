# M0-Entscheidung – Monatliches Budget für externe APIs

**Datum der Produktentscheidung:** 10.11.2026  
**Entscheidung:** Product Owner bestätigt **10,00 USD je Kalendermonat** als Obergrenze für kostenpflichtige externe API-Ausgaben von FootballStudio.  
**Status:** **Budgetentscheidung bestätigt; Kostenkontrollen noch nicht implementiert.**  
**Betroffene Issues:** [#8 – LLM/Kosten](https://github.com/whiteyOnTheMoon/FootballStudio/issues/8), [#9 – TTS](https://github.com/whiteyOnTheMoon/FootballStudio/issues/9).  
**Kontext:** [LLM-Vergleich](llm-and-budget.md), [TTS-Vergleich](tts-and-voice.md), [MVP-Spezifikation](../mvp/acceptance-criteria.md).

## Geltungsbereich

Der **genehmigte Gesamtbetrag von 10,00 USD pro Monat** gilt als **gemeinsames Ausgabenbudget** für alle künftig aktivierten *kostenpflichtigen externen APIs* des FootballStudio-Prototyps. Dazu zählen insbesondere LLM (Rechercheaufbereitung, Titel, Skript), TTS (Sprecherstimme) und ggf. kostenpflichtige externe Suche oder Medien-APIs. Das Budget gilt **nicht je Anbieter**, sondern insgesamt.

Das Budget enthält **nicht** vorhandene VPS-/Hosting-Kosten, Datenspeicher, Internet/Traffic, Docker/FFmpeg-Rechenzeit oder sonstige laufende Infrastrukturkosten. Neue Abos mit fixen Grundgebühren sind **nicht automatisch freigegeben**; solche Verträge müssen vorher gesondert geprüft und entschieden werden.

**Nicht bestätigt:**
- Der zuvor vorgeschlagene Grenzwert von **0,50 USD pro Film** ist **noch kein genehmigtes Limit** und bleibt ein Beispiel.
- **Kein** spezifischer LLM-Anbieter, kein TTS-Anbieter und keine Stimme ist durch diese Budgetzusage endgültig ausgewählt.
- Diese Entscheidung allein beauftragt **keine** externe Abrechnung, API-Schlüssel-Hinterlegung oder kostenpflichtigen Testlauf.

## Technische Regeln für die spätere Umsetzung

1. **Konfigurierbare Monatsgrenze:** `API_MONTHLY_BUDGET_USD=10.00`. Wenn Budget- oder Preiskonfiguration fehlt, sind bezahlte Aufrufe standardmäßig **deaktiviert**.
2. **Ein gemeinsamer Zähler:** Jeder Provideraufruf mit möglicher Belastung zählt für dasselbe globale Monatsbudget; bereits feststehende Beträge sowie geschätzte, noch offene Reservierungen werden berücksichtigt.
3. **Vor jedem kostenpflichtigen Request:** Kostenobergrenze des konkreten Aufrufs konservativ schätzen und Budget **transaktionssicher reservieren**. Falls die neue Schätzung den verbleibenden Betrag überschreitet, **nicht** senden, sondern den Job mit einer klaren Kostenmeldung blockieren/pausieren.
4. **Nach dem Request:** Tatsächliche Gebühren anhand Provider-Nutzungsdaten verbuchen; Schätzung und tatsächliche Kosten (USD), Tarif-/Modellversion, Zeit, Job und Anbieter nachvollziehbar speichern. Wenn ein Provider keine verlässliche Nutzung zurückliefert, die vorsichtige Reservierung nicht automatisch als `0` freigeben.
5. **Warnung bei 80 % = 8,00 USD** als technische Voreinstellung; keine automatische Erhöhung nach Warnung.
6. **Monatliche Periode:** Für die Implementierung einheitlich UTC-Kalendermonate verwenden und die Zeitzone in der Oberfläche nennen; abweichende Provider-Abrechnungsperioden separat beobachten. Eine neue Periode löscht **keine** alten Kostenprotokolle.
7. **Wiederholungen:** Jeder neue kostenpflichtige API-Request benötigt eine **neue** Budgetprüfung. Bei Render-Retry gespeicherte Recherche/TTS-Artefakte wiederverwenden.
8. **DRY_RUN / Fallback:** UI, Jobstatus und Fehlertests müssen ohne bezahlten Provider mittels Fixtures oder ausdrücklich als Demo markierten Testdaten möglich sein.
9. **Keine Geheimnisse:** API-Schlüssel nur über gesicherte Konfiguration im Docker-Stack, nicht in GitHub, PRs oder Logs. Der Budgetzähler liegt in PostgreSQL, keine bloße Prozessspeicher-Variable in Web/Worker.
10. **Mehr Anbieter und parallele Requests:** Reservierung mit DB-Transaktion/Locking, damit zwei Worker/Calls nicht beide denselben Restbetrag verbrauchen. Konservative Obergrenzen für unvollständige/providerverzögerte Kostenmeldungen.

## Grenzen der technischen Garantie

**Die 10 USD sind eine Produkt-/Betriebsgrenze, keine durch uns garantierbare harte Obergrenze auf der Rechnung eines Drittanbieters.** Preise können sich ändern; asynchron abgerechnete Requests, Provider-Rundungen, separate Dienste, Accountgebühren und Messunterschiede können abweichen. Wenn möglich zusätzlich beim Provider **Billing-Alerts/Quotas oder harte Provider-Limits** einstellen und Guthaben bzw. Prepaid-Modelle nutzen. Auch Provider-Limits sind je nach Anbieter nicht immer sofort wirksam.

**Für die erste Entwicklung** bleiben alle bezahlten Aufrufe bis zur konkreten Provider-/Testfreigabe deaktiviert. Wir implementieren und testen zunächst die Kostenlogik gegen Test-Fixtures.

## Noch offene Entscheidungen

| Thema | Stand |
| --- | --- |
| Monatliches Gesamtbudget für externe APIs | **10,00 USD – bestätigt** |
| Betrag je Film / separate Filmgrenze | **Offen**, zuvor vorgeschlagene 0,50 USD nicht genehmigt |
| LLM-Anbieter, Modell und Qualitätstest | **Offen**, Dokumentation in #8 |
| TTS-Anbieter, englische Stimme und Hörtest | **Offen**, Dokumentation in #9 |
| Abos mit monatlicher Grundgebühr | **Nicht freigegeben** |
| Zusätzliche VPS-/Hosting-Kosten | **Nicht Teil dieser Freigabe** |

## Definition of Done – Dokumentation

- [x] Zustimmung zu 10 USD monatlich eindeutig und begrenzt erfasst.
- [x] Pro-Film-Limit ausdrücklich von freigegebenem Monatsbudget getrennt.
- [x] Warnschwelle und vorläufiger technischer Schutzmechanismus spezifiziert.
- [x] Keine unberechtigte API-Nutzung/Providerwahl behauptet.
- [ ] Budgetprüfung und Tests im MVP-Code **tatsächlich implementieren**, bevor irgendein bezahlter Call möglich wird.
