#!/usr/bin/env bash
set -euo pipefail
# Run in the repository root. Creates only local files, never cloud resources.
cd "$(dirname "$0")/../.."
python3 -m venv .venv
.venv/bin/python -m pip install -r cloud/health_exam/requirements.lock.txt
if [[ -z "${HEALTH_API_KEY:-}" ]]; then
  echo 'Set HEALTH_API_KEY in this shell before starting (at least 24 random characters).' >&2
  exit 1
fi
export DATABASE_URL="${DATABASE_URL:-sqlite:///./data/exams.db}"
exec .venv/bin/python -m uvicorn cloud.health_exam.app:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}"
