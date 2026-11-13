# FS-014a / #31 – Automatische, freie Wikimedia-Recherche

**Motivation:** Die Auswahl Land → Liga → Verein muss die Recherche
auslösen können. Bisher sammelte die App manuelle Quellen/Fakten,
ohne automatisch recherchierte Tatsachen im Dossier. Der neue
erste Integrationsschritt bietet eine explizite
**„Vereinsdaten automatisch recherchieren“**-Aktion im
privaten Recherchedossier. Keine Q-ID-Eingabe oder manuelle
Vorab-Recherche nötig.

## Was automatisch passiert

1. Nur ein angemeldeter Job-Eigentümer darf per CSRF-geschütztem
   **POST** starten; GET löst niemals externe Zugriffe aus.
2. Name und Landescode werden ausschließlich aus dem ausgewählten
   `ProductionJob` ermittelt, nie frei aus einem Request-URL-/QID-Feld.
3. Wikidatas `wbsearchentities` sucht bis zu sieben Kandidaten;
   es werden maximal drei plausible Namensübereinstimmungen geprüft.
   Zulässig ist nur ein **eindeutiges** Wikidata-Objekt mit
   `P31=Q476028` (association football club) und `P17`-Land,
   dessen `P297`-ISO-Code zum gewählten Land passt.
   Bei Zweifeln wird nichts importiert.
4. Die feste Wikidata-EntityData-URL liefert `P571`
   (Gründungszeit) als mögliche `founded_year`-Angabe.
   Unterschiedliche Jahreswerte erzeugen **keinen** geratenen Fakt.
5. Über den vorhandenen englischen Wikipedia-Sitelink wird ein
   kurzer Textauszug über die **feste** Wikipedia-API geladen,
   sofern erreichbar. Der Text wird **nicht vollständig
   gespeichert**; nur eine sichere Quelle und gegebenenfalls
   ein knapper Locator, wenn der Einstieg ein klares
   `founded/established/formed ... YEAR`-Muster enthält.
   Wikidata und Wikipedia sind dabei **nicht automatisch**
   als zwei unabhängige Primärbelege zu betrachten.
6. Der Import legt unter Job-Row-Lock eine neue
   `FactDossier`-Version mit Quellen, Zeitpunkt und
   **unverified**-Faktenvorschlag + `unknown`-Evidenzrolle an.
   Historische Dossiers bleiben unverändert. Ein wiederholter
   Start nach erfolgreichem Import ruft Wikimedia nicht erneut ab.
   Vorhandene Wikidata-Quellen aus früheren manuellen Importen
   sperren die automatische Suche nicht.

## Sicherheits- und Produktgrenzen

- Nur fest eingebaute HTTPS-Hosts `www.wikidata.org` und
  `en.wikipedia.org`, **keine Redirects**, kein freier
  URL-/Domainparameter, begrenzte Antwortgrößen,
  6-Sekunden-Timeout pro Request und `maxlag=5`.
- User-/Job-Owner- und Versionsprüfung **vor** dem ersten
  Netzwerkzugriff; Datenbankschreibvorgänge nur nach
  erfolgreicher eindeutiger Vereinsidentität.
- Keine Suche oder Abfrage von Wikidata-P856-Websites;
  solche Domains erfordern weiterhin eigenständige
  Identitäts-, Website-Bedingungs-, Robots- und SSRF-Prüfung.
- Kein LLM, keine kostenpflichtige API, kein Voice-Output,
  kein Worker, kein YouTube-Upload, **keine Migration**.
- Der Import erfindet **keine menschliche Reviewentscheidung**.
  Das bestehende Skript-Gate sperrt ungeprüfte Fakten weiterhin.
  Nächste Arbeitspakete müssen automatische Quellenabgleiche,
  nachvollziehbare automatische Confidence-/Conflict-Entscheidungen
  und den großen automatischen Filmproduktionsablauf umsetzen.
  Das ist ausdrücklich **noch nicht erledigt**.
- Für manche Katalogvereine fehlen Wikidata-Einträge oder P17/P31.
  Diese werden statt falsch zugeordnet als
  `no_confident_match` angezeigt; später ist eine
  geführte Ausnahme-/Kandidatenauflösung erforderlich.
- Keine Live-Wikimedia-Requests in CI: alle Endpunkte
  werden dort mit festen Mock-Antworten getestet.
  Live-Verhalten (429, Änderungen an Wikidata-Einträgen)
  muss nach Deployment separat kontrolliert werden.

