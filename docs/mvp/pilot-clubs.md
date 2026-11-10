# FS-001c – Frei wählbare Vereine und Testszenarien

**Status:** M0-Spezifikation; keine Festlegung auf einen bestimmten Verein.  
**Issue:** [#3](https://github.com/whiteyOnTheMoon/FootballStudio/issues/3) · **Roadmap:** FS-001 / M0 (Version 1.0 vom 09.11.2026, Seite 4).  
**Verwandt:** [MVP-Nutzerfluss](user-flow.md), [Abnahmekriterien](acceptance-criteria.md), [M1-Auswahl #24](https://github.com/whiteyOnTheMoon/FootballStudio/issues/24), [M2-End-to-End-Test #50](https://github.com/whiteyOnTheMoon/FootballStudio/issues/50).

## 1. Verbindliche Produktentscheidung: kein festgelegter Pilotverein

Der Nutzer wählt **auch im ersten M1-Prototyp** den Verein selbst über **Land → Liga → Verein**. In M2 wird das fertige Video für **den ausgewählten Verein** produziert.

- **Kein hart codierter Verein**, keine technisch vorgegebene feste Pilotclub-Liste und keine Pflicht, Malmö FF oder einen anderen benannten Club zu verwenden.
- Nach Wahl eines Landes werden dessen unterstützte Ligen angeboten; nach Wahl einer Liga die zugehörigen Vereine. Ein Wechsel setzt abhängige Auswahlen zurück.
- Das MVP soll für jedes unterstützte Land möglichst die höchsten **zwei** Ligen anbieten, eine dritte wo die Datenquelle sie liefert. Die tatsächliche Länder-/Ligenabdeckung wird beim Adapter geprüft und dokumentiert.
- Kann ein Verein nicht über die Datenquelle gefunden werden, steht die **manuelle Vereinsanlage** zur Verfügung. Ein manuell angelegter Club kann genauso für einen Produktionsjob ausgewählt werden.
- **Testbeispiele sind keine Produktbeschränkung.** Weder die Oberfläche noch das Backend dürfen den Produktionsablauf auf die nachstehenden Beispiele begrenzen.
- Ausgewähltes Land, Liga und Verein müssen im Job nachvollziehbar gespeichert werden. Die App läuft dabei über **Docker Compose**.

Der MVP-Erfolg ist ein end-to-end erzeugter **englischer Film von 8–10 Minuten** für einen **zur Laufzeit frei ausgewählten** Verein, mit Quellen, Skript, Untertiteln und MP4-Download. Ein einzelner End-to-End-Abnahmelauf ist ausreichend, sofern die dynamische Auswahl **mit mindestens zwei unterschiedlichen Clubs** separat nachgewiesen wird.

## 2. Unverbindliche Testbeispiele aus der Roadmap

| Beispielverein | Möglicher Testschwerpunkt | Verbindlichkeit |
| --- | --- | --- |
| Malmö FF | Historischer Erzählbogen und potenziell umfangreiche Quellen | Optionales Testbeispiel |
| SK Sturm Graz | Ereignisse über mehrere Epochen | Optionales Testbeispiel |
| NK Celje | Potenziell weniger zugängliche Quellen und Medien; Fallback | Optionales Testbeispiel |
| FC Zürich | Deutschsprachige Recherchequellen | Optionales Testbeispiel |

Die vier Beispiele sind **austauschbar**. Sie stammen als Vorschläge aus der Roadmap; Quellenqualität, tatsächliche API-Erreichbarkeit und Medienrechte wurden nicht live verifiziert. Der Nutzer muss für keinen dieser Clubs eine Vorabentscheidung treffen.

## 3. Testfälle für den Prototyp und M2

### T1 – Frei wählbare Clubs und abhängige Dropdowns (M1)
- [ ] Anmeldung in der Docker-betriebenen Web-App.
- [ ] Land auswählen → passende Ligen anzeigen → Liga auswählen → passende Clubs anzeigen.
- [ ] Land- oder Ligawahl ändern → abhängige Werte zurücksetzen, keine veraltete Vereinszuordnung.
- [ ] **Zwei verschiedene Clubs aus der Datenquelle** nacheinander auswählen und jeweils als getrennten Testjob verwenden; kein vorprogrammierter Standardclub als einziger Weg.
- [ ] Für das gewählte unterstützte Land die höchsten zwei Ligen testen, sofern die Datenquelle die Abdeckung bietet; fehlende Abdeckung als Einschränkung und eigenes Issue dokumentieren.
- [ ] Nicht gefundener Verein: manuell anlegen, auswählen und Testjob anlegen; damit wird der dritte unabhängige Auswahlweg geprüft.
- [ ] Ausgewählter Verein ist für jeden Job korrekt gespeichert.

**Implementierung:** [#24](https://github.com/whiteyOnTheMoon/FootballStudio/issues/24), [#25](https://github.com/whiteyOnTheMoon/FootballStudio/issues/25), [#26](https://github.com/whiteyOnTheMoon/FootballStudio/issues/26).

### T2 – Frei ausgewählter Club wird vollständiger Film (M2)
- [ ] Einen beliebigen aus der unterstützten Auswahl **zur Laufzeit** wählen oder zuvor manuell anlegen; nicht im Code hart hinterlegen.
- [ ] Titel manuell eingeben oder aus drei KI-Vorschlägen auswählen.
- [ ] Vollständigen Job mit Recherche/Faktendossier, Quellen, Drehbuch, TTS, Grafiken, Untertiteln und MP4 im Docker-Stack durchführen.
- [ ] 8–10 Minuten tatsächliche Laufzeit prüfen; 16:9, Ziel 1080p, interne 720p-Testrender separat kennzeichnen.
- [ ] MP4, Skript und Quellen über die geschützte App ansehen und herunterladen.
- [ ] Einen Fehler-/Wiederaufnahmefall protokollieren, ohne abgeschlossene Recherche unnötig neu durchzuführen.

**Implementierung und Abnahme:** [#50](https://github.com/whiteyOnTheMoon/FootballStudio/issues/50), [#51](https://github.com/whiteyOnTheMoon/FootballStudio/issues/51). Es gibt **keine vorgeschriebene Club-ID oder vorherige Einzelfreigabe**.

### T3 – Unvollständige Quellen oder fehlende Medien (M2/M3)
- [ ] Einen Club mit tatsächlich knapper Quellen- oder Medienlage im Test auswählen; NK Celje ist ein mögliches, aber nicht vorgeschriebenes Beispiel.
- [ ] Unbelegte Aussagen nicht als gesicherte Fakten ausgeben.
- [ ] Fehlende lizenzrechtlich geeignete Bilder durch eigene Karten/Textgrafiken/Zeitleisten ersetzen.
- [ ] Quellen und Lizenzstatus verwendeter Medien nachvollziehbar speichern; ohne Freigabe nicht öffentlich publizieren.

### T4 – Zeitlich komplexe Vereinsgeschichte (M3/M4)
Einen Club mit belegbarer, längerer Chronologie aus der UI wählen (z. B. SK Sturm Graz). Epochen/Datumsangaben korrekt verarbeiten; Template-Ausbau erst M4.

### T5 – Anderer Quellraum (M3)
Einen Club mit anderen Sprachquellen wählen (z. B. FC Zürich). Originalbelege behalten und korrekt ins englische Skript übertragen.

## 4. Nachweispflicht und Grenzen

Für alle Pilotläufe: Land, Liga, Vereins-ID/Name, Datenquelle oder Kennzeichen „manuell angelegt“, Job-ID, Sprache, Titeleingabe/-auswahl, Pipeline-Status, MP4-Dauer/-Auflösung, Quellen und Medien-/Lizenzstatus protokollieren.

**Noch keine Implementierung und kein Test bestanden:** API-Abdeckung, Medienrechte, Container-Start, Renderausgabe und Mehrfachauswahl werden erst in M1/M2 tatsächlich getestet.

## 5. M0-Abnahme dieser Spezifikation

- [x] Kein bestimmter Pilotverein wird vom Product Owner verlangt.
- [x] Beispielvereine aus der Roadmap sind als **optional** gekennzeichnet.
- [x] M1 muss dynamische Vereinsauswahl in Docker bieten.
- [x] Abnahmetests mit zwei unterschiedlichen API-Clubs und einem manuell angelegten Club sind geplant.
- [x] M2-End-to-End-Video ist für einen zur Laufzeit ausgewählten Verein vorgesehen.
- [x] Schwache Fakten-/Medienlage wird als separater Testfall berücksichtigt.

Die Dokumentationsaufgabe kann damit ohne Vereinsentscheidung geschlossen werden; die eigentlichen Funktionstests bleiben in M1/M2 offen.
