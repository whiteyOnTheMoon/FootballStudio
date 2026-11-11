# FootballStudio: eigener Cloudflare-Tunnel auf dem VPS

**Verbindliche Entscheidung (11.11.2026):** FootballStudio verwendet einen
**eigenständigen Cloudflare-Tunnel `footballstudio`** mit einem eigenen
`cloudflared`-Docker-Container, analog zum bestehenden Projekt
`videonews-studio`. Die vorherige Mitbenutzung von `ap-pixels` ist
**verworfen**. Andere Tunnel, Websites und Netzwerke nicht verändern.

## Bestätigter Serverbestand

Der Nutzer hat folgende **lesenden** VPS-Ergebnisse geliefert:
`systemctl is-active cloudflared.service` → **inactive**.
`docker ps` zeigt unabhängige Connectoren:
`kurvenfunk-prod-cloudflared-1`,
`kurvenfunk-staging-cloudflared-1`,
`kurvenfunk-dev-cloudflared-1`,
`videonews-studio-cloudflared` und
`cloudflared_ap_pixels`, jeweils auf separaten Docker-Netzen.
Das bestehende Tunnel-Dashboard zeigt
`videonews-studio` → `studio.ap-pixels.com` →
`http://web:3000`. **Diese Route nicht überschreiben.**

FootballStudios neue Route lautet stattdessen:

| Einstellung | Wert |
| --- | --- |
| Cloudflare Tunnel | `footballstudio` (neu, eigener Tunnel) |
| Published application | `studio2.ap-pixels.com` |
| Service / Origin Type | `HTTP` |
| Service URL | `http://web:8000` |
| VPS-Verzeichnis | `/home/ap/footballstudio` |
| Compose Services | `web`, `db`, `cloudflared` |
| Öffentliche Host-Ports | **keine** |

Die Projekte in `/home/ap/www` bleiben unangetastet. Ein eigener
Compose-Projektname `footballstudio`, PostgreSQL-Volume und eigene
Netze trennen die Container von allen vorhandenen Projekten. Docker
löst den Servicenamen `web` **im eigenen Tunnel-Netz**
`tunnel_frontend` auf; `http://localhost:8000` wäre aus Sicht
des Connector-Containers falsch.

## 1. Neuen Tunnel im Dashboard anlegen

Im Cloudflare-Dashboard **Networking → Tunnels → Create a tunnel**
öffnen, den Typ **cloudflared** wählen und den Namen
**`footballstudio`** vergeben. Beim Connector-Setup Docker wählen.
Den **neuen** Token ausschließlich auf dem VPS in
`/home/ap/footballstudio/.env` unter
`CLOUDFLARE_TUNNEL_TOKEN` speichern.
**Niemals** im Chat, GitHub, Screenshot oder Terminalausgaben teilen.
Den vorgeschlagenen `docker run`-Befehl **nicht zusätzlich**
ausführen: Compose startet den Container selbst.

Unter **Routes → Add route → Published application** eine neue
Route für `studio2.ap-pixels.com` und den internen Service
**`http://web:8000`** hinzufügen. Prüfen, dass der DNS-Eintrag
diesem **neuen** Tunnel zugeordnet ist. Andere Routen und Connectoren
bleiben unverändert. Am Cloudflare Edge HTTPS / Always Use HTTPS
prüfen; **HSTS zunächst auf 0** lassen.

## 2. Eigenständiges Docker-Projekt auf dem VPS

Zuerst freie Kapazität, vorhandene Verzeichnisse, Docker-/Compose-Version
und bereits gestartete Container **nur lesend** prüfen.
Keine fremden Container neustarten oder stoppen. Falls
`/home/ap/footballstudio` noch nicht existiert:

```bash
cd /home/ap
git clone https://github.com/whiteyOnTheMoon/FootballStudio.git footballstudio
cd /home/ap/footballstudio
cp .env.example .env
chmod 600 .env
```

In `.env` **verschiedene sichere Werte** für `DJANGO_SECRET_KEY`,
`POSTGRES_PASSWORD` und den **neuen**
`CLOUDFLARE_TUNNEL_TOKEN` setzen; keine Beispielwerte verwenden.
`DJANGO_HSTS_SECONDS=0` bis zur TLS-Liveprüfung. Kein Token
eines anderen Projekts kopieren.

```bash
# config --quiet gibt keine aus .env aufgelösten Secrets aus.
docker compose -f compose.yaml -f compose.tunnel.yaml config --quiet
docker compose -f compose.yaml -f compose.tunnel.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.tunnel.yaml ps
```

