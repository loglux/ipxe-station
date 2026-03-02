#!/bin/bash
# iPXE Station — deploy helper
# Wraps docker-compose and frontend build for common operations.

set -e

COMPOSE="docker-compose"
CONTAINER="ipxe-station"
PORT="9021"
FRONTEND_DIR="frontend"

# ── colours ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
info() { echo -e "${BLUE}→ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
err()  { echo -e "${RED}✗ $*${NC}"; exit 1; }

# ── helpers ────────────────────────────────────────────────────────────────────
build_frontend() {
    info "Building frontend..."
    if [ ! -d "$FRONTEND_DIR" ]; then
        warn "No frontend/ directory — skipping"
        return
    fi
    if command -v npm >/dev/null 2>&1; then
        (cd "$FRONTEND_DIR" && npm install && npm run build)
    else
        info "npm not found — building via Docker Node container..."
        docker run --rm \
            -v "$(pwd)/$FRONTEND_DIR:/frontend" \
            -w /frontend \
            node:20-alpine \
            sh -c "npm install && npm run build"
    fi
    ok "Frontend built → app/frontend/dist/"
}

wait_ready() {
    info "Waiting for service on :${PORT}..."
    for i in $(seq 1 20); do
        if curl -sf "http://localhost:${PORT}/status" >/dev/null 2>&1; then
            ok "Service is up: http://localhost:${PORT}"
            return
        fi
        sleep 2
    done
    warn "Service did not respond in time — check: $COMPOSE logs -f"
}

# ── commands ───────────────────────────────────────────────────────────────────

cmd_deploy() {
    info "Full deploy: build frontend → build image → (re)start container"
    build_frontend
    $COMPOSE up -d --build
    wait_ready
}

cmd_redeploy() {
    info "Redeploy without rebuilding image (frontend + restart)"
    build_frontend
    $COMPOSE restart
    wait_ready
}

cmd_frontend() {
    build_frontend
    warn "Hard-reload your browser (Ctrl+Shift+R) to pick up new assets"
}

cmd_start()   { $COMPOSE up -d;   ok "Started"; }
cmd_stop()    { $COMPOSE down;    ok "Stopped"; }
cmd_restart() { $COMPOSE restart; wait_ready; }
cmd_logs()    { $COMPOSE logs -f; }
cmd_status()  {
    $COMPOSE ps
    docker exec "$CONTAINER" curl -sf http://localhost:${PORT}/status 2>/dev/null \
        | python3 -m json.tool 2>/dev/null || true
}

cmd_backup() {
    local name="ipxe-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    info "Backing up data/ → ${name}"
    tar -czf "$name" data/
    ok "Backup saved: $name  ($(du -sh "$name" | cut -f1))"
}

cmd_restore() {
    local file="$1"
    [ -z "$file" ] && err "Usage: $0 restore <backup-file.tar.gz>"
    [ -f "$file" ]  || err "File not found: $file"
    warn "This will overwrite data/ — continue? (y/N)"
    read -r confirm
    [[ $confirm == [yY] ]] || { info "Cancelled"; exit 0; }
    tar -xzf "$file"
    ok "Restored from $file"
}

cmd_info() {
    echo
    echo "  Container : $(docker ps --filter name=$CONTAINER --format '{{.Status}}' 2>/dev/null || echo 'not running')"
    echo "  URL       : http://localhost:${PORT}"
    echo "  Data dir  : $(pwd)/data"
    echo
    echo "  Storage:"
    du -sh data/srv/tftp data/srv/http data/srv/ipxe data/srv/dhcp 2>/dev/null \
        | awk '{printf "    %-30s %s\n", $2, $1}' || true
    echo
    echo "  Ubuntu versions:"
    find data/srv/http -maxdepth 1 -name "ubuntu-*" -type d 2>/dev/null \
        | sort | sed 's|.*/|    • |' || echo "    none"
    echo
}

cmd_help() {
    cat <<'EOF'

  iPXE Station — deploy.sh

  Usage: ./deploy.sh <command>

  Commands:
    deploy      Build frontend + Docker image, start container   (first run / Dockerfile changed)
    redeploy    Rebuild frontend, restart container              (Python code changes)
    frontend    Rebuild frontend only, no container restart      (JS/CSS changes)

    start       docker-compose up -d
    stop        docker-compose down
    restart     docker-compose restart
    logs        Follow container logs
    status      Container status + /status endpoint

    backup      Archive data/ to timestamped .tar.gz
    restore     Restore data/ from a .tar.gz backup
    info        Show data directory sizes and installed versions

  When to use what:
    Dockerfile / requirements.txt changed  →  deploy
    Python (app/) changed                  →  restart   (uvicorn --reload picks it up automatically)
    Frontend (frontend/src/) changed       →  frontend  (then Ctrl+Shift+R in browser)

EOF
}

# ── dispatch ───────────────────────────────────────────────────────────────────
case "${1:-help}" in
    deploy)         cmd_deploy ;;
    redeploy)       cmd_redeploy ;;
    frontend)       cmd_frontend ;;
    start)          cmd_start ;;
    stop)           cmd_stop ;;
    restart)        cmd_restart ;;
    logs)           cmd_logs ;;
    status)         cmd_status ;;
    backup)         cmd_backup ;;
    restore)        cmd_restore "$2" ;;
    info)           cmd_info ;;
    help|--help|-h) cmd_help ;;
    *)              err "Unknown command: $1 — run ./deploy.sh help" ;;
esac
