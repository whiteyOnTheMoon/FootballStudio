# Marktwerte in FootballStudio (M2)

## Produktentscheidung – Marktwert nur mit Quelle und Stichtag

Optional sollen Filmprojekte für einen frei ausgewählten Verein einen
**geschätzten Kadergesamtmarktwert** (`squad_total`) enthalten. Ist ein
belegter Einzelspielerwert sinnvoll, muss er separat als
`player_estimate` bezeichnet werden. Kaderwerte sind Schätzungen,
**weder Eigentumswert/Bilanzwert eines Clubs noch Transfergebühren**.
Ein fehlender Marktwert bleibt fehlend; bitte keine Zahl herleiten oder
aus älteren Saisonständen als aktuell ausgeben.

Jeder Datensatz benötigt:
- exakten positiven numerischen Betrag ohne „Mio./bn“-Abkürzungen,
  eine ausdrücklich genannte Währung (EUR/GBP/USD) und das verwendete
  Bewertungsdatum;
- **Original-Quellen-URL**, zeitlich dokumentierten Abruf,
  Metrik `squad_total` vs. `player_estimate` und dokumentierte
  Nutzungsberechtigung;
- anfangs `unverified`, bis die Quelle und konkrete Aussage wirklich
  geprüft und mit `SourceReference`/`Evidence` belegt wurden.

Der rein lokale Validator
`app.production.market_values.normalize_market_value(...)` stellt
einen solchen strukturierten, JSON-serialisierbaren Datensatz aus
**bereits rechtmäßig verfügbaren** Angaben zusammen. Er ruft
**keine** Website auf, speichert **nichts** in der DB und setzt
`verification_state=unverified`. Die Angaben `rights_basis="licensed"`
bzw. `"permission_granted"` müssen vom aufrufenden Prozess nach
tatsächlicher Berechtigungsprüfung belegt werden; die Kennzeichnung
allein ist **kein Lizenznachweis**.

## Transfermarkt – derzeit kein automatisches Crawling

Transfermarkt ist für Schätzwerte bekannt; die [Marktwertdefinition]
(https://www.transfermarkt.co.uk/navigation/mwdefinition) erklärt, dass
es sich nicht um tatsächlich bezahlte Ablösen handelt. Nach der am
11.11.2026 geprüften [Transfermarkt-Nutzungsbedingung, Abschnitt 11.1]
(https://www.transfermarkt.de/intern/anb) ist der Abruf bzw. die Kopie
digitaler Inhalte per Bots/Spidern/Screenscraping oder sonstigen
automatisierten Verfahren **nicht erlaubt**. Ein offener robots.txt-Eintrag
ersetzt keine Nutzungserlaubnis. Daher **kein** Transfermarkt-Scraper,
auch nicht über Umgehungsdienste oder inoffizielle Drittanbieter-APIs.

Weiteres Vorgehen: Eine offiziell genehmigte Datenintegration,
ausdrücklich autorisierte Lieferung oder geeignete anderweitig
lizenzierte Datenquelle prüfen. Bis zur Klärung wird kein automatischer
Transfermarkt-Wert erhoben. Einzelne öffentlich recherchierte Angaben
dürfen nicht ohne Rechteprüfung in die KI-Produktion übernommen werden.

## Nächste Integrationsschritte

Den Validator erst nach Rechtefreigabe mit dem bestehenden
versionierten `FactDossier` und konkreten Quellen-/Beleg-Einträgen
verbinden. Vor Narration Werte mit Datum und als Schätzung kennzeichnen
und die Aktualität prüfen. Ohne zulässige Datenquelle die Passage
auslassen statt eine Zahl zu erfinden.

Diese Änderung betrifft nicht die Vereins- oder Liga-Auswahl und löst
keine Paid-API-Aufrufe aus.


## Optionales manuelles Feld in der Weboberfläche (#132)

Im Bereich **M1-Testjob anlegen** kann man nun optional
`Kader-Marktwert manuell ergänzen` öffnen. Die Zahl wird in **Millionen**
eingegeben (z. B. `125.50` für 125.500.000), die Währung EUR/GBP/USD ist
auswählbar. Ein Wertstichtag und die Original-HTTPS-URL sind freiwillig;
sie helfen später bei der Belegprüfung. Ist kein Marktwert bekannt, wird
gar keine Zahl gespeichert (nicht `0`). Datum und Quellenlink ohne
Wert sind nicht zulässig.

Der Betrag wird in absoluten Währungseinheiten als nullable
`ProductionJob.manual_market_value_amount` persistiert, zusammen
mit `manual_market_value_currency`, `manual_market_value_as_of`
und `manual_market_value_source_url`. Die gespeicherte Information
bleibt ein **privater Snapshot pro Job** (nicht am Club für alle Nutzer);
über die nur für den Job-Eigentümer zugängliche API wird sie als
`manual_market_value` mit `metric=squad_total`,
`provenance=user_entered` und `verification_state=unverified`
angezeigt. Der ursprüngliche M1-Prototyp erstellt weiterhin **kein Video**.

**Rechte- und Qualitätsgrenze:** Die Eingabe erlaubt keine automatische
Transfermarkt-Abfrage und behauptet keine Lizenz zur Wiederverwendung.
Ein manuell recherchierter Wert ist eine unbestätigte Notiz, die nicht
ungeprüft als gesicherte Information ins Narrativ gelangen darf.
Vor einer späteren Aufnahme ins Faktendossier / Skript müssen Quelle,
Aktualität, Beleg und Nutzungsrechte geprüft werden. Eine optionale
Quellen-URL wird **niemals** vom Server heruntergeladen.

Eine spätere Bearbeitung bereits angelegter Jobs ist noch nicht
implementiert; hier wird die Zahl beim Erstellen gespeichert.
