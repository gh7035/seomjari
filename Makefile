PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: setup setup-web data dev api web build run test clean deploy

## Python 환경 (평가 환경은 이것만 필요)
setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e ".[dev]"

## 프론트 개발 환경 (개발자만 필요)
setup-web:
	cd apps/web && npm install

## data/raw CSV → data/processed parquet
data:
	$(BIN)/python -m pipeline.build_data

## 개발: API(8000) + Vite(5173) 동시 실행
dev:
	$(MAKE) -j2 api web

api:
	$(BIN)/uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

## 프론트 빌드 → apps/api/static (커밋 대상)
build:
	cd apps/web && npm run build

## 평가 실행: Python만으로 API + 프론트 서빙
run:
	$(BIN)/uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

test:
	$(BIN)/pytest -q

## Ubuntu 인스턴스에 scp 후 blue/green 무중단 교체
deploy:
	bash deploy/deploy.sh

clean:
	rm -rf $(VENV) apps/web/node_modules
