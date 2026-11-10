# FS-001a – MVP-Nutzerfluss und Muss-Funktionen

**Status:** M0-Arbeitsdokument, Spezifikation ohne Implementierung  
**Roadmap-Basis:** *Football Stories Studio / Projektroadmap*, Version 1.0 vom 09.11.2026; insbesondere Abschnitt 01 (Seite 2), Architektur (Seite 3) und M0–M2 (Seite 4).  
**Zugehöriges Issue:** [#1](https://github.com/whiteyOnTheMoon/FootballStudio/issues/1) · **Roadmap-ID:** FS-001

## 1. Produktziel

Football Stories Studio ist eine eigenständige, passwortgeschützte Web-Anwendung auf einem VPS. Ein angemeldeter Nutzer wählt einen Fußballverein, legt einen Titel fest und startet die automatische Produktion einer **englischsprachigen, ca. 8–10-minütigen Vereinsdokumentation**. Die App stellt anschließend das **MP4-Video**, das **Drehbuch**, die **Quellen** und den **Produktionsstatus** bereit.

Das MVP wird zunächst an einem vollständigen, einfach gestalteten End-to-End-Film gemessen. Die Qualität von Design, Medienfreigaben und Automatisierung wird in späteren Meilensteinen vertieft.

## 2. Primärer Nutzerfluss

| Schritt | Eingabe oder Aktion | Erwartetes Systemverhalten | Pflicht im MVP? |
| --- | --- | --- | --- |
| 1. Anmelden | E-Mail und Passwort | Anmeldung prüfen; alle Produktionsfunktionen nur authentifiziert anbieten | Ja |
| 2. Land wählen | Land im ersten Dropdown | Passende Ligen zur Auswahl bereitstellen | Ja |
| 3. Liga wählen | Liga im zweiten Dropdown | Vereine der Liga im dritten Dropdown bereitstellen | Ja |
| 4. Verein wählen | Verein auswählen oder bei Bedarf neu anlegen | Gewählten Verein dem geplanten Filmprojekt zuordnen | Ja |
| 5. Titel festlegen | Einen von drei KI-Vorschlägen auswählen **oder** einen Titel selbst eingeben | Gewählten Titel für den Job übernehmen | Ja, die Titelentscheidung; KI-Vorschläge sind optional |
| 6. Generieren | Produktion starten | Produktionsjob anlegen und Pipeline ausführen | Ja |
| 7. Job verfolgen | Jobansicht öffnen | Fortschritt, Status und verständliche Fehlermeldungen zeigen | Ja |
| 8. Ergebnis prüfen | Vorschau öffnen | Fertigen Film intern abspielbar bereitstellen; Drehbuch und Quellen einsehbar machen | Ja |
| 9. Ergebnis herunterladen | MP4 und Begleitdaten herunterladen | Video, Drehbuch und Quellen dem Job zugeordnet exportieren | Ja |

**Kompakt:** Anmelden → Land → Liga → Verein → Titel → Generieren → Jobstatus → Vorschau / Quellen / Drehbuch → Download.

### 2.1 Vereinswahl

- Die Auswahllogik ist kaskadierend: **Land → Liga → Verein**.
- Pro Land sollen **mindestens die beiden höchsten Ligen** verfügbar sein; eine dritte Liga ist ausdrücklich erwünscht, wo die Datenlage es ermöglicht.
- Vereinsdaten sollen möglichst über eine **freie API** bezogen werden. Die konkrete Datenquelle ist **noch nicht entschieden**.
- Nutzer können einen Verein **manuell anlegen**, falls er nicht in der Auswahl vorhanden ist.
- Fehler beim Laden von Ländern, Ligen oder Vereinen dürfen nicht zu einer unverständlichen oder blockierenden Oberfläche führen; bei fehlendem Verein bleibt die manuelle Anlage als vorgesehener Pfad.

### 2.2 Titelauswahl

- Drei KI-generierte Titelvorschläge werden zur Auswahl angeboten.
- Die Auswahl von KI-Vorschlägen ist **nicht verpflichtend**: Ein manuell eingegebener Titel muss nutzbar sein.
- Für den Produktionsstart muss genau **ein festgelegter Titel** vorliegen.
- Die konkrete KI-Anbieter- und Modellwahl gehört zu **FS-004a**, die spätere Implementierung der Oberfläche zu **FS-015a/b**.

### 2.3 Produktionsjob

Nach dem Start durchläuft ein Job die in der Roadmap vorgeschlagenen Stufen:

1. Vereinsprofil und Quellenrecherche
2. Quellenbezogenes Faktendossier und Faktenprüfung
3. Story-/Titelplanung, englisches Drehbuch und Szenenplan
4. Medienauswahl samt Quelle, Urheber und Lizenz-/Statusangaben
5. Englische Sprachausgabe (TTS)
6. Untertitel, Bildszenen und einfache Textgrafiken
7. FFmpeg-Rendering, Qualitätscheck und MP4-Export

Die Pipeline speichert **Zwischenergebnisse getrennt**, sodass ein fehlgeschlagener Render keine neue Recherche erzwingt. Die Oberfläche muss den Produktionsfortschritt und nachvollziehbare Fehler anzeigen.

### 2.4 Ergebnis und Umgang mit Quellen

- Fertige Dokumentation als **MP4**, mit interner Vorschau und Download.
- **Drehbuch und Quellen** sind für denselben Job einsehbar und exportierbar.
- Zentrale Aussagen sollen anhand gespeicherter Quellen prüfbar sein; unsichere Informationen dürfen nicht als gesicherte Tatsachen erfunden werden.
- Zu Medien werden mindestens **Quelle/URL, Urheber, Lizenz bzw. Lizenzstatus und Verwendungszweck** gespeichert.
- **Interner Prototyp ≠ Freigabe zur Veröffentlichung:** Material mit ungeklärten Rechten wird nicht ungeprüft öffentlich veröffentlicht.
- Bei knapper Materiallage sind eigene Karten, Zeitleisten und Infografiken als Ersatz vorgesehen.

## 3. Funktionale Muss-Anforderungen als User Stories

| ID | Als angemeldeter Nutzer möchte ich … | Ergebnis / Nachweis |
| --- | --- | --- |
| US-01 | mich per E-Mail und Passwort anmelden | Zugriff auf Produktionsansichten nur nach Login |
| US-02 | zunächst ein Land, dann eine Liga, dann einen Verein wählen | Dropdowns aktualisieren ihre Auswahl abhängig von der vorherigen Auswahl |
| US-03 | bei fehlendem Verein einen Eintrag selbst anlegen | Manuell angelegter Verein ist wählbar |
| US-04 | drei KI-Titelvorschläge erhalten | Drei Vorschläge werden zur Auswahl angezeigt, sofern der KI-Pfad verwendet wird |
| US-05 | alternativ einen eigenen Titel eingeben | Manueller Titel kann den Job starten |
| US-06 | eine englische Dokumentation erzeugen | Ein Produktionsjob startet aus der Web-App |
| US-07 | Fortschritt und Fehler sehen | Jobstatus und relevante Fehler sind nachvollziehbar |
| US-08 | belegbare Fakten und das Drehbuch prüfen | Quellenbezüge und englisches Skript sind dem Job zugeordnet |
| US-09 | das Video vor dem Download ansehen | Interne Vorschau des fertigen Videos funktioniert |
| US-10 | MP4, Drehbuch und Quellen herunterladen | Dateien sind dem jeweiligen Job zugeordnet |
| US-11 | Medienherkunft nachvollziehen | Medien-URLs, Urheber und Lizenz-/Statusangaben sind gespeichert |

## 4. Anforderungen an Video und Sprache

| Dimension | MVP-Festlegung laut Roadmap |
| --- | --- |
| Ausgabesprache | **Englisch** |
| Filmlänge | **Ca. 8–10 Minuten**; tatsächliche Audiodauer abschließend prüfen |
| Format | **16:9**, Ziel **1920 × 1080** |
| Interne Testauflösung | **1280 × 720** zulässig |
| Gestaltung | Anfangs einfache Fotos, Karten, Texttafeln und Untertitel statt komplexer Animationen |
| Veröffentlichung | Zunächst ausschließlich interne Vorschau und Download; externe Veröffentlichung erst nach Rechteprüfung |

## 5. Sprachen von Anfang an mitdenken

Im MVP wird nur **Englisch (`en`) produziert**. Die Architektur soll sechs Sprachvarianten unterstützen, ohne das gemeinsame Faktenmaterial zu vervielfachen:

| Phase | Sprachcodes | Verwendung |
| --- | --- | --- |
| MVP | `en` | Englisch: Skript, TTS, Untertitel, Grafiktexte, Titel und Export |
| Ab M5 | `de`, `fr`, `it`, `es`, `pt` | Deutsch, Französisch, Italienisch, Spanisch, Portugiesisch |

**Vorgesehene Trennung:** Ein möglichst sprachneutrales Vereins-/Faktendossier wird mit getrennten Skripten, TTS-Stimmen, Untertiteln, Grafikbeschriftungen, Titeln und Videoergebnissen pro Sprache verknüpft. Die Variante des Portugiesischen wird **vor M5 entschieden**.

> Hieraus entsteht **noch keine Verpflichtung**, die fünf weiteren Sprachen bereits im MVP zu implementieren.

## 6. Bewusst nicht Teil des MVP

Gemäß Roadmap ausdrücklich **später**:

- Automatische YouTube-Veröffentlichung
- Aufwendige KI-Videogenerierung
- Vollautomatische Vereinsauswahl und Ideengenerierung
- Mehrere parallele Render-Worker
- Premium-Animationen und komplexe Timeline-Bearbeitung
- Vollständige Lokalisierung in allen sechs Sprachen

Diese Nicht-Ziele dürfen nicht die Fertigstellung des ersten einfachen Films verzögern.

## 7. Prüfszenarien für diese Spezifikation

- [ ] **Login-Schutz:** Unangemeldete Nutzer können Produktionsfunktionen nicht aufrufen.
- [ ] **Kaskadierende Auswahl:** Nach Land werden nur passende Ligen angeboten; nach Liga die passenden Clubs.
- [ ] **Ligaabdeckung:** Die beiden höchsten Ligen sind das MVP-Mindestziel; eine dritte ist Wunschziel.
- [ ] **Manuelle Vereinseingabe:** Fehlender Verein ist anlegbar und auswählbar.
- [ ] **Titelwahl:** Sowohl KI-Vorschlag als auch manuelle Eingabe führen zu einem gültigen Titel.
- [ ] **Start und Status:** Ein Job kann über die Web-App erzeugt und verfolgt werden; Fehler werden sichtbar.
- [ ] **Ergebnis:** Englisches MP4 kann intern geprüft und heruntergeladen werden; Skript und Quellen sind verfügbar.
- [ ] **Quellen und Medien:** Faktenbelege und Medien-Lizenzmetadaten werden nachvollziehbar gespeichert.
- [ ] **Sprachen:** Englisch ist im MVP aktiv; Sprachvarianten sind als spätere getrennte Ergebnisse vorgesehen.

**Wichtig:** Dies sind spezifizierte Testfälle. Ihre technische Durchführung erfolgt in M1/M2; sie gelten hier **nicht** als bereits bestanden. Die formalen MVP-Abnahmekriterien werden im gesonderten **FS-001b / #2** konkretisiert.

## 8. Offene Detailentscheidungen, nicht stillschweigend festgelegt

| Frage | Weiteres Issue / Meilenstein |
| --- | --- |
| Genaues MVP-Abnahmeprotokoll und endgültiger erster Pilotverein | FS-001b / #2, FS-001c / #3 |
| Tatsächliche API für Länder/Ligen/Vereine und Abdeckung pro Land | FS-011a / #24 |
| Technologiestack-Entscheidung und Modulgrenzen | FS-002a / #4, FS-002b / #5 |
| Konkreter LLM-Anbieter, TTS-Anbieter und Kostenlimits | FS-004a / #8, FS-004b / #9 |
| Genaue Felder für Fakt-, Quellen- und Lizenzmodell | FS-005a / #10, FS-005b / #11 |
| Späteres Portugiesisch (Variante) | Vor M5 |

## 9. Dokumenten-Review für FS-001a / #1

- [x] Vollständiger Nutzerweg vom Login bis zum Download beschrieben.
- [x] Verpflichtende Funktionen und optionale Pfade voneinander abgegrenzt.
- [x] Die sechs geplanten Sprachcodes mit Englisch als erster Ausbaustufe berücksichtigt.
- [x] Keine technische Implementierung Bestandteil dieses Arbeitspakets.
- [x] Ungeklärte Fragen sind ausdrücklich markiert und nachfolgenden Issues zugeordnet.

**Referenz:** *Football Stories Studio / Projektroadmap*, Version 1.0, 09.11.2026, Seiten 1–4 und 6–8.
