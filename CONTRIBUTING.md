# Mitarbeit und GitHub-Arbeitsprozess

**Quelle:** FootballStudio-Projektroadmap v1.0, Seite 6; [Repository-Struktur](docs/development/repository-layout.md).  
**Status:** Arbeitsregeln für das Projekt. Eine bereits erledigte Dokumentationsaufgabe ist **kein** Beweis für funktionierende Laufzeitsoftware.

## Verbindlicher Ablauf

1. **Issue zuerst:** Vor technischen Arbeiten ein GitHub-Issue anlegen. Es enthält Ziel, Umfang, Nicht-Ziele, nachprüfbare Abnahmekriterien, Roadmap-Meilenstein M0–M6, Typ, Priorität, Bereich, Abhängigkeiten und Sicherheit/Kosten/Tests, wo betroffen.
2. **Klein halten:** Große Vorhaben als kleinere, überprüfbare Aufgaben führen. Bestehende Issues aktualisieren, wenn der Product Owner eine Anforderung präzisiert.
3. **Branch pro Arbeit:** Von aktuellem `main` abzweigen, z. B. `feat/fs-011a-club-picker`, `docs/fs-005b-media-rights` oder `infra/fs-007b-compose`.
4. **PR und Prüfung:** Änderungen dokumentieren, Tests **real** ausführen, Ungetestetes als offen bezeichnen. Sicherheits-, Fakten-, Lizenz- und Kostenfolgen prüfen.
5. **Mergen:** Nach Review und erfüllten Kriterien. Ein PR kann ein Issue durch `Closes #123` automatisch schließen; zuvor muss das Ergebnis nachvollziehbar sein.
6. **Betrieb:** Deployment, DNS-/TLS-/Secrets-Änderungen und Test auf dem produktiven VPS sind eigenständige, zuvor genehmigte Aufgaben. Ein Merge ist kein automatisches Deployment.

## Issue-/PR-Status

`Backlog` → `Ready` → `In Progress` → `Review / Test` → `Done`.

Die tatsächlichen GitHub-Milestones, Labels und das Projektboard werden im eigenständigen [Issue #14](https://github.com/whiteyOnTheMoon/FootballStudio/issues/14) eingerichtet; die bloße Nennung im Text bedeutet **nicht**, dass GitHub sie schon besitzt.

## Commit-/Review-Regeln

- Commit-Nachrichten kurz, fachlich und nachvollziehbar, z. B. `feat: add country-to-league selector (#24)`.
- PR-Beschreibung: Ziel, betroffene Dateien, konkrete Tests, Sicherheits-/Lizenz-/Kostenprüfung, offene Risiken.
- **Keine** Zugangsdaten oder private VPS-Daten in GitHub oder hier in Chat teilen. `.env`, generierte Filme, Produktionsrohdateien und Datenbankdumps gehören nicht ins öffentliche Repository.
- **Keine** hart codierte Club-ID. Schon M1: Land → Liga → Verein oder manuelle Anlage; M2 produziert für den tatsächlich gewählten Club.
- **Docker Compose** ist Pflicht für Web + PostgreSQL (M1) sowie getrennten Worker (M2).
- Bei unbekannter Medienlizenz nicht blind rendern/veröffentlichen; eigene, belegte Text-/Karten-/Daten-Grafiken als Ersatz.
- Fehlgeschlagene Render-Schritte gezielt wiederholen können, ohne Fakten-/Skriptrecherche unnötig zu duplizieren.

## Definition of Done

Ein Task ist fertig, wenn die Issue-Akzeptanzkriterien erfüllt sind, die Änderung auf einem nachvollziehbaren PR überprüft wurde, Testbefunde angegeben wurden, Sicherheit/Kosten/Lizenzen geprüft wurden soweit betroffen und ggf. Dokumentation/Deployment erledigt sind.

### Rollentrennung

- **Product Owner:** entscheidet über Produktfunktionen, Ausgabekriterien, Budgetobergrenzen und Veröffentlichungen.
- **Technische Umsetzung:** zerlegt Tasks, programmiert, dokumentiert, eröffnet PRs, überprüft Tests und meldet Entscheidungen/Blocker.
- Bei fehlendem VPS-Zugriff oder nicht ausgewähltem API-/TTS-Budget bleiben die konkreten betroffenen Tickets **offen**; keine erfundenen Messwerte oder stillschweigenden kostenpflichtigen Anbieterentscheidungen.

## Vorlagen

- [Technisches Issue](.github/ISSUE_TEMPLATE/technical-task.md)
- [Pull-Request-Vorlage](.github/pull_request_template.md)

**Wichtig:** Die Auswahl einer Vorlage ersetzt nicht die spätere Zuordnung zu einem echten GitHub-Milestone oder Projektboard.
