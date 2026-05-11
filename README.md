# mahjong

Web-based multiplayer Taiwanese 16-tile Mahjong (with full DAN scoring per ~/subterfuge).

## Stack

- Server: Python (FastAPI + python-socketio + uvicorn). Imports `subterfuge` as a git submodule.
- Client: React (existing). socket.io-client for the realtime layer.
- Scoring: pluggable via subterfuge's `DanFullRuleset`.

## Setup

```bash
git clone --recurse-submodules git@github.com:darkterbear/mahjong.git
cd mahjong

# Server
cd server-py
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../subterfuge
pip install -e '.[dev]'
uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload

# Client (in another terminal)
cd ../client
yarn install
yarn start
```

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
