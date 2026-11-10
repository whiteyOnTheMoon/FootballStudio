"""Fail closed on an unsafe merged Cloudflare Tunnel Compose configuration.

Use: docker compose -f compose.yaml -f compose.tunnel.yaml config --format json
     | python scripts/verify_tunnel_compose.py

The configuration may contain secrets; this tool never prints the input.
"""
import json
import sys

config = json.load(sys.stdin)
services = config["services"]
web = services["web"]
db = services["db"]
tunnel = services["cloudflared"]

for name, service in (("web", web), ("db", db), ("cloudflared", tunnel)):
    assert not service.get("ports"), f"{name} must not publish any host ports"

env = web["environment"]
expected = {
    "DJANGO_ALLOWED_HOSTS": "studio2.ap-pixels.com",
    "DJANGO_DEBUG": "0",
    "DJANGO_LOCAL_HTTP": "0",
    "DJANGO_TRUST_PROXY": "1",
    "DJANGO_FORCE_HTTPS": "1",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://studio2.ap-pixels.com",
}
for key, value in expected.items():
    assert env.get(key) == value, f"Invalid production setting {key}"
assert int(env["DJANGO_HSTS_SECONDS"]) >= 0

assert tunnel["image"] == "cloudflare/cloudflared:2026.10.7"
assert tunnel.get("read_only") is True
assert "ALL" in tunnel.get("cap_drop", [])
assert tunnel["environment"].get("TUNNEL_TOKEN"), "Missing tunnel token"
assert tunnel.get("command") == ["tunnel", "--no-autoupdate", "run"]
assert tunnel["depends_on"]["web"]["condition"] == "service_healthy"

web_networks = set(web.get("networks", {}))
db_networks = set(db.get("networks", {}))
tunnel_networks = set(tunnel.get("networks", {}))
assert web_networks & tunnel_networks, "Web and tunnel need a private bridge"
assert not db_networks & tunnel_networks, "Tunnel must not share DB network"
assert "tunnel_frontend" in tunnel_networks, "Expected dedicated ingress network"
print("Tunnel Compose validation passed: no host ports, isolated DB, proxy settings, token supplied.")
