# FS-005a – Fakten-, Beleg- und Quellenmodell (MVP)

**Status:** M0-Spezifikation, noch keine implementierten Django-Modelle.  
**Roadmap:** FS-005, M0 / Seite 3 (Fakten belegen, Konflikte kennzeichnen) und M2.  
**Issue:** [#10](https://github.com/whiteyOnTheMoon/FootballStudio/issues/10).  
**Abhängigkeiten:** [Pipeline-Verträge](../architecture/pipeline-contracts.md) und [ADR-0001](../architecture/ADR-0001-mvp-stack.md).

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
