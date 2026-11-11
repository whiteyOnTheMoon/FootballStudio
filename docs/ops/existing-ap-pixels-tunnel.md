# FootballStudio neben bestehenden VPS-Websites betreiben (FS-012a / #27)

## Vom Nutzer gezeigter Bestand (11.11.2026)

**Dateiansicht:** Bereits vorhandene Projekte liegen unter `/home/ap/www/`,
darunter `ap-pixels`, `cafe-bruen`, `kurvenfunk`,
`kurvenfunk-production`, `kurvenfunk-staging`,
`kurvenfunk-task174` und `videonews-studio`. Diese Verzeichnisse
werden von FootballStudio **nicht verschoben, ersetzt oder verändert**.

**Cloudflare-Screenshot:** Beim bestehenden Tunnel **`ap-pixels`**
sind veröffentlichte Anwendungen für `ap-pixels.com`,
`www.ap-pixels.com` und `cafe-bruen.ap-pixels.com` zu sehen.
Die gewünschte vierte Route `studio2.ap-pixels.com` ist auf diesem
Ausschnitt **nicht** vorhanden. Die Bilder belegen **nicht**, ob
`cloudflared` als Host-Dienst oder Docker-Container läuft.

**Festlegung:** FootballStudio erhält einen **eigenen Repo-Ordner**
`/home/ap/footballstudio` (außerhalb von `www`) und einen
eigenen Compose-Projektnamen `footballstudio` mit eigenem
PostgreSQL-Volume. Die bestehenden Docker-Projekte, Verzeichnisse
und drei Cloudflare-Routen bleiben unangetastet. Kein zweiter
Tunnel-Connector, kein Tunnel-Token für diese Anschlussvariante.

