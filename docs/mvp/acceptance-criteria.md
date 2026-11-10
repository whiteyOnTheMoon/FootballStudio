# FS-001b – MVP-Abnahme, Quality Gates und Nicht-Ziele

**Status:** M0-Spezifikation / geplanter Abnahmevertrag – noch **nicht** technisch erfüllt.  
**Issue:** [#2](https://github.com/whiteyOnTheMoon/FootballStudio/issues/2) · **Roadmap-Referenz:** FS-001, M0–M2.  
**Basis:** *Football Stories Studio / Projektroadmap*, Version 1.0, 09.11.2026, besonders Seiten 2–5; [FS-001a – Nutzerfluss](user-flow.md).  
**Ziel:** Gemeinsames, beobachtbares Verständnis von „MVP fertig“.

## 1. Definition des MVP-Erfolgs

Der **MVP ist abgenommen**, wenn ein angemeldeter Nutzer über die Web-App für einen selbst ausgewählten Fußballverein **ohne manuelle Bearbeitung von Produktionsdateien** einen **vollständigen englischen, ungefähr 8–10-minütigen Film** erzeugen, **intern ansehen** und **als abspielbare MP4 herunterladen** kann. Das englische **Drehbuch** und die **wesentlichen Faktenquellen** stehen im selben Job zur Prüfung bereit. Produktionsstatus und Fehler lassen sich nachvollziehen.

Die Abnahme ist ein **End-to-End-Test**, kein Nachweis allein durch funktionierende Einzelmodule oder einen manuell montierten Beispielfilm.

Die M0/M1/M2-Stufen sind unabhängig:
- **M0:** Anforderungen und Nachweise sind spezifiziert – keine implementierte App wird behauptet.
- **M1:** HTTPS, Login, **Land → Liga → Verein**, Testjob und **Docker-Compose-Betrieb** funktionieren.
- **M2:** Ein vollständiges englisches Video wird **aus dem Docker-betriebenen Stack** über die App tatsächlich generiert, geprüft und heruntergeladen.

### Verbindliche Produktentscheidung vom 10.11.2026

Bereits der **M1-Prototyp** muss **Land → Liga → Verein** als kaskadierende Auswahl anbieten (keine ausschließlich manuelle Texteingabe und kein fest verdrahteter Pilotclub). Der M1-Prototyp und die M2-Filmproduktion laufen **in Docker**; **Docker Compose** startet die Web-App und die PostgreSQL-Datenbank in getrennten Containern, ab M2 zusätzlich den Background-Worker. Die Containerisierung ist ein **MVP-Pflichtkriterium**, nicht nur eine mögliche spätere Deployment-Option.

## 2. Messbare Abnahmekriterien

Die Kennungen `AC-XX` dienen als Abnahme-Checkliste. Ein Punkt gilt erst als **bestanden**, wenn ein entsprechender Nachweis im M1-/M2-Pilotprotokoll dokumentiert wurde.

| Gate | Kriterium | Prüfmethode / erwarteter Nachweis | Voraussetzung |
| --- | --- | --- | --- |
| AC-01 | Die Web-App ist unter **https://studio2.ap-pixels.com** erreichbar. | HTTPS-Aufruf und Zertifikatsprüfung dokumentiert; kein erzwungenes unsicheres HTTP. | M1 · FS-012 |
| AC-02 | Nur angemeldete Nutzer erreichen Produktionsfunktionen. | Test: unautorisierter Aufruf wird geblockt; korrekter E-Mail-/Passwort-Login ermöglicht Zugriff; Logout beendet Zugriff. | M1 · FS-009 |
| AC-03 | **Bereits im M1-Prototyp:** **Land → Liga → Verein** als kaskadierende Dropdowns; mindestens zwei höchste Ligen je unterstütztem Land, dritte wenn verfügbar. Keine fest codierte Clubauswahl als einziger Weg. | Land wählen → passende Ligen → passende Vereine; bei Land-/Ligawechsel abhängige Auswahl zurücksetzen; Pilotverein direkt auswählen und im Testjob nachweisen. | M1 · FS-011a/011c |
| AC-04 | Ein Verein ist **auch manuell** anlegbar und für einen Job nutzbar. | Verein außerhalb der API-Auswahl anlegen und im Formular auswählen. | M1 · FS-011b |
| AC-05 | Titelwahl funktioniert über **drei KI-Vorschläge** oder **manuellen Titel**. | Beide Pfade durchspielen; gewählter Titel erscheint im Job. | M2 · FS-015 |
| AC-06 | Ein Nutzer startet eine Produktion über die Web-App; der Job ist eindeutig erkennbar. | Job-ID, zugeordneter Verein, Titel, Sprache und Startstatus prüfen. | M1/M2 · FS-010/011/020 |
| AC-07 | Recherche erzeugt ein **strukturiertes Faktendossier** mit prüfbaren Quellverweisen. | Wesentliche Aussagen im Drehbuch mit im Job gespeicherten Belegen vergleichen; unbelegte Tatsachen werden nicht erfunden. | M2 · FS-014/016 |
| AC-08 | Die Medienauswahl dokumentiert **URL, Urheber, Lizenz bzw. Lizenzstatus und Verwendung**. | Metadaten je verwendetem externen Medium überprüfen; ungeklärtes Material ist als solches markiert. | M2 · FS-017 |
| AC-09 | Ein **englisches Drehbuch** und ein **Szenenplan** sind vorhanden. | Gespeichertes Skript und Szenenplan anhand des ausgewählten Vereins und Titels prüfen; erkennbarer Erzählbogen. | M2 · FS-016 |
| AC-10 | TTS, Szenengrafiken und **englische Untertitel** sind im Video enthalten. | Video abspielen: Ton verständlich, Bildszenen vorhanden, Untertitel zeitlich passend und lesbar. | M2 · FS-018/019 |
| AC-11 | Der **exportierte Film** ist insgesamt **8–10 Minuten** lang. | Tatsächliche Audio- und MP4-Dauer mit Medien-Tools auslesen und im Prüfprotokoll festhalten; nicht nur Wortzahl schätzen. | M2 · FS-018/022 |
| AC-12 | Export ist ein **abspielbares MP4 in 16:9**. **1920×1080 ist Zielauflösung**; **1280×720 ist für interne Testrender zulässig**. | Container, Video-/Audiostream, Seitenverhältnis und tatsächliche Pixelauflösung automatisch prüfen. Eine geringere finale Auflösung ist **nicht stillschweigend** als 1080p-Erfolg zu deklarieren, sondern als Abweichung zu entscheiden. | M2 · FS-019/022 |
| AC-13 | Die Oberfläche zeigt **Jobstatus, nachvollziehbare Fehler und Fortschritt**. | Erfolgreichen Lauf und einen kontrollierten Fehlerfall ansehen; Meldungen auf betroffene Stufe zurückführen. | M2 · FS-020 |
| AC-14 | Ein fehlgeschlagener späterer Schritt ist **ohne erneute vollständige Recherche** wiederholbar. | Nach gespeichertem Faktendossier einen späteren Testfehler auslösen und betroffenen Schritt neu ausführen; vorhandenes Dossier bleibt erhalten. | M2 · FS-020 |
| AC-15 | **Interne Vorschau** und **geschützter MP4-Download** funktionieren. | Als eingeloggter Nutzer abspielen und herunterladen; als nicht eingeloggter Nutzer keine geschützten Produktionsdateien abrufen. | M2 · FS-021 |
| AC-16 | **Drehbuch und Quellen** können eingesehen und als Begleitdaten exportiert werden. | Heruntergeladene Dateien einem Job zuordnen und Inhalt öffnen; Medienmetadaten sind zuordenbar. | M2 · FS-021 |
| AC-17 | Der vollständige Job läuft **ohne manuelle Dateimontage** und erzeugt einen für das Pilotteam verständlichen Film. | Ein End-to-End-Lauf direkt aus der App; Prüfer bestätigt verständlichen Erzählfluss und dokumentiert Mängel. | M2 · FS-022 |

| AC-18 | **Docker-Pflicht ab M1 und M2:** Django-Web-App läuft in eigenem Container; PostgreSQL in separatem Compose-Service mit persistentem Volume; M2-Worker ebenfalls containerisiert. | `docker compose up -d --build` auf Testhost/VPS ausführen; Healthchecks/Logs prüfen; DB-Daten nach Neustart erhalten; Login, Auswahl und Testjob aus dem Stack demonstrieren; M2-Render im Worker-Container nachweisen. | M1 · FS-007b/008a; M2 · FS-020a/022b |

**Präzisierung:** „Reproduzierbar“ bezeichnet einen **erneut startbaren und nachvollziehbaren Prozess** mit gespeicherten Zwischenständen. Wegen externer Quellen, LLM und TTS wird **keine bitgenaue identische MP4-Datei** bei Wiederholung versprochen.

## 3. Minimaler Testlauf zur M2-Abnahme

**Vorbereitung:** Pilotverein wird in [FS-001c / #3](https://github.com/whiteyOnTheMoon/FootballStudio/issues/3) gewählt. VPS-Ressourcen, API und TTS-Kostenlimits werden in [#6–#9](https://github.com/whiteyOnTheMoon/FootballStudio/issues/6) konkretisiert. Testkonto mit angemeldeter Sitzung bereitstellen.

**Durchführung und Nachweise:** Vor Beginn den Docker-Compose-Stack starten und Web-/DB-/Worker-Status dokumentieren; direkte Host-Python-Ausführung zählt nicht als Nachweis.

1. HTTPS/Login prüfen und Pilotland, Liga und Verein auswählen; für die manuelle Anlage separaten Testfall durchführen.
2. Drei Titelvorschläge abrufen; einen Titel wählen. Zusätzlich die manuelle Titeloption prüfen.
3. Filmproduktion starten, **Job-ID und Konfiguration** protokollieren; Jobstatus bis `completed` verfolgen.
4. Faktendossier, Drehbuch, Szenenplan und Medien-Metadaten für denselben Job öffnen.
5. MP4 rendern, intern ansehen, herunterladen und im lokalen Videoplayer öffnen.
6. Laufzeit, Codec/Container, Auflösung/16:9, Audiospur und Untertitel überprüfen; **tatsächliche Werte** dokumentieren.
7. Wesentliche Fakten/Quellen und verständlichen Erzählfluss stichprobenartig prüfen.
8. Simulierten Fehler in einem späteren Produktionsschritt prüfen; erneut starten, ohne erfolgreiche frühere Schritte (insbesondere Recherche) erneut ausführen zu müssen.
9. Login-geschützte Abrufe testen: anonyme Sitzung darf Produktionsdaten nicht abrufen.
10. Eine Abweichung als **eigenes GitHub-Issue** erfassen; abschließende Entscheidung **bestanden / nicht bestanden / Abweichung zur Entscheidung** dokumentieren.

**Erforderliche Nachweisartefakte:** Job-ID, Produktionsprotokoll, Film-Metadaten (Dauer/Auflösung), Skript, Faktendossier mit Quelllinks, Medien-/Lizenzliste, Ergebnis der Zugriffsprüfung, Fehler-/Retry-Protokoll und Link auf das M2-Abnahme-Issue [#51](https://github.com/whiteyOnTheMoon/FootballStudio/issues/51).

## 4. Qualität, Nachweisbarkeit und Veröffentlichungsgrenze

- **Fakten:** Keine erfundenen Zitate, unbelegten Superlative oder als sicher dargestellten widersprüchlichen Angaben. Beleglage im Dossier ersichtlich.
- **Medien:** Nur mit dokumentierter Quelle und Lizenz-/Statusinformation auswählen. **Ungeklärte Rechte berechtigen nicht zur öffentlichen Veröffentlichung.**
- **Ton/Bild:** Verständliche englische Sprachausgabe, vollständiger Audiomix, keine fehlenden Szenen; Untertitel und Grafiktexte lesbar.
- **Export:** Film ist technisch abspielbar, Dauer und Auflösung werden nach dem Rendering gemessen.
- **Prozess:** Fehler sind auffindbar; Komponenten speichern Zwischenstände. Keine Verschleierung fehlgeschlagener Schritte als „erfolgreich“.

**Abgrenzung:** Die Roadmap sieht erst **M3** ein umfassendes Lizenz-Freigabeverfahren, stärkere Quellenvalidierung, drei unterschiedliche geprüfte Filme, aussagekräftige Kostenmessung und erweiterte automatische QA vor. Diese M3-Arbeiten werden **nicht** als Voraussetzung für die Abnahme des *internen* M2-MVP behauptet. Vor einer öffentlichen Veröffentlichung bleibt jedoch eine gesonderte Rechtefreigabe erforderlich.

## 5. Explizite MVP-Nicht-Ziele

Diese Funktionen werden nicht als M2-Muss-Kriterien bewertet:

- Automatische Veröffentlichung auf YouTube oder anderen Plattformen.
- Aufwendige generative Videoclips bzw. Premium-Animationen.
- Vollautomatische Vereinsauswahl und ausgebaute KI-Ideengenerierung.
- Mehrere parallel arbeitende Render-Worker.
- Komplexer visueller Timeline-Editor und umfangreiche Medienbibliothek.
- Vollständige Lokalisierung in **de, fr, it, es, pt** (M5). `en` bleibt die einzige MVP-Ausgabesprache.
- Vollständige Templates für Karten, Tabellen, Rekordgrafiken, Intro/Outro und Thumbnails (M4).

## 6. Abnahmeentscheidung und Umgang mit Abweichungen

- Ein **technisches Gate** gilt nur als erfüllt, wenn der erwartete Testnachweis vorliegt.
- Eine **nicht bestandene Pflichtprüfung** blockiert die MVP-Abnahme und bekommt ein eigenes GitHub-Issue.
- Die Zielauflösung 1920×1080 ist zu prüfen. Wird für den **finalen** M2-Film nur 1280×720 erreicht, dokumentieren wir die Abweichung samt Ursache und bitten um **explizite Produktentscheidung**, statt stillschweigend die Zielvorgabe zu ändern.
- Änderungen an Muss-Funktionen, Budget, Ausgabeanforderungen oder Veröffentlichung brauchen eine dokumentierte Produktentscheidung und gegebenenfalls eigene Issues.
- Der M2-Abnahmebericht enthält das Urteil samt Links auf die Nachweise und gegebenenfalls offene Mängel.

## 7. Selbstprüfung dieser M0-Dokumentation (nicht M2-Testresultat)

- [x] Messbare Abnahmekriterien für vollständigen englischen 8–10-Minuten-MP4-Film festgehalten.
- [x] Quellen, Drehbuch, Vorschau, Download und wiederaufnehmbare Jobausführung berücksichtigt.
- [x] MVP-Nicht-Ziele und 16:9 / 1920×1080-Ziel sowie 720p-Testausnahme dokumentiert.
- [x] M0-Spezifikation klar von späteren M1/M2-Tests getrennt.
- [x] Noch offene Produktentscheidungen sind nicht stillschweigend getroffen.
- [x] Produktentscheidung vom 10.11.2026: M1-Vereinsauswahl und Docker-Betrieb sowie M2-Worker als explizite Abnahme-Gates aufgenommen.

**Wichtig:** Die Kontrollkästchen in Abschnitt 7 bestätigen ausschließlich, dass die **Spezifikation** erstellt wurde. Die Gates `AC-01` bis `AC-17` wurden **noch nicht ausgeführt**.

---

*Roadmap-Quellen: Seiten 2–5 (MVP, Architektur, Meilensteine, Quality Gates) und Seite 6 (GitHub-Prozess), Version 1.0 vom 09.11.2026.*
