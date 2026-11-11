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
