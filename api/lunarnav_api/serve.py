"""Production entry point: ONE process serving the built web UI and the API (Stage 11 deployment).

    uvicorn lunarnav_api.serve:app --host 0.0.0.0 --port 8000

* `/api/...` is the existing API, unchanged (the UI already calls `/api`, so the built UI works with no proxy).
* `/` serves the built UI (`web/dist`, or LUNARNAV_WEB_DIST) with a Content-Security-Policy that allows only this origin plus
  the NASA Moon Trek tile server for the basemap images.
* If the UI has not been built, only the API is served and `/` explains how to build it.
The plain API app (`lunarnav_api.main:app`, used by the tests and the dev server) is not changed by this module.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import get_settings
from .hardening import SecurityHeadersMiddleware
from .main import create_app

# Only this origin, plus NASA Moon Trek for the basemap tiles (plain images, no scripts). `style-src 'unsafe-inline'` is
# needed because React sets inline style attributes; scripts stay 'self' only.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://trek.nasa.gov; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


class _UiHeaders:
    """Add the CSP (and a revalidating cache policy) to UI responses only; `/api` keeps its own headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_ui(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"content-security-policy", CSP.encode()))
                if not scope["path"].startswith("/assets/"):          # hashed asset files may be cached; the HTML must revalidate
                    headers.append((b"cache-control", b"no-cache"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_ui)


def create_serving_app() -> ASGIApp:
    settings = get_settings()
    outer = FastAPI(title="Lunar Landing Site Navigator", docs_url=None, redoc_url=None, openapi_url=None)
    outer.mount("/api", create_app())            # API docs are at /api/docs

    dist = Path(settings.web_dist)
    if (dist / "index.html").is_file():
        ui = _UiHeaders(StaticFiles(directory=dist, html=True))
        outer.mount("/", ui)
    else:
        @outer.get("/", response_class=PlainTextResponse)
        def _no_ui() -> str:
            return ("The web UI has not been built. Run `npm ci && npm run build` in web/ (or set LUNARNAV_WEB_DIST). "
                    "The API is available under /api (see /api/docs).")

    return SecurityHeadersMiddleware(outer)


app = create_serving_app()
