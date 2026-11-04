#!/usr/bin/env bash
# Build, then run the unit and browser checks. Screenshots land in shots/.
#   test/run.sh            # local recordings (fast)
#   test/run.sh --r2       # stream the public R2 recordings, as the published page does
set -euo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)"; cd "$H"
for f in src/js/*.js serve.cjs test/*.cjs; do node --check "$f"; done
python3 build.py "${BUILD_ARGS:---skip-media}" 2>/dev/null || python3 build.py
node test/unit.test.cjs
node test/browser.test.cjs "$@"
