#!/usr/bin/env bash
# M4 排期信号包机械 gate；不证明 N10，不授权部署，也不自动解冻路线图。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

exec python3 scripts/verify_m4_signal_package.py "$@"
