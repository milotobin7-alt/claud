#!/bin/bash
# SessionStart hook: install cloudledger and its dev tooling so that pytest,
# ruff and the `cloudledger` console script are available from the first turn
# of a Claude Code on the web session.
set -euo pipefail

# Local sessions manage their own virtualenv; only set up the remote container.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# Editable install, so the tree stays the source of truth and re-running this
# hook on resume is a cheap no-op rather than a rebuild.
# No pip self-upgrade here: on a distro-managed pip that fails outright and
# would take the whole hook down with it under `set -e`.
python3 -m pip install --quiet -e ".[dev]"

echo "cloudledger dev environment ready: $(python3 -m pytest --version 2>&1 | head -1), $(ruff --version)"
