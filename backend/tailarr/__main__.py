"""Start Tailarr: `python -m tailarr`."""

from __future__ import annotations

import copy
import logging
import os
import re
from typing import Any

import uvicorn
from uvicorn.config import LOGGING_CONFIG

# `?secret=…` / `&secret=…` in a webhook address (Radarr/Sonarr send it on every webhook).
_SECRET = re.compile(r"([?&]secret=)[^&\s\"]*", re.IGNORECASE)


def hide_secrets(text: str) -> str:
    """Replace webhook secrets in a request line with `…`."""
    return _SECRET.sub(r"\1…", text)


class HideSecretFilter(logging.Filter):
    """Keep webhook secrets out of the container log.

    Uvicorn's access log prints each request with its query string, so without this
    anyone who can read the Docker log could copy the secret and send fake webhooks.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                hide_secrets(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.msg, str):
            record.msg = hide_secrets(record.msg)
        return True


def log_config() -> dict[str, Any]:
    """Uvicorn's usual log settings, with the secret filter on the access log."""
    config = copy.deepcopy(LOGGING_CONFIG)
    config.setdefault("filters", {})["hide_secrets"] = {"()": HideSecretFilter}
    config["handlers"]["access"]["filters"] = ["hide_secrets"]
    return config


def trusted_proxies(env: dict[str, str] | None = None) -> str:
    """Addresses allowed to say who the real visitor is (`X-Forwarded-For`).

    Only the container itself by default, so a visitor can't pretend to be a different
    device on each login attempt. People with a reverse proxy list its address in
    `TAILARR_TRUSTED_PROXIES` (comma-separated addresses or networks like 172.18.0.0/16).
    """
    env = os.environ if env is None else env
    listed = [part.strip() for part in env.get("TAILARR_TRUSTED_PROXIES", "").split(",")]
    listed = [part for part in listed if part]
    return ",".join(["127.0.0.1", *listed])


def uvicorn_options(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if env is None else env
    return {
        "factory": True,
        "host": env.get("TAILARR_HOST", "0.0.0.0"),
        "port": int(env.get("TAILARR_PORT", "8484")),
        "proxy_headers": True,
        "forwarded_allow_ips": trusted_proxies(env),
        "log_config": log_config(),
    }


def main() -> None:
    uvicorn.run("tailarr.main:create_app", **uvicorn_options())


if __name__ == "__main__":
    main()
