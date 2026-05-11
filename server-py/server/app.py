"""FastAPI + python-socketio entrypoint."""
from __future__ import annotations

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routes import router

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["https://mahjong.terranceli.com", "http://localhost:5000"],
)
fastapi_app = FastAPI()
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mahjong.terranceli.com", "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
fastapi_app.include_router(router)
app = socketio.ASGIApp(sio, fastapi_app)


@fastapi_app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@sio.event
async def connect(sid: str, environ: dict) -> None:
    pass


@sio.event
async def disconnect(sid: str) -> None:
    pass
