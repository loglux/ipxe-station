#!/usr/bin/env bash
set -euo pipefail

HOST=""
USER_NAME="loglux"
REMOTE_PATH="/home/loglux/projects/ipxe-station"
BRANCH="master"
NO_PULL=0
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: scripts/remote-redeploy.sh --host <ip-or-host> [options]

Deploy iPXE Station on a remote machine over SSH by running:
  cd <remote-path>
  git fetch origin
  git checkout <branch>
  git pull --ff-only origin <branch>   (optional)
  ./deploy.sh redeploy

Options:
  --host <host>         Remote host/IP (required)
  --user <user>         SSH username (default: loglux)
  --path <path>         Remote repo path (default: /home/loglux/projects/ipxe-station)
  --branch <branch>     Git branch to deploy (default: master)
  --no-pull             Skip git pull (use current remote HEAD)
  --dry-run             Print SSH command without executing
  -h, --help            Show this help

Examples:
  scripts/remote-redeploy.sh --host 192.168.10.170
  scripts/remote-redeploy.sh --host 192.168.10.170 --branch master
  scripts/remote-redeploy.sh --host 192.168.10.170 --dry-run
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --user)
      USER_NAME="${2:-}"
      shift 2
      ;;
    --path)
      REMOTE_PATH="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --no-pull)
      NO_PULL=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "$HOST" ]; then
  echo "Error: --host is required" >&2
  usage
  exit 2
fi

read -r -d '' REMOTE_SCRIPT <<'REMOTE' || true
set -euo pipefail
cd "__REMOTE_PATH__"
git fetch origin
git checkout "__BRANCH__"
if [ "__NO_PULL__" = "0" ]; then
  git pull --ff-only origin "__BRANCH__"
fi
./deploy.sh redeploy
REMOTE

REMOTE_SCRIPT="${REMOTE_SCRIPT//__REMOTE_PATH__/$REMOTE_PATH}"
REMOTE_SCRIPT="${REMOTE_SCRIPT//__BRANCH__/$BRANCH}"
REMOTE_SCRIPT="${REMOTE_SCRIPT//__NO_PULL__/$NO_PULL}"

SSH_TARGET="${USER_NAME}@${HOST}"
SSH_CMD=(ssh "$SSH_TARGET" "bash -lc $(printf '%q' "$REMOTE_SCRIPT")")

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run command:"
  printf '%q ' "${SSH_CMD[@]}"
  echo
  exit 0
fi

echo "Deploying branch '$BRANCH' to $SSH_TARGET:$REMOTE_PATH"
"${SSH_CMD[@]}"
echo "Remote redeploy completed"
