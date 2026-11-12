# M0-Entscheidung – Monatliches Budget für externe APIs

**Datum der Produktentscheidung:** 10.11.2026  
**Entscheidung:** Product Owner bestätigt **10,00 USD je Kalendermonat** als Obergrenze für kostenpflichtige externe API-Ausgaben von FootballStudio.  
**Status:** **Budgetentscheidung bestätigt; P0-Kostenwächter in PR zu #90 implementiert, standardmäßig alle Paid-Calls deaktiviert.**  
**Betroffene Issues:** [#8 – LLM/Kosten](https://github.com/whiteyOnTheMoon/FootballStudio/issues/8), [#9 – TTS](https://github.com/whiteyOnTheMoon/FootballStudio/issues/9), [#90 – verbindlicher API-Kostenwächter vor Paid-Calls](https://github.com/whiteyOnTheMoon/FootballStudio/issues/90).  
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
- [x] Budgetprüfung und Tests im MVP-Code **implementiert**; noch keine Anbieteranbindung und keine echten kostenpflichtigen API-Aufrufe.


## P0 – Transaktionssicherer gemeinsamer Budgetwächter (#90, 12.11.2026)

**Implementation:** im Django-Service
app/production/paid_api_budget.py; additive Migration
production.0010_paid_api_shared_budget.py. Ein dauerhaftes
SharedPaidApiBudgetLock-Singleton (pk=1, in der Migration angelegt) wird
bei JEDEM schreibenden Budgetvorgang per PostgreSQL SELECT FOR UPDATE
innerhalb transaction.atomic() gesperrt. Damit konkurrieren mehrere
Jobs, Worker, Anbieter und API-Typen um denselben eindeutigen
Monatsbetrag. Eine fehlende Lock-Zeile wird NICHT während eines Requests
angelegt, sondern sperrt die Ausgabe. Die Buchungshistorie wird nicht
bei Monatswechsel oder Job-Retry gelöscht.

Das Modell PaidApiCharge hält pro **neuem** UUIDv4-Request genau eine
unter einem Job gespeicherte, globale USD-Reservierung. Persistiert
werden Anbieter-ID, Typ (LLM/TTS/Recherche/Medien), Modell, Tarifschlüssel
und -revision, Abrechnungseinheit, pessimistisch geplante maximale
Einheiten, in USD aufgerundeter Preis je Einheit, Reservierung,
Monatsstart UTC, Beginn des Versandversuchs und bei zuverlässiger
Provider-Rückmeldung die tatsächlichen Kosten. KEINE API-Schlüssel,
Prompttexte, TTS-Inhalte, Access-Tokens oder Rohantworten werden geloggt.

### Strikte Default-off-Konfiguration

Das reguläre Webcontainer-Compose überträgt die drei möglichen
Betreiberkonfigurationen:

- PAID_API_CALLS_ENABLED=0 (Standard, kein kostenpflichtiger Aufruf)
- API_MONTHLY_BUDGET_USD=10.00 (nur bei **expliziter** Aktivierung;
  ein fehlender/ungültiger Wert sperrt, ein größerer Wert als 10.00 USD
  wird ohne neue Product-Owner-Entscheidung ausdrücklich ABGELEHNT)
- PAID_API_RATE_CARDS_JSON (standardmäßig leer; vollständige,
  vertrauenswürdige Tarifkarten müssen zuvor gesondert mit echten,
  geprüften Anbieterpreisen und Tarifrevision durch Betreiber
  konfiguriert werden)

Eine Rate Card enthält einen stabilen Schlüssel sowie provider,
purpose, model, price_version, unit_name, usd_per_unit_upper_bound und
credential_env. Die letzte Eigenschaft ist AUSSCHLIESSLICH der
ENV-VARIABLENNAME für einen ggf. zukünftigen Anbieter-Key, niemals
dessen Wert. Ein fehlendes Secret sperrt die Reservierung und deren
Versand; echte Provider-Berechtigungen und Verträge müssen zuvor
gesondert bestätigt sein.

**Für die aktuelle Produktion gilt: Weiterhin PAID_API_CALLS_ENABLED=0,
API_MONTHLY_BUDGET_USD leer, keine Rate Cards und keine Provider-Keys.**
Das ist nicht als Unvollständigkeit eines Sicherheitschecks zu werten,
sondern verhindert bewusst jegliche versehentliche Rechnungsstellung.
Ein Produkt-/Anbieteradapter muss später zusätzlich gesondert
implementiert und überprüft werden; ein bloßes Aktivieren der ENV
verschickt KEINE Anfrage.

### Pflichtablauf für jeden zukünftigen, autorisierten Paid-Adapter

1. **Konservativ schätzen:** trusted rate_key aus der freigegebenen
   Preistabelle und max_units als obere Grenze für die gesamte
   jeweilige Anfrage (max. Prompt + Ausgabe-Token, Zeichen, Bilder
   etc.) bestimmen. Der Dienst lehnt ungültige/fehlende
   Preise, Modelle, Secret, Owner, Budget und Nullpreise ab.
2. **Vor dem externen Request atomar reservieren:**
   reserve_paid_api_budget(owner_id, job_id, rate_key,
   max_units, request_key=uuid4()). Die Methode prüft die globale
   USD-Gesamtsumme unter DB-Lock inklusive ALLER offenen oder
   unklaren Reservierungen. Bei Überschreitung -> budget_exhausted,
   kein Provider-Call. Der Rückgabewert enthält den aktualisierten
   Monatswert und warning_80_percent (ab 8.00 USD bei Limit 10).
3. **Direkt vor Netzversand einmalig beginnen:**
   mark_paid_api_dispatch_started(...). Unter demselben Lock
   werden Betreiber-Freigabe, Preisstand, Credential-Verfügbarkeit,
   aktueller UTC-Monat und Limit nochmals geprüft. Dieser
   irreversible Marker verhindert einen zweiten Versand mit
   derselben Reservierung und verhindert spätere Freigabe unter
   dem Vorwand, nichts gesendet zu haben. Bei Fehler -> NICHT
   anrufen; vor dem Versand ggf. bewusst freigeben.
4. **Nach erfolgreichem oder unklarem Request verbuchen:**
   reconcile_paid_api_budget(..., actual_usd="...") nur bei
   verlässlicher Anbieter-Nutzungs-/Preisangabe. Bei Timeout,
   Netzfehler, 429, ungeklärten oder asynchronen Rechnungen
   actual_usd=None übergeben: der konservative Betrag bleibt
   unbefristet als uncertain im Ledger. Keine automatische
   Rückgabe als Null und keine automatische Reaktivierung.
   Übersteigt die echte Providergebühr die Reservierung, wird
   die volle tatsächliche Schuld gezählt, und weitere Aufträge
   werden nach Budgetprüfung gesperrt.
5. **Nur wenn nachweislich NICHT gesendet:**
   release_unspent_paid_api_budget(...,
   verified_no_dispatch=True) ist ausschließlich möglich,
   solange noch KEIN dispatch_started_at existiert und der
   Zustand reserved ist. Eine nachweislich unnötige Reservierung
   wird als released auditiert, der einmalige UUID-Key kann nicht
   für einen neuen bezahlten Versuch wiederverwendet werden.
6. **Retry:** Gespeichertes Produktartefakt zuerst suchen;
   andernfalls vor JEDEM neuen kostenpflichtigen Request
   neuen UUIDv4-Key und neue Kosten-/Tarifprüfung verlangen.
   Ein Replay derselben UUID ist ausdrücklich verboten.

### Betrieb / Kostenübersicht

Nur in der Shell des Containers, niemals über eine public HTTP-Route:

    python manage.py show_paid_api_budget

Zeigt aktuellen UTC-Monat, Config-Status, gemeinsames Cap,
gebuchten/konservativ reservierten Betrag, Restbudget,
offene/unklare Positionen und eine Warnung bei >=80 %.
Keine Providerkontakte, kein Schlüssel und keine Job-/Nutzerdetails.
Bei nicht aktiviertem Paid-Modus: DISABLED, UNCONFIGURED, 0 USD.

Offline-CI verwendet **nur künstliche Tarife/Secrets**. Getestet
werden Nullbudget, unkonfiguriertes Pricing, ab 7.99 / genau 8.00 USD,
9.99 + größere neue Reservierung, parallele PostgreSQL-Requests
unter demselben Lock, Anbieter- und Jobübergreifung, UTC-Monatswechsel,
Replay, Fehler ohne verlässliche Gebühren, überteuerte Rückmeldung
und irreversible Dispatch-Freigabe. Kein Provider wird kontaktiert.
Die neue Migration 0010 darf erst nach produktivem PostgreSQL-Backup
UND verifiziertem isolierten Restore auf den VPS.

**Zusätzliche Drittanbieter-Sicherheit:** Im jeweiligen Anbieterportal
Billing-Alerts/Account-Quotas/Prepaid setzen, sofern angeboten,
und die Tarif-/Modellpreise vor Freigabe aktuell prüfen.
Der anwendungsinterne Zähler ist **keine garantierte harte Grenze
für die externe Anbieterrechnung**. Ein separater
Pro-Film-Grenzwert wurde ausdrücklich NICHT eingeführt.

