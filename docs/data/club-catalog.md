# FS-011a – Live-Vereinskatalog und Land/Liga/Verein-Auswahl

**Stand:** 10.11.2026 · **Implementierung:** [Issue #24](https://github.com/whiteyOnTheMoon/FootballStudio/issues/24)  
**Status:** API-Adapter und Dropdown-Oberfläche implementiert; reale Provider-Erreichbarkeit und End-to-End-Erlebnis werden durch separate Tests verifiziert.  
**Abhängigkeiten:** Länder-/Liga-/Clubs-Modelle #22, E-Mail-Login #20/#21; folgende manuelle Clubanlage #25 und Testjob #26.

## Funktion im ersten Docker-Prototyp

Nach dem Login erscheint die Oberfläche **Land → Liga → Verein**. Die Auswahl ist dynamisch, der Verein wird **nicht hart codiert**. Bei Änderung des Landes werden Liga und Club zurückgesetzt; bei Wechsel der Liga nur der Club. Ein ausgewählter Club wird über den Server gegen Land und Liga geprüft und mit seiner eindeutigen Datenbank-ID angezeigt. Die tatsächliche **Testjob-Erstellung** folgt separat in [#26](https://github.com/whiteyOnTheMoon/FootballStudio/issues/26).

Die vier geschützten Django-Endpunkte sind:

| GET-Endpunkt | Zweck |
| --- | --- |
| `/clubs/api/countries/` | aktuell unterstützte Länder mit Saison und Quellenhinweisen |
| `/clubs/api/leagues/?country=GB` | gegen das ausgewählte Land validierte Ligen (mindestens Tier 1 + 2) |
| `/clubs/api/clubs/?country=GB&league=ID` | aktuelle, vom Provider geladene Clubs dieser Liga |
| `/clubs/api/selection/?country=GB&league=ID&club=ID` | validiert die vollständige Auswahl; vermeidet fremde oder veraltete ID-Zuordnungen |

Alle vier Endpunkte sind nur angemeldet verfügbar. Die Oberfläche verwendet kleine lokale JavaScript-Funktionen ohne externe CDN-Abhängigkeit; die Entwicklung bleibt mit den serverseitigen Django-Views kompatibel. Ein CDN-abhängiges HTMX-Skript ist für diese drei Dropdowns noch nicht nötig.

## Kostenlose Provider und aktuelle Länderabdeckung

Die Provider bestimmen per API, ob ihre laufende Saison ausreichend abgedeckt ist. Die untenstehende Konfiguration enthält **nur Länder-/Liga-Kennungen**, **keine Vereinslisten**.

| Region / UI-Land | ISO-Code | Liga 1 | Liga 2 | Liga 3 |
| --- | --- | --- | --- | --- |
| England (UK) | GB | Premier League (`en.1`) | Championship (`en.2`) | League One (`en.3`) **nur falls im aktuellen API-Katalog vorhanden** |
| Deutschland | DE | Bundesliga (`bl1`) | 2. Bundesliga (`bl2`) | 3. Liga (`bl3`) **nur falls vorhanden** |

**GB ist der ISO-3166-1-Code des Vereinigten Königreichs**, nicht ein eigener England-ISO-2-Code. Die beiden angebotenen Wettbewerbe sind englische Ligen und können Vereine aus Wales enthalten; die UI beschriftet den Katalog deshalb **England (UK)**. Das ist keine allgemeine Abdeckung aller vier Landesteile des Vereinigten Königreichs.

**Quelle A – OpenFootball (CC0):** Für die Saison 2026/27 werden über die öffentliche [GitHub-Contents-API](https://api.github.com/repos/openfootball/football.json/contents/2026-27) vorhandene JSON-Dateien ermittelt. Wenn die Dateien `en.1.json` und `en.2.json` vorhanden sind, werden England und beide Ligen angeboten. Die Vereinsnamen werden aus **allen `team1`-/`team2`-Einträgen** der [Saisondateien](https://github.com/openfootball/football.json/tree/master/2026-27) extrahiert – nicht manuell vorgegeben. OpenFootball selbst weist darauf hin, dass die Quell-Football.TXT-Dateien nicht zwingend automatisch täglich inhaltlich aktualisiert werden.

**Quelle B – OpenLigaDB (ODbL 1.0):** Die API [`getavailableleagues/{season}`](https://api.openligadb.de/index.html) prüft die Verfügbarkeit der Top-2-Ligen und ggf. der 3. Liga. Für die Mannschaften wird `getavailableteams/{leagueShortcut}/{season}` verwendet. Die API ist kostenfrei und ohne Anmeldung nutzbar, aber communitygepflegt; **Vollständigkeit und Aktualität sind nicht garantiert**. Ligen ohne die beiden höchsten verfügbaren Stufen werden nicht als unterstütztes Land beworben.

**Lizenz-/Attributionspflicht:** Der Katalog nennt OpenLigaDB mit Link zur [ODbL-1.0-Lizenz](https://www.openligadb.de/lizenz); OpenFootball-Daten stehen nach deren [Projektangabe](https://github.com/openfootball/football.json) unter CC0. **Vereinswappen, Fotos und Logos** sind dadurch nicht automatisch frei nutzbar und werden vom Auswahladapter **nicht importiert**.

### Warum nicht die kostenlose TheSportsDB-Teamliste?

Die dokumentierte freie V1-Schnittstelle hat je Endpoint eingeschränkte Ergebniszahlen (z. B. Teamlisten und Ligen). Für FootballStudio darf eine abgeschnittene Liste **nicht** als vollständiger Ligakatalog erscheinen. Die gewählten offenen Quellen haben keinen festen Zehn-Teams-Deckel. Die API-Adapterschicht bleibt austauschbar.

## Datenhaltung und Aktualität

- Die Tabelle `Country` speichert Land, `League` zusätzlich `catalog_season` und `last_synced_at`; `Club` speichert Ursprung, externe ID und Kennzeichen `is_manual`.
- Die laufende Saison wird aus dem aktuellen Datum abgeleitet: **ab Juli Startjahr = aktuelles Jahr**, sonst Vorjahr. Für November 2026 gilt somit **2026/27**. Fehlende Daten einer neuen Saison führen zur **sichtbaren Nichtverfügbarkeit**, nicht zur stillen Nutzung einer vorjährigen Saison.
- Ligen werden höchstens einmal pro 6 Stunden pro Django-Prozess bei der Quelle entdeckt. Ein einmal erfolgreich geladenes Vereinsverzeichnis wird **12 Stunden** gespeichert und danach bei erneutem Aufruf aktualisiert; diese Zeitstempel liegen in PostgreSQL. **Kein automatisch häufiger Provider-Poll.**
- Bei Fehlern der Länder-/Liga-Ermittlung bleiben bereits ermittelte aktuelle Katalogdaten verfügbar, mit Warnung. Bei Fehlern des Teamimports wird ein vorhandener Datenbankstand nur **ausdrücklich als möglicherweise veraltet** gezeigt; ohne Datenstand folgt HTTP 503.
- Importaktualisierungen betreffen nur Provider-Clubs. **Manuell angelegte Clubs werden nicht überschrieben oder gelöscht.** Fehlende, zuvor vom Provider importierte Clubs werden als inaktiv markiert; es wird keine vermeintlich aktuelle Mannschaft erfunden.
- Nachweis: Mindestens **zehn unterschiedliche** Clubnamen müssen aus einer Team-/Fixture-Quelle gewonnen werden. Offensichtlich leere/gekürzte Daten werden abgelehnt; zehn Namen allein garantieren allerdings noch keine vollständige Liga. Die tatsächliche Ligagröße muss bei Liveprüfung kontrolliert werden.
- **Sicherheit:** HTTP-Anfragen nur an feste vertrauenswürdige API-Hosts über HTTPS, maximal 7 Sekunden und 2 MB Antwort je Abruf. Keine aus Benutzereingaben konstruierte Remote-Hostadresse und kein externes Scripting im Browser.

## Geplanter Prüfnachweis

- [ ] Django-Tests mit Fake-Quellen prüfen 2 unterstützte Länder mit mindestens zwei Ligen, dritte nur bei Verfügbarkeit, 20–24 englische bzw. 18 deutsche Testclubs.
- [ ] Wechselt ein Nutzer Land/Liga, werden veraltete Optionen geleert; serverseitig dürfen mismatched IDs **niemals** validiert werden.
- [ ] API-Ausfälle: deutliche Fehlermeldung bzw. explizit als veraltet gekennzeichnete lokale Daten; nicht auf einen Pilotclub zurückfallen.
- [ ] PostgreSQL-Migrationen und Auth-Schutz in Docker Compose bestehen.
- [ ] Live-Quellenprobe bestätigt **tatsächlich** die Saison 2026/27 für mindestens zwei Ligen pro angebotenem Land.

Die Django-Unit-Tests nutzen **ausschließlich Mock-Provider**, um nicht bei jedem CI-Run von fremden APIs abhängig zu werden. Eine zusätzliche Liveprüfung ist erforderlich, bevor von produktiver Länder-/Vereinsabdeckung gesprochen werden darf. Der VPS wurde bisher nicht verändert.

## Manuell angelegte Vereine im Dashboard (FS-011b / #25)

In der interaktiven Vereinsauswahl erscheint nach der Ligawahl eine **separate Eingabemaske** für nicht gelistete Clubs. Ein angemeldeter Nutzer kann einen Namen erfassen und als **neuen Verein in exakt dieser Liga** speichern. Der neue Datensatz hat `is_manual=True`, `provider=manual` und steht anschließend sofort in derselben Auswahl zur Verfügung.

**Geschützter Endpoint:** `POST /clubs/api/manual/` mit `country`, `league` und `name`. Django prüft Session und CSRF-Token. Der Server validiert Land/Liga gegen den aktuellen Katalog und lehnt fremde Ligazuordnungen ab (HTTP 404). Fehlende oder ungültige Pflichtfelder führen zu HTTP 400, doppelte Clubnamen **unabhängig von Groß-/Kleinschreibung** innerhalb einer Liga zu HTTP 409. Der Datenbank-Constraint verhindert auch parallele Dubletten. Bereits importierte API-Clubs bleiben unberührt; ein manuell angelegter Club wird bei späterem API-Sync **nicht überschrieben**.

**Grenze:** Eine manuelle Vereinsanlage ist in dieser Phase nur für **bereits unterstützte Länder/Ligen** möglich. Das frei anlegbare Länder-/Ligen-Verzeichnis ist derzeit über den Django Admin verwaltbar; ein eigenes Nutzerformular dafür ist noch nicht Bestandteil des MVP. Wer einen Club in einer nicht unterstützten Liga eintragen möchte, benötigt zunächst eine unterstützte Liga oder später eine entsprechende Erweiterung.

**Abnahmetests #25:** Django-Tests validieren normalen POST, sofortige serverseitige Auswahl, Duplikatnamen, ungültige Felder, Länder-/Ligenwechsel, Loginpflicht, CSRF und dass die Vereinsanlage **keinen kostenpflichtigen externen API-Aufruf** benötigt.

**Umgesetzt:** Der im Dashboard ausgewählte (oder manuell angelegte) Verein kann mit Titel und geprüfter Land-/Liga-Zuordnung als persistenter, benutzerbezogener **M1-Testjob** gespeichert werden (#23/#26). **Noch nicht erledigt:** öffentliches VPS-Deployment und echte Video-Worker-/Filmproduktion (M2).
