# FS-012: FootballStudio auf dem VPS über Cloudflare Tunnel

**Vorgegebene Architektur:** Docker Compose auf dem bestehenden VPS.
Die öffentliche Domain und der HTTPS-Zugang werden über einen
**remotely-managed Cloudflare Tunnel** geführt. Der bisherige Plan
für einen eigenen öffentlich erreichbaren Nginx-/Caddy-Reverse-Proxy
wird für dieses MVP **nicht** benötigt.

> Status: **Konfiguration und CI-Validierung bereitgestellt**, aber
> weder ein echter VPS noch das Cloudflare-Konto wurden aus diesem
> Repository geprüft oder verändert. Ohne Token und Cloudflare-Route
> gibt es noch keinen erreichbaren Dienst.

## Zieltopologie

```text
Browser --HTTPS--> Cloudflare edge (DNS/TLS, HTTPS redirect)
                             |
                      verschlüsselter Tunnel
                             |
             cloudflared (Docker; nur ausgehende Verbindung)
                             |
               Docker-Netz tunnel_frontend
                             |
                    web:8000 (Django)
                             |
                Docker-Standardnetz default
                             |
                      db:5432 (PostgreSQL)
```

Die Produktionsdatei `compose.tunnel.yaml` wird **zusätzlich** zur
lokalen `compose.yaml` genutzt. Dabei wird die Loopback-Publikation
des Django-Ports über `ports: !reset []` **entfernt**, statt sie
öffentlich freizuschalten. `db` und `cloudflared` haben
ebenfalls **keine** veröffentlichten Host-Ports; `cloudflared`
liegt nicht im Datenbank-Netz. Docker Compose benötigt Unterstützung
für `!reset` (Docker Compose V2).

## Cloudflare einmalig konfigurieren

Im Cloudflare-Dashboard unter **Networking → Tunnels** den vorhandenen
Tunnel auswählen oder einen neuen **remotely-managed Tunnel** anlegen.
Dort einen **Published application**-Eintrag für
`studio2.ap-pixels.com` mit folgendem Origin-Service konfigurieren:

- **Hostname:** `studio2.ap-pixels.com`
- **Service URL:** `http://web:8000` (Docker-Service `web`, **nicht**
  `http://localhost:8000`, da cloudflared im eigenen Container läuft)
- **Transport:** Öffentliches **HTTPS** über Cloudflare; zum Django-
  Container intern HTTP im privaten Docker-Netz (kein Origin-TLS nötig).
- Cloudflare am Edge auf **Always Use HTTPS** konfigurieren.
- Optional den Zugang zum MVP zusätzlich über **Cloudflare Access**
  schützen; die Django-Anmeldung bleibt trotzdem aktiv.

Für einen **bereits auf dem VPS-Host laufenden** Cloudflare-Connector
ist die Docker-Service-URL nicht direkt erreichbar. In diesem Fall
vorher entscheiden, ob der Connector in den Compose-Stack migriert
wird (diese Anleitung) oder ob stattdessen der vorhandene Connector
gezielt auf den lokalen Loopback-Port des separaten, nur lokal
gebundenen Webdiensts zeigt. **Nicht unbeabsichtigt zwei Connectoren
für denselben Anwendungsdienst starten.** Die hier vorgeschlagene
Produktionsvariante ist **ein Connector im Compose-Stack**.

## Geheimwerte und lokale Startprüfung

Von Cloudflare unter **Networking → Tunnels → (Tunnel) →
Add a replica** den Token abrufen. **Token niemals hier im Chat,
in GitHub, auf Screenshots oder in Tickets posten.** Er verleiht
dem Inhaber Zugriff auf den Tunnel; ein Leak erfordert Rotation.

In einer privaten `.env` auf dem autorisierten VPS sind zu setzen:
`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` und
`CLOUDFLARE_TUNNEL_TOKEN`. Verschiedene starke Werte nutzen;
`DJANGO_HSTS_SECONDS=0` für die erste Inbetriebnahme belassen.
`.env` nicht einchecken. Vorsicht: `docker compose config`
**ohne `--quiet` kann aufgelöste Geheimwerte anzeigen**. Das
CI verwendet ausschließlich wirkungslose Platzhalter.

```bash
# Vorab: Inventur des VPS und bestehender Container/Dienste (#6)
docker compose version

# .env eigenständig auf dem autorisierten VPS anlegen (nicht teilen!)
chmod 600 .env

# Compose-Overlay validieren, ohne dessen Secrets auszugeben:
docker compose -f compose.yaml -f compose.tunnel.yaml config --quiet

# Die tatsächlich benötigten drei Container starten:
docker compose -f compose.yaml -f compose.tunnel.yaml up -d --build --wait

# Health und Django-Konfiguration intern im Compose-Netz prüfen:
docker compose -f compose.yaml -f compose.tunnel.yaml ps
docker compose -f compose.yaml -f compose.tunnel.yaml exec -T web python manage.py check

# Tunnel-Laufzeit prüfen, ohne den Token aus der Umgebung zu drucken:
docker compose -f compose.yaml -f compose.tunnel.yaml logs --tail=30 cloudflared
```

