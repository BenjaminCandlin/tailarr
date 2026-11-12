"""Small clients for the Radarr, Sonarr and Plex web APIs, with plain-English errors.

Only the few calls Tailarr needs. Every failure becomes a :class:`ConnectionProblem`
whose message the owner can act on (for example: the name isn't known on the Docker
network, or the API key is wrong).
"""

from __future__ import annotations

import socket
from typing import Any
from urllib.parse import urlparse

import httpx

TIMEOUT = httpx.Timeout(15.0, connect=5.0)

NAMES = {"radarr": "Radarr", "sonarr": "Sonarr", "plex": "Plex"}


class ConnectionProblem(Exception):
    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


def _explain(service: str, url: str, error: Exception) -> ConnectionProblem:
    name = NAMES[service]
    host = urlparse(url).hostname or url
    text = str(error)
    if isinstance(error, httpx.ConnectError):
        cause = error.__cause__ or error.__context__
        if (
            isinstance(cause, socket.gaierror)
            or "Name or service not known" in text
            or ("nodename nor servname" in text)
            or "Temporary failure in name resolution" in text
            or "No address associated" in text
        ):
            return ConnectionProblem(
                f"Tailarr can't find “{host}”. If {name} runs in Docker, make sure Tailarr and "
                f"{name} are on the same custom Docker network, and use the container's name "
                f"(for example http://{service}:{_default_port(service)}). Otherwise use the "
                "server's IP address.",
                text,
            )
        return ConnectionProblem(
            f"Tailarr found “{host}” but {name} didn't answer. Check {name} is running and "
            f"the port number is right ({name} normally uses {_default_port(service)}).",
            text,
        )
    if isinstance(error, httpx.TimeoutException):
        return ConnectionProblem(f"{name} took too long to answer. Is it busy or stopped?", text)
    if isinstance(error, httpx.UnsupportedProtocol | httpx.InvalidURL):
        return ConnectionProblem(
            f"That doesn't look like a web address. Use something like "
            f"http://{service}:{_default_port(service)}.",
            text,
        )
    return ConnectionProblem(f"Tailarr couldn't talk to {name}.", text)


def _default_port(service: str) -> int:
    return {"radarr": 7878, "sonarr": 8989, "plex": 32400}[service]


class ServiceClient:
    """Shared request handling. `transport` lets tests answer instead of a real server."""

    service = ""

    def __init__(self, url: str, key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        name = NAMES[self.service]
        if not self.url:
            raise ConnectionProblem(f"{name}'s address isn't filled in.")
        try:
            with httpx.Client(
                timeout=TIMEOUT, transport=self._transport, follow_redirects=True
            ) as client:
                response = client.request(
                    method, f"{self.url}{path}", headers=self._headers(), **kwargs
                )
        except httpx.HTTPError as error:
            raise _explain(self.service, self.url, error) from error
        if response.status_code in (401, 403):
            what = "token" if self.service == "plex" else "API key"
            raise ConnectionProblem(
                f"{name} refused the {what}. Copy it again from {name}"
                + (" (Settings → General → Security)." if self.service != "plex" else ".")
            )
        if response.status_code == 404:
            raise ConnectionProblem(
                f"Tailarr reached the address, but it doesn't look like {name} (or {name}'s "
                "address needs a different ending, such as a URL base).",
                f"404 for {path}",
            )
        if response.status_code >= 400:
            raise ConnectionProblem(
                f"{name} answered with an error ({response.status_code}).", response.text[:2000]
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise ConnectionProblem(
                f"Tailarr reached the address, but the answer didn't come from {name}.",
                response.text[:500],
            ) from error

    def get_bytes(self, path: str) -> bytes:
        """A picture. Radarr/Sonarr's picture paths already include any URL base, so they're
        joined to the server's address only (scheme, name and port)."""
        parsed = urlparse(self.url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        try:
            with httpx.Client(
                timeout=TIMEOUT, transport=self._transport, follow_redirects=True
            ) as client:
                response = client.get(f"{origin}{path}", headers=self._headers())
        except httpx.HTTPError as error:
            raise _explain(self.service, self.url, error) from error
        if response.status_code >= 400:
            raise ConnectionProblem(f"Couldn't fetch a picture ({response.status_code}).")
        return response.content


class ArrClient(ServiceClient):
    """Radarr or Sonarr (both use the same v3 API style)."""

    def __init__(self, service: str, url: str, key: str, **kwargs: Any) -> None:
        super().__init__(url, key, **kwargs)
        self.service = service

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.key, "Accept": "application/json"}

    def status(self) -> dict[str, Any]:
        data = self.request("GET", "/api/v3/system/status")
        app = (data or {}).get("appName", "")
        if app and app.lower() != self.service:
            raise ConnectionProblem(
                f"That address belongs to {app}, not {NAMES[self.service]}. "
                f"Check the address and port."
            )
        return data or {}

    def items(self) -> list[dict[str, Any]]:
        """All films (Radarr) or series (Sonarr)."""
        path = "/api/v3/movie" if self.service == "radarr" else "/api/v3/series"
        return list(self.request("GET", path) or [])

    def rescan(self, arr_id: int) -> None:
        if self.service == "radarr":
            body = {"name": "RescanMovie", "movieId": arr_id}
        else:
            body = {"name": "RescanSeries", "seriesId": arr_id}
        self.request("POST", "/api/v3/command", json=body)


class PlexClient(ServiceClient):
    service = "plex"

    def _headers(self) -> dict[str, str]:
        return {
            "X-Plex-Token": self.key,
            "Accept": "application/json",
            "X-Plex-Product": "Tailarr",
            "X-Plex-Client-Identifier": "tailarr",
        }

    def status(self) -> dict[str, Any]:
        data = self.request("GET", "/identity") or {}
        container = data.get("MediaContainer", data)
        if "machineIdentifier" not in container:
            raise ConnectionProblem("Tailarr reached the address, but it doesn't look like Plex.")
        # /identity works without a token, so check the token with a call that needs it.
        self.sections()
        return {"version": container.get("version", "")}

    def sections(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/library/sections") or {}
        return list(data.get("MediaContainer", {}).get("Directory", []) or [])

    def refresh(self, section_id: str, path: str | None) -> None:
        params = {"path": path} if path else None
        self.request("GET", f"/library/sections/{section_id}/refresh", params=params)
