#!/usr/bin/env bash
# N10 申报观察记录完整性检查；不认证真人、不证明可用性或 M4、不自动解冻路线图。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

exec python3 scripts/verify_n10_observation_package.py "$@"
