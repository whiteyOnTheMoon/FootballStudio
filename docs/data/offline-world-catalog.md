# Offline-Weltkatalog – Verband → Land → Liga → Verein

**Umsetzung FS-011d / [#100](https://github.com/whiteyOnTheMoon/FootballStudio/issues/100)** · Datenstand: **10. November 2026**.

## Produktanforderung

Die vier Dropdown-Stufen sind **Konföderation → Nationalverband/Land → Liga → Verein**. Die App fragt dabei **ausschließlich PostgreSQL** ab. Weder im Browser noch im Django-View wird ein öffentliches API aufgerufen. Der Katalog wird aus **versionierten lokalen JSON-Dateien** eingespielt – beim ersten Docker-Start und danach idempotent beim Anwendungsstart. Spätere Updates sind **bewusste und prüfbare Daten-Releases**, keine regelmäßigen Webabrufe.

**Zielbild:** Alle sechs FIFA-Konföderationen und möglichst die gesamte Welt; UEFA hat Priorität. Aktuelle verfügbare Vereinszuordnungen pro Liga sind eine **gesonderte Qualitätsanforderung**, die nicht durch das Anlegen leerer Ligen erfüllt wird.

## Aktuell tatsächlich enthalten

| Eigenschaft | Stand des Datenpakets | Verlässlichkeit |
| --- | ---: | --- |
| FIFA-Kontinentalverbände | 6 | Referenzverzeichnis |
| UEFA-Mitgliedsverbände | **55 von 55** | nach [UEFA-Verbandsliste](https://www.uefa.com/nationalassociations/) |
| Verbände weltweit in dieser ersten Ausgabe | **106** | nicht 211 von 211; Ausbau noch offen |
| Nationale Liga-Referenzen weltweit | **201** | Namensverzeichnis; einzelne Wettbewerbsnamen können veraltet sein und müssen überprüft werden |
| UEFA-Verbände mit zwei als Referenz erfassten Ligastufen | **52** | Liga-Namen **nicht automatisch als Saison 2026/27 verifiziert** |
| Verifizierbare Teilnehmerlisten aus OpenFootball 2026/27 | **8 Ligen / 156 Clubs** | Stand des versionierten OpenFootball-Spielplanauszugs; zu prüfen bei Saisonwechsel |

Die acht Club-Snapshots umfassen **England 1. und 2. Liga**, dazu jeweils die 1. Liga von Deutschland, Spanien, Frankreich, Italien, Niederlanden und Portugal. Weitere in der Datenbank gelistete Ligen haben noch **keine belegte vollständige Club-Zuordnung**. Das UI zeigt sie als Referenz und weist darauf hin, statt falsche Vereine zuzuordnen. Ein Verein aus einem fehlenden Bestand kann optional weiterhin manuell angelegt werden, **ist aber nicht Voraussetzung oder Standardweg**.

**UEFA-Ausnahmen statt falscher Zweitliganamen:**

- **Liechtenstein:** Keine eigenständige Landesliga. Alle sieben Verbandsvereine spielen im Schweizer Ligensystem. Deshalb null eigene Ligaeinträge. [LFV, Spielbetrieb 2026/27](https://www.lfv.li/breitenfussball/vereinsfussball/erwachsenenfussball/).
- **Gibraltar:** Der nationale Wettbewerb 2026/27 ist die [Gibraltar Football League](https://www.gibraltarfa.com/competitions/gibraltar-football-league-26-27-3395567), nicht eine zusätzlich erfundene zweite Männerliga.
- **San Marino:** Der [Fußballverband](https://www.fsgc.sm/en/history) dokumentiert die Abschaffung der früheren zweiten Spielklasse. Die Meisterschaft ist einstufig.

Bei **Wales** bestehen zwei regionale zweite Ligen (Cymru North und Cymru South), bei **Bosnien und Herzegowina** zwei parallele zweite Ebenen (Föderation/Republika Srpska); beide stehen als Liga-Tier 2 im Referenzkatalog.

## Datenherkunft und Lizenzen

- **UEFA:** Mitgliedschaftsliste: https://www.uefa.com/nationalassociations/
- **FIFA:** Sechs Konföderationen: https://inside.fifa.com/associations
- **OpenFootball/leagues:** Freie Wettbewerbsreferenzen (CC0): https://github.com/openfootball/leagues
- **OpenFootball/football.json:** Acht eingebettete, im Stand 2026/27 verfügbare Teilnehmerlisten (CC0): https://github.com/openfootball/football.json/tree/master/2026-27

Die **Namen der weiteren Wettbewerbe** wurden für das erste Verzeichnis redaktionell ergänzt; ihr Status lautet **reference**, nicht *current verified*. Für neue Ligen und Saisonwechsel müssen Wettbewerb, Saison, Clubzugehörigkeit, Lizenz und Quelle vor Übernahme abgeglichen werden. Logos, Wappen und Clubfotos sind **nicht** durch diese Datensätze lizenziert.

## Umsetzung und Updateprozess

**Lokale Dateien:**
- `app/clubs/data/world_catalog.json`: Konföderationen, Verbände, nationale Liga-Namen, besondere Strukturen.
- `app/clubs/data/teams-2026-27.json`: mit Quelle, Saison und CC0-Lizenz versehene Teilnehmerlisten.
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
- [ ] **Vollständige tatsächlich belegte Vereinslisten für die beiden höchsten Ligen in jedem UEFA-Verband**, wo zwei Ligen existieren; Sonderfälle prüfen.
- [ ] Alle **211 FIFA-Verbände weltweit**, dann jeweils ihre real existierenden Ligastufen und Clubzuordnungen vervollständigen.
- [ ] Daten-Saisonalität/Lizenzen je Liga dokumentiert abnehmen; UI-Browsertest auf Test/VPS-Host.

**Das Issue #100 darf erst nach der sachlichen Club-/Weltabdeckung geschlossen werden.** Die hier umgesetzte Softwarestruktur ist ein wichtiger, aber noch nicht abschließender Teil.