## Tests

`python manage.py test app.production.test_wikimedia_auto app.production.test_wikimedia_auto_views`

Das Sturm-Graz-Pilotszenario verwendet **keine feste Q-ID
im Produktcode**. Die Q-ID stammt in den Tests aus der
gemockten Suchantwort. Geprüft werden eindeutige Zuordnung
bei `Sturm Graz`/`AT`, falsch zugeordnete Länder,
Mehrdeutigkeit, fehlende/abweichende Gründungsjahre,
Wikipedia-Ausfall, Redirects, unbekannte Hosts,
versionierter Datenbankimport, Idempotenz,
fehlende automatische Verifikation, Login, CSRF,
stale Version und kein Netzaufruf für fremde Jobs.

Referenz zur freien Wikimedia-Schnittstelle:
https://www.wikidata.org/wiki/Wikidata:Data_access/en


## Ergänzung: Stadionsuche als zweiter automatischer Schritt

Nach dem ersten kostenlosen Wikimedia-Import (z. B. Sturm Graz,
Dossierversion 3 mit `founded_year=1909`) zeigt das aktuelle
Recherchedossier jetzt den Knopf
**„Weitere Fakten automatisch recherchieren: Stadion“**.

Diese Aktion nimmt **ausschließlich** die bereits für den
eigentümergeschützten Job automatisch zugeordnete Club-Q-ID
aus dem gespeicherten Dossier. Sie fragt Wikidata P115
(*home venue*) ab, verwirft beendete oder erst für die
Zukunft vorgesehene Heimspielstätten und akzeptiert nur
eine eindeutige aktuelle P115-Zuordnung. Ein `preferred`-Wert
hat Vorrang vor `normal`. Wenn keine aktuelle eindeutige
Zuordnung oder kein geeigneter englischer Stadionname
existiert, wird **kein** Fakt erfunden oder gespeichert.

Der Name wird aus der **zugehörigen Stadion-Q-ID** über
die feste Wikidata EntityData-API ermittelt, nicht aus
freiem Nutzereingabetext und ohne manuelle Q-ID-Suche.

Im Erfolgsfall erzeugt der Import genau einen
**ungeprüften** `stadium_name`-Faktenvorschlag in der
nächsten Dossierversion; die beiden strukturierten
Wikidata-Links P115 (Vereinsobjekt) und English label
(Stadionobjekt) bleiben in der Evidenz sichtbar.
**Beide Wikidata-Seiten zählen ausdrücklich nicht als
zwei unabhängige Quellennachweise.**

Voraussetzungen: Login, gültiger CSRF-Token, eigene
Job-ID, neuester Dossierstand, vorhandene automatische
Club-Q-ID. Abgefangene upstream/API-Fehler, unbekannte
Stadien und widersprüchliche Zuordnungen führen zu
einer erklärten Nichtübernahme. Keine fremden Domains,
keine Bilddateien, keine bezahlten APIs, kein Freitext-LLM.
Wiederholte erfolgreiche POSTs erzeugen keine neuen
Dossierversionen und führen keine weiteren Netzabfragen
aus. Frühere Versionsstände und bereits verifizierte
Fakten bleiben unangetastet.

Die kritische Produktgrenze bleibt: Das ist eine
**automatische Faktenrecherche**, keine automatische
Verifikation und kein vollständiger 8–10-Minuten-Film.
In den nächsten Schritten müssen breit belegte weitere
Clubevents, unabhängig geprüfte Quellencrosschecks und
eine formale automatische Freigabeentscheidung folgen.
Automatisch gefundene Aussagen werden nicht als
menschlich geprüft ausgegeben.

Offline-Tests (Wikidata-HTTP gemockt):
`python manage.py test app.production.test_wikimedia_stadium app.production.test_wikimedia_stadium_views`

Keine Datenbankmigration; bestehende Dossierversion 3
von Sturm Graz wird erst durch ausdrückliches Klicken
der neuen Folgeaktion um einen Stadionkandidaten ergänzt.


## Ergänzung: Kandidaten bekannter ehemaliger/aktueller Spieler (P54)

