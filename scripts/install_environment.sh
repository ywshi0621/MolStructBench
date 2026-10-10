#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v bwrap >/dev/null || { echo "Install bubblewrap and python3.10-venv with your OS package manager"; exit 2; }
mkdir -p .runtime/bin .runtime/cache
if [ -f vendor/opencode-linux-x64 ]; then
  cp vendor/opencode-linux-x64 .runtime/bin/opencode
else
  curl --fail --location --connect-timeout 20 --max-time 120 --retry 2 https://github.com/anomalyco/opencode/releases/download/v1.2.27/opencode-linux-x64.tar.gz -o .runtime/opencode.tar.gz
  python3.10 - <<'PY'
import hashlib,json,pathlib
expected=json.loads(pathlib.Path('configs/artifact_hashes.json').read_text())['opencode-linux-x64.tar.gz']
assert hashlib.sha256(pathlib.Path('.runtime/opencode.tar.gz').read_bytes()).hexdigest()==expected
PY
  tar -xzf .runtime/opencode.tar.gz -C .runtime/bin
fi
chmod +x .runtime/bin/opencode
python3.10 - <<'PY'
import hashlib,json,pathlib
expected=json.loads(pathlib.Path('configs/artifact_hashes.json').read_text())['opencode-linux-x64']
assert hashlib.sha256(pathlib.Path('.runtime/bin/opencode').read_bytes()).hexdigest()==expected
PY
python3.10 -m venv .runtime/venv
.runtime/venv/bin/python -m pip install -r tools/requirements-lock.txt
.runtime/venv/bin/python -m pip install -e .
.runtime/bin/opencode --version
.runtime/venv/bin/python -m tests.isolation_probe --venv "$PWD/.runtime/venv" --output .runtime/isolation_test.json
