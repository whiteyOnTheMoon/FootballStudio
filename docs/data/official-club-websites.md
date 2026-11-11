# Offizielle Vereinsseiten als M2-Recherchequellen

**Entscheidung (11.11.2026):** Wird für den frei ausgewählten Fußballverein
eine **nachvollziehbar offizielle Vereinswebsite** gefunden, sollen ihre
öffentlich zugänglichen Informationsseiten als **Primärquellen** berücksichtigt
werden — vor allem Vereinsgeschichte, Stadion, Erfolge, Vereinsprofil und Team.
Wikidata/Wikipedia bleiben ergänzende Sekundärquellen. Offizielle Webseiten
können eigene Interessen darstellen und ersetzen weder unabhängige
Gegenprüfung noch konkrete Quellenbelege.

## Teilumsetzung: gezielter Linkplaner (#123)

`app.production.official_site_links.discover_official_pages(homepage_url,
homepage_html, limit=8)` erzeugt aus **bereits vorliegendem HTML** eine
priorisierte, deduplizierte Auswahlliste. Der Funktionsaufruf führt **keinen
Netzwerkzugriff** aus und speichert nichts in PostgreSQL. Er akzeptiert nur
HTTPS-Homepages mit öffentlichem DNS-Namen, findet nur Links derselben
Hostname, verwirft Tracking-Query-Strings, Fremdlinks, HTTP-Links, Shops,
Tickets, Login-Links sowie Medien-Dateien. Die Liste ist standardmäßig
auf acht, maximal auf zehn Vorschläge begrenzt.

**Das ist ausdrücklich noch kein Crawler.** Wer Links als offizielle Vereinsseiten
übernimmt, muss vorher nachweisen, dass die Domain wirklich dem ausgewählten
Verein gehört. Offizielle Identität wird **niemals** aus zufälliger
Namensgleichheit abgeleitet.

## Vorgaben für die nächste Stufe: begrenzter HTTP-Rechercheadapter

1. **Bewusst bestätigte Domain** statt automatischer Suche nach beliebigen
   Vereinsnamen; kein Abruf nicht überprüfter User-URLs.
2. **Netzwerksicherheit:** HTTPS, öffentliche DNS-Adressen, Redirects, DNS
   Rebinding, DNS-Auflösung und die tatsächliche Socket-Verbindung müssen
   durchgehend vor SSRF schützen. Kein Zugriff auf private, Loopback- oder
   Container-Adressen. Nie externe Links oder Subdomains ungeprüft nachladen.
3. Vor dem Abruf **robots.txt** für den eigenen Crawler-User-Agent prüfen,
   Regeln gemäß [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html)
   befolgen; bei Fehlern oder Unklarheit für MVP **nicht crawlen**. Nutzungs-
   bedingungen und ein mögliches Crawl-Verbot beachten.
4. **Klein und langsam:** maximal wenige HTML-Seiten pro bewusst bestätigter
   Website, feste Timeouts/Antwortgröße, seriell statt parallel, Pause
   zwischen Anfragen und Cache/Standzeit. 429/403 respektieren, keine
   CAPTCHA-/Access-Schranken umgehen. Kein regelmäßiger unkontrollierter Scan.
5. **Quellengebunden:** für jede relevante Aussage Original-URL, Titel,
   Abrufdatum, Abschnitt/Locator und kurze eigene Zusammenfassung speichern,
   nicht komplette fremde Artikel als kopierten Text. Beleg muss wirklich
   **die konkrete Aussage** tragen, nicht nur von der gleichen Website stammen.
   Fakten bleiben ohne Prüfung `unverified`; Widersprüche kennzeichnen.
6. **Fallback:** Ist eine Seite gesperrt, nicht erreichbar, nicht eindeutig
   offiziell oder nicht zum Crawlen freigegeben, Quellenlücke dokumentieren
   und bestehende Wikidata-/Wikipedia- bzw. manuelle Recherche nutzen.
7. **MVP-Budget:** reine freie HTTP-Recherche, keine Paid-LLM-/TTS-Aufrufe,
   kein Upload und keine Änderung an fremden VPS-Projekten.

Der eigentliche Abruf/Extraktion in einen Datenbank-Quellennachweis ist eine
gesonderte M2-Teilaufgabe. Die bestehende App-/Job-Oberfläche bleibt
unverändert.


## Offizielle Ligaseiten als zusätzliche Primärquellen (#126)

Für den **ausgewählten Ligadatensatz** soll künftig auch eine unabhängig
identifizierte, offizielle Ligadomain eingebunden werden. Dort sind besonders
Tabellen, Spielpläne, Ergebnisse, Regelwerk/Ligaformat und offizielle
Vereinsprofile hilfreich. Fehlt eine offizielle Ligaseite, wird dies
ausdrücklich als Datenlücke behandelt; es wird keine URL erfunden.

Der vorhandene rein lokale Linkplaner unterstützt dafür
`discover_official_pages(league_homepage_url, already_fetched_html,
context="league", limit=8)`. Die Domain muss zuvor bewusst als offizielle
Ligaseite bestätigt werden. Die Funktion lädt **nichts herunter**,
wendet die bisherigen Host-/HTTPS-/Query-/Limit-Schutzregeln an und
liefert lediglich Kandidaten für spätere kontrollierte Recherche.
Die aktivierte Live-Abfrage muss wie bei Vereinsseiten zuvor
`robots.txt`, Nutzungsbedingungen, DNS-/Redirect-/SSRF-Sicherheit
und Abfrage-/Speicherlimits prüfen. Quellen werden datiert und
Fakten niemals nur wegen ihres offiziellen Ursprungs automatisch bestätigt.

Liga-/Saisonangaben (z. B. Tabelle der Saison 2026/27) dürfen niemals mit
historischen Tabellen oder einer nicht erkennbaren Saison vermischt werden.
