# Offline-Weltkatalog – Verband → Land → Liga → Verein

**Umsetzung FS-011d / [#100](https://github.com/whiteyOnTheMoon/FootballStudio/issues/100)** · Datenstand: **10. November 2026**.

## Produktanforderung

Die vier Dropdown-Stufen sind **Konföderation → Nationalverband/Land → Liga → Verein**. Die App fragt dabei **ausschließlich PostgreSQL** ab. Weder im Browser noch im Django-View wird ein öffentliches API aufgerufen. Der Katalog wird aus **versionierten lokalen JSON-Dateien** eingespielt – beim ersten Docker-Start und danach idempotent beim Anwendungsstart. Spätere Updates sind **bewusste und prüfbare Daten-Releases**, keine regelmäßigen Webabrufe.

**Zielbild (Scope-Update 10.11.2026):** Alle **211 FIFA-Mitgliedsverbände**, pro Verband soweit tatsächlich vorhanden die **obersten drei nationalen Ligastufen** und ihre Teams. Verifizierbare Teilbestände und ältere datierte Saisons sind vorläufig ausdrücklich zulässig. Regionalgruppen der gleichen Stufe werden als mehrere Ligen geführt; fehlende Listen bleiben sichtbar, es werden keine Ligen oder Vereine erfunden.

## Aktuell tatsächlich enthalten

| Eigenschaft | Stand des Datenpakets | Verlässlichkeit |
| --- | ---: | --- |
| FIFA-Kontinentalverbände | 6 | Referenzverzeichnis |
| UEFA-Mitgliedsverbände | **55 von 55** | nach [UEFA-Verbandsliste](https://www.uefa.com/nationalassociations/) |
| Verbände weltweit in dieser ersten Ausgabe | **211 von 211** | FIFA-Mitgliedsverbände im Referenzverzeichnis; viele Ligen und Clubs fehlen noch |
| Nationale Liga-Referenzen weltweit | **231** | +4 belegte afrikanische Erstligen; weiterhin kein vollständiger weltweiter Top-3-Katalog |
| UEFA-Verbände mit zwei als Referenz erfassten Ligastufen | **52** | Liga-Namen **nicht automatisch als Saison 2026/27 verifiziert** |
| Teilnehmerlisten insgesamt | **106 Ligen / 1.682 Vereinsdatensätze** | 105 datierte Snapshots und 1 ausdrücklich unvollständiger A-League-Teilbestand; viele Saisons 2024/25–2025/26 |

Die 16 Club-Snapshots umfassen **England 1. und 2. Liga**, dazu jeweils die 1. Liga von Deutschland, Spanien, Frankreich, Italien, Niederlanden und Portugal. Weitere in der Datenbank gelistete Ligen haben noch **keine belegte vollständige Club-Zuordnung**. Das UI zeigt sie als Referenz und weist darauf hin, statt falsche Vereine zuzuordnen. Ein Verein aus einem fehlenden Bestand kann optional weiterhin manuell angelegt werden, **ist aber nicht Voraussetzung oder Standardweg**.

**UEFA-Ausnahmen statt falscher Zweitliganamen:**

- **Liechtenstein:** Keine eigenständige Landesliga. Alle sieben Verbandsvereine spielen im Schweizer Ligensystem. Deshalb null eigene Ligaeinträge. [LFV, Spielbetrieb 2026/27](https://www.lfv.li/breitenfussball/vereinsfussball/erwachsenenfussball/).
- **Gibraltar:** Der nationale Wettbewerb 2026/27 ist die [Gibraltar Football League](https://www.gibraltarfa.com/competitions/gibraltar-football-league-26-27-3395567), nicht eine zusätzlich erfundene zweite Männerliga.
- **San Marino:** Der [Fußballverband](https://www.fsgc.sm/en/history) dokumentiert die Abschaffung der früheren zweiten Spielklasse. Die Meisterschaft ist einstufig.

Bei **Wales** bestehen zwei regionale zweite Ligen (Cymru North und Cymru South), bei **Bosnien und Herzegowina** zwei parallele zweite Ebenen (Föderation/Republika Srpska); beide stehen als Liga-Tier 2 im Referenzkatalog.

## Datenherkunft und Lizenzen

- **UEFA:** Mitgliedschaftsliste: https://www.uefa.com/nationalassociations/
- **FIFA:** Sechs Konföderationen: https://inside.fifa.com/associations
- **OpenFootball/leagues:** Freie Wettbewerbsreferenzen (CC0): https://github.com/openfootball/leagues
- **OpenFootball/football.json:** 16 eingebettete 2026/27-Teilnehmerlisten aus OpenFootball-Spielplänen bzw. OpenLigaDB-abgeleiteten Dateien (CC0): https://github.com/openfootball/football.json/tree/master/2026-27

Die **Namen der weiteren Wettbewerbe** wurden für das erste Verzeichnis redaktionell ergänzt; ihr Status lautet **reference**, nicht *current verified*. Für neue Ligen und Saisonwechsel müssen Wettbewerb, Saison, Clubzugehörigkeit, Lizenz und Quelle vor Übernahme abgeglichen werden. Logos, Wappen und Clubfotos sind **nicht** durch diese Datensätze lizenziert.

## Umsetzung und Updateprozess

**Lokale Dateien:**
- `app/clubs/data/world_catalog.json`: Konföderationen, bestehende 106 Verbände, nationale Liga-Namen, besondere Strukturen.
- `app/clubs/data/fifa_member_associations_2026.json`: die zusätzlich aufgenommenen 105 FIFA-Verbände, bewusst ohne unbelegte Liga- und Vereinszuordnungen.
- `app/clubs/data/teams-2026-27.json`: vorherige 16 Teilnehmerlisten aus 2026/27.
- `app/clubs/data/teams-additional.json`: 17 ausdrücklich datierte OpenFootball-Listen der Saisons 2024/25, 2025, 2025/26 und 2026.
- `app/clubs/data/teams-verified-2026.json`: 6 dritte Ligastufen bzw. Gruppen in Spanien, Frankreich, Schweden und Japan, nach offiziellen öffentlichen Teilnehmerlisten; Lizenzrechte vor Weitergabe prüfen.
- `app/clubs/management/commands/seed_world_catalog.py`: idempotenter Offline-Importer ohne Netzwerkzugriff.
- `app/clubs/migrations/0003_confederation_offline_coverage.py`: Konföderationsbeziehungen, 2–3-stellige Verbandskennungen und Quell-/Abdeckungsstatus.
- `app/production/migrations/0002_global_association_code.py`: drei Zeichen für Nationalverbände (u. a. `SCO`, `WAL`, `NIR`).

**Import in bestehende Docker-Compose-Instanz:** Nach gesichertem Backup `docker compose exec web python manage.py migrate --noinput` und `docker compose exec web python manage.py seed_world_catalog`. Das Startkommando führt beides in der **lokalen Entwicklungsumgebung** bereits automatisch aus. Es werden keine bereits manuell angelegten Clubs gelöscht und keine alten Produktionsjobs überschrieben. Bei Datenänderungen den Import bewusst erneut ausführen; er prüft die sechs Kontinentalverbände, exakt 55 UEFA-Verbände und die Clublisten.

**Hinweis zu Kennungen:** Der frühere Code `GB` für England bleibt für bestehende Daten erhalten. Weitere eigenständige Heimatverbände nutzen `SCO`, `WAL` und `NIR` (Fußballverbands- statt ISO-Ländercodes); Kosovo nutzt `XK`. Das Modell bildet bewusst Fußballverbände statt ausschließlich souveräne Staaten ab.

**API:** `GET /clubs/api/confederations/`, `/countries/?confederation=UEFA`, `/leagues/?country=SCO`, `/clubs/?country=GB&league=...`, `/selection/?country=...&league=...&club=...`. Alle Endpunkte verlangen Login und senden **keine** externen HTTP-Anfragen.

## Offene Aufgaben / Abnahmekriterien

- [x] Alle sechs Konföderationen und 55 UEFA-Verbände als Offline-Verzeichnis.
- [x] Ligastufen als Referenzen, reale Sonderfälle korrekt modelliert.
- [x] Vierstufige Dropdowns und nach wie vor überprüfter M1-Testjob.
- [x] Lokale, versionierte Quellenpakete und idempotenter Import.
- [ ] **Die drei höchsten real existierenden Ligastufen und ihre Vereine je FIFA-Verband** nach und nach ergänzen; unvollständige oder ältere verifizierbare Daten sind vorerst erlaubt und müssen sichtbar gekennzeichnet werden.
- [x] Alle **211 FIFA-Mitgliedsverbände weltweit** im Offline-Verzeichnis (106 + 105 zusätzliche Referenzen).
- [ ] Für alle FIFA-Verbände die tatsächlichen Ligastufen und Clubzuordnungen vervollständigen.
- [ ] Daten-Saisonalität/Lizenzen je Liga dokumentiert abnehmen; UI-Browsertest auf Test/VPS-Host.

### Datenpaket 3: alle FIFA-Mitgliedsverbände, noch nicht alle Ligen

Der zweite Offline-Dateibestand ergänzt **105 bisher fehlende Verbände**: CAF +43,
AFC +32, CONCACAF +25 und OFC +5. Gesamt: **211 Mitgliedsverbände**
(UEFA 55, CAF 54, AFC 46, CONCACAF 35, CONMEBOL 10, OFC 11).
Die Zuordnung basiert auf dem [FIFA-Mitgliederverzeichnis](https://inside.fifa.com/about-fifa/associations)
sowie den Verzeichnissen von [CAF](https://www.cafonline.com/en/inside-caf/member-associations/),
[AFC](https://www.the-afc.com/en/about_afc/member_associations.html/),
[Concacaf](https://qa-backoffice.concacaf.com/inside-concacaf/member-associations/)
und [OFC](https://www.oceaniafootball.com/member-associations/).
AFC hat zusätzlich Northern Mariana Islands als nicht-FIFA-Mitglied; die Concacaf führt
auch Nicht-FIFA-Verbände. Hier werden bewusst **nur FIFA-Verbände** importiert.

Für die 105 ergänzten Verbände werden **keine Ligen behauptet**. Die
Oberfläche erklärt den Status „noch nicht verifiziert“, statt fiktive Wettbewerbe
oder Vereinszugehörigkeiten anzubieten. Die bereits importierten 202 Liga-Referenzen
und 278 Clubs bleiben unverändert. Die Erweiterung ist offline und beim
erneuten Import idempotent.

**Das Issue #100 darf erst nach der sachlichen Club-/Weltabdeckung geschlossen werden.** Die hier umgesetzte Softwarestruktur ist ein wichtiger, aber noch nicht abschließender Teil.

## Zusätzlich importierte Vereinslisten (UEFA – Datenpaket 2)

Die laufende Saison 2026/27 wurde in den offenen [OpenFootball-Länderdatensätzen](https://github.com/openfootball) anhand der tatsächlichen Spielpaarungen analysiert. Im lokalen Datenpaket sind neu enthalten: **Deutschlands 2. Bundesliga (18 Clubs) und 3. Liga (20)**, **Österreichs Bundesliga (12)**, **Scottish Premiership (12)**, **Swiss Super League (12)**, **Czech First League (16)**, **Super League Greece (14)** und **türkische Süper Lig (18)**. Die Gesamtzahl steigt auf **16 Vereinslisten mit 278 Clubnamen**.

Die deutschen 2./3.-Liga-Dateien stammen aus dem OpenFootball-Export von **OpenLigaDB**; sie sind als **ODbL-abgeleitet** gekennzeichnet und müssen bei einer späteren öffentlichen Weitergabe des gesamten Datenbankpakets hinsichtlich der ODbL-Lizenzpflichten überprüft werden. Diese Datensätze wurden **einmalig für das versionierte Paket** erhoben, nicht für periodische Laufzeitabfragen.

## Datenpaket 4: Weltweit drei Ligaebenen – erste belegte Teilbestände

**Neuer Product-Owner-Scope:** Nicht mehr nur 1./2. UEFA-Liga, sondern möglichst
die drei höchsten tatsächlichen Ligastufen **aller 211 FIFA-Mitgliedsverbände**.
Zunächst reicht eine belegte unvollständige Vereinsliste; Datenlücken bleiben offen.

- **227 statt 202 Ligareferenzen**: +24 belegte 3.-Stufen-Ligen/Regionalgruppen
  unter anderem in England, Spanien, Frankreich, Schweden, Österreich (vier
  Regionalligen ab 2026/27), Italien (Serie-C-Gruppen), Schottland, Niederlanden,
  Dänemark, der Schweiz, Polen, Portugal, Brasilien, Japan, China und den USA.
  Zusätzlich ist die USL Championship als unabhängige zweite US-Profidivision
  hinterlegt; das US-System ist **kein einheitlicher Auf-/Abstiegsbaum**.
- **6 neue offizielle Drittliga-Teilnehmerlisten, 110 Clubs**:
  [Spanien, 2026/27](https://rfef.es/es/noticias/aprobados-los-grupos-de-primera-federacion-para-la-temporada-202627)
  (2 × 20),
  [Frankreichs neue Ligue 3, 2026/27](https://www.fff.fr/article/17022-le-calendrier-2026-2027-est-servi.html)
  (18),
  [Schweden Ettan 2026](https://ettanfotboll.se/seriesammansattning-for-ettan-2026/)
  (2 × 16),
  [Japan J3 2026/27](https://www.jleague.jp/en/j3/standings/2026-27/)
  (20).
- **17 weitere OpenFootball-Spielplan-Snapshots, 340 Vereine** aus 2024/25,
  2025, 2025/26 oder 2026; darunter England League One, mehrere europäische
  Zweitligen und Liga-1-Listen aus Europa, Südamerika, Nordamerika, Afrika und
  Asien. Die Quelldatei ist pro Liga hinterlegt, z. B.
  [League One 2025/26](https://github.com/openfootball/football.json/blob/master/2025-26/en.3.json).
- **39 Liga-Teilnehmerlisten und 728 Clubdatensätze insgesamt**.
  Es handelt sich nicht um 728 unterschiedliche historische Clubidentitäten und
  **nicht um aktuelle Kader aller 211 Länder**.
- Die App zeigt die **Ligastufe, Regionalgruppe und Saison**. Ältere Saisons
  erhalten eine Warnung; bei Kalenderjahres-Saisons wie Schweden 2026 wird
  nicht fälschlich 2026/27 vorausgesetzt.
- Der Importer erzwingt für parallel laufende Ligen eine eindeutige Zuordnung
  über den exakten Liganamen; alte offene Vereinslisten werden nicht willkürlich
  der ersten Liga derselben Stufe zugeordnet. Offline, ohne neue Migration.

**Quellenrecht:** OpenFootball-Datenpakete sind quellenvermerkt, darunter
OpenLigaDB-abgeleitete ODbL-Daten aus dem vorherigen Release. Für offizielle
Verbandsseiten sind Fakten wie Teilnehmernamen mit URL dokumentiert, **aber
keine CC0-Lizenz behauptet**. Vor öffentlicher Weitergabe ganzer
Datensammlungen ist die rechtliche Nutzung gesondert zu prüfen.

**Weiter offen:** Alle FIFA-Verbände auf drei realen Ebenen erweitern, fehlende
Teams sowie Saisonstand schrittweise nachpflegen. Keine Anforderungen an
vollständige Ergebnisse, um eine erste Teilmenge anzubieten.

## Datenpaket 5: zusätzliche weltweite Vereinslisten aus Offline-Spielplandaten

**Quelle:** [OpenFootball Europe](https://github.com/openfootball/europe),
[OpenFootball World](https://github.com/openfootball/world) und
[OpenFootball South America](https://github.com/openfootball/south-america).
Die drei GitHub-Projekte stehen unter **CC0-1.0**. Die einmalig aus
Spielplänen extrahierten Namen sind **lokal versioniert**; der spätere
Django-Import führt keine Netzwerkabfragen aus.

**Erweiterung gegenüber Datenpaket 4:** +67 Liga-Teilnehmerlisten und
+954 Vereinsdatensätze; damit **106 erfasste Ligateilnehmerlisten
und 1.682 Vereinsdatensätze** in **231 Ligaeinträgen** bei 211 Verbänden.
Die neuen Daten decken 61 Länder/Verbände ab, darunter zahlreiche
bislang leere kleinere UEFA-Ligen, acht zusätzliche europäische
Zweitliga-Teilnehmerlisten, afrikanische Verbände, Liga 2 Nigeria, AFC,
CONCACAF und CONMEBOL. Die vier ersten Ligareferenzen für Malawi,
Ruanda, Senegal und Sambia sind separat mit Quell-URLs dokumentiert.

**Qualitätsregeln:**
- 2024/25, 2025 und 2025/26 sind historische Momentaufnahmen.
  Die App zeigt das zugehörige Jahr und warnt vor möglicher Veraltung.
- Bei der **A-League Men 2024/25** enthält die Quelle 14
  Teilnehmerpositionen, aber nur 13 echte Clubnamen; der verbleibende
  Platzhalter wird **nicht als Verein importiert**. Die Liga ist daher als
  `partial` gekennzeichnet und erhält eine eigene Warnung.
- Nicht alle Ländernamen implizieren vorhandene Liga- oder Vereinslisten.
  Fehlende zweite/dritte Ebenen werden nicht erfunden; einige
  Ligasysteme haben parallele Regionalgruppen.
- Der Import erlaubt auch belegte Ligen mit weniger als 10 Teilnehmern
  (z. B. Moldau mit 8 Clubs) und validiert Eindeutigkeit, Quellen,
  Teilabdeckung und reproduzierbare idempotente Importe.
- `teams-europe-history-a.json` bis `-e.json`,
  `teams-world-africa.json`, `teams-world-other.json` und
  `teams-world-recovered.json` enthalten die neuen Daten.

**Offen:** Alle drei realen Ebenen weltweit schrittweise ergänzen,
Saisons aktualisieren, ehemalige Vereine bei Katalogupdates revisionssicher
historisieren und tatsächliche Rechte aller Quellen vor Veröffentlichung
prüfen. Eine vollständige aktuelle Klubauswahl aller 211 Mitgliedsverbände
ist **nicht** erreicht.
