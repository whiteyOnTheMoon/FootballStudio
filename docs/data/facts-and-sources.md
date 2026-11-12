# FS-005a – Fakten-, Beleg- und Quellenmodell (MVP)

**Status:** M0-Spezifikation; erste persistente M2-Dossier-Modelle in PR #120 (#119).  
**Roadmap:** FS-005, M0 / Seite 3 (Fakten belegen, Konflikte kennzeichnen) und M2.  
**Issue:** [#10](https://github.com/whiteyOnTheMoon/FootballStudio/issues/10).  
**Abhängigkeiten:** [Pipeline-Verträge](../architecture/pipeline-contracts.md) und [ADR-0001](../architecture/ADR-0001-mvp-stack.md).

## Implementierter M2-Teilumfang (#119)

`FactDossier` ist pro `ProductionJob` und Versionsnummer eindeutig. `SourceReference`, `Fact` und `Evidence` sind relationale Django-Modelle; Belege müssen dieselbe Dossier-Version referenzieren wie ihr Fakt. `load_fact_dossier(owner=..., job_id=..., version=...)` liefert einen JSON-serialisierbaren, nur für den Job-Eigentümer lesbaren Snapshot. Ohne konkret gespeicherten, stützenden Beleg einer erreichbaren Quelle darf `Fact.save()` nicht den Status `verified` erhalten. **Auch ein solcher Beleg ersetzt keine inhaltliche Quellenprüfung.**

Die Modelle/lesende Schnittstelle sind noch nicht an die Web-UI oder die externe Recherche angebunden. Insbesondere erfolgt **kein** automatischer Wikidata-Import, keine automatische Fakten-Verifikation und keine KI/TTS-Ausgabe. M1-Testjobs bleiben unverändert. Die beschriebene Datenstruktur ist eine Grundlage; weitergehende Belegprüfung und Import folgen in #31/#32/#33.


## M2 – Offizielle Vereins- und Ligaseiten als Quellensnapshots (#136)

Der interne, **nicht per Weboberfläche aufrufbare** Dienst
`import_official_site_sources(owner=..., job_id=..., homepage_url=...,
context="club"|"league", identity_confirmed=True, terms_confirmed=True)`
nutzt die sichere, explizit ausgelöste Recherche aus #134. Er prüft
den **Job-Eigentümer vor dem ersten Netzwerkaufruf** und übernimmt
höchstens vier Seiten-Metadatensätze (Homepage + drei interne Seiten)
mit HTTPS-URL, kurzen Seitentiteln und UTC-Abrufzeitpunkten. Eine
Quellenreferenz ist noch kein inhaltlich geprüfter Beleg: neue
`Fact`- oder `Evidence`-Zeilen werden dabei **nicht** erzeugt,
und aus einer erfolgreichen HTTP-Antwort entsteht **kein** `verified`.
Artikeltexte, HTML und Überschriften werden nicht dauerhaft gespeichert.

Die Quellentypen `club_official` und das neu ergänzte
`league_official` unterscheiden Vereins- von Ligadaten. Ein
Abruf-Ergebnis muss zu Job, Club, Liga, ausdrücklich bestätigtem
Website-Kontext und Hostname passen. Alle Einträge werden vor einem
Schreibzugriff geprüft. Ein fehlerhaftes oder nicht freigegebenes
Ergebnis erzeugt **keine** neue Dossierversion.

Bei neuer Quelle wird eine **eigene versionierte Kopie des gesamten
bisherigen Dossiers** erzeugt: vorhandene Quellen, Fakten und
Belege werden mit neuen FKs derselben Version übernommen. Frühere
Versionen bleiben unverändert; vorhandene Review-Zustände werden
nur nach dem Kopieren zugehöriger Belege erhalten, nie durch neue
Quellen angehoben. Das gilt jetzt auch für weitere Wikidata-Q-IDs.
Ein zweiter identischer Import derselben offiziellen Homepage verwendet
die letzte Version ohne erneuten Netzaufruf; ein späteres bewusstes
Refresh mit eigenem Zeit-/Beleg-Snapshot ist eine separate Funktion.

**Vertrauensgrenze:** `identity_confirmed=True` und
`terms_confirmed=True` sind nur ausdrückliche Bestätigungen des
internen Aufrufers. Sie beweisen **nicht automatisch**, dass eine
Domain offiziell ist oder dass Rechte zur Weiterverwendung bestehen.
Vor jeder Nutzung muss die Zuordnung samt Nutzungsbedingungen geprüft
werden. Der Dienst ist noch nicht mit einer Review-Oberfläche verbunden.
`SourceReference.access_state="accessible"` beschreibt allein einen
erfolgreichen Abruf, nicht die Korrektheit der Website-Aussagen.

**Deployment:** Neue additive Migration
`production.0005_league_official_source` für den Quellentyp.
VPS vorher sichern und den Restore in einer Wegwerf-Datenbank prüfen.


## M2 – Atomare Faktenvorschläge aus konkreter offizieller Quelle (#139)

Der **interne** Dienst `propose_official_fact(owner=..., job_id=...,
expected_version=..., source_id=..., predicate=..., value=...,
assertion_text=..., locator=..., evidence_summary=...)` bietet eine
erste strukturierte, manuelle **Recherche-Notiz** an. Er verwendet
ausschließlich eine bereits im *angezeigten neuesten Dossier* erfasste,
erreichbare offizielle Vereins- oder Ligaquelle. Der source-ID-Bezug ist
an die Dossierversion gebunden: Quellen anderer Jobs, alte/andere
Versionen, Wikidata-Einträge und gesperrte URLs sind dafür kein Ersatz.

Unterstützte atomare Aussagen in diesem ersten Teil:
- `founded_year`: ganzzahliges Gründungsjahr (historische Angabe);
- `stadium_name`: kurzer Stadionname;
- `competition_win`: Wettbewerb **und** konkret bezeichnete Saison;
- `league_membership`: Liga **und** konkrete Saison;
- `standings_position`: Liga/Wettbewerb, Saison **und** Tabellenplatz.

Hinzu kommen ein kurzer, selbst formulierter Aussagesatz
(`assertion_text`), eine eindeutige Abschnitts-/Tabellen-Fundstelle
(`locator`) sowie eine kurze **eigene Zusammenfassung** der dort
gefundenen Aussage (`evidence_summary`). Das sind menschlich
eingegebene Vorschläge, keine automatisiert extrahierten Fakten.
**Keine vollständigen kopierten Artikel und keine ungefragten
Netzwerkzugriffe.** Der Service prüft Syntax und referenzielle
Zuordnung, nicht die Wahrheit der zugrundeliegenden Aussage.

Neue Vorschläge erhalten immer
`Fact.verification_state=unverified` und
`Evidence.role=unknown`. Selbst bei erreichbarer offizieller Quelle
gilt: Ein Locator und eine Zusammenfassung beweisen noch nicht,
dass die angegebene Fundstelle die Aussage trägt. Für eine tatsächliche
`verified`-Freigabe braucht es eine **spätere bewusste inhaltliche
Prüfung**, ggf. unabhängige Gegenquellen und Konfliktbehandlung
(Hauptissue #138, Verifikation #33).

Jeder neue Vorschlag erzeugt atomar eine vollständig geklonte
Dossierversion einschließlich Quellen/Fakten/Belegen samt neuen
Foreign Keys. Die Vorgängerversion bleibt unverändert. Identische
Wiederholungen werden ohne zusätzliche Version erkannt. Wenn zwischen
Ansicht und Eingabe eine andere Änderung erfolgt ist, wird ein
abweichender Vorschlag wegen **veralteter Version** abgewiesen.
Der Dienst ist noch **nicht** über das öffentliche Webformular
erreichbar.


## M2 – Menschlicher Faktenreview und Gegenbelege (#141)

**Nur intern, keine automatisch gestartete Recherche und keine öffentliche
Web-UI:** Zwei owner-gebundene Funktionen bearbeiten jeweils die **neueste
Dossierversion** und erfordern die konkrete `fact_id`, die angezeigte
`expected_version` sowie bei neuen Belegen die `source_id` aus exakt
derselben Version.

- `append_review_evidence(..., role="supports"|"contradicts"|"context_only",
  locator=..., summary=..., source_checked=True)` dokumentiert, welche
  konkrete Fundstelle der Anwender bewusst gegen eine Aussage gelesen hat.
  Die Quelle muss bereits zum Dossier gehören und erreichbar sein.
  Als Kontext gekennzeichnete oder unbekannte Belege begründen **keine**
  Verifikation. Die Quellenzusammenfassung ist kurz und selbst verfasst:
  **kein** massenhaftes Speichern geschützter Webseiten.
- `decide_fact_review(..., decision="verified"|"conflicted"|
  "insufficient_sources"|"rejected", review_note=...,
  review_confirmed=True, source_checked=..., season_checked=...)`
  hält eine ausdrücklich bestätigte menschliche Entscheidung fest.
  Das neue Modell `FactReview` verbindet eine Version eines Fakts mit
  dem **Eigentümer als Reviewer**, Entscheidung, knapper nachvollziehbarer
  Begründung, Quelle-/Saisonprüfflags und Review-Zeitstempel.

**Statusregeln:** `verified` erfordert einen konkret lokalisierten,
zugänglichen stützenden Beleg, eine bestätigte inhaltliche Sichtprüfung
und **keinen ungeklärten Gegenbeleg**. Bei saisonalen Aussagen muss
der Reviewer die Saison ausdrücklich bestätigen und jeder stützende
Fundstellenverweis die behauptete Saison eindeutig nennen. `conflicted`
erfordert geprüfte stützende **und** widersprechende Fundstellen.
`insufficient_sources` und `rejected` sind bewusste Entscheidungen
mit dokumentierter Begründung, kein künstlicher Ersatz für gesicherte
Fakten. Ein HTTP 200, eine Quellen-URL, ein `supports`-Label oder
eine reine Zusammenfassung führt **niemals automatisch** zu `verified`.
Die Software prüft nur Struktur/Referenzen und Reviewerbestätigungen;
sie kann die semantische Richtigkeit der Aussage **nicht beweisen**.

Jeder Änderungsvorgang erstellt **atomar eine neue vollständige
Dossierversion**, inklusive der bisheriger Quellen, Evidenzen,
Status und historischen Review-Entscheidungen. Der Aufruf mit altem
Versionsstand scheitert. Doppeltes Erfassen identischer Evidenz
oder identischer Entscheidung in derselben aktuellen Version bleibt
ohne weitere Version. Wird nach einer Freigabe ein neuer Beleg
hinzugefügt, wird das **neue** Fact vorsorglich wieder
`unverified`, der **neue** Stand verliert die alte Review-Freigabe.
Die vorherige Dossierversion mit ursprünglichem Reviewer/Zeitpunkt
bleibt als Prüfhistorie erhalten.

`load_fact_dossier` gibt die Review-Metadaten nur für den Job-Eigentümer
als `fact.review` zurück; wenn noch keine Prüfung erfolgte, ist das
Feld `null`. Zeitliche/widersprüchliche Angaben müssen weiterhin
fachlich geprüft werden, insbesondere Gründungs- und Saisondaten sowie
offizielle Darstellung vs. unabhängige Belege.

**Deployment:** Neue additive Django-Migration
`production.0006_fact_review`. Vor dem VPS-Update wie üblich
PostgreSQL-Backup **und verifizierte Testwiederherstellung** ausführen.


## M2 – Erste private Rechercheansicht im Browser (#144)

Die erste reine **Leseansicht** aus UI-Parent #143 ist unter
\`/jobs/<job_id>/research/\` erreichbar und wird bei jedem gespeicherten
M1-Testjob als **„Recherchedossier ansehen“** in der bestehenden
FootballStudio-Jobliste verlinkt. Der Nutzer muss angemeldet und
**Eigentümer des Jobs** sein, sonst folgt Redirect zum Login bzw. 404
ohne Rückschlüsse auf fremde Daten. Ein GET ohne \`?version=\` zeigt
den neuesten Dossiostand, \`?version=N\` eine ältere unveränderliche
Version. Die letzten 100 Versionen sind direkt verlinkt; eine noch
ältere bekannte Version kann explizit über den URL-Parameter
angefordert werden. Ein Job ohne importierte Recherchequellen zeigt
einen ehrlichen Leerzustand statt erfundener Fakten.

Pro Version zeigt der Server gerenderte, HTML-escaped Django-Templates:
Quellen-Titel/Typ/Abrufstatus/Original-URL/Zeitpunkt; atomare Aussage,
strukturierten Wert, Status \`unverified\`, \`verified\`, \`conflicted\`,
\`insufficient_sources\` oder \`rejected\`; jeweils Quellen-ID, Rolle,
Fundstelle und kurze Review-Zusammenfassung. Existiert eine explizite
Review-Entscheidung, sind Prüfer-ID, Zeitpunkt, Quell-/Saisoncheck und
Begründung sichtbar. Widersprüche werden klar gekennzeichnet.
Nur als öffentliche HTTPS-Referenz validierte URLs werden überhaupt
anklickbar; alle anderen URL-Strings bleiben sichtbarer Plaintext.
Fremde Daten dürfen niemals per \`innerHTML\` in die Jobliste gelangen.

**Wichtige Abgrenzung:** Das ist eine **nur lesende** Sicht auf
**bereits gespeicherte** Daten. Das Öffnen ruft **keine** Clubseite,
Wikidata-Daten, Transfermarkt, LLM oder Worker auf, speichert nichts
und führt keine automatischen Verifikationen aus. Aus einer vorhandenen
URL entsteht auch in der Anzeige keine bestätigte Aussage.
Die bewusste Domainprüfung und separate, owner-geschützte
Schreib-/Faktenreview-Bedienoberfläche folgen im Parent-Issue #143.
Für diese Änderung sind **keine neuen Datenbankmigrationen** nötig.
Der VPS muss nur nach erfolgreichem PR-Merge neu gebaut werden, damit
die zusätzliche Seite sichtbar ist.


## M2 – Faktenvorschläge über Browser erfassen (#146)

Die bisher interne, ausdrücklich **ungeprüfte** manuelle Faktenaufnahme
aus #139 ist jetzt als owner-geschütztes HTML-Formular erreichbar:
\`/jobs/<job_id>/research/facts/new/\`. Ein Link zur Maske erscheint
im aktuellen (nicht historischen) Recherchedossier genau dann, wenn
zuvor bereits mindestens eine **zugängliche offizielle Vereins- oder
Ligaquelle** für diesen Job importiert wurde. Das Formular zeigt nur
diese Quellen mit Typ, Titel und bisherigem Abrufdatum. **Eine neue,
beliebige Webadresse kann über dieses Formular weder eingegeben noch
abgerufen werden.** Für einen noch leeren Job – z. B. ein frisch
angelegtes M1-Testprojekt – wird verständlich erklärt, dass zunächst
die separat zu implementierende bestätigte Quellenaufnahme nötig ist.

Eingabefelder sind nach Faktentyp strukturiert:
\`founded_year\`, \`stadium_name\`, \`competition_win\`,
\`league_membership\` und \`standings_position\`. Saisons und
Tabellenplätze werden serverseitig typisiert und streng validiert;
alle nicht zur gewählten Faktenart gehörenden Eingaben müssen leer
bleiben. Hinzu kommen der kurze, selbst formulierte Faktensatz, eine
präzise Fundstelle, eine eigene kurze Zusammenfassung des Belegs
und die explizite Bestätigung, dass Quelle und Fundstelle **gelesen**
wurden. Letzteres ist keine \`verified\`-Entscheidung: Neue
\`Fact.verification_state\` bleiben \`unverified\`, neue
\`Evidence.role\` bleiben \`unknown\`.

Der POST verwendet die normale Django-CSRF-Middleware und prüft
zuerst die Jobzugehörigkeit zum eingeloggten Nutzer. Die Quellenauswahl
wird dynamisch auf die explizite, zu diesem Job gehörende
\`expected_version\` und die zwei erlaubten Quellentypen beschränkt.
Der interne Service sperrt den Job über \`SELECT FOR UPDATE\` und
erzeugt atomar eine **neue vollständige Dossierversion**. Exakte
Doppelübermittlungen erzeugen keinen zusätzlichen Versionsstand;
abweichende Änderungen aus einem veralteten Formular liefern
HTTP **409** mit dem Hinweis, die aktuelle Ansicht neu zu laden.
Fehlerhafte Angaben liefern 400; nach Erfolg führt
**Post/Redirect/Get** direkt zum neuen Dossiostand.

Als server- und workerübergreifendes Limit sind höchstens
**10 neue Dossierversionen pro Job und Minute** erlaubt, auf Basis
von PostgreSQL-Datensätzen statt rein lokalem In-Memory-Cache.
Das schützt die Datenbank vor schnell wiederholten Anfragen;
es ist **kein** globales Benutzer- oder IP-Request-Limit. Fehlende
CSRF-Tokens werden vor Verarbeitung abgewiesen. Die Regressionstests
decken CSRF, Identitäts-/Quellen-/Saisonvalidierung, Quell- und
Owner-Trennung, Staleness, idempotente Wiederholung und No-Network ab.

**Unverändert:** keine automatischen HTTP-Abrufe, keine KI-, TTS-,
FFmpeg- oder kostenpflichtigen APIs; das Formular erklärt keinen
Kandidaten zur offiziellen Website. Die ausdrücklich bestätigte
Quellenaufnahme sowie spätere stützende/widersprechende Belegreviews
und \`verified\`-Freigaben bleiben separate Schritte in #143 und #138.
**Keine neue Datenbankmigration** erforderlich.


## M2 – Offizielle Club-/Ligaquelle manuell im Browser bestätigen (#148)

Der **bewusst manuelle** Einstieg in die Recherche ist jetzt für
eingeloggte Job-Eigentümer unter
\`/jobs/<job_id>/research/sources/new/\` verfügbar. Die leere
und die aktuellste Dossieransicht zeigen einen Link zur Eingabemaske.
Historische Versionen bleiben lesend. Im Formular werden Job, Verein,
Liga und Quellenkontext (offizielle Vereins- oder Ligaseite) sichtbar
angezeigt. Der Nutzer muss eine konkrete Seite **außerhalb der App
selbst im Browser geprüft haben** und explizit bestätigen:

1. Domain und Inhalt sind wirklich dem ausgewählten Verein / der Liga
   zugeordnet; die Zuordnung erfolgt **nicht automatisch** durch Wikidata
   oder eine bloße URL.
2. Die Website-Bedingungen wurden zur manuellen Quellenreferenz geprüft;
   die Erklärung begründet **keine** Lizenz für fremde Texte oder Videos.
3. Die konkrete Seite war für den Nutzer manuell zugänglich; ein
   öffentliches GET vom FootballStudio-Server wird **nicht** ausgeführt.

Ein kurzer eigener Zuordnungsgrund, URL und Seitentitel sind Pflicht.
Serverseitig werden nur kanonische DNS-artige HTTPS-Adressen ohne
Credentials, Port, URL-Fragmente, Query, unzulässige Steuerzeichen oder
private/reservierte Hostnamen akzeptiert. IP-Literale, interne Testdomains,
ungeeignete Downloads und Transfermarkt als angebliche Club-/Ligaquelle
sind ausgeschlossen. **Es gibt weder DNS-Auflösung noch HTTP, robots
Fetch, Redirect-Follow-up, Artikel-Scraping oder KI/LLM-Aufruf** in
diesem Eingabepfad.

**Quellenprovenienz und Zeitangaben:** Die additive Migration
\`production.0007_source_confirmation\` ergänzt das Modell
\`SourceConfirmation\` mit genau einem Datensatz je ausdrücklich
manuell geprüfter \`SourceReference\` und Dossierversion. Er enthält
Prüfer, UTC-Bestätigungszeit, überprüften Hostnamen, bestätigte
Identitäts-/Bedingungs-/Zugangs-Aussagen und kurze eigene
Zuordnungsbegründung. Die Quelle bekommt
\`access_state=accessible\` **nur aufgrund der ausdrücklichen
manuellen Browserprüfung**, nicht aufgrund eines Serverabrufs. Das
vorhandene \`retrieved_at\`-Datenfeld erhält technisch den manuellen
Prüfzeitpunkt; die UI kennzeichnet dies explizit **„Manuell geprüft
(kein Serverabruf)“**, statt einen Abruf des Servers vorzutäuschen.
\`load_fact_dossier\` liefert die Provenienz in
\`source.manual_confirmation\` für den Eigentümer, oder \`null\` für
historische / anders importierte Quellen. Das bestätigt ausdrücklich
**nicht** die Faktenwahrheit.

**Transaktion und Limits:** Besitzerprüfung geht dem Schreibzugriff
voraus, Django-CSRF ist aktiv, alle Eingaben werden serverseitig
validiert. \`expected_version=0\` ist ausschließlich für einen
erstmals leeren Job vorgesehen. Das Produkt sperrt den Job vor
Versionsvergabe via \`SELECT FOR UPDATE\` und erstellt ein neues,
vollständiges Dossier inklusive bisheriger Quellen, Fakten,
Beleg-/Review-Historie **und** aller zuvor abgelegten manuellen
Quellenbestätigungen. Exakt identische Einsendungen sind auch nach
einem Versionswechsel idempotent; bei abweichenden Daten zur gleichen
URL folgt **409**, bei veraltetem Stand ebenfalls **409**.
Das datenbankbasierte Limit umfasst höchstens zehn neue
Dossierversionen pro Job/Minute und wird vor der Versionierung geprüft;
eine zusätzliche globale IP-Request-Drosselung ist **nicht** enthalten.
Es gibt **keine automatische Faktverifikation**, und die
manuell bestätigten Quellen werden in der Faktvorschlagsmaske
weiterhin nur für **unverified** Facts und Evidence-Rolle **unknown**
bereitgestellt.

**Deployment:** Vor \`0007\` das PostgreSQL-Backup erzeugen und die
Testwiederherstellung in einer Wegwerf-Datenbank erfolgreich prüfen.
Danach normal \`git pull --ff-only\`, Compose-Rebuild und
\`showmigrations production\`; produktives Datenvolume niemals löschen.
Die Domainfreigabe für späteres robot-/SSRF-konformes automatisiertes
Crawling sowie eine inhaltliche Freigabe einzelner Fakten bleiben
getrennte, explizite Roadmap-Schritte (#125/#143/#138).


## M2 – Bewusste Belegrollenprüfung im Browser (#150)

Der bisher interne owner-geschützte Dienst \`append_review_evidence\` aus
#141 ist jetzt über
\`/jobs/<job_id>/research/facts/<fact_id>/evidence/new/\` als mobile
Browseroberfläche für die **neueste** Dossierversion zugänglich. Jede
Faktkarte im aktuellen Dossier hat den Link „Konkrete Fundstelle
prüfen und Belegrolle ergänzen“; historische Versionen sind weiterhin
rein lesend, und ihre alten Fakt-IDs öffnen kein aktuelles Review.

Die Ansicht zeigt die konkrete atomare Aussage, ggf. die Saison und
bereits vorhandene Belegrollen, Fundstellen und kurze eigene
Belegnotizen. Auswählbar sind ausschließlich bereits im selben
Job-Dossier gespeicherte, zugängliche Quellen mit sicher
validierbaren öffentlichen HTTPS-Referenzen. Zu jeder Quelle wird
angezeigt, ob sie **manuell geprüft (kein Serverabruf)** oder früher
über einen vorhandenen Importdienst erfasst wurde; ihr Zeitstempel
wird entsprechend als manueller Prüf- oder Import-/Abrufzeitpunkt
dargestellt. Fremde Quellen oder frei eingegebene URLs sind nicht
möglich. Seiten werden nur durch einen bewussten Klick auf einen
externen HTTPS-Link im Browser geöffnet, **nie vom FootballStudio-Server
automatisch**.

Das CSRF-geschützte Formular erfordert eine explizite Bestätigung,
dass die genaue Fundstelle persönlich gelesen und mit der Aussage
verglichen wurde. Eine Belegrolle ist genau eine der Optionen
\`supports\`, \`contradicts\` oder \`context_only\`; die Fundstelle
und kurze eigene Zusammenfassung sind Pflicht. Der neue Eintrag
erzeugt eine **vollständige neue Dossierversion**, außer bei
identischer Wiederholung. Die alte Dossierversion samt Quellen,
Facts, Evidence und Review-Historie bleibt unverändert. Bei einem
bereits ausdrücklich freigegebenen Fakt führt ein **neuer** Beleg
dazu, dass der Fakt in der **neuen** Version vorsichtshalber wieder
\`unverified\` wird und erneut menschlich geprüft werden muss. Ein
\`supports\`-Beleg führt niemals automatisch zu \`verified\`.

Das Formular prüft Login/Owner, die Fakt- und Quellen-IDs **im
übermittelten Dossiostand**, alle Feld- und Textlängen sowie
\`expected_version\`. Bei abweichendem veraltetem Inhalt folgt
HTTP **409**. Ein exakt identischer Retry kann den neuesten Dossiostand
wiederverwenden, wenn der Fakt durch Klonen eindeutig identifizierbar
ist und der gleiche Beleg dort bereits existiert; alte Dossiers werden
nicht erneut geändert. Der DB-gestützte Änderungsgrenzwert aus den
anderen Formularen bleibt: höchstens zehn neue Dossierversionen
je Job/Minute (HTTP **429**). Nicht CSRF-autorisierte POSTs liefern
403. Ein HTML-Aufruf löst weder externe HTTP-/DNS-Aufrufe noch
LLM, TTS, Paid-API oder Rendering aus.

**Wichtig:** Die Form bestätigt allein, dass der Nutzer seine eigene
inhaltliche Prüfung durchgeführt hat; die Software kann die Richtigkeit
der Aussage nicht selbst beweisen. Der explizite abschließende
Entscheidungsdialog (\`verified\`, \`conflicted\`,
\`insufficient_sources\`, \`rejected\`) sowie Gegenquellen-Konsistenz
folgen separat in Parent #143. Für diese Ergänzung ist **keine
zusätzliche Datenbankmigration** erforderlich. Zur Inbetriebnahme
genügen Git-Pull und der bekannte Docker-Compose-Rebuild – sofern
die Migration \`0007_source_confirmation\` aus #148 auf dem VPS
bereits angewendet ist; andernfalls zuerst Backup/Restore-Test und
Migration wie in #148 beschrieben.


## M2 – Abschließende, explizite menschliche Faktenentscheidung im Browser (#152)

Der interne `decide_fact_review`-Dienst aus #141 ist jetzt über die
**owner-geschützte Browseroberfläche**
`/jobs/<job_id>/research/facts/<fact_id>/decision/` erreichbar.
Jede Faktkarte der **aktuellsten** Dossierversion verlinkt die
Reviewentscheidung. Historische Versionen und Fakt-IDs sind
weiterhin nur lesend; GET/POST benötigen Login, Job-Eigentum
und explizit aktuellen Dossierversionsbezug.

Angezeigt werden die konkrete Behauptung mit Datenwert/Saison,
alle aktuellen Belegrollen (`supports`, `contradicts`,
`context_only`, `unknown`), konkrete Fundstellen und eigene
Zusammenfassungen, zugängliche HTTPS-Originalquellen sowie deren
manuelle Prüfzeit beziehungsweise Abrufzeit. Bestehende Reviews
einschließlich Status, Reviewer, Begründung und Prüfzeitpunkt
bleiben sichtbar. Nicht vertrauenswürdige URLs werden **nicht**
anklickbar; alle Texte werden im Django-Template maskiert.

Der Nutzer wählt nach eigener Prüfung eine **ausdrückliche**
Entscheidung: `verified`, `conflicted`,
`insufficient_sources` oder `rejected`. Pflicht sind eine kurze
eigene Begründung von 30–500 Zeichen und die gesonderte
Bestätigung, dass die Entscheidung bewusst getroffen wurde.
`verified` setzt zusätzlich einen tatsächlichen zugänglichen,
konkret geprüften unterstützenden Beleg, bestätigtes eigenes
Quellenlesen und **keinen ungeklärten Gegenbeleg** voraus.
`conflicted` verlangt sowohl überprüfte stützende als auch
widersprechende Fundstellen; `insufficient_sources` und
`rejected` sind nachvollziehbare menschliche Bewertungen.
Saisonabhängige Fakten benötigen für `verified` außerdem
eine eigene ausdrückliche Saisonprüfung; die behauptete Saison
muss in den Fundstellen **aller** stützenden Belege stimmen.
**Ein „supports“-Label oder HTTP 200 allein verifiziert nichts.**
Die Software prüft die Belegstruktur und Bestätigungen, nicht die
inhaltliche Wahrheit. Die entscheidende Person muss das Material
tatsächlich selbst lesen.

Der POST ist durch Django-CSRF geschützt und kontrolliert
die Fakt-ID im zugehörigen Dossier sowie den Versionsstand.
Unter einem serialisierten, DB-gestützten Job-Lock wird bei einer
neuen Entscheidung **eine vollständige neue Dossierversion**
mit Quellen, Fact-/Evidence-Verknüpfungen und Review-Historie
erstellt. Prüfer, UTC-Zeitpunkt und Begründung sind in
`FactReview` dokumentiert; die ältere Version ist unverändert.
Exakt identische Entscheidungen in der aktuellen Version
werden ohne neuen Snapshot zurückgegeben. Ein identischer
Retry aus der unmittelbar vorherigen Version darf nur dann
die neueste Version liefern, wenn Fakt und **alle Belege**
unverändert geklont wurden und die damalige Entscheidung
dort exakt vorliegt. Unterschiedliche veraltete Änderungen
liefern HTTP **409**, der DB-Schreibschutz begrenzt auf
maximal zehn neue Dossierversionen pro Job/Minute (HTTP **429**).
Keine neue Datenbankmigration erforderlich.

Diese Browseraktion löst weder ein automatisches DNS-/HTTP-Crawling,
noch LLM, TTS, Video-Rendering oder kostenpflichtige API-Aufrufe aus.
Die späteren Skript-/Filmprozesse dürfen die Prüfhistorie nicht mit
einer unabhängigen technischen Beweisgarantie verwechseln. Die
Prüfung von Quellenrechten und Veröffentlichungsfähigkeit bleibt
ein gesonderter Arbeitsschritt der M2-Roadmap.


## M2 – Sichere Formulierungen für spätere englische Doku-Skripte (#154)

Der **rein deterministische** Baustein
`app.production.script_safety.prepare_script_fact(fact, sources_by_id)`
übernimmt einen atomaren Fact aus dem schon serialisierten Dossier.
`prepare_script_preview(snapshot)` stellt die Fakten in einem
gleichartigen, **read-only** Preview-Kontext zusammen. Diese Funktionen
greifen selbst **nicht** auf Django-Modelle, Datenbanken, DNS, HTTP,
LLM, TTS, Bild-/Video-Tools oder kostenpflichtige APIs zu.

Die gespeicherte `verification_state`-Angabe ist noch **keine**
automatische Skriptfreigabe. Ein Eintrag wird nur `usable`, wenn
**alle** folgenden Bedingungen zusammen erfüllt sind:

- Ein in der **aktuellen Snapshot-Version** zugeordneter
  `FactReview` hat Entscheidung `verified`, eine reale Prüfer-ID,
  den dokumentierten UTC-Prüfzeitpunkt, eine substanzielle eigene Notiz
  und die ausdrückliche Bestätigung der Quellensichtung.
- Es gibt mindestens einen konkreten `supports`-Beleg mit
  Fundstelle, eigener knapper Zusammenfassung und einer im Dossier
  vorhandenen, zugänglichen, syntaktisch sicheren HTTPS-Quelle.
  **Alle** als `supports` markierten Fundstellen müssen diese
  Anforderungen erfüllen; schon eine unvollständige oder unzugängliche
  stützende Referenz führt zur vorsichtigen Ausgabe.
- Der Reviewzeitpunkt liegt **nicht vor** dem Quellen-/Prüfzeitpunkt
  eines verwendeten Supports. Ein ausgelagerter oder nicht eindeutig
  verknüpfter Beleg darf nicht als gültiger Nachweis zählen.
- Es gibt keinen noch ungeklärten `contradicts`-Beleg – selbst eine
  inzwischen unerreichbare Gegenquelle bleibt als Warnsignal sichtbar.
- Bei saisonabhängigen Fakten muss `checked_season` ausdrücklich
  wahr sein, und **jede** stützende Fundstelle muss die **exakte**
  Saison nennen. Beispielsweise wird die Saison `2025` nicht mit
  `2025/26` gleichgesetzt; mehrere widersprüchliche Saisonbereiche
  in einem Beleg führen ebenfalls zur Zurückhaltung.
- Der gespeicherte Wert entspricht einem unterstützten strukturierten
  Faktentyp (`founded_year`, `stadium_name`, `competition_win`,
  `league_membership`, `standings_position`) und erscheint auch
  im tatsächlich geprüften Faktensatz, damit ein zwar verifiziertes,
  aber anders kodiertes Zahlen- oder Saisonfeld nicht versehentlich
  als neue Behauptung ausgegeben wird.

Die Funktion gibt **immer** eine nachvollziehbare Einstufung zurück:

- `usable`: ausschliesslich aus **validierten strukturierten Werten**
  erzeugte knappe englische Sprecherzeile. Keine Quelle, kein
  Reviewer-Freitext und kein Original-`assertion_text` wird als
  Voiceovertext kopiert.
- `caution`: neutrale englische Platzhalter/Übergänge ohne
  konkrete, unbelegte Jahreszahl, Stadionname, Saison oder Tabellenrang.
- `conflicted`: vorsichtige englische Formulierung eines offenen
  Konflikts, **ohne** angeblich richtige der strittigen Alternativen.
- `omit`: verworfener Fact liefert einen **leeren** Sprechertext;
  seine Metadaten bleiben nur für die Auditansicht erhalten.

Ein Faktenstatus kann deshalb höchstens auf `caution` oder
`conflicted` **herabgestuft**, nie durch einen Textbaustein
auf `verified` angehoben werden. Die strukturierten Gründe
(`reason_codes`), Review-Metadaten, ursprünglicher Forschungswert
und kurze Quellen-/Fundstellen-Referenzen werden getrennt vom
Sprechertext für Redakteure ausgegeben. Originale Artikeltexte,
fremde HTML-Fragmente und unkontrollierte Modellprompts gelangen
**niemals** in die Sprecherzeile.

### Private Browser-Vorschau

Unter `/jobs/<job_id>/research/script-preview/` gibt es für den
**eingeloggten Job-Eigentümer** eine gegen Schreibmethoden geschützte
`GET`-Vorschau für den neuesten Stand oder mit
`?version=N` für eine historische Dossioversion. Die vorhandene
Rechercheansicht verlinkt die Vorschau pro Version. Django prüft die
Jobzugehörigkeit **vor** dem Abruf des owner-scoped Dossiers, maskiert
alle Texte und zeigt nur sichere HTTPS-Referenzen als anklickbare
Originalquellen. `never_cache` verhindert Browser-/Proxy-Caching.
Es gibt eine sichtbare Trennung zwischen englischer Sprecherzeile,
lediglich internem Forschungswert, Prüferprovenienz und unsicheren
oder verworfenen Fakten. **Das ist noch kein generiertes
Dokumentarskript, kein Export, kein Film und keine
Veröffentlichungsfreigabe.**

Der Baustein erhält das bei #152 hinzugefügte Human-FactReview
und darf in späteren Skript- oder Sprachmodulen **nur als eigenes
streng geprüftes Eingangs-Gate**, nicht als automatisch akzeptierte
Quellenwahrheit, dienen. Regressionstests für alle vier Klassen,
alle unterstützten Faktentypen, boolesche/nicht vorhandene Werte,
falsche Jahres-/Saisongrenzen, veraltete Reviewer, Cross-Source-
Belege, XSS, Owner-Zugriff, historical snapshots und
No-Network sind Bestandteil des PR. **Keine neue Migration**,
kein Worker-Start und keine zusätzlichen API-Kosten.


## M2 – Vorabprüfung für kontrollierte offizielle Website-Recherche (#157)

Die **lesende**, owner-geschützte Ansicht
\`/jobs/<job_id>/research/preflight/\` ergänzt #148 (manuell
bestätigte offizielle Quellen), #125 (internes robots-/SSRF-geschütztes
Rechercheverfahren) und Parent #156. Sie ist aus dem **leeren und
aktuellen** Recherchedossier erreichbar; für eine noch leere
Quellenliste bietet sie den Weg zur bewussten manuellen Erfassung.

Die Liste zeigt nur auf die **aktuellste, eigene Dossioversion**
bezogene \`SourceReference\`-Einträge, wenn alle Gates erfüllt sind:
\`source_kind=club_official|league_official\`,
\`access_state=accessible\`, eine echte \`SourceConfirmation\`
mit demselben prüfenden Job-Eigentümer, allen drei ausdrücklich
bestätigten Identitäts-/Bedingungs-/Zugangsangaben, brauchbarer eigener
Zuordnungsbegründung, nicht in der Zukunft liegender Prüfzeit und
exakt mit der Quelle übereinstimmender kanonischer HTTPS-Domain.
Die Quelle durchläuft erneut die bestehende syntaktische
\`validate_manual_source_url\`-Prüfung. Wikidata-P856-Kandidaten,
unbestätigte/gesperrte Quellen, andere Jobs und historische
Quellen-IDs werden nicht freigegeben. Bei manipuliertem
\`source_id\`-Parameter wird ohne Metadatenauskunft HTTP 404
geliefert; kein Parameter darf eine URL ersetzen.

Nach bewusstem Anklicken einer Quellen-ID
(\`?source_id=N\`) zeigt der Vorabcheck **nur** die selbst bestätigte
Ausgangs-URL, ihren Host, die syntaktisch aus dem Host abgeleitete
\`robots.txt\`-Adresse sowie den originalen Prüfer, Zeitpunkt und
Zuordnungsgrund. Die Auswahl ist **keine** Bestätigung der
Server-Identität, kein Lizenznachweis und keine neue Zustimmung
zu automatischen Abrufen.

Die Übersicht nennt höchstens **eine Ausgangsseite plus drei
Unterseiten** und die obersten möglichen Recherche-Themen aus dem
bereits bestehenden Offline-Linkklassifikator. **Es werden weder
konkrete Unterseiten-URLs geraten noch ihr tatsächliches
Vorhandensein behauptet.** Welche Seiten erreichbar sind, könnte
erst ein späterer und gesondert zugelassener Rechercheauftrag mit
echtem \`robots.txt\`-Check, TLS, Domain-/IP-Prüfung und den
vorhandenen Content-/Timeout-/Delay-Limits ermitteln.

**Wesentliches Sicherheitsversprechen dieser Phase:** Nur HTTP
\`GET\` auf der eigenen, \`never_cache\`-geschützten Preflight-Seite;
\`POST\`, \`PUT\` und \`DELETE\` werden mit 405 verweigert.
Es gibt **keine** Datenbankmutation, keinen CSRF-pflichtigen
Schreibvorgang, keine DNS-Auflösung, keinen HTTP-/robots-Abruf,
keinen Worker, keine Paid-API, keinen unlizenzieren Inhalt und
keine automatische Verifikation. Der sichtbare Hinweis
„Recherche noch nicht startbar“ ist bewusst und verhindert,
dass Nutzer eine bloße früher angeklickte Quellenbestätigung
als autorisierte Crawling-Freigabe missverstehen.

**Folge-PR nach separater Sicherheitsprüfung:** neuer expliziter
einmaliger Zustimmungsdialog mit CSRF, Job-Owner-/Source-ID- und
Versionsschutz, Datenbank-Rate-Limit, zeitlich begrenztem
Worker-Lauf und dem bereits vorhandenen robots-/SSRF-sicheren
Adapter. Kein Netzwerkaufruf im normalen Preflight-GET.
Die gesamte Recherchequelle und alle daraus ggf. abgeleiteten
Fakten bleiben bis zum bewussten Human-FactReview
\`unverified\`. Für diesen ersten Preflight ist **keine
Datenbankmigration** erforderlich.


## M2 – Einmalfreigabe für offizielle Quellen als noch nicht ausgeführten Auftrag dokumentieren (#159)

Nach dem **rein lesenden** Preflight #157 kann der Besitzer eines
konkreten Jobs für genau eine bereits in der **aktuellsten**
Dossierversion enthaltene, ausdrücklich manuell bestätigte
\`SourceReference\` einen eigenen Zustimmungsdialog aufrufen:
\`/jobs/<job_id>/research/requests/source/<source_id>/\`.
Die Quelle wird wie im Preflight noch einmal auf gültige HTTPS-Adresse,
identische geprüfte Domain, Vereins-/Ligakontext, erreichbaren Status,
Prüferidentität sowie alle drei zuvor dokumentierten
\`SourceConfirmation\`-Bestätigungen geprüft. Bei Fremd- oder
historischer Quellen-ID erfolgt HTTP 404.

**Neue, unabhängige Zustimmung:** Das mobile, Django-CSRF-geschützte
Formular zeigt die genaue Ausgangsadresse, den Club-/Liga-Kontext
und das mögliche spätere Budget von **maximal einer Ausgangsseite plus
drei HTML-Unterseiten**. Der Eigentümer muss **erneut** unabhängig
bestätigen: korrekte Club-/Liga-Domain, selbst geprüfte Website-
Nutzungsbedingungen sowie seine ausdrückliche Einmalfreigabe
für den jetzt erfassten Vorgang. Bestehende manuelle Checkboxen werden
nicht als neue Crawl-Erlaubnis übernommen. Die URL wird **niemals**
aus dem POST gelesen; sie stammt ausschließlich aus dem erneut
prüfbaren neuesten Dossier.

Ein gültiger POST legt atomar genau eine
\`OfficialResearchRequest\` in der additiven Migration
\`production.0008_official_research_request\` an. Dokumentiert werden:
Job, tatsächlicher Eigentümer, versionsgebundene SourceReference,
eingefrorene kanonische Ausgangs-URL/Domain/Club-/Ligakontext,
Dossierversion, eine pro Formular neu erzeugte UUIDv4 als
Idempotenzschlüssel, drei neue Consent-Flags, UTC-Prüfzeit,
**Ablaufzeit nach 15 Minuten**, Status \`pending_worker\`,
\`attempt_count=0\` und \`max_pages=4\`.
**Es gibt derzeit überhaupt keinen Worker**, keinen automatisch
ausgeführten Rechercheauftrag, keinen Status \`completed\` und
keinen externen Website-/robots-/DNS-Aufruf. Der Eintrag ist
nur eine nachvollziehbare, befristete **Absichtserklärung**,
keine gestartete Forschung.

**Schreibsicherheit:** Der Dienst sperrt die Produktionsjob-Zeile
mittels \`transaction.atomic()\` + \`SELECT FOR UPDATE\`,
prüft aktuelle Dossierversion, URL und Eigentümer erneut und
erzwingt per Datenbank-Unique-Constraint höchstens einen noch
ausstehenden \`pending_worker\`-Eintrag pro Job. Identische erneute
POSTs mit derselben UUIDv4 dürfen einen **noch gültigen**
Eintrag wiederfinden, ohne einen zweiten zu erstellen.
Bereits stornierte, abgelaufene oder abweichende UUID-Wiederholungen
ergeben HTTP **409**, ebenso eine noch aktive zweite
Freigabe. Beim Versionswechsel wird abweichender oder veralteter
Stand zurückgewiesen; fehlende Checkboxen ergeben HTTP **400**
und fehlendes CSRF HTTP **403**. DB-basierte zusätzliche Limits:
höchstens **drei Freigaben je Eigentümer in 24 Stunden**,
davon höchstens **eine für denselben Domainhost**; bei Überschreitung
HTTP **429**. Diese Grenzen zählen auch bereits abgebrochene
oder abgelaufene Einträge und erlauben kein Fenster durch
Neustart eines Gunicorn-Workers. Bereits abgelaufene, bislang
nicht materialisiert als \`expired\` gespeicherte Einträge
werden im GET anhand der aktuellen UTC-Zeit trotzdem korrekt
als abgelaufen ausgewiesen.

Unter \`/jobs/<job_id>/research/requests/\` kann **nur der Eigentümer**
die letzten dreißig Freigaben, ihre gespeicherten Quellen-Fingerprints,
Prüf- und Ablaufzeit, Versuchszahl und tatsächlichen Status sehen.
Eine neue CSRF-geschützte \`POST\`-Aktion kann eine gültige Freigabe
nachvollziehbar **abbrechen**. Derselbe Abbruch ist idempotent;
abgelaufene Freigaben dürfen niemals reaktiviert werden.
Diese Seite ist privat und \`never_cache\`-geschützt.
Abbruch und Freigabe lösen **keine** Netzwerkanfrage aus.

**Folgearbeit / Sicherheitsgrenze:** Das Erzeugen eines Eintrags
startet kein Hintergrundverfahren, keinen Timer und keine
Sofort-Recherche. Ein späterer, separat geprüfter Worker muss
vor **jedem** Zugriff noch einmal Source-Fingerprint,
Dossier-Version/Job-Owner, Ablaufzeit, Einmaligkeit,
Nutzungsbedingungen und die unveränderten
robots-/SSRF-/TLS-/DNS-Pinning-Schutzregeln prüfen.
Ein abgelaufener Eintrag darf nicht erneut genutzt werden.
Die spätere Verarbeitung darf höchstens kurze
**unverified** Seitenmetadaten eintragen; keine Artikeltexte,
keine automatischen Fakten und keine TTS-/MP4-Pipeline.
Die Vorkehrungen dieser Phase sind **keine technische
Beweisgarantie**, dass eine vom Nutzer bestätigte Domain
tatsächlich berechtigt ist.

**Produktions-Deployment:** Vor dem Upgrade mit neuer
\`0008\`-Migration ein PostgreSQL-Backup erstellen und den
Restaurierungstest in einer isolierten Wegwerf-Datenbank
verifizieren. Danach den bestehenden Compose-Rebuild starten,
\`showmigrations production\` und den Tunnel-/Web-Healthcheck
kontrollieren. Das persistente PostgreSQL-Docker-Volume niemals
löschen.

## M2 – Einmaliger, strikt begrenzter Recherche-Worker (#161)

Nach dem **GET-only Preflight** #157 und dem **frisch bestätigten,
15 Minuten gültigen Einmal-Consent** #159 existiert nun ein gesonderter,
**nur vom Betreiber bewusst ausführbarer** Django-Managementbefehl.
Es gibt **keinen** Celery-/Cron-/Scheduler-Loop, keine automatische
Abarbeitung aller Freigaben und **keinen externen Fetch aus einer
Browser-GET/POST-Anfrage**. Ein echter Websiteabruf ist daher niemals
eine Nebenwirkung des bloßen Öffnens/Speicherns einer Zustimmung.

Die additive Migration **\`production.0009_bounded_official_research\`**
ergänzt den bestehenden \`OfficialResearchRequest\` mit
\`running\`, \`succeeded\`, \`failed\`, \`blocked\`, einer befristeten
Ausführungskennung/Lease, \`started_at\`, \`finished_at\`,
\`failure_code\`, \`result_count\` und der übernommenen
Dossierversion. Die partielle Datenbank-Eindeutigkeit umfasst
**pending und running**: pro Job höchstens eine aktive Freigabe.
Außerdem ergänzt \`OfficialResearchPage\` einen eigenständigen
Audit-Beleg pro tatsächlich gelesener HTML-Seite mit ausschließlich
kanonischer URL, kurzer Titel-/Heading-Referenz, Kategorie,
Abrufzeit und **unverified**-Status. Eine Datenbank-Constraint
verbietet \`verified\` selbst bei umgangener Modellvalidierung.
Maximal vier Seitenpositionen und eindeutige URL/Position je Request.

### Bewusste Bedienung – ausschließlich durch Betreiber

Den Managementbefehl \`run_official_research_request\` **nicht**
automatisch im Container-Startskript, in Compose \`up\`, einer
periodischen Aufgabe oder im normalen Web-Request verwenden.
Falls der Job-Eigentümer **gerade eben** im Browser für genau eine
manuell bestätigte offizielle Quelle eine Freigabe erteilt hat und
diese noch nicht abgelaufen/abgebrochen ist, kann der Betreiber
die konkrete Job-, Freigabe- und Besitzer-ID aus der privaten
Auditansicht prüfen und *einmalig* im Webcontainer aufrufen:

\`\`\`bash
docker compose -f compose.yaml -f compose.tunnel.yaml exec -T web \
  python manage.py run_official_research_request \
  --job-id JOB_ID --request-id REQUEST_ID --owner-id OWNER_ID --execute
\`\`\`

**Keine** freie Homepage-URL und keine Site-Override-Option gehören
zum Befehl. Ohne das zusätzliche explizite \`--execute\` wird nichts
ausgeführt. **Bereits abgelaufene Freigaben nicht nachholen**;
stattdessen nach einer neuen Prüfung eine neue zeitlich begrenzte
Zustimmung einholen. Keine weiteren automatischen Retries desselben
consent-Schlüssels.

### Sicherheits- und Datenfluss

1. Der Befehl beansprucht **unter \`transaction.atomic()\` und
   PostgreSQL-Job-Zeilenlock** eine frische, unbenutzte Freigabe.
   Er prüft Eigentümer, aktuelle Dossierversion, verknüpfte
   SourceReference und SourceConfirmation, kanonischen
   HTTPS-Domain-/Club-/Ligafingerprint sowie die drei zusätzlichen
   Einmal-Consent-Flags. Anschließend wird **vor dem ersten
   externen Zugriff** \`attempt_count=1\`, Status \`running\`
   und eine zufällige Lease gesetzt. Alle Locks werden vor
   Netzwerk-I/O wieder freigegeben. Ein abgestürzter/abgelaufener
   Versuch wird endgültig fehlgeschlagen, niemals neu gestartet.
2. Das bereits vorhandene \`research_official_website\` erzwingt
   **robots.txt** und dessen Disallow- und Delay-Regeln, pro
   Verbindung neu kontrollierte öffentliche DNS-Adressen,
   IP-Pinning mit Host-/SNI-/TLS-Prüfung, HTTPS-only und
   Redirect-Verbot. 403/429, CAPTCHA, blockierte/fehlende robots,
   unpassende Content-Types, übergroße Antworten und Timeouts
   dürfen nicht umgangen werden. Eine kleine konservative
   Robot-Policy kann absichtlich auch eigentlich erlaubte
   Pfade überspringen. Maximal **eine Startseite plus drei
   gleichnamige Host-Unterseiten**, keine Artikel-Downloads.
3. Mit \`time.monotonic\`, Kooperationschecks vor/nach einzelnen
   HTTPS-Aufrufen und Pausen, max. **60 Sekunden Laufbudget**,
   **70 Sekunden POSIX-Hardalarm** und **80 Sekunden DB-Lease**
   wird ein zeitlich endlicher Versuch angestrebt. Kein
   Endlosschlafen oder unbeschränkter Retry. Schon eine
   veränderte/abgebrochene/abgelaufene Freigabe bzw. Dossioversion
   blockiert vor dem nächsten Request und bei der endgültigen
   Übernahme. Ein bereits laufender Einzelrequest kann bis zu
   dessen eigenem Timeout enden, bevor ein Abbruch greift.
4. Der Server speichert **nur nach erneuter Job-/Source-/Version-/
   Lease-Prüfung unter frischem Joblock** eine vollständig
   geklonte Dossioversion; Fakten, Evidence und manuelle
   SourceConfirmations bleiben erhalten. Max. zehn neue
   Versionen pro Job/Minute. Fehlende/schädliche/abweichende
   Antworten werden vollständig verworfen; es entstehen
   weder halbfertige Dossiers noch Fake-Reviews. Die
   Ausgangsquelle behält ihre menschliche Prüfprovenienz;
   ggf. neu aufgenommene HTML-Unterseiten sind **maschinen-
   abgefragte, unverified Quellenverweise**, keine
   menschlich geprüften Behauptungen.
5. In der owner-only, \`never_cache\`-geschützten
   \`/jobs/<job_id>/research/requests/\`-Ansicht werden
   sichere Zustands-/Fehlercodes und bei Erfolg nur kurze
   Seitenmetadaten angezeigt. Sie startet bei GET nie einen
   externen Abruf. Ein laufender Versuch kann per CSRF-POST
   kooperativ abgebrochen werden. Weder technische Details
   aus Upstream-Responses noch komplette Artikeltexte werden
   in der UI gespeichert/angezeigt.

**Einschränkungen:** Die persönliche Domain-/Bedingungsprüfung
ist keine unabhängige Lizenz- oder Faktenprüfung. Dass eine URL
erreichbar ist, autorisiert weder die Reproduktion geschützter
Inhalte noch ein \`verified\`-Fact. Jede neu gefundene konkrete
Aussage muss weiterhin im menschlichen Fakten- und Belegreview
geprüft werden. Es gibt **keine** LLM-, TTS-, FFmpeg-, Paid-API-
oder Veröffentlichungsfunktion in diesem Worker. Das erste
produktive Ausführen gegen eine echte Clubdomain sollte nur
nach nochmaliger Prüfung der Websitebedingungen und robots-
Konformität durch den Betreiber erfolgen; CI verwendet
ausschließlich synthetische/mocked HTTP- und Datenbanktests.

**Deployment mit neuer Migration:** Vor \`0009\`
PostgreSQL-Backup und **verifizierten isolierten Restore**
durchführen. Danach Compose-Rebuild, \`showmigrations
production\`, Container-Healthchecks und öffentlichen
\`/healthz/\` prüfen; niemals \`down -v\` ausführen.
Ein erfolgreiches Deployment **führt keinen** der bereits
gespeicherten Requests automatisch aus.

## Grundregeln

1. Der **zur Laufzeit ausgewählte** Verein (Land → Liga → Verein, bei Bedarf manuell angelegt) bestimmt den Recherchekontext. Es gibt keine fest vorgegebene Club-ID.
2. Ein **Fakt** ist eine überprüfbare atomare Aussage; jedes im Skript als gesichert formulierte zentrale Faktum muss auf mindestens einen gespeicherten **Beleg** mit identifizierbarer **Quelle** zurückführbar sein.
3. Die Existenz einer URL ist **kein Beweis**: der Beleg muss die konkrete Aussage stützen. Fehlende, zweifelhafte oder widersprüchliche Angaben dürfen nicht als gesicherte Tatsachen ausgegeben werden.
4. Dossier und Belege bleiben **sprachneutral** (`en` zuerst in den generierten Skripten; spätere Sprachvarianten nutzen dieselben Fakten).
5. Rechercheergebnisse werden pro Job/Version gespeichert und sind bei erneutem Rendern **wiederverwendbar**. Quellenänderungen erzeugen neue Versionen statt stiller Überschreibung.

## Entitäten und vorgeschlagene Felder

### `SourceReference` – identifizierbare Quelle

| Feld | Pflicht | Zweck |
| --- | --- | --- |
| `id` | ja | stabile interne ID (UUID oder DB-Key) |
| `url` | ja | Originaladresse des konkret verwendeten Quelleneintrags (HTTPS bevorzugt) |
| `publisher` | ja, sofern bekannt | Herausgeber / Plattform, sonst „unbekannt“ |
| `title` | ja, sofern bekannt | Quellentitel oder Datensatzbeschreibung |
| `source_kind` | ja | `wikidata`, `wikipedia`, `club_official`, `news`, `other` |
| `retrieved_at` | ja | ISO-8601-Zeitstempel mit Zeitzone des letzten tatsächlichen Abrufs |
| `published_at` | optional | publizierter Zeitpunkt, falls belegbar |
| `external_id` | optional | stabile externe ID (z. B. Wikidata-Item), sofern verfügbar |
| `access_state` | ja | `accessible`, `not_found`, `unavailable`, `restricted`, `error` |
| `language` | optional | Sprachcode der Quelle, sofern bekannt |
| `retrieval_note` | optional | zurückhaltender Abruf-/Parsinghinweis ohne Tokens oder private Daten |

Eine Quelle kann mehrere Belege enthalten. **Nicht** voraussetzen, dass jede offizielle Website, Wikipedia-Seite oder Mediendatei automatisch verlässlich oder frei nutzbar ist.

### `Evidence` – konkret zugeordneter Beleg

| Feld | Pflicht | Zweck |
| --- | --- | --- |
| `id` | ja | stabiler Belegschlüssel |
| `source_id` | ja | FK auf `SourceReference` |
| `locator` | ja, soweit möglich | Abschnitt, Tabelle, Datensatz-Property oder eindeutiger Abschnittsanker |
| `excerpt_or_paraphrase` | optional | knapper erlaubter Belegauszug **oder eigene Paraphrase**, keine vollständige fremde Artikelkopie |
| `supports_fact` | ja | `supports`, `contradicts`, `context_only`, `unknown` |
| `checked_at` | optional | Zeitpunkt der konkreten Belegprüfung |
| `validation_note` | optional | Unklarheit, Einordnung, Zahlen-/Namensabgleich |

**Rechte:** Für die internen Belegverweise möglichst URLs, IDs und knappe eigene Zusammenfassungen speichern. Keine massenhafte Speicherung vollständiger urheberrechtlich geschützter Artikel voraussetzen.

### `Fact` – atomare überprüfbare Aussage

| Feld | Pflicht | Zweck |
| --- | --- | --- |
| `id` | ja | stabiler Faktenschlüssel |
| `club_id` | ja | der im Job ausgewählte Verein (kein hart codierter Testclub) |
| `predicate` | ja | z. B. `founded_year`, `stadium_name`, `competition_win` |
| `value` | ja, wenn bekannt | strukturierter Wert, Einheit/Typ passend zum Prädikat |
| `assertion_text` | ja | kurze, sprachneutrale eigene Beschreibung |
| `time_context` | optional | Datumsbereich oder „Stand der Angabe“, wenn zeitabhängig |
| `verification_state` | ja | siehe Statusmodell unten |
| `uncertainty_note` | optional | Erklärung zu Unsicherheit, Lücken oder Widersprüchen |
| `dossier_version` | ja | zu welchem gespeicherten Recherchestand dieser Fakt gehört |
| `created_at`, `updated_at` | ja | Zeitstempel |
| `evidence_ids` | ja | Liste oder relationale Join-Tabelle der Belege; kann bei ungeprüften Fakten leer sein |

**Normalisierung:** Ein Ereignis mit Datum, Gegner und Ergebnis sollte nicht als ein einziges schwer prüfbares Textfeld behandelt werden, wenn die Teilbehauptungen unterschiedlich belegt sind. `value` kann im MVP ein typisiertes JSON-Feld sein, während Kernkennungen/Relationen in PostgreSQL bleiben.

### `Dossier` und Verwendungsnachweise

- `FactDossier`: `job_id`, `club_id`, `version`, `language_neutral=true`, `built_at`, referenzierte Fakten/Quellen, `input_fingerprint`, `status`.
- `ScriptFactUsage`: `script_version`, `scene_id` optional, `fact_id`, `usage_kind` (`assertion`, `qualified`, `background`). Damit kann das fertige Skript auf den tatsächlichen Beleg zurückführen.
- Neue Recherche erzeugt eine neue Dossier-Version. Alte Produktionsjobs behalten ihren bisherigen Quellen-/Faktenstand als nachvollziehbaren Snapshot aus IDs/Artefakten.

## Verifikations- und Fehlzustände

| `verification_state` | Interpretation | Nutzung im Skript |
| --- | --- | --- |
| `verified` | mindestens ein konkreter stützender Beleg, keine ungeklärten wesentlichen Gegenbelege | sachlich formulierbar, sofern die Quelle zur Behauptung passt |
| `unverified` | Aussage vorhanden, aber noch nicht überprüft / noch kein ausreichender Beleg | nicht als sichere Tatsache darstellen |
| `conflicted` | wesentliche Quellen/Belege widersprechen einander | Konflikt kenntlich machen oder Aussage auslassen |
| `insufficient_sources` | erreichbare Quellen liefern keine ausreichende Grundlage | Ersatzszene / allgemeinere belegte Aussage nutzen |
| `rejected` | widerlegt, unzulässig oder offensichtlich fehlerhaft | nicht für eine behauptete Tatsache verwenden |

**Abgrenzung:** `SourceReference.access_state` bezeichnet den Abrufzustand; `Fact.verification_state` beschreibt **die Aussage**. Ein HTTP-200-Erfolg impliziert keine inhaltliche Faktenvalidierung. Bei widersprechenden Belegen wird nichts automatisch durch einen unbelegten Mehrheitsentscheid „korrigiert“.

**MVP-Regel:** Die Pipeline speichert diese Zustände bereits ab M2; anspruchsvolle automatische Konflikterkennung, systematische Review-Freigaben und mehrere Filme gehören zu M3 (#52/#53).

## Durchgängiges Beispiel mit fiktiven Daten

Das Beispiel **„Beispiel FC“ und alle Zahlen/URLs sind reine Testdaten**, keine Behauptungen über einen realen Fußballverein und keine abrufbaren Live-Quellen.

```json
{
  "dossier_version": 1,
  "club": {"id": "example-club-001", "name": "Beispiel FC"},
  "sources": [
    {
      "id": "source-01",
      "url": "https://example.com/club/history",
      "source_kind": "club_official",
      "retrieved_at": "2026-11-10T12:00:00Z",
      "access_state": "accessible"
    }
  ],
  "facts": [
    {
      "id": "fact-001",
      "predicate": "founded_year",
      "value": 1901,
      "assertion_text": "The club was founded in 1901.",
      "verification_state": "verified",
      "evidence": [
        {
          "source_id": "source-01",
          "locator": "History / Foundation",
          "supports_fact": "supports"
        }
      ]
    },
    {
      "id": "fact-002",
      "predicate": "stadium_name",
      "value": "Unknown",
      "assertion_text": "Current stadium name is not established.",
      "verification_state": "insufficient_sources",
      "evidence": []
    }
  ]
}
```

**Hinweis:** In der echten Implementierung darf `verified` **erst nach tatsächlichem Abruf und Aussageprüfung** gesetzt werden. Das Beispiel demonstriert ausschließlich die Datenstruktur.

## Prüfregeln und Testfälle für die spätere Implementierung

- [ ] Jede im englischen Skript als gesichert formulierte wesentliche Zahl/Behauptung ist über `ScriptFactUsage → Fact → Evidence → SourceReference` zurückverfolgbar.
- [ ] Eine 404-/Timeout-Quelle setzt einen passenden `access_state`; daraus entsteht **keine** automatisch verifizierte Tatsache.
- [ ] Zwei widersprüchliche Belege führen zu `conflicted` oder qualifizierter Darstellung; keine erfundene Auflösung.
- [ ] Fehlende Quellen ergeben `insufficient_sources`, nicht einen erfundenen Vereinsrekord.
- [ ] Die Quelle behält **Original-URL und Abrufzeitpunkt**, Fakten bleiben je Dossier-Version nachvollziehbar.
- [ ] Das Dossier übersteht Fehler/Retry im Render ohne neu durchgeführte Recherche.
- [ ] Verein aus Land → Liga → Verein und manuell angelegter Verein sind gleichermaßen zulässig.
- [ ] Keine Geheimnisse oder vollständige unzulässige Artikelkopien in Logs oder Exporten.

## Definition of Done – dieses M0-Dokument

- [x] Fakten, Belege, Quellen-URL, Abrufzeitpunkte und Unsicherheit spezifiziert.
- [x] Widerspruchs- und fehlende-Quellen-Zustände spezifiziert.
- [x] Konkret verknüpftes **fiktives** Beispielfaktum beigefügt.
- [x] Trennung zwischen M0-Datenvertrag und späteren M1-/M2-/M3-Implementierungen dargestellt.

**Folge-Issues:** Datenmodell [#22](https://github.com/whiteyOnTheMoon/FootballStudio/issues/22), Recherche/Dossier [#31–#33](https://github.com/whiteyOnTheMoon/FootballStudio/issues/31), Konfliktprüfung M3 [#52](https://github.com/whiteyOnTheMoon/FootballStudio/issues/52).


## Q-ID-Rechercheübernahme als bewusst ausgelöster M2-Schritt (#121)

`app.production.wikidata_import.import_wikidata_source(owner=..., job_id=..., qid=..., identity_confirmed=True)`
ist ein interner Python-Service ohne HTTP-Endpunkt oder Hintergrundjob. Der Aufrufer
muss zuvor den Wikidata-Eintrag für den **zur Laufzeit gewählten Verein** bewusst
bestätigen: Ein Namensgleichklang oder eine Q-ID allein sind kein Identitätsbeleg.

Zuerst wird geprüft, ob der Job dem aufrufenden Nutzer gehört. Nur dann werden
eventuell öffentliche Wikidata-Daten abgerufen (ohne Paid-API). Gespeichert
werden ausschließlich die zurückgegebene SourceReference, der sichere
EntityData-Link, die Q-ID und der Abrufzeitpunkt. Eine bereits in der letzten
Dossierversion vorhandene Q-ID wird ohne weiteren Netzaufruf wiederverwendet;
bei einer anderen bestätigten Q-ID entsteht ein neuer, getrennter
Versionsstand. Ein Netzwerk- oder Schemafehler speichert keine Teilversion.

**Wichtig:** Die neue Version enthält zunächst weder Fakten noch Belege.
Die Importfunktion setzt deshalb niemals `verification_state=verified`.
Belegextraktion, Club-Identitätsprüfung, mögliche Widersprüche und die
spätere Bedienoberfläche folgen separat in #31/#32/#33.
