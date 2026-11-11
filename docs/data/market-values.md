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
