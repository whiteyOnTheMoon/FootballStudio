"""Fail-closed inspection of FootballStudio's *existing*-tunnel Compose overlays.

Usage:
 docker compose -f compose.yaml -f compose.existing-tunnel.host.yaml config --format json \
   | python scripts/verify_existing_tunnel_compose.py host
 docker compose -f compose.yaml -f compose.existing-tunnel.docker.yaml config --format json \
   | python scripts/verify_existing_tunnel_compose.py docker

The merged Compose configuration may include secrets. Do NOT echo the input.
"""
import json
import sys

if len(sys.argv) != 2 or sys.argv[1] not in {"host", "docker"}:
    raise SystemExit("Expected mode: host or docker")

mode = sys.argv[1]
config = json.load(sys.stdin)
services = config["services"]
assert set(services) == {"web", "db"}, "An existing-tunnel overlay must not start cloudflared"
web, db = services["web"], services["db"]
assert not db.get("ports"), "Database must have no published host ports"
assert "cloudflared" not in services, "Must reuse the existing Cloudflare connector"

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
    assert str(env.get(key)) == value, f"Unsafe production env setting: {key}"
assert int(env.get("DJANGO_HSTS_SECONDS", -1)) >= 0
assert not any(k in env for k in ("TUNNEL_TOKEN", "CLOUDFLARE_TUNNEL_TOKEN"))

db_networks = set(db.get("networks", {}))
web_networks = set(web.get("networks", {}))
assert "default" in db_networks and "default" in web_networks, (
    "Web and DB need their own Compose private bridge"
)

for name, service in services.items():
    log = service.get("logging", {})
    assert log.get("driver") == "local", f"{name} must retain local log rotation"
    opts = log.get("options", {})
    assert str(opts.get("max-size")) == "10m"
    assert str(opts.get("max-file")) == "3"

if mode == "host":
    ports = web.get("ports", [])
    assert len(ports) == 1, "Host mode must publish exactly one loopback port"
    port = ports[0]
    assert port.get("host_ip") == "127.0.0.1", "Never publish on 0.0.0.0"
    assert int(port.get("target", -1)) == 8000
    assert str(port.get("published", "")) == "18080", (
        "CI expects a deliberately distinct origin port (18080)"
    )
    assert port.get("protocol") == "tcp"
    assert web_networks == {"default"}, "Host mode needs no other Docker networks"
else:
    assert not web.get("ports"), "Docker connector mode must publish NO host ports"
    assert "existing_tunnel" in web_networks
    assert "existing_tunnel" not in db_networks, (
        "PostgreSQL must not join the shared tunnel network"
    )
    external = config.get("networks", {}).get("existing_tunnel", {})
    assert external.get("external") is True, "Only a pre-existing Docker network"
    assert external.get("name") == "footballstudio_tunnel", (
        "CI expects a dedicated reviewed shared network"
    )
    net_config = web["networks"]["existing_tunnel"]
    assert "footballstudio-origin" in net_config.get("aliases", []), (
        "Existing cloudflared must resolve footballstudio-origin"
    )

print(f"Existing Cloudflare tunnel: safe {mode} Compose config validated.")
