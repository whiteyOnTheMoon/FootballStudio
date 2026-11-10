# FS-003b – Render-Kapazität und FFmpeg-Benchmark

**Stand:** 10.11.2026 · **Status:** M0-Schätzung und isolierter Testplan; VPS-Ressourcen noch nicht geprüft.  
**Issue:** [#7](https://github.com/whiteyOnTheMoon/FootballStudio/issues/7)  
**Abhängigkeit:** [VPS-Inventur #6](vps-inventory.md) · [ADR-0001](../architecture/ADR-0001-mvp-stack.md) · [MVP-Abnahme](../mvp/acceptance-criteria.md)

## Ziel und Nicht-Ziele

M1 umfasst eine Django-Web-App und PostgreSQL in getrennten Docker-Compose-Services. Bereits im ersten Prototyp wählt der Nutzer **Land → Liga → Verein** oder legt einen Club selbst an. Ab M2 rendert ein **separater Worker** genau einen englischen Film von 8–10 Minuten auf einmal. **720p** ist die interne Testauflösung, **1080p (1920×1080, 16:9)** das Ziel für den fertigen Film.

Das Dokument behauptet weder vorhandenen VPS-Zugang noch getestete Docker-Container. Die konkreten VPS-Daten (CPU, RAM, freie Platte, bestehende Dienstlast und Compose-Verfügbarkeit) sind weiterhin **unbekannt**.

## Rechnerischer Speicherbedarf

Einfache Planung ohne Container-Overhead: Ausgabebytes ≈ Sekunden × (Video-Bitrate + Audio-Bitrate) / 8.

| Szenario | Video | Audio | 8 Minuten | 10 Minuten |
| --- | --- | --- | ---: | ---: |
| 720p / 24 fps | 2,5 Mbit/s | 128 kbit/s | 157,7 MB | 197,1 MB |
| 1080p / 24 fps | 6,0 Mbit/s | 128 kbit/s | 367,7 MB | 459,6 MB |
| 1080p mit höherer Bitrate | 8,0 Mbit/s | 128 kbit/s | 487,7 MB | 609,6 MB |

Dies sind **Rechenbeispiele**, kein Ergebnis des tatsächlich gewählten CRF-Encoders. Nicht enthalten sind MP4-Overhead, Medien-/Bilddateien, Audiospuren, Untertitel, Intro, Exportvarianten, mehrere Jobversionen, Cache, temporäre Dateien, Datenbank, Logs und Backups.

**Großer Risikotreiber:** 10 Minuten *unkomprimiertes* 1080p-YUV420-Video mit 24 fps benötigt rund **44,8 GB** (720p rund **19,9 GB**). Deshalb keine vollständigen Frame-Sequenzen unkomprimiert vorhalten; Szenen direkt in komprimierte Ausgaben rendern. Zehn Minuten unkomprimierter 48-kHz/16-Bit-Mono-Ton benötigen rund **57,6 MB** (Stereo rund 115,2 MB).

### Vorläufige Ressourcengrößen, ausdrücklich nicht gemessen

Als erste **Planungshypothese**, nicht als nachgewiesene Mindestanforderung: **2 vCPU**, **4 GiB RAM** und **mindestens 10 GiB aktuell freier Raum** für Rendercache/Artefakte könnten als Ausgangspunkt für einen isolierten Pilotversuch dienen. Bei vorhandenen Diensten oder aufwendigen Bildfiltern können diese Werte **deutlich unzureichend** sein. Die tatsächliche Mindestkonfiguration kann erst nach Inventur (#6), Messung und einem repräsentativen M2-Proberender entschieden werden.

- Maximal **ein Render-Worker** im MVP; keine parallelen Vollfilme.
- Produktionsausgaben und Datenbank auf gesicherten, nicht öffentlich zugänglichen Docker-Volumes.
- Vor dem Render ausreichend Platz **für Ausgaben, Zwischenstände und andere VPS-Dienste** nachweisen.
- Nicht auf gut Glück Container, Reverse Proxy, Swap oder Firewall verändern.
- Bei Ressourcendruck Jobs sicher stoppen und Fehler sichtbar machen; keine teuren Endlos-Retries.

## Isolierter 720p-/1080p-Test

Werkzeug: [`scripts/benchmark_ffmpeg.py`](../../scripts/benchmark_ffmpeg.py)

Das Skript erzeugt **ausschließlich künstliches Testbild mit FFmpeg testsrc2 und einen 440-Hz-Ton**. Es greift weder auf reale Vereinsbilder noch auf das Netzwerk oder bestehende Produktionsdateien zu. Für beide Größen gelten identische Parameter: **24 fps, H.264/libx264, veryfast, CRF 23, AAC 128 kbit/s, zwei Encoder-Threads**. Es prüft die MP4-Dateien per ffprobe und löscht die eigens angelegten temporären Dateien anschließend.

Voraussetzung: autorisierter **Testhost** mit Linux, Python 3 sowie FFmpeg und ffprobe mit libx264/AAC. Erst nach #6 den Test auf dem echten VPS oder später im M2-Worker durchführen. Ein Beispielaufruf für eine geeignete **nichtproduktive Testumgebung**:

```sh
python3 scripts/benchmark_ffmpeg.py --seconds 5 --threads 2 --workdir /tmp
```

- Ausgabe: maschinenlesbares JSON mit Laufzeit pro Auflösung, Codec, tatsächlicher MP4-Dauer und Größe, gesampelter Prozess-RSS sowie freier Plattenkapazität im Testverzeichnis.
- Eingebaute Grenzen: maximal **30 Sekunden pro Profil**, Threads 1–4, Standard-Timeout 180 Sekunden pro Profil.
- Ein Benchmark auf einem GitHub-Actions-Runner oder einem Entwicklungsrechner **beweist keine VPS-Tauglichkeit**. Der Report markiert sich absichtlich nicht selbst als geprüfte VPS-Messung.
- **RSS** aus /proc wird in kurzen Abständen gesampelt. Das ist nicht zwingend der echte kurzzeitige Speicherspitzenwert.
- Der kurze Test mit künstlichen Bildern ist **kein Ersatz** für reale Fotos, Textgrafiken, Karten, Untertitel, TTS, Übergänge, Django und PostgreSQL.

Grundlagen: [FFmpeg-Dokumentation](https://ffmpeg.org/ffmpeg.html), [ffprobe](https://ffmpeg.org/ffprobe.html), [Docker-Containerstatistik](https://docs.docker.com/reference/cli/docker/container/stats/).

## Echte Kapazitätsprüfung auf dem VPS (noch offen)

1. **FS-003a (#6)** abschließen: OS, vCPU, RAM, Swap, Festplatte, bestehende Docker-Dienste und Proxy ausschließlich lesend inventarisieren; keine Secrets in GitHub kopieren.
2. Vor einem autorisierten Test die Last bestehender Dienste und freie Kapazität dokumentieren. Geeignete Uhrzeit wählen; andere Projekte nicht beeinflussen.
3. 720p-Kurztest **und** 1080p-Kurztest mit denselben Encoding-Einstellungen auf dem vorgesehenen Host/Worker vergleichen. Host- und Containerlast mit `docker compose stats --no-stream` oder `docker stats` beobachten.
4. Nur wenn Ressourcen ausreichen, in M2 **30–60 Sekunden repräsentative echte Szenen** mit Fotos/Grafiken, Untertiteln, TTS und Übergängen testen.
5. Danach den **8–10-Minuten-Vollfilm** auf 1080p erzeugen; effektive Renderzeit, Spitzenlast, freien Platz vor/nachher und Ausgabequalität erfassen.
6. Bei Engpässen Arbeitspaket zur Optimierung oder VPS-Größe eröffnen. **1080p nicht ohne Produktentscheidung auf 720p herabstufen.**

**Zu erfassen:** Testumgebung (VPS vs. sonstige), Zeitpunkt, verfügbare vCPU/RAM/Disk vor dem Start, gleichzeitige Last, FFmpeg-Version, Auflösung/FPS/Encoder, gemessene Zeit, Speicher-/CPU-Spitzen mit Messmethode, Dateigröße, ffprobe-Codec/Dauer, Fehler und Auswirkungen auf Web/DB.

**Freigabekriterien:** Die Web-App und Datenbank bleiben verfügbar; keine OOM-Kills oder volle Disk; 1080p-MP4 mit 16:9 und Ton ist technisch intakt; genügend Platz für andere Services und Backups bleibt; keine unbeabsichtigte Veröffentlichung privater Assets.

## Abnahmestand #7

- [x] Speicher-/Temp-Dateirisiken mit Bitraten- und Rohframe-Beispielen abgeschätzt.
- [x] 720p-Test und 1080p-Ziel bei **einem** Worker verglichen.
- [x] Vorläufige Kapazitätsannahmen und Risiken explizit dokumentiert.
- [x] Isoliertes, begrenztes FFmpeg-Benchmark-Werkzeug und Prüfschritte vorbereitet.
- [ ] **Tatsächliche freie VPS-Ressourcen und vorhandene Dienste aus #6 bekannt.**
- [ ] Benchmarks auf dem **Ziel-VPS** einschließlich repräsentativer Szenen ausgeführt und Eignung bestätigt.

**Issue #7 bleibt bis zur VPS-Prüfung offen.** Dokumentationsarbeit und isolierte Tests sind ohne VPS-Zugang möglich; ein reales Ressourcenurteil nicht.
