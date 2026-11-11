# FS-003a – VPS-Bestandsaufnahme (Prüfplan)

**Status:** Prüfplan erstellt; **Live-Inventur ausstehend** (kein Serverzugang für diese Aufgabe).  
**Issue:** [#6](https://github.com/whiteyOnTheMoon/FootballStudio/issues/6) · **Meilenstein:** M0  
**Ziel:** Tragfähigkeit des bereits vorgesehenen VPS für den Docker-basierten FootballStudio-Prototyp prüfen, **ohne bestehende Anwendungen zu verändern**.

## Grundsätze

1. Zunächst ausschließlich **lesende Prüfungen**. Keine Paketinstallation, keine Firewall-/DNS-Änderung, kein Container-Neustart.
2. Keine Passwörter, API-Schlüssel, Tokens, privaten IPs, Zugangsdaten, Session-Cookies, Konfigurationsinhalte oder vollständigen Prozess-Umgebungsvariablen im GitHub-Issue dokumentieren.
3. Falls fremde Dienste auf dem VPS laufen, ihre Existenz und groben Ressourcenverbrauch erfassen, **ohne** Konfigurationsdateien oder geschützte Daten zu kopieren.
4. Docker Compose ist eine **Pflichtanforderung**. M1-Web-App und PostgreSQL laufen in separaten Containern; M2-Worker ebenfalls separat.
5. Der Report bleibt **offen**, bis tatsächliche Serverbefunde vorliegen. Die Roadmap enthält keine konkreten CPU-/RAM-/Disk-Werte; keine Schätzung als Messwert ausgeben.

## Zu prüfende Bereiche

| Bereich | Erforderlicher Befund | Status |
| --- | --- | --- |
| Betriebssystem | Distribution, Version, Architektur, Kernel | Nicht geprüft |
| CPU | vCPU-Anzahl, Architektur | Nicht geprüft |
| RAM | Gesamt- und verfügbarer Arbeitsspeicher, Swap | Nicht geprüft |
| Speicher | Gesamt/Verfügbar, Dateisystem, freie Kapazität für Render-/Temporärdateien | Nicht geprüft |
| Container | Docker Engine verfügbar? `docker compose` Plugin installiert? Versionen | Nicht geprüft |
| Laufende Dienste | Bestehende Web-/Datenbank-/Containerdienste, nur Namen und Ports wo gefahrlos | Nicht geprüft |
| Reverse Proxy/TLS | Bereits vorhandener Proxy, HTTPS-Zertifikatsmechanismus, ohne Geheimnisse | Nicht geprüft |
| Netz/Ports | Belegte HTTP/HTTPS-Ports, mögliche Konflikte, keine Firewalländerung | Nicht geprüft |
| Sicherung | Existierender Backup-Prozess und mögliche Datenvolumes | Nicht geprüft |
| Logs und Kapazität | Grobe freie Log-/Renderkapazität sowie vorhandenes Monitoring | Nicht geprüft |
| Deployment | Geeigneter Pfad und Berechtigungsmodell für getrennten Docker-Compose-Stack | Nicht geprüft |

## Sichere, lesende Befehle für einen autorisierten VPS-Check

*Die Befehle sind nur ein technischer Prüfplan. Ihre Ausführung ist nicht erfolgt. Fehlende Tools werden notiert, nicht automatisch nachinstalliert.*

```sh
# OS / Architektur / Ressourcen
cat /etc/os-release
uname -m
uname -r
nproc
free -h
df -h

# Docker nur lesen, keine Änderungen
docker version
docker compose version
docker info --format '{{.ServerVersion}} / {{.Driver}}' 2>/dev/null
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# Belegte TCP-Listener (vor Weitergabe auf Sensibilität prüfen)
ss -ltn

# Laufende Proxy-Dienste nur feststellen
systemctl is-active nginx caddy apache2 2>/dev/null
```

**Hinweis:** `docker info` kann ohne Berechtigung nicht funktionieren; keine generelle Rechteerweiterung oder Veränderung von Docker-Socket-Berechtigungen als Nebenwirkung dieses Prüfschritts durchführen. `docker ps` und `ss` können interne Dienstnamen/Adressen offenbaren – nicht ungeprüft in öffentlichen Issues veröffentlichen.

## Dokumentation der Ergebnisse (erst nach echter Prüfung)

| Feld | Messwert / Befund |
| --- | --- |
| Datum des Checks | Ausstehend |
| Linux-Distribution + Architektur | Ausstehend |
| vCPU | Ausstehend |
| RAM / Swap | Ausstehend |
| Freier Datenträgerspeicher | Ausstehend |
| Docker-Version / Compose | Ausstehend |
| Reverse Proxy / HTTPS | Ausstehend |
| Port- und Containerkonflikte | Ausstehend |
| Bestehende Backups | Ausstehend |
| Einordnung für einen M1-Prototyp | **Ausstehend – keine Vorabfreigabe** |
| Einordnung für einen M2-FFmpeg-Worker | **Ausstehend – gesonderter Render-Benchmark (#7)** |

## Prüfreihenfolge und Folgetasks

1. Berechtigten **lesenden** Zugang zum VPS/Hosting-Panel klären (ohne Geheimnisse in Chat oder Issues).
2. CPU/RAM/Platte/OS und den Docker-/Port-/Proxy-Bestand **messen**.
3. Ergebnisse auf **nicht sensible Kenndaten** reduzieren und hier dokumentieren.
4. Erst dann die Eignung und Ressourcengrenzen für M1 bewerten.
5. In [#7](https://github.com/whiteyOnTheMoon/FootballStudio/issues/7) geplanten FFmpeg-Benchmark für 720p/1080p und temporäre Dateien vorbereiten.
6. Noch keine Konfigurations-, DNS-, Firewall- oder Deployment-Änderungen vornehmen; diese folgen ihren eigenen GitHub-Issues.

## Issue #6 – Fertigstellungskriterien

- [ ] **Tatsächliche** CPU-/RAM-/Platten-/OS-Daten aufgenommen.
- [ ] Docker/Compose sowie bestehende Dienste und Portkonflikte überprüft.
- [ ] Sensible Inhalte aus dem öffentlichen Repository ferngehalten.
- [ ] Messergebnis und Entscheidung zur M1-Tauglichkeit im Issue verlinkt.

**Bis diese Punkte erfüllt sind, bleibt #6 ausdrücklich offen.**

## Teilinventur aus VPS-Ausgabe (11.11.2026)

- `cloudflared.service` (systemd): **inactive**.
- Existierende Tunnel-Connectoren als Docker-Container: drei
  `kurvenfunk-*-cloudflared-1`, ein
  `videonews-studio-cloudflared` und
  `cloudflared_ap_pixels`, auf voneinander getrennten
  Docker-Netzen.
- **Vorgabe:** FootballStudio nutzt einen **eigenen** Tunnel und
  separaten Connector `footballstudio`, nicht den bestehenden
  `ap-pixels`-Tunnel. [Aktuelle Anleitung](cloudflare-tunnel.md).
- CPU/RAM/Platte, Docker-/Compose-Versionen, Portbelegung und
  öffentliche TLS-/DNS-Antwort **noch nicht** durch einen
  vollständigen Hostbericht nachgewiesen.
