# FS-001c – Pilotvereine und Testszenarien

**Status:** M0 – Testplanung vorbereitet; **Freigabe des ersten Pilotvereins durch Product Owner ausstehend**.  
**Issue:** [#3](https://github.com/whiteyOnTheMoon/FootballStudio/issues/3) · **Roadmap:** FS-001 / M0, Pilotvereine aus Seite 4 der Version 1.0 (09.11.2026).  
**Verwandt:** [MVP-Nutzerfluss](user-flow.md), [MVP-Abnahmekriterien](acceptance-criteria.md), [M2-Filmtest #50](https://github.com/whiteyOnTheMoon/FootballStudio/issues/50), [M2-Abnahme #51](https://github.com/whiteyOnTheMoon/FootballStudio/issues/51).

## 1. Auswahlprinzip

Das erste M2-Ziel bleibt ein **einfacher, vollständiger englischsprachiger 8–10-Minuten-Film** aus der geschützten, via **Docker Compose** betriebenen Web-App. Der Pilotverein muss durch den Nutzer über **Land → Liga → Verein** ausgewählt werden können; eine fest verdrahtete Club-Auswahl erfüllt die Anforderung **nicht**.

Für die erste technische End-to-End-Abnahme ist eine **voraussichtlich praktikable Quellen- und Erzählgrundlage** hilfreich. Danach prüfen wir bewusst schwierigere Fälle. Das ist ein Planungskriterium, keine Behauptung, dass Quellen oder Medienrechte bereits geprüft wären.

## 2. Vier Kandidaten aus der Projektroadmap

| Verein | In der Roadmap vorgesehenes Testziel | Einsatz im Testplan | Status |
| --- | --- | --- | --- |
| **Malmö FF** | Historisch erzählbare internationale Ereignisse; **möglicherweise** gute Quellenlage | **Empfehlung für den ersten End-to-End-Film**: Kernpipeline und englischen Erzählbogen prüfen | Vorgeschlagen, **nicht freigegeben** |
| **SK Sturm Graz** | Längere Geschichte mit mehreren Epochen und durchgängigem Erzählbogen | Szenenplanung, Chronologie und längere Dramaturgie testen | Weitere Testoption |
| **NK Celje** | Weniger international zugängliche Quellen und Bildmaterial | Schwieriger Fall: fehlende Fakten, alternative Text-/Karten-Szenen und Medienfallback | Geplanter Belastungstest |
| **FC Zürich** | Alternativer deutschsprachiger Quellraum und Vereinsprofil | Quellenarbeit in einem weiteren deutschsprachigen Umfeld testen | Weitere Testoption |

**Grenze der Aussage:** Die Matrix übernimmt die vorgesehenen **Testzwecke aus der Roadmap**. Tatsächliche API-Abdeckung, Beleglage, Lizenzlage, Aktualität der Liga und verfügbare Medien wurden **noch nicht live geprüft**. Ergebnisse einer späteren Recherche dürfen die Reihenfolge verändern.

## 3. Empfohlene Reihenfolge (zur Entscheidung)

1. **Malmö FF als erster vollständiger M2-Pilot:** Die Roadmap sieht hier einen aussichtsreichen Erzählansatz und mögliche Quellenbreite vor. Ein einfach zu prüfender Film bietet den schnellsten Nachweis der gesamten Produktionskette.
2. **NK Celje als nächster schwieriger Quellen-/Medienfall:** Gezielter Nachweis, dass das System fehlende Informationen klar markiert und statt ungeklärter Bilder **eigene Grafiken** verwenden kann.
3. **SK Sturm Graz** zum Test einer längeren, epochenübergreifenden Geschichte.
4. **FC Zürich** zum zusätzlichen Test deutschsprachiger Quellen.

**Kein Automatismus:** Die Entscheidung über den ersten Pilotverein trifft der **Product Owner**. Eine Zustimmung in Chat oder im Issue wird nachträglich hier dokumentiert, bevor die Aufgabe #3 abgeschlossen wird.

## 4. Konkrete Prüfszenarien

### T1 – Interaktive Vereinswahl im M1-Prototyp
**Vorbedingungen:** Web-App läuft via Docker Compose; Testnutzer ist angemeldet.

- [ ] Nutzer wählt zuerst das Land; nur passende Ligen erscheinen.
- [ ] Nutzer wählt eine Liga; passende Vereine erscheinen.
- [ ] Wechsel von Land/Liga setzt darunter liegende Auswahlen zurück.
- [ ] Mindestens zwei höchste Ligen pro unterstütztem Land werden für die pilotierten Länder geprüft; Verfügbarkeitsgrenzen dokumentieren.
- [ ] Der gewählte Club wird im Testjob gespeichert und im Dashboard dargestellt.
- [ ] Bei Datenlücken funktioniert die manuelle Vereinsanlage als Fallback.
- [ ] Der Test verwendet **nicht** ausschließlich einen fest codierten Pilotclub.

**Nachweis:** Screenshots/Protokoll der Auswahl, verwendete Datenquelle und Job-ID. Implementierung in [#24](https://github.com/whiteyOnTheMoon/FootballStudio/issues/24), [#25](https://github.com/whiteyOnTheMoon/FootballStudio/issues/25), [#26](https://github.com/whiteyOnTheMoon/FootballStudio/issues/26).

### T2 – Erster durchgängiger englischer Film (M2)
- [ ] Verein über T1 ausgewählt, Titel (KI-Vorschlag oder manuell) festgelegt.
- [ ] Faktendossier mit Quellen, Drehbuch, Szenen und Medien-/Lizenzmetadaten erstellt.
- [ ] TTS, Untertitel und MP4 aus der Docker-basierten Produktionspipeline erzeugt – **ohne manuelle Montage**.
- [ ] Tatsächliche Laufzeit von **8 bis 10 Minuten** nachgemessen; Format **16:9**, Ziel **1920×1080**, interne 720p-Testausgabe zulässig.
- [ ] Geschützte Vorschau und Download von MP4 sowie Skript und Quellen geprüft.
- [ ] Jobstatus und ein gezielter Fehler-/Retry-Fall nachvollzogen.
- [ ] Keine ungeprüfte Veröffentlichung des Films.

**Nachweis:** Job-ID, generierte Ausgaben, Probe-Render, tatsächliche Medienmetadaten, Quellenliste, Retry-Protokoll. Abnahme in [#50](https://github.com/whiteyOnTheMoon/FootballStudio/issues/50) und [#51](https://github.com/whiteyOnTheMoon/FootballStudio/issues/51).

### T3 – Schwache Quellenlage / Medien fehlen (M2/M3)
**Kandidat:** **NK Celje**, vorbehaltlich Bestätigung der konkreten Datenlage bei der Recherche.

- [ ] Wenig belegte oder widersprüchliche Angaben werden **nicht als Fakten erfunden**.
- [ ] Fehlt geeignetes oder rechtlich klares Bildmaterial, werden Karten, Zeitleisten oder eigene Infografiken als Ersatz verwendet.
- [ ] Quellen und Lizenzstatus je verwendeter externer Mediendatei dokumentiert.
- [ ] Fehlende Daten führen nicht zu unbegründeten Superlativen oder erfundenen Zitaten.
- [ ] Nicht eindeutig nutzbares Material wird **nicht ungeprüft veröffentlicht**.

**Hinweis:** Belastungstest und anspruchsvollere Qualitäts-/Lizenz-Gates werden in M3 vertieft; für den M2-Prototyp muss zunächst der grundlegende sichere Fallback funktionieren.

### T4 – Komplexe Chronologie (M3/M4)
**Kandidat:** SK Sturm Graz. Über mehrere Epochen verteilte, belegbare Ereignisse werden in einer nachvollziehbaren Timeline / Szenenabfolge verarbeitet, ohne Zeitangaben zu erfinden. Umfangreiche Timeline-Templates folgen erst in M4.

### T5 – Alternativer Quellraum (M3)
**Kandidat:** FC Zürich. Quellen aus einem weiteren deutschsprachigen Umfeld werden unter Wahrung der Originalbelege in ein englisches Skript überführt; Eigennamen und Daten bleiben überprüfbar.

## 5. Dokumentation der späteren Abnahme

Zum jeweiligen Lauf werden gesammelt: Pilotclub, Land/Liga, Auswahlweg, Quelle der Clubdaten, Sprache `en`, generierter Titel, Job-ID, Pipeline-Status, MP4-Dauer/-Auflösung, Medienmetadaten und Quellenreferenzen. Der M1-Auswahltest beweist **keine** erfolgreiche M2-Filmproduktion.

**Noch nicht durchgeführt:** Live-API-Prüfung, Verfügbarkeit externer Medien, Lizenzfreigabe, Render- oder VPS-Benchmark. Diese Arbeitspakete stehen erst in späteren GitHub-Issues.

## 6. Product-Owner-Entscheidung (offen)

- [ ] **Malmö FF** als erster Pilotverein bestätigen **oder** Alternative benennen.
- [x] Vier Kandidaten mitsamt Roadmap-Testzweck dokumentiert.
- [x] Mindestens ein absichtlich schwieriger Quellen-/Medien-Testfall (NK Celje) beschrieben.
- [x] Prüfszenarien mit M1-Auswahl und Docker sowie M2-Filmabnahme verbunden.

**Erst wenn die erste Checkbox entschieden ist**, kann FS-001c / #3 als erledigt geschlossen werden.
