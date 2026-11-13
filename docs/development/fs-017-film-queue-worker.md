# FS-017: One-click Filmauftrag mit eigenständigem Worker

**Produktziel:** Verein auswählen → **Video erstellen**. Danach arbeitet FootballStudio selbstständig; der Quellen-/Fakteneditor ist optional. Dieses Teilstück implementiert den ersten **dauerhaften Serverauftrag**, noch nicht die fertige MP4-Produktion. Die vollständige Anforderung steht in [Issue #181](https://github.com/whiteyOnTheMoon/FootballStudio/issues/181).

## Stand des Features

- Auf der Vereinsauswahl ist **Video erstellen** jetzt die Hauptaktion. Es ist **kein manueller Arbeitstitel, keine Eingabe von P856-URLs und keine Einzelentscheidung über Fakten** nötig. Das alte M1-Testjobformular befindet sich optional unter „Erweiterte Testwerkzeuge“.
- POST `/jobs/api/film/` ist login- und CSRF-geschützt, prüft Club/League/Country gegen die aktive lokale DB und legt einen `ProductionJob(kind=film,status=queued,language=en)` an. Zwei Klicks für denselben Verein bei noch wartendem/laufendem Film liefern denselben Auftrag.
- Die Statusseite `/jobs/<job_id>/production/` ist ausschließlich für den Eigentümer lesbar, ebenso der JSON-Status `/jobs/api/film/<job_id>/`. Sie zeigt frei erfasste Dossierbausteine, aber **keine erfundene Faktensicherheit oder einen MP4-Download**. Während Warteschlange oder Bearbeitung aktualisiert sich die Seite selbstständig; ein offener Browser ist nicht erforderlich.
- Neuer dedizierter Docker-Dienst `film-worker`: Start nach dem gesunden Webservice, Datenbank-basierte `queued`-Filmjobs, `SELECT FOR UPDATE SKIP LOCKED`, Rückholung länger als eine Stunde inaktiver `running`-Jobs, 10-Sekunden-Leerlauf-Poll. Der Worker führt Recherche im eigenen Prozess aus; der Webserver bleibt frei. In der Docker-Umgebung des Workers ist `PAID_API_CALLS_ENABLED=0` **erzwungen**.
- Der Worker versucht vorhandene **kostenfreie, quellengebundene** Rechercheimporte nacheinander: Wikidata-Clubidentität, P115-Heimspielstätte, P54-Spieler, P856-Domainvorschläge, offizielle Legenden und Titel nur wenn bereits **zulässig und explizit bestätigt**. Er wechselt bei fehlenden optionalen Daten ohne weitere Benutzerklicks zur nächsten sinnvollen Stufe. Bei fehlender Clubidentität stoppt er sicher.
- **Ein vorhandener Quellenvorschlag ist keine Nutzereinwilligung**. Der Worker umgeht nie DNS-/TLS-, robots.txt-, Quellenidentitäts- oder Terms-Gates, legt keine automatischen `FactReview`-Einträge an, schaltet keine bezahlten Anbieter frei und startet keine TTS-/Filmprozesse, die noch nicht implementiert sind.
- Nach den bislang verfügbaren Schritten zeigt er einen ehrlichen Status: **Noch keine MP4**, da Story-/Quellenvertrauen, Textgenerierung, frei lizenzierte Medien und Renderdienst weiterhin fehlen. Deshalb geht der Auftrag vorerst von `running` in `failed` mit erklärendem Text. Das ist ein bewusster **Zwischenstand**, kein fertiges Video und kein stilles „success“.
- Kein neues DB-Schema notwendig: die bestehenden status-/zeitgestempelten Film-Job-Felder und Dossierversionen speichern den Zustand. Prototypen werden vom Worker **nie** ausgeführt.

## Betrieb

```bash
cd /home/ap/www/footballstudio
git pull --ff-only

docker compose -f compose.yaml -f compose.tunnel.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.tunnel.yaml ps

docker compose -f compose.yaml -f compose.tunnel.yaml \
  exec -T web python manage.py check

docker compose -f compose.yaml -f compose.tunnel.yaml \
  exec -T web python manage.py show_paid_api_budget

curl -fsS https://studio2.ap-pixels.com/healthz/
```

Es muss nun ein zusätzlicher Container `footballstudio-film-worker-1` laufen. Zu Diagnosezwecken:
```bash
docker compose -f compose.yaml -f compose.tunnel.yaml \
  logs --tail=100 --no-color film-worker
```

Alternativer gezielter Offline-Test eines einzelnen Warteschlangenauftrags in einem **Testcontainer** (nicht parallel zu dem aktiven Produktiv-Worker):

```bash
python manage.py produce_films --once
```

## Grenzen und nächste Schritte

1. Dauerhaften Produktionsfortschritt künftig in ein eigenständiges Run-/Stage-Modell mit robusten Worker-Leases statt nur Jobstatus überführen; bei Wechsel des Workerprozessmodells echte verteilte Fencing-Tokens verwenden.
2. Bessere vollautomatische Quellenfindung und maschinell belegbare, überprüfte Claim-Vertrauensentscheidung **ohne fingierte menschliche Prüfer**.
3. Ausreichend abwechslungsreiches 8–10-Minuten-Englischskript ohne Fülltext und mit nachvollziehbaren Belegen.
4. Lokal TTS und lizenzierte Medien; FFmpeg Render, persistente Dateiausgabe/Downloads und fehlergerechtes Wiederaufnehmen.
5. Den Status erst bei existierender, überprüfter MP4-Datei `completed` setzen.

**Tests:** `python manage.py test app.production.test_film_views app.production.test_film_worker`

Keine Datenmigration, keine neu freigegebene Paid API.

## FS-018: automatische Belegbewertung ohne vorgetäuschte menschliche Prüfung

Der Film-Worker berechnet nach der kostenlosen Recherche eine deterministische
maschinelle Quellenvergleichsauswertung über das jüngste private Dossier.
Die private Filmstatus-Seite zeigt das Ergebnis ohne weitere Pflichtklicks.
Es werden keine FactReview-Objekte erstellt und keine Fakten auf
verification_state=verified gesetzt.

Der erste enge, sicher auswertbare Teilfall: eine Meisterschaft oder ein
Pokalsieg in einer konkreten Saison mit corroboration=both, für den
die ursprünglich importierten offiziellen Liga- und Clubquellen
beide zugänglich und mit passender Q-ID, Saison, Kategorie und
einem eigenen Locator in derselben Dossierversion referenziert sind.
Die beiden Quellen müssen unterschiedliche Organisationsdomains
aufweisen. Ein P856-URL-Hinweis, zwei Quellen-IDs oder eine
alleinstehende Behauptung reichen ausdrücklich NICHT aus.

- matching_records: Zwei sicher zugeordnete Quellenlisten stimmen überein;
  dies ist keine Garantie für inhaltliche Wahrheit.
- listing_difference: Bei tatsächlich vorhandener zweiter Originalseite
  fehlt eine Saison in der anderen Titelliste. Das widerlegt keinen Titel.
- single_source: Der zweite Quellkontext war nicht sicher auswertbar.
- not_evaluated: Andere Themen (Gründung, Stadion, Personen) oder
  unzureichend strukturierte Daten benötigen eigene Prüfadapter.
- conflict: Dokumentierte ausdrückliche Gegenbelege oder Konfliktstatus.
- excluded: Der Nutzer hat diese Aussage ausdrücklich verworfen.

Das Ergebnis ist ausschließlich RECHERCHE: Englische Satzvorschläge
benennen lediglich die Übereinstimmung der aufgezeichneten Quellen.
approved_for_voiceover bleibt immer false; weder freigegebener
Sprechertext noch TTS/MP4 werden vorgetäuscht. Bestehende menschliche
Reviewregeln und die vorherige Skriptvorschau bleiben unverändert.

Kein weiterer Providerzugriff, keine neue Migration, keine Paid API.
Die Auswertung ist aus dem gespeicherten, owner-scoped Dossier jederzeit
reproduzierbar. Der Worker protokolliert nur die aggregierten Werte.

Der Ein-Klick-Workflow hat noch nicht automatisch Zugriff auf offizielle
Vereins-/Ligaseiten ohne zuvor zulässige Freigabe: 0 übereinstimmende
Quellpaare sind dann ein ehrliches Ergebnis. Künftig müssen weitere
kostenfrei/legal verwendbare Quellen, maschinelle Vertrauensregeln
sowie das englische Skript, TTS, Medienrechte und FFmpeg ergänzt werden.

Tests: python manage.py test app.production.test_film_claim_assessment
