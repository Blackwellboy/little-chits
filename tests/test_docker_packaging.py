"""Docker that works without hand-editing: a compose file for Docker Desktop (Windows, macOS), and a workflow that
publishes the image on version tags only."""

import asyncio
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return yaml.safe_load((ROOT / name).read_text())


def service(name):
    doc = load(name)
    assert list(doc["services"]) == ["little-chits"]
    return doc["services"]["little-chits"]


def test_linux_compose_still_uses_host_networking_and_a_token():
    s = service("docker-compose.yml")
    assert s["network_mode"] == "host" and "ports" not in s
    assert "CHITS_TOKEN" in s["environment"]


def test_desktop_compose_maps_the_port_and_reaches_the_host():
    s = service("docker-compose.desktop.yml")
    assert "network_mode" not in s  # Docker Desktop has no host networking
    assert s["build"] == "."
    assert len(s["ports"]) == 1
    # published on this computer only, on a port of the user's choice
    assert re.fullmatch(r"127\.0\.0\.1:\$\{CHITS_PORT:-8000\}:8000", s["ports"][0]), s["ports"]
    assert "host.docker.internal:host-gateway" in s["extra_hosts"]  # (so the name resolves on Linux too)
    assert s["environment"]["CHITS_SCAN_HOST"] == "host.docker.internal"
    assert any(str(v).endswith(":/data") for v in s["volumes"])


def test_desktop_compose_refuses_to_start_without_a_token():
    token = service("docker-compose.desktop.yml")["environment"]["CHITS_TOKEN"]
    # ${VAR:?message}: compose stops with the message when the variable is unset or empty. No default secret.
    assert re.fullmatch(r"\$\{CHITS_TOKEN:\?[^}]+\}", token), token


def test_readme_and_makefile_point_at_the_desktop_file_instead_of_hand_edits():
    readme = (ROOT / "README.md").read_text()
    assert "docker compose -f docker-compose.desktop.yml up" in readme
    assert "remove\n`network_mode: host`" not in readme and "remove network_mode" not in (ROOT / "docker-compose.yml").read_text()
    mk = (ROOT / "Makefile").read_text()
    assert "\ndocker-desktop:" in mk and "docker-compose.desktop.yml" in mk


def test_build_context_leaves_saves_and_installs_out():
    ignored = (ROOT / ".dockerignore").read_text().split()
    for path in ("server/data", "data", "web/node_modules", ".venv", ".git", ".env"):
        assert path in ignored, path


def test_image_workflow_publishes_on_tags_only_with_least_privilege():
    wf = load(".github/workflows/image.yml")
    on = wf.get("on", wf.get(True))  # (YAML 1.1 reads the bare key `on` as true)
    assert set(on) == {"push"}, "tags only: never pull_request or pull_request_target (code from forks)"
    assert set(on["push"]) == {"tags"} and on["push"]["tags"] == ["v*"]
    assert wf["permissions"] == {"contents": "read"}
    (job,) = wf["jobs"].values()
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    steps = job["steps"]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@v\d+", u) for u in uses), uses  # pinned, like ci.yml
    login = next(s for s in steps if s.get("uses", "").startswith("docker/login-action@"))
    assert login["with"]["registry"] == "ghcr.io"
    assert login["with"]["password"] == "${{ secrets.GITHUB_TOKEN }}"
    meta = next(s for s in steps if s.get("uses", "").startswith("docker/metadata-action@"))
    assert meta["with"]["images"] == "ghcr.io/${{ github.repository }}"
    build = next(s for s in steps if s.get("uses", "").startswith("docker/build-push-action@"))
    assert build["with"]["push"] is True and "linux/arm64" in build["with"]["platforms"]
    text = (ROOT / ".github/workflows/image.yml").read_text()
    assert "secrets." not in text.replace("secrets.GITHUB_TOKEN", "")  # no other secret is used


def test_the_model_scan_looks_where_chits_scan_host_says(monkeypatch):
    from chits.brain import llm

    seen = []

    async def fake_open_ports(host, ports, *a, **k):
        seen.append(host)
        return []

    monkeypatch.setattr(llm, "_open_ports", fake_open_ports)
    monkeypatch.delenv("CHITS_SCAN_HOST", raising=False)
    asyncio.run(llm.scan_local(ports=[9]))
    monkeypatch.setenv("CHITS_SCAN_HOST", "host.docker.internal")
    asyncio.run(llm.scan_local(ports=[9]))
    asyncio.run(llm.scan_local("127.0.0.1", ports=[9]))  # an explicit host still wins
    assert seen == ["127.0.0.1", "host.docker.internal", "127.0.0.1"]
