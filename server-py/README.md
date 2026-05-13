# mahjong-server

Python server for Taiwanese 16-tile mahjong. Imports `subterfuge` as a path dependency.

## Setup

```bash
cd server-py
python3 -m venv .venv
source .venv/bin/activate
pip install -e ../subterfuge       # editable install of the submodule
pip install -e '.[dev]'            # this server, with dev deps
```

## Run

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
```

## Test

```bash
pytest -v
```
