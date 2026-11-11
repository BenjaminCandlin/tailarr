#!/usr/bin/env python3
"""A tiny fake Radarr, Sonarr and Plex for the browser tests.

One server; the first part of the address says which app it pretends to be:
http://127.0.0.1:PORT/radarr, /sonarr and /plex. Film and show paths are the real sample
folders, so no path mapping is needed. Keys: "radarr-key", "sonarr-key", "plex-token".
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MOVIES = os.environ["TAILARR_MOVIES_DIR"]
TV = os.environ["TAILARR_TV_DIR"]
ART = Path(os.environ.get("FAKE_ART_DIR", "."))
KEYS = {"radarr": "radarr-key", "sonarr": "sonarr-key"}

MOVIE_LIST = [
    {"id": 1, "title": "Colour Test", "year": 2023, "folder": "Colour Test (2023)"},
    {"id": 2, "title": "Streaming Only: The Film", "year": 2024, "folder": "Streaming Only (2024)"},
    {"id": 3, "title": "Bright Lights", "year": 2019, "folder": "Bright Lights (2019)"},
]
SERIES_LIST = [{"id": 7, "title": "Test Show", "year": 2019, "folder": "Test Show"}]


def _images(app: str, item_id: int) -> list[dict]:
    return [
        {"coverType": "poster", "url": f"/{app}/MediaCover/{item_id}/poster.jpg?lastWrite=1"},
        {"coverType": "fanart", "url": f"/{app}/MediaCover/{item_id}/fanart.jpg?lastWrite=1"},
    ]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def _send(self, status: int, body: object = None, content_type: str = "application/json"):
        data = b"" if body is None else body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._route("POST")

    def _route(self, method: str) -> None:
        path = self.path.split("?")[0]
        app, _, rest = path.lstrip("/").partition("/")
        rest = "/" + rest
        if app in KEYS:
            if rest.startswith("/MediaCover/"):
                pictures = sorted(ART.glob("*.jpg"))
                if not pictures:
                    return self._send(404)
                return self._send(200, pictures[0].read_bytes(), "image/jpeg")
            if self.headers.get("X-Api-Key") != KEYS[app]:
                return self._send(401, {"error": "Unauthorized"})
            if rest == "/api/v3/system/status":
                return self._send(200, {"appName": app.title(), "version": "5.9.1"})
            if rest == "/api/v3/movie" and app == "radarr":
                return self._send(
                    200,
                    [
                        {**m, "path": f"{MOVIES}/{m['folder']}", "images": _images(app, m["id"])}
                        for m in MOVIE_LIST
                    ],
                )
            if rest == "/api/v3/series" and app == "sonarr":
                return self._send(
                    200,
                    [
                        {**s, "path": f"{TV}/{s['folder']}", "images": _images(app, s["id"])}
                        for s in SERIES_LIST
                    ],
                )
            if rest == "/api/v3/command" and method == "POST":
                return self._send(201, {"id": 1})
            return self._send(404)
        if app == "plex":
            if rest == "/identity":
                return self._send(200, {"MediaContainer": {"machineIdentifier": "x", "version": "1.41.0"}})
            if self.headers.get("X-Plex-Token") != "plex-token":
                return self._send(401)
            if rest == "/library/sections":
                return self._send(
                    200,
                    {
                        "MediaContainer": {
                            "Directory": [
                                {"key": "1", "type": "movie", "Location": [{"path": MOVIES}]},
                                {"key": "2", "type": "show", "Location": [{"path": TV}]},
                            ]
                        }
                    },
                )
            if rest.endswith("/refresh"):
                return self._send(200)
        return self._send(404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8496
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
