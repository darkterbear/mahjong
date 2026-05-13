.PHONY: dev install test build run serve clean

# Make yarn (via corepack shims) available when it isn't already on PATH.
export PATH := /usr/local/lib/node_modules/corepack/shims:$(PATH)

# Override with: make serve PORT=9000
PORT ?= 8080

help:
	@echo "Targets:"
	@echo "  make install              — first-time setup (submodule + venv + yarn)"
	@echo "  make dev                  — run server + client concurrently (hot reload), Ctrl+C kills both"
	@echo "  make serve [PORT=8080]    — production-style: build client + run server on a single port"
	@echo "  make test                 — run all server + client tests"
	@echo "  make build                — production build of the client only"
	@echo "  make run  [PORT=8080]     — run the Python server only (no client build)"
	@echo "  make clean                — remove caches + client build artifacts"

dev:
	@trap 'kill 0' INT TERM EXIT; \
	(cd server-py && .venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload 2>&1 | sed -u 's/^/[server] /') & \
	(cd client && REACT_APP_API_URL=http://localhost:8080 NODE_OPTIONS=--openssl-legacy-provider PORT=5000 BROWSER=none yarn start 2>&1 | sed -u 's/^/[client] /') & \
	wait

install:
	git submodule update --init --recursive
	cd server-py && python3 -m venv .venv && \
	  .venv/bin/pip install --upgrade pip && \
	  .venv/bin/pip install -e ../subterfuge && \
	  .venv/bin/pip install -e '.[dev]'
	cd client && yarn install

test:
	cd server-py && .venv/bin/pytest -v
	cd client && CI=true yarn test --watchAll=false

build:
	cd client && NODE_OPTIONS=--openssl-legacy-provider yarn build

serve: build
	cd server-py && .venv/bin/uvicorn server.app:app --host 0.0.0.0 --port $(PORT)

run:
	cd server-py && .venv/bin/uvicorn server.app:app --host 0.0.0.0 --port $(PORT)

clean:
	rm -rf server-py/.pytest_cache server-py/server/__pycache__ server-py/tests/__pycache__
	rm -rf server-py/server.egg-info
	rm -rf client/build
