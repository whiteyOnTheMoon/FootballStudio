"""Fail closed on an unsafe merged Cloudflare Tunnel Compose configuration.

Use: docker compose -f compose.yaml -f compose.tunnel.yaml config --format json
     | python scripts/verify_tunnel_compose.py

The configuration may contain secrets; this tool never prints the input.
"""
import json
import sys

config = json.load(sys.stdin)
assert config.get("name") == "footballstudio", "Isolate Compose project from other sites"
services = config["services"]
assert set(services) == {"db", "web", "cloudflared", "film-worker"}, "Exactly one dedicated connector"
web = services["web"]
db = services["db"]
tunnel = services["cloudflared"]
worker = services["film-worker"]

for name, service in (("web", web), ("db", db), ("cloudflared", tunnel), ("film-worker", worker)):
    assert not service.get("ports"), f"{name} must not publish any host ports"
    logging = service.get("logging", {})
    assert logging.get("driver") == "local", f"{name}: unexpected log driver"
    options = logging.get("options", {})
    assert str(options.get("max-size")) == "10m", f"{name}: log size limit missing"
    assert str(options.get("max-file")) == "3", f"{name}: log rotation missing"

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
health = web.get("healthcheck", {}).get("test", [])
assert health[:3] == ["CMD", "python", "-c"], (
    "Use an in-container healthcheck, not a public URL"
)
script = health[3] if len(health) > 3 else ""
assert "http://127.0.0.1:8000/healthz/" in script
assert "'Host':'studio2.ap-pixels.com'" in script, (
    "Production healthcheck must use a valid Django Host"
)
assert "response.status==200" in script and "response.read()==b'ok'" in script

assert worker["image"] == "footballstudio-web", "Worker must use the application image"
assert worker.get("command") == [
    "python", "manage.py", "produce_films", "--loop", "--interval", "10",
], "Worker may only run the bounded production command"
assert worker["depends_on"]["web"]["condition"] == "service_healthy"
assert worker["environment"]["PAID_API_CALLS_ENABLED"] == "0", "Worker must not enable paid APIs"
assert "TUNNEL_TOKEN" not in worker["environment"]
assert "CLOUDFLARE_TUNNEL_TOKEN" not in worker["environment"]
assert set(worker.get("networks", {})) == {"default"}, "Worker must stay off tunnel ingress"

assert tunnel["image"] == "cloudflare/cloudflared:2026.10.7"
assert tunnel.get("read_only") is True
assert "ALL" in tunnel.get("cap_drop", [])
assert tunnel["environment"].get("TUNNEL_TOKEN"), "Missing dedicated tunnel token"
assert "TUNNEL_TOKEN" not in web["environment"]
assert "TUNNEL_TOKEN" not in db["environment"]
assert tunnel.get("command") == ["tunnel", "--no-autoupdate", "run"]
assert tunnel["depends_on"]["web"]["condition"] == "service_healthy"

web_networks = set(web.get("networks", {}))
db_networks = set(db.get("networks", {}))
tunnel_networks = set(tunnel.get("networks", {}))
assert web_networks & tunnel_networks, "Web and tunnel need a private bridge"
assert not db_networks & tunnel_networks, "Tunnel must not share DB network"
assert web_networks == {"default", "tunnel_frontend"}
assert db_networks == {"default"}, "DB must stay outside ingress network"
assert tunnel_networks == {"tunnel_frontend"}, "Connector must not share DB or other network"
assert not config.get("networks", {}).get("tunnel_frontend", {}).get("external"), "Use project-owned ingress network"
print("Dedicated FootballStudio tunnel: ports closed, networks isolated, config valid.")
