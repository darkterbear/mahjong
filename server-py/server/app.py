"""FastAPI + python-socketio entrypoint."""
from __future__ import annotations

from pathlib import Path

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.routes import router

_ALLOWED_ORIGINS = [
    "http://localhost:5000",     # dev split mode (client served by yarn start)
    "http://localhost:8080",     # single-port local (make serve)
    "https://mahjong.terranceli.com",
]
# Plus any onrender.com subdomain so the deployed instance Just Works.
_ALLOWED_ORIGIN_REGEX = r"^https://[a-z0-9-]+\.onrender\.com$"

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_ALLOWED_ORIGINS,
    # Ping every 15s so even a 30s nginx proxy_read_timeout stays awake.
    # ping_timeout is how long we wait for a pong before declaring the peer
    # dead — keep it modest so a broken socket cleans up quickly.
    ping_interval=15,
    ping_timeout=20,
)
fastapi_app = FastAPI()
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.include_router(router)


@fastapi_app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@sio.event
async def connect(sid: str, environ: dict) -> None:
    pass


# Mount the built React client if it exists. Production single-port mode:
# `yarn build` produces client/build/, FastAPI serves those static assets
# from / and falls back to index.html for SPA routing.
_BUILD_DIR = Path(__file__).resolve().parent.parent.parent / "client" / "build"
if _BUILD_DIR.is_dir():
    # Catch-all SPA fallback. Must be registered BEFORE the StaticFiles mount
    # so that paths like /game, /lobby, /join return index.html rather than 404.
    _INDEX_HTML = _BUILD_DIR / "index.html"

    @fastapi_app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Try the exact file first.
        candidate = _BUILD_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        # Otherwise serve the SPA's index.html.
        return FileResponse(_INDEX_HTML)


# Wrap FastAPI with socket.io to share the same ASGI app.
app = socketio.ASGIApp(sio, fastapi_app)

# Side-effect import: registers all socket event handlers.
from server import sockets  # noqa: F401, E402
