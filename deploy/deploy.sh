#!/usr/bin/env bash
# 로컬에서 실행한다. 소스를 scp 로 올리고, 서버의 remote-up.sh 가 무중단 교체한다.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
HOST=${DEPLOY_HOST:-ubuntu@43.202.11.30}
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=12)
if [[ -n "${DEPLOY_SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$DEPLOY_SSH_KEY" -o IdentitiesOnly=yes)
fi
SSH=(ssh "${SSH_OPTS[@]}")
SCP=(scp "${SSH_OPTS[@]}")

SRC=$(mktemp /tmp/seomjari-src.XXXXXX.tar.gz)
IMG=""
cleanup() {
  rm -f "$SRC" ${IMG:+"$IMG"}
}
trap cleanup EXIT

tar -C "$ROOT" -czf "$SRC" \
  --exclude .git \
  --exclude .venv \
  --exclude node_modules \
  --exclude data/raw \
  --exclude 'data/sessions.sqlite3*' \
  --exclude .env \
  --exclude deploy/active \
  --exclude deploy/mem.env \
  --exclude deploy/site.env \
  --exclude docs \
  .

echo "소스를 ${HOST} 로 올립니다."
"${SSH[@]}" "$HOST" 'mkdir -p "$HOME/seomjari-incoming"'
"${SCP[@]}" "$SRC" "${HOST}:seomjari-incoming/seomjari-src.tar.gz"

if [[ -f "$ROOT/.env" ]]; then
  "${SCP[@]}" "$ROOT/.env" "${HOST}:seomjari-incoming/seomjari.env"
fi

if docker info >/dev/null 2>&1; then
  echo "로컬 Docker 로 이미지를 만들어 올립니다."
  docker build --platform "${DEPLOY_PLATFORM:-linux/amd64}" -t seomjari:app "$ROOT"
  IMG=$(mktemp /tmp/seomjari-app.XXXXXX.tar.gz)
  docker save seomjari:app | gzip > "$IMG"
  "${SCP[@]}" "$IMG" "${HOST}:seomjari-incoming/seomjari-app.tar.gz"
else
  echo "로컬 Docker 데몬이 없어 서버에서 빌드합니다."
  "${SSH[@]}" "$HOST" 'rm -f "$HOME/seomjari-incoming/seomjari-app.tar.gz"'
fi

"${SSH[@]}" "$HOST" 'bash -s' < "$ROOT/deploy/remote-up.sh"