**Nicht live ausgeführt:** Diese Anleitung ist CI-geprüft, aber
keine tatsächliche VPS-/Cloudflare-Konfigurationsänderung.
Cloudflare Dashboard und Serverressourcen müssen erst inventarisiert
werden (#6, #27, #28 und #29).

## 1. Connector-Typ ohne Secrets feststellen

Auf dem **autorisierten VPS** nur lesende Befehle ausführen:

```bash
# Erkennt man einen vorhandenen Host-Systemdienst?
systemctl is-active cloudflared.service 2>/dev/null || true

# Erkennt man einen cloudflared-Container?
docker ps --format '{{.Names}}  {{.Image}}  {{.Networks}}' |
  grep -Ei 'cloudflared|cloudflare' || true

# Welche Docker-Bridges existieren? (Nur Namen, keine Zugangsdaten.)
docker network ls --format '{{.Name}}'
docker compose version

# Ist der vorgeschlagene lokale Host-Origin-Port bereits belegt?
ss -ltn | grep ':18080 ' || true

# Sicherstellen, dass nicht bereits ein FootballStudio-Verzeichnis existiert:
test -e /home/ap/footballstudio && echo 'Exists: inspect before changing' ||
  echo 'Free: /home/ap/footballstudio'
```

**Bitte niemals** `.cloudflared/`, Tunnel-Tokens, Docker-`inspect`-
`Env`-Listen, vollständige `docker compose config`-Ausgaben,
`.env` oder einen `systemctl cat cloudflared`-Inhalt posten.
Dienstkonfigurationen können Credentials als Argumente enthalten.

Die Dateiansicht `/home/ap/.cloudflared` allein beweist
**keinen** laufenden Host-Connector.

## 2. Separates Repo und geheime Konfiguration

Nur wenn `/home/ap/footballstudio` noch nicht existiert:

```bash
cd /home/ap
git clone https://github.com/whiteyOnTheMoon/FootballStudio.git footballstudio
cd /home/ap/footballstudio

# Vor Nutzung: private Secrets erzeugen; Beispielwerte NICHT übernehmen.
cp .env.example .env
chmod 600 .env
```

**Keine** fremden Ordner unter `/home/ap/www` umbenennen,
stoppen oder löschen. Vor Änderungen am Server Backup und freien
Speicher überprüfen (siehe [PostgreSQL-Backup](postgres-backup-restore.md)).
Die lokale `.env` enthält ausschließlich starke, eigene Werte für
`DJANGO_SECRET_KEY` und `POSTGRES_PASSWORD`. Den Cloudflare-
Tunnel-Token **nicht** in diesen Stack kopieren: Der schon bestehende
Connector verwaltet seine eigenen Credentials.

Die folgenden zwei Varianten sind **Alternativen**. **Genau eine**
auswählen, nachdem der tatsächliche Connector-Typ bekannt ist.

## Variante A: bestehender `cloudflared`-Host-Dienst

Nur wenn `cloudflared` direkt auf dem VPS-Host läuft oder dessen
Netzwerk-Namespace benutzt:

- In `.env`: `FOOTBALLSTUDIO_ORIGIN_PORT=18080` setzen,
  **nur nachdem Port 18080 als frei bestätigt wurde**.
- Die Datei `compose.existing-tunnel.host.yaml` ersetzt die
  lokale Entwicklungsportveröffentlichung 8000 mittels
  `ports: !override` durch **`127.0.0.1:18080:8000`**.
  Damit ist die App nicht über die öffentliche Host-IP erreichbar.
- **Cloudflare Dashboard → Tunnel `ap-pixels` → Add route →
  Published application**: `studio2.ap-pixels.com` →
  **`http://127.0.0.1:18080`**.
- Die anderen drei veröffentlichten Routen **nicht bearbeiten**.

```bash
cd /home/ap/footballstudio
# Keine Secrets ausgeben – config --quiet statt config:
docker compose -f compose.yaml -f compose.existing-tunnel.host.yaml config --quiet
docker compose -f compose.yaml -f compose.existing-tunnel.host.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.existing-tunnel.host.yaml ps

# Vom VPS-Host aus nur den internen, portgebundenen Healthcheck prüfen:
curl --fail --silent --show-error http://127.0.0.1:18080/healthz/
```

**Wichtig:** `127.0.0.1` in der Cloudflare-Service-URL bezieht
sich auf den Host des laufenden Connectors. Für einen standardmäßig
im Docker-Bridge-Netz laufenden `cloudflared`-Container wäre diese
Adresse **der Container selbst** und damit falsch.

## Variante B: bereits vorhandener `cloudflared`-Docker-Container

Falls der bestehende Cloudflare-Connector als Container läuft und
**nicht** Host-Netzwerkmodus verwendet:

- Es soll eine **eigene, überprüfte Docker-Bridge** geben, z. B.
  `footballstudio_tunnel`, die ausschließlich vom bestehenden
  Cloudflare-Connector und FootballStudios `web`-Dienst genutzt
  wird. **Keine fremden Webprojekte** in dieses Netz verschieben.
- Nach Bestandsaufnahme und gezielter Freigabe die **bereits laufende**
  Connector-Instanz an dieses Netz anbinden. Das darf nur der
  berechtigte VPS-Betreiber tun; keine automatischen Änderungen
  am vorhandenen Connector durch unser Compose-Projekt.
- In `.env`: `CLOUDFLARE_EXISTING_NETWORK=footballstudio_tunnel`.
- `compose.existing-tunnel.docker.yaml` veröffentlicht **keinen
  Host-Port**. Die Web-App erhält im dedizierten Netz den
  eindeutigen DNS-Namen `footballstudio-origin`. Die Datenbank
  bleibt ausschließlich im **privaten** Compose-Standardnetz.
- Cloudflare-Tunnel **`ap-pixels`**: zusätzliche Published
  application `studio2.ap-pixels.com` →
  **`http://footballstudio-origin:8000`**.
  Voraussetzung: Connector und Web-Container teilen diese Bridge.

```bash
cd /home/ap/footballstudio
docker compose -f compose.yaml -f compose.existing-tunnel.docker.yaml config --quiet
docker compose -f compose.yaml -f compose.existing-tunnel.docker.yaml up -d --build --wait
docker compose -f compose.yaml -f compose.existing-tunnel.docker.yaml ps
```

Docker-Netzwerk erstellen/verbinden oder den Connector neu starten
**erst nach überprüfter Bestandsaufnahme**; die genaue sichere
Änderung hängt von dessen bestehendem Compose-Projekt und
Netzkonfiguration ab. Der Name `footballstudio-origin` darf im
gemeinsamen Netz nicht bereits belegt sein. Das bestehende
`compose.tunnel.yaml` würde **einen zweiten Connector starten**:
für diese VPS-Konfiguration **nicht verwenden**.

## 3. Öffentliche HTTPS-Route prüfen

Nach erfolgreichem Start **genau eine neue Route** im bestehenden
Tunnel anlegen. Cloudflare veröffentlicht die Anwendung über HTTPS,
der private Origin-Service verwendet HTTP. Die beiden Varianten
setzen die Produktionswerte von Django fest auf:

```text
DJANGO_ALLOWED_HOSTS=studio2.ap-pixels.com
DJANGO_DEBUG=0
DJANGO_LOCAL_HTTP=0
DJANGO_TRUST_PROXY=1
DJANGO_FORCE_HTTPS=1
DJANGO_CSRF_TRUSTED_ORIGINS=https://studio2.ap-pixels.com
DJANGO_HSTS_SECONDS=0
```

Das Vertrauen in `X-Forwarded-Proto` setzt voraus, dass ausschließlich
der überprüfte Cloudflare-Connector den Web-Ursprung erreicht und
die Weiterleitungsheader nicht unkontrolliert von fremden
Netzteilnehmern gesetzt werden. Insbesondere Variante B braucht
ein **dediziertes, nicht allgemein freigegebenes Docker-Netz**.

Live prüfen:

- Extern `https://studio2.ap-pixels.com/healthz/` → `200 ok`
  (bei Cloudflare Access nur nach Authentifizierung).
- `http://studio2.ap-pixels.com/` → öffentlich auf HTTPS.
- Django-Login, CSRF-Formulare, Vereinsauswahl und Testjob über HTTPS.
- Vorhandene URLs `ap-pixels.com`, `www.ap-pixels.com` und
  `cafe-bruen.ap-pixels.com` funktionieren weiterhin unverändert.
- HSTS erst **nach** erfolgreichem TLS-/Redirect-Test aktivieren.
- Keine `docker compose down -v`-Befehle, kein Entfernen von
  fremden Containern oder `www`-Verzeichnissen.

**Rollback:** Nur den neuen `footballstudio`-Compose-Stack
anhalten/auf den vorherigen Commit zurückgehen und die
**neu angelegte** `studio2`-Route entfernen bzw. pausieren.
Niemals den existierenden Tunnel `ap-pixels` oder dessen drei
bisherige Routen löschen. Das PostgreSQL-Volume beim Rollback
nicht löschen.

**Referenzen:** [Cloudflare: mehrere veröffentlichte Apps pro Tunnel](https://developers.cloudflare.com/tunnel/concepts/routing/);
[Docker: gemeinsame externe Netze](https://docs.docker.com/compose/how-tos/networking/);
[Docker: `!override` und `!reset`](https://docs.docker.com/reference/compose-file/merge/).

**Offene Gates:** Tatsächlichen Connector-Typ, Hostressourcen,
Netzwerkbelegung, Secrets und öffentliche DNS-/TLS-Antwort
erst am echten VPS nachweisen. Screenshots sind nur ein
Teil der Inventur, nicht der Deployment-Nachweis.
