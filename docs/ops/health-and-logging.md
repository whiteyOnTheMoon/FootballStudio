# M1: Healthchecks und datensparsame Fehlerlogs (FS-013b)

**Stand:** Docker-/Django-Konfiguration und CI-Tests; echter Cloudflare/VPS-
Betrieb steht noch aus. Bezug: [Issue #30](https://github.com/whiteyOnTheMoon/FootballStudio/issues/30).

## Readiness

`GET /healthz/` führt einen minimalen `SELECT 1`-Test gegen die
konfigurierte Datenbank aus. Die Antwort besteht ausschließlich aus:

- `200 ok` wenn die Datenbank erreichbar ist
- `503 unavailable` wenn der Datenbank-Check fehlschlägt
- `Cache-Control: no-store`, keine SQL-/Host-/Stacktrace-Daten

Das Endpoint wird vom Docker-Healthcheck über private HTTP-Verbindungen
aufgerufen. Die Anwendung ignoriert `/healthz/` für den internen
HTTPS-Redirect, während Browser-Zugriffe via Cloudflare HTTPS verwenden.

## Sichere, strukturierte HTTP-Fehlerprotokolle

`SafeRequestLoggingMiddleware` erstellt serverseitig pro Anfrage eine
**neue zufällige Kennung** (`X-Request-ID`, 16 hexadezimale Zeichen).
Sie wird nicht aus einer Client-Header-Angabe übernommen. Für HTTP-Fehler
ab 400 wird eine Zeile im JSON-Format nach stderr geschrieben:

```json
{"timestamp":"2026-11-10T00:00:00Z","level":"ERROR","event":"http_error","status_code":503,"method":"GET","request_id":"0123456789abcdef"}
```

Eine Whitelist im JSON-Formatter erlaubt ausschließlich
`timestamp`, `level`, `event`, `status_code`, `method` und
`request_id`. Es gibt **keine** URL-Pfade, Query-Parameter,
IP-Adressen, User-IDs, E-Mail-Adressen, Formulareingaben, Cookies,
Datenbankausgaben oder Exception-Nachrichten. Auch
`django.request` und `django.security` benutzen diesen Formatter;
eventuelle rohe Django-Log-Nachrichten werden **niemals**
interpoliert. Die zuvor aktiven rohen Gunicorn-Zugriffslogs wurden
deaktiviert, damit z. B. URLs mit Tokens nicht protokolliert werden.

**Grenze:** Fehlerlogs von Betriebssystem, Docker Engine,
PostgreSQL, Cloudflare-Connector sowie von unabhängigen
Drittkomponenten folgen ihren eigenen Regeln. In einem echten
Deployment müssen diese separat auf Geheimnisse/Privatdaten geprüft
werden. Bei Problemen niemals komplette Logs ungeprüft in
öffentliche Issues oder Chats kopieren.

## Docker-Logrotation

Die drei Dienste `db`, `web` und `cloudflared` verwenden
den Docker-Logging-Treiber `local`, mit `max-size: 10m` und
`max-file: 3`. Das begrenzt die lokale Logbelegung pro Container
und ist **keine Offsite-Protokollierung oder Langzeitarchivierung**.

Betriebsprüfung (ohne Secrets auszugeben):

```bash
docker compose -f compose.yaml -f compose.tunnel.yaml ps
docker compose -f compose.yaml -f compose.tunnel.yaml logs --tail=30 web
docker compose -f compose.yaml -f compose.tunnel.yaml exec -T web python manage.py check
```

Der zweite Befehl kann dennoch Meldungen aus anderen Logquellen
enthalten; vor Weitergabe stets prüfen.

## CI-Abnahme und Grenzen

Der Django-Testsatz kontrolliert:

- Datenbank-Ready und datensparsame `503`-Antwort;
- zufällige Request-IDs ohne Vertrauen auf vom Client gesendete IDs;
- JSON für HTTP 404/500 sowie methoden-/statusbezogene Metadaten;
- dass URLs, E-Mail, Query-Tokens, IP, Cookie, Formulareinträge,
  unkontrollierte Django-Exceptions **nicht** im JSON erscheinen;
- ob Compose-Logrotation und bestehende Tunnel-Isolierung erhalten
  bleiben. Der Docker-Job prüft weiterhin Start, PostgreSQL,
  Backup/Restore sowie `/healthz/`.

Vor Live-Freigabe noch den echten VPS (#6) und die Cloudflare-
Route (#27/#28) prüfen. **Der erfolgreiche CI-Lauf ist kein
Live-Monitoring- oder Server-Freigabenachweis.**
