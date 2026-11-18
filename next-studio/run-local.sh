#!/bin/sh
set -eu
cd "$(dirname "$0")"
studio_node=${STUDIO_NODE:-$(command -v node || true)}
if [ -z "$studio_node" ]; then
  studio_node="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
fi
if [ ! -x "$studio_node" ] || [ ! -f node_modules/next/dist/bin/next ]; then
  printf '%s\n' 'Node.js 24 and project Next.js dependencies are required.' >&2
  exit 1
fi
export NEXT_TELEMETRY_DISABLED=1
case "${1:-start}" in
  build) exec "$studio_node" node_modules/next/dist/bin/next build ;;
  dev|start) exec "$studio_node" node_modules/next/dist/bin/next "${1:-start}" --hostname 127.0.0.1 --port "${STUDIO_PORT:-3037}" ;;
  worker) exec "$studio_node" --env-file-if-exists=.env.local scripts/worker.mjs ;;
  test) exec "$studio_node" --test scripts/workflow.test.mjs ;;
  *) printf '%s\n' 'Usage: sh run-local.sh [build|start|dev|worker|test]' >&2; exit 2 ;;
esac
