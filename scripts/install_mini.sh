#!/usr/bin/env bash
# Install mini-swe-agent for agent:mini (ADR-0018), the one way it is installed:
# exact versions from requirements-mini.txt, hash-checked, WITHOUT dependencies.
#
#   scripts/install_mini.sh
#   PYTHON=~/.venvs/blindspots/bin/python scripts/install_mini.sh
#
# Why without dependencies: mini-swe-agent 2.4.6 requires litellm, whose
# filelock<4 cap would downgrade the harness's filelock. agent:mini never
# imports litellm; see requirements-mini.txt and ADR-0018.
#
# Uses pip when the Python has it (CI), otherwise uv (the local venv).

set -euo pipefail

PYTHON=${PYTHON:-python}
repo_root=$(cd "$(dirname "$0")/.." && pwd)
req="$repo_root/requirements-mini.txt"

if "$PYTHON" -m pip --version >/dev/null 2>&1; then
    "$PYTHON" -m pip install --no-deps --require-hashes -r "$req"
else
    uv pip install --python "$PYTHON" --no-deps --require-hashes -r "$req"
fi

"$PYTHON" - <<'EOF'
from importlib.metadata import version
for name in ("mini-swe-agent", "jinja2", "markupsafe"):
    print(f"installed {name}=={version(name)}")
EOF