Cloudflare-Tunnelverbindungen werden **ausgehend** aufgebaut. Je nach
VPS-/Firewall-Konfiguration muss ausgehend TCP/UDP **7844** erreichbar
sein; **kein öffentliches Inbound-Portforwarding** für 8000, 5432,
80 oder 443 einrichten. Eventuelle SSH-Verwaltung separat absichern.

## HTTPS/CSRF/Healthchecks

Der Overlay setzt für Django:

```text
DJANGO_DEBUG=0
DJANGO_LOCAL_HTTP=0
DJANGO_ALLOWED_HOSTS=studio2.ap-pixels.com
DJANGO_TRUST_PROXY=1
DJANGO_FORCE_HTTPS=1
DJANGO_CSRF_TRUSTED_ORIGINS=https://studio2.ap-pixels.com
DJANGO_HSTS_SECONDS=0
```

`SECURE_PROXY_SSL_HEADER` vertraut `X-Forwarded-Proto` ausschließlich
in diesem **portlosen Tunnel-Deployment**. Cloudflare überschreibt
den vom Browser gesetzten Header. Django leitet echtes HTTP auf
HTTPS um, akzeptiert Cookies nur als Secure und vermeidet durch
den vertrauenswürdigen Proxy-Header HTTPS-Redirectschleifen.
`/healthz/` bleibt bewusst von Django-internen HTTPS-Redirects
ausgenommen, damit der **private Docker-Healthcheck** weiter funktioniert.

**HSTS** vor dem öffentlichen HTTPS-/Redirect-Test deaktiviert
lassen. Erst nach erfolgreichem Live-Test vorsichtig z. B.
`DJANGO_HSTS_SECONDS=3600` einschalten; nicht sofort `preload`
oder `includeSubDomains` auf einer gemeinsam genutzten Domain
aktivieren. Änderung durch erneutes `up -d` ausrollen.

## Live-Abnahme (ausstehend)

1. Auf einem autorisierten VPS prüfen, dass Docker/Compose,
   bestehende Tunnel/Reverse-Proxies, freie Ressourcen und Portbelegung
   mit #6 übereinstimmen. Keine fremden Dienste deaktivieren.
2. Cloudflare-Tunnel und Route im Dashboard prüfen; Tunnelstatus
   **Healthy** allein beweist **keine** funktionierende Origin-Route.
3. Von außerhalb `https://studio2.ap-pixels.com/healthz/`
   aufrufen (bei Cloudflare Access erst nach Anmeldung).
   Nur `ok` und 200, keine Datenbankdiagnostik.
4. Django-Login, CSRF-geschützte Formulare, Vereinsauswahl und
   Testjob im Browser testen; nur Secure-Cookies über HTTPS.
5. `http://studio2.ap-pixels.com/` muss auf die HTTPS-Domain
   umleiten. TLS-Zertifikat und Gültigkeitsdatum im Browser prüfen.
6. Nach erfolgreicher HTTPS-Abnahme HSTS behutsam aktivieren.
7. Backup-/Restore-Ablauf gemäß [FS-008c](postgres-backup-restore.md)
   mit tatsächlich verfügbarem Speicher und gesicherter Offsite-Ablage
   überprüfen. Erst dann Zielbetrieb freigeben.

Zum Healthcheck, datensparsamen JSON-Logging und begrenzten Docker-Logs siehe
[Healthcheck und Logging](health-and-logging.md).

**Offene Abnahmepunkte:** echte Domain-/DNS- und Tunnel-Route (#27),
gültiges öffentliches Zertifikat und HTTP→HTTPS (#28), realer
VPS-Secret-/Rollback-Nachweis (#29). Ein erfolgreicher CI-Lauf ist
nur ein Nachweis für die *Konfiguration*, nicht für Cloudflare oder
einen tatsächlichen VPS-Deploy.

## Rollback und Sicherheit

Bei Fehlkonfiguration nicht an fremden Diensten oder den
PostgreSQL-Volumes arbeiten. Auf den letzten funktionierenden
Git-Commit der Web-Konfiguration zurücksetzen, danach
`docker compose -f compose.yaml -f compose.tunnel.yaml up -d --build`
mit **derselben bestehenden DB** ausführen; Migrationen
vorher auf Rückwärtskompatibilität prüfen. Den Tunnel über das
Cloudflare-Dashboard pausieren, falls eine öffentliche Route
vorübergehend geschlossen werden muss. Weder `down -v` noch
Löschbefehle gegen Datenbank-Volumes verwenden.

**Quellen:** [Cloudflare Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/),
[Cloudflare token](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/),
[Cloudflare routing](https://developers.cloudflare.com/tunnel/concepts/routing/),
[Cloudflare Proxy Header](https://developers.cloudflare.com/fundamentals/reference/http-headers/),
[Compose reset](https://docs.docker.com/reference/compose-file/merge/).