Die nächste ausdrücklich bestätigte Rechercheaktion
**„Spieler und mögliche Vereinslegenden automatisch suchen“**
steht allen zuvor automatisch identifizierten Vereinsjobs zur
Verfügung, darunter Sturm Graz. Der Nutzer muss weder Spieler
noch Q-IDs oder Quellen von Hand eingeben.

- Einmalige, auf **eine exakte Club-Q-ID** eingeschränkte
  Wikidata Query Service-Abfrage nach \`P54\` (Vereinszugehörigkeit),
  \`P31=Q5\` (Mensch) und \`P106=Q937857\` (Fußballspieler).
  Keine Stichwortsuche über alle Wikidata-Objekte.
- Maximal 12 strukturierte Treffer vom Query Service, davon
  bis zu acht eindeutige Namen mit englischem Label und
  mindestens drei Wikimedia-Sitelinks speichern.
  Die Sitelink-Anzahl bestimmt lediglich die Reihenfolge
  einer **begrenzten Auswahl**, niemals einen sportlichen
  Wert oder eine Legendenbewertung.
- Eigene Faktenart \`club_player_candidate\` mit
  \`unverified\`-Status, strukturierter Person-Q-ID,
  Wikidata-P54-Fundstelle und individueller Quellen-URL.
  **Kein** \`FactReview\`, kein Freigeben für Skript,
  Szenen, TTS oder Rendering.
- Alte Fakten, Dossiers und manuelle Reviewentscheidungen
  werden nicht überschrieben. Der erste erfolgreiche Import
  forked die aktuellste Dossierversion; wiederholte Starts
  erkennen einen persistierten Abrufmarker und rufen die
  externe API nicht erneut auf.
- Abruf ausschließlich von
  \`https://query.wikidata.org/sparql\`,
  ohne Redirect, mit festem User-Agent, maximal
  8 Sekunden Wartezeit und 128 KiB JSON-Antwort.
  Owner, CSRF, Job, Dossier-Version und vorherige
  automatische Club-Zuordnung werden vor der Anfrage
  überprüft. Clientseitig frei gewählte Q-IDs und
  externe URLs werden nicht akzeptiert.
- Die Weboberfläche zeigt die Kandidaten **separat**
  von endgültig belegten Fakten mit eindeutiger Warnung:
  **„Noch keine offiziell anerkannten Vereinslegenden“**.

**Bedeutender Unterschied:** Wikidata \`P54\` bedeutet lediglich,
dass jemand für eine Mannschaft spielte oder spielt. Daraus
folgt **weder** ein Legendenstatus **noch**, dass die Person
heute nicht mehr dort spielt. Eine gesonderte automatische
Gegenprüfung in offiziellen Vereinsquellen ist weiterhin
erforderlich.

**Sturm-Graz-Testziel:** Der Verein veröffentlicht einen
eigenen offiziellen Legendenklub und die Aufnahmekriterien:
- https://sksturm.at/c/legendenklub
- https://sksturm.at/c/sk-sturm-graz-legenden

Diese URLs sind **externe Belegbeispiele**, kein
fest kodierter Klub-Sonderfall und werden in diesem PR
nicht serverseitig gecrawlt. Ein separater zukünftiger
Adapter muss die bestätigte Clubdomain, Websitebedingungen,
robots.txt, sichere DNS-/TLS-Verbindung und belegte
Namenszuordnung beachten. Erst dann darf die Anwendung
die offizielle Legendenbenennung ausgeben.

Offline-Tests:
\`python manage.py test app.production.test_wikimedia_players app.production.test_wikimedia_players_views\`.
Keine echte Query-Service-Anfrage in CI, keine Paid API,
keine Migration.


## Ergänzung: Abgleich mit **offiziellen** Vereinslegenden

Für einen bereits automatisch erkannten Verein (Club-Q-ID aus Wikidata),
bereits automatisch gefundene Spieler (Wikidata P54) und eine zuvor vom
Job-Eigentümer bestätigte **offizielle Vereinsdomain**
zeigt der neueste Dossierstand die Aktion
**„Offizielle Vereinslegenden automatisch abgleichen“**.

Die Aktion startet genau einmal einen **auf die bestätigte Domain
begrenzten** kostenlosen HTTPS-Abruf:
1. Eigentümer, aktuelle Dossierversion, frühere Wikidata-Identität und
   bestehende Club-Website-Zuordnung mit dokumentierter Website-/Terms-
   Bestätigung **vor Netzwerk** prüfen.
2. Bereits existierende DNS-gepinnte TLS-Verbindungen,
   Redirect-/IP-/Content-Type-Blockierung und Robots-Regeln aus
   \`safe_official_fetch\` und \`official_site_research\` verwenden.
   robots.txt muss eindeutig anwendbar sein; kein CAPTCHAs-/429-Bypass,
   keine Fremddomain, kein Transfermarkt-Crawl.
3. **Eine** geeignete Legenden-Übersichtsseite abrufen; wo vorhanden
   anhand **eines begrenzten Links** auf der Clubhomepage finden.
   Für die reale Pilotzuordnung Q124007617 + sksturm.at
   existiert ein *Pfad-Hinweis* \`/c/legendenklub\` zur Suchverkürzung.
   Dies ist **keine** fest eingebaute Namens-/Legendenliste und
   keine Ausnahme vom Robots-/TOS-/TLS-Schutz.
4. Nur die ausdrücklich überschriebenen Bereiche
   „Spielerlegenden“ bzw. „Trainerlegenden“ oder die englischen
   Äquivalente auswerten, jeweils kurze comma-/semicolon-getrennte
   Namenslisten, keine Nachrichten-/Artikeltexte.
   Nur **exakte** normalisierte Namensübereinstimmungen mit den
   zuvor per Wikidata P54 gefundenen Spielern als
   \`official_player_legend_candidate\` erfassen.
5. Zusätzlich bis zu zwölf namentlich veröffentlichte
   Trainerlegenden als \`official_coach_legend_candidate\` mit
   eigener Quellen-Fundstelle übernehmen. Hier fehlt noch ein
   unabhängiger Personen-ID-/Biografie-Abgleich.
6. Dossier unter \`SELECT FOR UPDATE\` forken und nur
   Quellen-URL, Abrufzeit, ausgewählte Namen, Quellenhinweise und
   **\`unverified\`**-Faktenvorschläge persistieren. Keine Seite
   oder geschützten Volltexte speichern, ältere Dossierstände
   nicht ändern. Idempotenter Retry ohne erneuten Websiteabruf.

**Warum keine automatische Verifikation?**
Eine dokumentierte Vereinsliste kann belegen, dass der Verein die
betreffende Person offiziell als Legende aufführt. Die technische
Extraktion ist aber weiterhin ein maschineller Abgleich.
Die bestehende \`FactReview\`-Schnittstelle und die Regeln für
\`verified\`-Fakten / Skript / TTS werden **nicht** umgangen.
Zwischen „offiziell gelistet“ und redaktionell freigegeben wird
bewusst unterschieden. Besonders frühere Namen und Trainer benötigen
ggf. Identitätsprüfung, bevor eine lebendige Biografie erzählt wird.

**Begrenzung:** Nicht jeder Verein veröffentlicht eine solche Liste,
manche Seiten verbergen sie hinter JavaScript, verlinken sie nicht
auf der Homepage oder verbieten den automatischen Abruf.
Dann wird nichts geraten und es findet keine fingierte erfolgreiche
Recherche statt. Die nächste Stufe ergänzt weitere vereinsübergreifende
Discovery-Quellen und redaktionell abgesicherte automatisch
wiederverwendbare Entscheidungen.

**Offline-Tests:**
\`python manage.py test app.production.test_official_legends app.production.test_official_legends_views\`

Keine Migration, keine Paid API, keine externe Website im CI-Test.


## FS-014b: offizielle Titelchronik mit dokumentierten Quellenunterschieden

Nach den ersten Vereins- und Legenden-Recherchen bietet das neueste
Dossier jetzt **„Meisterschaften und Pokalsiege automatisch recherchieren“**.

Ein bewusst kleiner, sicherer Pilot-Adapter kann eine bereits
eigentümerbestätigte offizielle **Ligaquelle** auswerten
(Saison/Meister/Cup-Sieger) und die Saisonlisten nach Möglichkeit mit
einer separat bestätigten **Vereinsquelle** vergleichen.
Dazu werden die vorhandenen identitäts-/terms-geprüften
\`SourceConfirmation\`-Einträge und exakt derselbe DNS-gepinnte
HTTPS-/TLS-, IP-, no-redirect-, Content-Type-, Robots- und
Politeness-Schutz wie beim Legendenabruf verwendet.
CSRF, Eigentümer, aktuelle Dossierversion und zuvor automatisch
erkanntes Club-Wikidata-Objekt sind Vorbedingungen **vor** der
ersten externen Anfrage.

Für den bereits bestätigten Sturm-Graz-Pilot
nutzt der Adapter lediglich URL-**Pfadhinweise**:
- Liga (AT + bestätigtes \`www.bundesliga.at\`):
  \`/de/titel-uebersicht\`;
- Verein (Q124007617 + bestätigtes \`sksturm.at\`):
  \`/en/c/steckbrief\`.

Es werden **keine** Saisons, Titel, Quelleninhalte oder Siegernamen
im Produktcode fest eingetragen. Die Parser verarbeiten:
- ausschließlich eine eindeutige Tabellenstruktur mit Saison,
  Meister und Cup-Sieger;
- ausschließlich exakt gezählte Meister-/Pokalsaisonlisten im
  Bereich **National success** des offiziellen Vereinsprofils;
- ausschließlich die ausgewählte Teambezeichnung mit
  konservativem Präfix-/Sponsorenabgleich (z. B.
  \`SK Puntigamer Sturm Graz\` vs. \`Sturm Graz\`).
  U21-, Frauen- oder Reserveteams werden nicht als derselbe Verein
  angesehen.

Pro eindeutige Kombination aus Saison und Meisterschaft/Pokal
entsteht ein \`club_honour_candidate\`-Eintrag mit
\`verification_state=unverified\`, \`Evidence.role=unknown\`,
Saison, Wettbewerb, konkreten Quell-URLs und einer
Quellenvergleichskategorie:

- \`both\`: offizielle Liga und eigenes Clubprofil nennen
  denselben Titel für die Saison;
- \`league_only\`: Titel auf Ligaseite, im tatsächlich
  ausgewerteten Vereinsprofil **nicht aufgeführt** (keine
  Behauptung, dass er falsch sei);
- \`club_only\`: nur Clubprofil, nicht in Ligatabelle
  nachgewiesen;
- \`club_not_checked\`: Ligaseite erfolgreich, aber das
  Vereinsprofil war nicht verfügbar/auswertbar.
  **Diese Kategorie ist keine Quellenabweichung.**

Die Webseite zeigt die saisonweise Chronik und die
Vergleichszahlen mit Klicks zur offiziellen Quelle.
Für den realen Sturm-Graz-Fall ist der Pokal
2023/24 auf der offiziellen Ligaseite verzeichnet,
fehlt jedoch in der zum Analysezeitpunkt veröffentlichten
englischen Vereinsprofil-Liste. Das System soll diese
Abweichung **sichtbar** lassen, nicht automatisch
eine Seite zum Gewinner erklären.

**Sicherheits-/Produktschranken:** Keine ungeprüften
Sprechertexte oder FactReview-Fälschung. Ein
Zwei-Quellen-Treffer bedeutet noch **keine**
redaktionelle Verifikation. Maximal 32
Saison-/Wettbewerbs-Kandidaten, mindestens 10
Saisoneinträge in einer eindeutigen Ligatabelle,
keine externe URL aus Formularen, höchstens
eine Ligaseite und eine Clubprofil-Seite (plus
je eine Homepage für generische Linksuche),
maximale Abrufzeit sowie keine kostenpflichtigen APIs.
Fehlt die Clubprofilseite, wird die Ligarecherche
nur als \`club_not_checked\` gespeichert.
Ist die Ligaseite nicht sicher abrufbar oder
nicht strukturiert erkennbar, wird gar nichts
übernommen. Historische Dossierversionen
werden nur kopiert, nicht mutiert; erneuter
POST nach Erfolg bleibt idempotent.

Es handelt sich um den **österreichischen Pilot**
für dieses Tabellenformat; fremde Ligaformate
benötigen separate, quellenspezifische Parser.
Ein Klick ersetzt noch nicht den gesamten
Vereinsfilm-Workflow. Die nächste Stufe
ist automatische Einordnung der relevanten
historischen Wendepunkte und eine sichere
editoriale Überleitung zum englischen Skript.

Offline-Tests:
\`python manage.py test app.production.test_official_honours app.production.test_official_honours_views\`

Keine neue Migration; bestehender Sturm-Graz-Job
Version 6 bleibt unverändert, bis die
neue Aktion ausdrücklich gestartet wird.

## FS-014c: Gemeinsamer Rechercheablauf mit browserseitiger Fortsetzung

Das private Recherchedossier zeigt einen gemeinsamen Start
**„Automatische Recherche starten / fortsetzen“** und einen Plan aus
fünf bereits existierenden Recherchediensten:

1. Kostenlose Wikidata-/Wikipedia-Vereinszuordnung.
2. Kostenfreie P115-Heimspielstätte.
3. Kostenfreie P54-Spieler der Vereinsgeschichte.
4. Offizielle Vereinslegenden (nur mit zuvor bestätigter offizieller
   Vereinsdomain und bereits dokumentierter Website-/Terms-Bestätigung).
5. Meisterschafts-/Pokalchronik (nur mit zuvor bestätigter offizieller
   Ligadomain).

Der zentrale Controller ersetzt **keine** der bisherigen
Sicherheitsgrenzen. Jeder POST /jobs/<id>/research/auto-continue/
führt höchstens einen vorhandenen Importdienst aus. Dieser prüft
erneut Job-Eigentümer, die exakt aktuelle Dossierversion, die
Quellenherkunft und die bestehenden Robots-/DNS-gepinnten
TLS-/Domainregeln. GET ist stets lesend. Der Knopf akzeptiert
keine nutzerseitige Club-Q-ID, Spieler, Ziel-URLs oder Providerbudgets.
Eine fehlende bestätigte offizielle Quelle wird **nie**
automatisch autorisiert; die betreffende Stufe erscheint
als „wartet auf bestätigte offizielle Quelle“.

Im Browser können nach **einem ausdrücklichen Klick** bis zu
fünf nacheinander abgeschlossene POST-Requests per JavaScript
fortgesetzt werden. So blockiert kein einzelner HTTP-Request
für die gesamte Recherche. Bei einem Netzwerk-/Robots-/
CSRF-Fehler, mehrdeutigen Ergebnissen oder geändertem Dossier
stoppt die Fortsetzung ohne automatischen Retry. Vorherige
Stufen behalten ihre unveränderlichen Dossierversionen.
Ein Statusbereich ist für Screenreader per aria-live markiert.
Ohne JavaScript führt die Form pro Klick nur einen Schritt
aus und leitet zum aktuellen Dossier weiter.

Vorherige Einzelaktionen bleiben optional in einem
aufklappbaren Bereich. Bei vollständig recherchierten
Dossiers (Sturm Graz, ab Version 7) wird kein Netzabruf
wiederholt, sondern „5/5 Recherchestufen abgeschlossen“
angezeigt. Das bedeutet **nicht**, dass alle Fakten
bewiesen oder für die Filmproduktion freigegeben sind.

### Englischer Story-Aufbau – nur Rechercheplanung

Der deterministische Adapter research_outline.py
gruppiert bereits gespeicherte strukturierte Fakten
in einen vorgeschlagenen 9-Minuten-Aufbau:

- 0:00–1:00: *Origins of the club* – Gründungsjahr.
- 1:00–2:00: *A home and an identity* – Stadion.
- 2:00–6:30: *Turning points and silverware* – Titeljahre.
- 6:30–9:00: *People who shaped the club* – offiziell
  gelistete Spieler- und Trainerlegenden.

Jede Gruppe zeigt höchstens zehn Faktenbeispiele samt
Quelle-/Fact-ID und Reviewstatus. Nur klar definierte,
strukturierte Prädikate gehen in die Kapitel ein.
Nicht offiziell zugeordnete P54-Spieler werden
**nicht** als Legenden dargestellt. Die Ausgabe ist
mode=research_outline_only mit ready_for_voiceover=false;
kein Skript, kein TTS und keine automatische Filmproduktion.
Bestehende FactReview- und Skript-Gates bleiben unangetastet.

### Tests und Grenzen

python manage.py test app.production.test_research_autopilot app.production.test_research_autopilot_views app.production.test_research_outline

Alle Importer-Aufrufe sind in CI gemockt.
Geprüft werden Eigentümer und CSRF, Planreihenfolge,
fehlende offizielle Websitebestätigung, lesende GET-
Ansicht, Idempotenz bereits erledigter Jobs, stale
Formulare, Fehlerstopp, korrekte Quellenzuordnung
und keine Sprechertextfreigabe.

**Noch offen:** dauerhafter Hintergrund-Worker,
sichere offizielle Domain-Discovery ohne fingierte
Nutzerfreigabe, vollständige unabhängige Quellencrosschecks
und ein generiertes englisches 8–10-Minuten-Drehbuch.
Die browserseitige automatische Fortsetzung ist
**kein** im Hintergrund weiterlaufender Worker.

Keine Migration, keine Paid API, keine Filmproduktion.


## FS-014e: Offizielle Website-Kandidaten aus Wikidata automatisch vorschlagen

Der bisherige browsergesteuerte Rechercheablauf besitzt nun **sechs**
statt fünf Stufen. Nach dem freien Wikimedia-Club-, Stadion- und
Spielerimport läuft automatisch eine neue bounded Wikidata-P856-Abfrage:

1. Der zuvor anhand von Name, Land und Football-Club-Instanz
   identifizierte Club-QID wird aus der neuesten eigenen Dossierversion
   verwendet, niemals als freie Nutzereingabe.
2. Die Wikidata-Entität wird über den bestehenden freien, begrenzten
   Fixed-Host-HTTPS-Client geladen. Nur ein **eindeutiger**
   `P856`-Eintrag mit sicher aussehendem öffentlichem HTTPS-URL-Schema,
   ohne Port, Login, Query oder Fragment, gilt als Club-Website-Kandidat.
   Zwei unterschiedliche geeignete URLs gelten als **mehrdeutig**.
3. Für eine Liga darf nur ein per `P118` (Liga der Club-Entität)
   verknüpfter Wikidata-Liga-QID als Kandidat dienen. Die Liga muss
   einen **konservativ exakt** passenden englischen/deutschen
   Liga-Namen (mit wenigen sportbezogenen Stoppwörtern) und eine
   `P17`-Länderzuordnung haben, deren `P297`-ISO-Code zum
   ausgewählten Land passt. Maximal vier P118-Einträge
   werden geprüft; mehrdeutige Ergebnisse werden verworfen.
4. In einer neuen unveränderlichen Dossierversion werden nur
   `official_club_site_candidate` und gegebenenfalls
   `official_league_site_candidate` mit `unverified`-Status,
   P856-Beleg und Wikidata-Original-URL gespeichert. Ein
   persistenter Abrufmarker macht die Aktion bei erneutem Klick
   idempotent. Leere sichere Ergebnislisten bleiben leer,
   keine URL wird erfunden.
5. **Kein HTTP-/DNS-/Robots-Abruf der gefundenen Websites** beim
   Discovery-Schritt, beim GET des Dossiers oder beim Öffnen
   des vorausgefüllten Quellenformulars. Der Nutzer kann die
   vorgeschlagene HTTPS-Adresse als externen Link öffnen.
6. Der Link **„Als Quelle prüfen und übernehmen (vorbefüllt)“**
   öffnet das bestehende manuelle Quellenformular. Dort sind
   nur `url`, `context`, `title` und die aktuelle
   Dossierversion automatisch gesetzt. Die persönliche
   Begründung bleibt leer; die drei Identitäts-, Zugriffs-
   und Websitebedingungen-Bestätigungen bleiben **nicht
   angekreuzt**. Der vorhandene Eigentümer-/CSRF-/Stale-/
   Rate-Limit-/URL-Schutz von `register_manual_official_source`
   bleibt maßgeblich. Erst ein tatsächlich separat
   bestätigter Quelleneintrag erlaubt dem Autopilot den
   späteren offiziellen Vereins- oder Ligaabruf.

**Begrenzungen:** Wikidata P856 ist ein Drittanbieter-Hinweis,
keine Echtheitsgarantie. Einige Vereine haben keinen P856-Eintrag,
mehrere Websites oder keine passende P118-Liga. Dann bleibt die
bisherige manuelle Quellenerfassung möglich. Ein vorgeschlagener
Link kann veraltet oder ungeeignet sein. Die Software behauptet
nicht, die Domain, Nutzungsbedingungen oder Erreichbarkeit
bereits selbst geprüft zu haben. Es entsteht weiterhin
**kein automatisch verifizierter Fakt, kein Voiceover und kein
Video**. Die Recherche läuft browsergebunden, nicht
als dauerhafter Hintergrundjob.

**Offline-Tests:** `python manage.py test
app.production.test_official_source_candidates
app.production.test_official_source_candidates_views
app.production.test_research_autopilot
app.production.test_research_autopilot_views`

Keine Migration, keine kostenpflichtige API.
