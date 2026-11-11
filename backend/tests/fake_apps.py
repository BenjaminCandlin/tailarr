"""Fake Radarr, Sonarr and Plex servers for tests (answering through httpx.MockTransport)."""

from __future__ import annotations

import io
import json
import socket
from dataclasses import dataclass, field
from typing import Any

import httpx
from PIL import Image

RADARR_KEY = "radarr-key"
SONARR_KEY = "sonarr-key"
PLEX_TOKEN = "plex-token"


def _jpeg(colour: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1000, 1500), colour).save(buffer, "JPEG")
    return buffer.getvalue()


@dataclass
class FakeApps:
    """Remote paths: Radarr sees films under /movies, Sonarr shows under /tv, Plex /media/…"""

    movies: list[dict[str, Any]] = field(default_factory=list)
    series: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    plex_refreshes: list[dict[str, Any]] = field(default_factory=list)
    plex_sections: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "key": "1",
                "type": "movie",
                "title": "Films",
                "Location": [{"path": "/media/movies"}],
            },
            {"key": "2", "type": "show", "title": "TV", "Location": [{"path": "/media/tv"}]},
        ]
    )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host in ("nowhere", "unknown-container"):
            raise httpx.ConnectError(
                "[Errno -2] Name or service not known", request=request
            ) from socket.gaierror(-2, "Name or service not known")
        if host == "refused":
            raise httpx.ConnectError("[Errno 111] Connection refused", request=request)
        if host in ("radarr", "sonarr"):
            return self._arr(host, request, path)
        if host == "plex":
            return self._plex(request, path)
        return httpx.Response(404)

    def _arr(self, host: str, request: httpx.Request, path: str) -> httpx.Response:
        key = RADARR_KEY if host == "radarr" else SONARR_KEY
        if path.startswith("/MediaCover/"):
            return httpx.Response(200, content=_jpeg("#336699" if "poster" in path else "#223344"))
        if request.headers.get("X-Api-Key") != key:
            return httpx.Response(401, json={"error": "Unauthorized"})
        if path == "/api/v3/system/status":
            return httpx.Response(200, json={"appName": host.title(), "version": "5.9.1"})
        if path == "/api/v3/movie" and host == "radarr":
            return httpx.Response(200, json=self.movies)
        if path == "/api/v3/series" and host == "sonarr":
            return httpx.Response(200, json=self.series)
        if path == "/api/v3/command" and request.method == "POST":
            self.commands.append({"app": host, **json.loads(request.content)})
            return httpx.Response(201, json={"id": len(self.commands)})
        return httpx.Response(404)

    def _plex(self, request: httpx.Request, path: str) -> httpx.Response:
        if path == "/identity":
            return httpx.Response(
                200, json={"MediaContainer": {"machineIdentifier": "abc", "version": "1.41.0"}}
            )
        if request.headers.get("X-Plex-Token") != PLEX_TOKEN:
            return httpx.Response(401)
        if path == "/library/sections":
            return httpx.Response(200, json={"MediaContainer": {"Directory": self.plex_sections}})
        if path.startswith("/library/sections/") and path.endswith("/refresh"):
            section = path.split("/")[3]
            self.plex_refreshes.append({"section": section, "path": request.url.params.get("path")})
            return httpx.Response(200)
        return httpx.Response(404)


def movie(movie_id: int, title: str, year: int, folder: str) -> dict[str, Any]:
    return {
        "id": movie_id,
        "title": title,
        "year": year,
        "path": f"/movies/{folder}",
        "images": [
            {"coverType": "poster", "url": f"/MediaCover/{movie_id}/poster.jpg?lastWrite=1"},
            {"coverType": "fanart", "url": f"/MediaCover/{movie_id}/fanart.jpg?lastWrite=1"},
        ],
    }


def series(series_id: int, title: str, year: int, folder: str) -> dict[str, Any]:
    return {**movie(series_id, title, year, folder), "path": f"/tv/{folder}"}
