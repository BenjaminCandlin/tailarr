"""Start Tailarr: `python -m tailarr`."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "tailarr.main:create_app",
        factory=True,
        host=os.environ.get("TAILARR_HOST", "0.0.0.0"),
        port=int(os.environ.get("TAILARR_PORT", "8484")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
