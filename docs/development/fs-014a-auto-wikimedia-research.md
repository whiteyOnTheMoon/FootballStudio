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
