"""How Tailarr starts uvicorn: no secrets in the log, no trusting made-up addresses."""

from __future__ import annotations

import io
import logging
import logging.config

from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tailarr.__main__ import HideSecretFilter, hide_secrets, trusted_proxies, uvicorn_options
from tailarr.main import create_app
from tests.conftest import page_client

SECRET = "ALVJx9_secret-Value"


def test_hide_secrets() -> None:
    line = f"/api/webhooks/radarr?secret={SECRET}"
    assert hide_secrets(line) == "/api/webhooks/radarr?secret=…"
    assert hide_secrets(f"/x?a=1&SECRET={SECRET}&b=2") == "/x?a=1&SECRET=…&b=2"
    assert hide_secrets("/api/films?search=secret") == "/api/films?search=secret"


def test_access_log_hides_the_webhook_secret() -> None:
    """Use the exact log settings `python -m tailarr` gives uvicorn, then log a request."""
    config = uvicorn_options({})["log_config"]
    logging.config.dictConfig(config)
    out = io.StringIO()
    handler = logging.getLogger("uvicorn.access").handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(out)
    # The same call uvicorn makes for each request.
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "172.18.0.5:41234",
        "POST",
        f"/api/webhooks/radarr?secret={SECRET}",
        "1.1",
        200,
    )
    logged = out.getvalue()
    assert "/api/webhooks/radarr?secret=…" in logged
    assert SECRET not in logged


def test_filter_handles_plain_messages() -> None:
    record = logging.LogRecord("x", logging.INFO, "", 0, f"GET /?secret={SECRET}", None, None)
    HideSecretFilter().filter(record)
    assert SECRET not in record.getMessage()


def test_only_the_container_itself_is_trusted_by_default() -> None:
    assert trusted_proxies({}) == "127.0.0.1"
    assert uvicorn_options({})["forwarded_allow_ips"] == "127.0.0.1"
    assert (
        trusted_proxies({"TAILARR_TRUSTED_PROXIES": " 172.18.0.2, 10.0.0.0/8 ,"})
        == "127.0.0.1,172.18.0.2,10.0.0.0/8"
    )


def _login_client(config, trusted: str) -> TestClient:  # noqa: ANN001
    app = create_app(config)
    client = page_client(ProxyHeadersMiddleware(app, trusted_hosts=trusted))
    response = client.put(
        "/api/settings/login",
        json={"enabled": True, "username": "ben", "password": "right password"},
    )
    assert response.status_code == 200, response.text
    client.cookies.clear()
    return client


def _attempts_with_fake_addresses(client: TestClient) -> list[int]:
    codes = []
    for n in range(7):
        response = client.post(
            "/api/auth/login",
            json={"username": "ben", "password": "wrong"},
            headers={"X-Forwarded-For": f"10.9.9.{n}"},
        )
        codes.append(response.status_code)
    return codes


def test_made_up_forwarded_addresses_dont_get_round_the_wait(config) -> None:  # noqa: ANN001
    client = _login_client(config, uvicorn_options({})["forwarded_allow_ips"])
    codes = _attempts_with_fake_addresses(client)
    assert codes[:5] == [401] * 5
    assert codes[5:] == [429, 429]


def test_a_listed_proxy_is_believed(config) -> None:  # noqa: ANN001
    # The test client's own address is "testclient"; listing it acts like a reverse proxy.
    trusted = uvicorn_options({"TAILARR_TRUSTED_PROXIES": "testclient"})["forwarded_allow_ips"]
    client = _login_client(config, trusted)
    assert _attempts_with_fake_addresses(client) == [401] * 7
