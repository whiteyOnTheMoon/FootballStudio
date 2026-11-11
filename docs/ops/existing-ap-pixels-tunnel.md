# VERALTETER Plan: FootballStudio über bestehenden ap-pixels-Tunnel

**Seit 11.11.2026 durch die Produktentscheidung für einen eigenen
`footballstudio`-Tunnel ersetzt.** Dieses Dokument bleibt nur als
historische Dokumentation von PR #111 erhalten. **Nicht als Anleitung
für den aktuellen VPS verwenden.**

Für den aktuellen Stand siehe
[Eigenen Cloudflare-Tunnel für FootballStudio](cloudflare-tunnel.md).

Der Nutzer hat nun bestätigt, dass `cloudflared` auf dem VPS in
eigenen Docker-Containern pro Projekt läuft; `systemctl` ist
`inactive`. Auch FootballStudio wird ein eigenständiges
`cloudflared`-Service in seinem eigenen Compose-Projekt erhalten.
Vorhandene Websites unter `/home/ap/www` bleiben unverändert.
