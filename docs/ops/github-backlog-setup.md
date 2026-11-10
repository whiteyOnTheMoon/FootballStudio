# FS-006c – GitHub-Roadmap-Metadaten und Projektboard

**Issue:** [#14](https://github.com/whiteyOnTheMoon/FootballStudio/issues/14) · **Meilenstein:** M0  
**Stand:** 10.11.2026 · **Wichtig:** Dieser Plan ist keine Behauptung, dass Milestones/Labels schon angelegt oder ein Projects-Board schon erstellt wurde.

## Einrichtung von Milestones und Labels

Das Repository enthält eine **idempotente GitHub-Action**:
- Workflow: [`.github/workflows/bootstrap-roadmap.yml`](../../.github/workflows/bootstrap-roadmap.yml)
- Script: [`scripts/bootstrap_roadmap.py`](../../scripts/bootstrap_roadmap.py)

Der Workflow wird bei Übernahme der beiden Dateien auf `main` oder durch einen späteren manuellen Workflow-Start ausgeführt. Es wird der integrierte, **auf das Repository begrenzte `GITHUB_TOKEN`** mit `issues: write` verwendet; kein persönlicher Zugriffstoken wird benötigt oder ins Repo geschrieben.

Der Script-Prozess:
1. Liest vorhandene Milestones M0–M6, legt fehlende an; lässt vorhandene unverändert.
2. Legt fehlende **Labels** für Priorität (P0–P3), Typ, Bereich und Status an.
3. Ordnet Issues mit Titeln `M0 / ...` bis `M6 / ...` dem entsprechenden GitHub-Milestone zu.
4. Übernimmt soweit vorhanden Priorität, Typ und Bereich aus dem Issue-Text als Labels.
5. Setzt `status:Done` für geschlossene Issues und `status:Backlog` bei offenen Issues ohne anderweitigen Status; bestehende manuell gesetzte offene Status bleiben erhalten.
6. Löscht **keine Issues**, keine vorhandenen fachlichen Labels und keine fremden Milestones. Pull Requests werden nicht als Issues verarbeitet.

**Sicherheitsgrenze:** Der Workflow prüft die exakte Repository-Kennung, bevor er Schreiboperationen ausführt, und verwendet keine persönlichen GitHub-Secrets. Ein zweiter Lauf soll ohne Duplikate funktionieren. Die tatsächliche Ausführung muss über die GitHub-Actions-Logs und die Milestone-/Label-Seiten überprüft werden.

## Label-Regeln

| Gruppe | Beispiele |
| --- | --- |
| Priorität | `priority:P0`, `priority:P1`, `priority:P2`, `priority:P3` |
| Typ | `type:docs`, `type:feature`, `type:research`, `type:infra`, `type:test`, `type:security`, `type:bug` |
| Bereich | `area:web`, `area:backend`, `area:research`, `area:media`, `area:audio`, `area:render`, `area:ops` |
| Status | `status:Backlog`, `status:Ready`, `status:In Progress`, `status:Review/Test`, `status:Done` |

**Sichtbarkeit:** Bis das eigentliche Projektboard bereitsteht, ermöglichen diese Labels bereits eine filterbare Issues-Ansicht.

## GitHub Projects v2 – weiterhin offen

Die Roadmap verlangt ein Board mit Spalten **Backlog**, **Ready**, **In Progress**, **Review/Test** und **Done**. GitHub Projects v2 arbeitet auf Benutzer-/Organisationsebene und benötigt **zusätzliche Projects-Berechtigungen**. Das standardmäßige GitHub-Actions-`GITHUB_TOKEN` ist repositorygebunden und kann das Board nicht erstellen.

Deshalb ist **kein** Projektboard im Workflow enthalten. Ein Board darf **nicht** als vorhanden bezeichnet werden, solange es nicht tatsächlich mit passender Berechtigung eingerichtet und verifiziert wurde. Wir verwenden zunächst die Statuslabels als nachvollziehbaren Zwischenstand. Die endgültige Einrichtung des Projektboards bleibt im Issue [#14](https://github.com/whiteyOnTheMoon/FootballStudio/issues/14) offen und wird über einen später verfügbaren Projektrechte-Zugang vorgenommen.

## Abnahmekriterien für #14

- [ ] Tatsächliche Milestones M0–M6 im Repository existieren; anhand API/Issues geprüft.
- [ ] Label-Gruppen angelegt; Statuslabels und Kategorien auf bestehende Issues angewendet.
- [ ] Bestehende Issues korrekt ihren Meilensteinen zugeordnet; Stichproben M0/M1/M2/M6.
- [ ] GitHub Projects v2 Board mit den fünf Statusspalten erstellt und Issues importiert.
- [ ] Prüfergebnis oder Blocker im Issue dokumentiert.

**Erst wenn alle fünf Prüfungen erfüllt sind, wird Issue #14 geschlossen.**

Quellen: GitHub-Dokumentation zu Milestones (https://docs.github.com/en/rest/issues/milestones) und zu separater GitHub-Projects-Authentifizierung (https://github.github.com/gh-aw/reference/auth-projects/).
