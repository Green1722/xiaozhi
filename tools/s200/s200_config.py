"""Local configuration shared by the S200 gateway and MCP playback."""
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = Path(os.environ.get("S200_PRIVATE_DIR") or ROOT / ".s200-private").resolve()


def cloud_url() -> str:
    value = os.environ.get("XIAOZHI_CLOUD_BASE_URL", "").strip().rstrip("/")
    url = httpx.URL(value)
    if url.scheme != "https" or not url.host or url.path != "/" or url.query or url.fragment or url.userinfo:
        raise ValueError("Set XIAOZHI_CLOUD_BASE_URL to the HTTPS service origin")
    return value


def api_headers() -> dict:
    env = dict(
        line.split("=", 1)
        for line in (PRIVATE / "xiaozhi-iotda.private.env").read_text(encoding="utf-8-sig").splitlines()
        if "=" in line and not line.startswith("#")
    )
    return {"X-Health-API-Key": env["HEALTH_API_KEY"]}
