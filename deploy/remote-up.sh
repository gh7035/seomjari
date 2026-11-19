#!/usr/bin/env bash
# 서버에서 실행된다. 프록시는 유지하고 앱 컨테이너만 blue/green 으로 교체한다.
set -euo pipefail

APP_DIR=/opt/seomjari
INCOMING="${HOME}/seomjari-incoming"
SRC_TAR="${INCOMING}/seomjari-src.tar.gz"
IMG_TAR="${INCOMING}/seomjari-app.tar.gz"
ENV_TAR="${INCOMING}/seomjari.env"

install_docker() {
  if docker compose version >/dev/null 2>&1 || sudo docker compose version >/dev/null 2>&1; then
    return
  fi
  sudo apt-get update
  sudo apt-get install -y docker.io docker-compose-v2
  sudo systemctl enable --now docker
}

if [[ -f "$SRC_TAR" ]]; then
  sudo mkdir -p "$APP_DIR"
  sudo chown "$(id -u):$(id -g)" "$APP_DIR"
  # 실행 중인 프록시가 보고 있는 업스트림은 압축을 풀며 되돌려 쓰지 않는다.
  saved_upstream=""
  if [[ -f "$APP_DIR/deploy/upstream.caddy" ]]; then
    saved_upstream=$(cat "$APP_DIR/deploy/upstream.caddy")
  fi
  tar -xzf "$SRC_TAR" -C "$APP_DIR"
  rm -f "$SRC_TAR"
  if [[ -n "$saved_upstream" ]]; then
    printf '%s\n' "$saved_upstream" > "$APP_DIR/deploy/upstream.caddy"
  fi
fi

cd "$APP_DIR"
install_docker

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

if [[ -f "$ENV_TAR" ]]; then
  mv "$ENV_TAR" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi
[[ -f "$APP_DIR/.env" ]] || touch "$APP_DIR/.env"
if [[ ! -f deploy/site.env ]]; then
  cp deploy/site.env.example deploy/site.env
fi

# 앱 하나당 RAM 의 30%. 상한 512MB, 하한 192MB. 스왑은 쓰지 않는다.
total_kb=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)
app_kb=$((total_kb * 30 / 100))
((app_kb < 192 * 1024)) && app_kb=$((192 * 1024))
((app_kb > 512 * 1024)) && app_kb=$((512 * 1024))
app_mb=$((app_kb / 1024))
cat > deploy/mem.env <<EOF
APP_MEM_LIMIT=${app_mb}m
CADDY_MEM_LIMIT=64m
EOF
echo "메모리 한도: 앱 ${app_mb}m x 2슬롯, caddy 64m (호스트 MemTotal $((total_kb / 1024))m)"

if [[ -f "$IMG_TAR" ]]; then
  gunzip -c "$IMG_TAR" | "${DOCKER[@]}" load
  rm -f "$IMG_TAR"
else
  avail_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
  build_kb=$((avail_kb - 160 * 1024))
  ((build_kb < 256 * 1024)) && build_kb=$((256 * 1024))
  build_mb=$((build_kb / 1024))
  echo "서버에서 이미지를 빌드합니다. 빌드 메모리 한도 ${build_mb}m"
  if ! "${DOCKER[@]}" build --memory "${build_mb}m" --memory-swap "${build_mb}m" -t seomjari:app .; then
    echo "메모리 한도 빌드가 거절되어 한도 없이 한 번 더 시도합니다."
    "${DOCKER[@]}" build -t seomjari:app .
  fi
fi

active=none
[[ -f deploy/active ]] && active=$(cat deploy/active)
if [[ "$active" == "blue" ]]; then
  next=green
else
  next=blue
fi

avail_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
need_kb=$((app_kb + 96 * 1024))
if ((avail_kb < need_kb)); then
  echo "가용 메모리가 $((avail_kb / 1024))m 입니다. 새 컨테이너에 $((need_kb / 1024))m 이 필요해 기존 서비스를 유지하고 중단합니다." >&2
  exit 1
fi

COMPOSE=("${DOCKER[@]}" compose --env-file deploy/site.env --env-file deploy/mem.env)

"${COMPOSE[@]}" up -d caddy
"${COMPOSE[@]}" up -d --no-deps --force-recreate --no-build "$next"

container="seomjari-${next}"
healthy=0
for _ in $(seq 1 40); do
  status=$("${DOCKER[@]}" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || echo missing)
  if [[ "$status" == "healthy" ]]; then
    healthy=1
    break
  fi
  if [[ "$status" == "unhealthy" ]]; then
    break
  fi
  sleep 3
done

if [[ "$healthy" != 1 ]]; then
  echo "새 컨테이너가 준비되지 않았습니다. 기존 슬롯을 유지합니다." >&2
  "${DOCKER[@]}" logs --tail 80 "$container" >&2 || true
  "${COMPOSE[@]}" stop "$next" || true
  exit 1
fi

printf 'reverse_proxy %s:8000\n' "$next" > deploy/upstream.caddy
reloaded=0
for _ in $(seq 1 5); do
  if "${DOCKER[@]}" exec seomjari-caddy caddy reload --config /etc/caddy/Caddyfile; then
    reloaded=1
    break
  fi
  sleep 2
done
if [[ "$reloaded" != 1 ]]; then
  echo "프록시 재적재에 실패했습니다. 새 컨테이너를 내리고 기존 슬롯을 유지합니다." >&2
  "${COMPOSE[@]}" stop "$next" || true
  if [[ "$active" != "none" ]]; then
    printf 'reverse_proxy %s:8000\n' "$active" > deploy/upstream.caddy
  fi
  exit 1
fi

if [[ "$active" != "none" && "$active" != "$next" ]]; then
  old="seomjari-${active}"
  for _ in $(seq 1 45); do
    open=$("${DOCKER[@]}" exec "$old" cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | awk '$4=="01" { split($2,a,":"); if (tolower(a[2])=="1f40") c++ } END { print c+0 }' || echo 0)
    [[ "${open:-0}" == "0" ]] && break
    sleep 2
  done
  "${COMPOSE[@]}" stop "$active"
fi

echo "$next" > deploy/active
echo "배포 완료. 활성 슬롯: ${next}"