Das geprüfte Overlay `compose.tunnel.yaml` entfernt das
Entwicklungs-Portmapping per `ports: !reset []`.
`web`, `db` und `cloudflared` veröffentlichen **keinen
Port am VPS**. `cloudflared` liegt ausschließlich im separaten
Ingress-Netz; die Datenbank ausschließlich im Compose-Standardnetz,
das sie nur mit `web` teilt. Jede Website hat ihr eigenes
Docker-Compose-Netz, deshalb ist der generische Service-Name
`web` korrekt.

`cloudflared` nutzt den neuen Token aus der privaten
Docker-Umgebung. **Wichtig:** `docker compose config` ohne
`--quiet` kann Geheimwerte anzeigen. Auch andere Logquellen
vor Weitergabe auf Secrets prüfen.

## 3. Live-Abnahme (noch ausstehend)

1. Cloudflare zeigt **`footballstudio` als Healthy** mit einer
   Published-Application-Route `studio2.ap-pixels.com`.
2. Von außen `https://studio2.ap-pixels.com/healthz/` testen:
   `200 ok` (ggf. nach Cloudflare-Access-Anmeldung).
3. `http://studio2.ap-pixels.com/` muss auf HTTPS umleiten;
   Browser-Zertifikat kontrollieren.
4. Anmeldung, CSRF-Formulare, Vereinspicker und Testjob prüfen.
5. Kontrollieren, dass `studio.ap-pixels.com` und die bestehenden
   `ap-pixels`-/`kurvenfunk`-Sites weiterhin funktionieren.
6. HSTS erst nach erfolgreichem HTTPS-Test vorsichtig aktivieren.
7. Datenbank-Backup und Wiederherstellungsprüfung aus
   [Backup/Restore](postgres-backup-restore.md) für den VPS planen.

`Healthy` zeigt die Connector-Verbindung an, **nicht**
automatisch die Erreichbarkeit des Django-Ursprungs. Keine
`docker compose down -v`-Befehle: das würde das
PostgreSQL-Volume löschen. Falls ein Rollback nötig ist, nur
den eigenen Stack und die neue `studio2`-Route zurücknehmen;
andere Tunnel und ihre Routen unverändert lassen.

**Status:** Die Compose-Konfiguration ist CI-geprüft,
aber **kein** tatsächlicher VPS-/Cloudflare-Deploy wurde hier
ausgeführt. Die live ausstehende Abnahme bleibt in #6/#27/#28/#29.

**Quellen:** [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/),
[Published application](https://developers.cloudflare.com/tunnel/routing/),
[Token](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/),
[Docker Compose merge](https://docs.docker.com/reference/compose-file/merge/).

## Troubleshooting: Django läuft, ist aber „unhealthy“

Beim ersten produktiven VPS-Start wurde ein interner Healthcheck entdeckt,
der `http://127.0.0.1:8000/healthz/` mit dem Standard-HTTP-Host
`127.0.0.1` statt der erlaubten Produktionsdomain aufrief. Die
Tunnel-Compose-Datei stellt deshalb den Host-Header für genau diesen
lokalen privaten Check auf `studio2.ap-pixels.com`. Die Web-App akzeptiert
weiterhin nur ihren konfigurierten öffentlichen Hostnamen; es wird
**kein** Port öffentlich freigegeben. Der CI-Docker-Job testet den
Produktions-Overlay jetzt auch tatsächlich gegen einen gestarteten
Django-Webcontainer (ohne echten Cloudflare-Tunnel).

Bei einem Fehler den Healthcheck-Status und die letzten Logs ansehen,
ohne Credentials zu posten:

```bash
cd /home/ap/www/footballstudio
docker inspect --format '{{range .State.Health.Log}}{{println .ExitCode .Output}}{{end}}' footballstudio-web-1
docker compose -f compose.yaml -f compose.tunnel.yaml logs --tail=40 web
```

Falls die neue Version gerade eingespielt wird, **kein**
`docker compose down -v` verwenden; der bestehende Postgres-Datenträger
bleibt erhalten:

```bash
git pull --ff-only
docker compose -f compose.yaml -f compose.tunnel.yaml up -d --build --wait
```

Ein grüner Docker-Healthcheck allein belegt noch **nicht** die Live-Verbindung
zum neuen Cloudflare-Tunnel oder die Korrektheit der öffentlichen Domainroute.
