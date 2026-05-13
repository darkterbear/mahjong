# mahjong

Web-based multiplayer Taiwanese 16-tile Mahjong (with full DAN scoring per ~/subterfuge).

## Stack

- Server: Python (FastAPI + python-socketio + uvicorn). Imports `subterfuge` as a git submodule.
- Client: React (existing). socket.io-client for the realtime layer.
- Scoring: pluggable via subterfuge's `DanFullRuleset`.

## Setup

Requires Python 3.11+, Node 16+ with yarn, and git.

```bash
git clone --recurse-submodules git@github.com:darkterbear/mahjong.git
cd mahjong
make install
```

## Run

```bash
make dev
```

Server on http://localhost:8080, client on http://localhost:5000. Ctrl+C kills both.

## Other Make targets

- `make test` — run all server + client tests
- `make build` — production build of the client
- `make run` — Python server only (no auto-reload)
- `make clean` — remove caches and the client build

## Bumping subterfuge

```bash
cd subterfuge
git fetch
git checkout <new-sha>
cd ..
git add subterfuge
git commit -m "Bump subterfuge to <new-sha>"
```

## Attribution

[Mahjong Tile Vectors](https://commons.wikimedia.org/wiki/Category:SVG_Oblique_illustrations_of_Mahjong_tiles) by [Cangjie6](https://commons.wikimedia.org/wiki/User:Cangjie6) is licensed under CC BY-SA 4.0.
