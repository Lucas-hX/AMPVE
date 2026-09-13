#!/usr/bin/env bash
# Build only. No serial port, flash, erase, security provisioning or deployment.
set -euo pipefail
AMPVE_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
: "${AMPVE_IDF_PATH:?Set AMPVE_IDF_PATH to the pinned ESP-IDF checkout}"
: "${AMPVE_WORK:?Set AMPVE_WORK to an isolated XiaoZhi checkout outside the repository}"
: "${AMPVE_TOOL_PYTHON:?Set AMPVE_TOOL_PYTHON to the firmware tooling virtualenv Python}"
if [[ $(git -C "$AMPVE_IDF_PATH" rev-parse HEAD) != fff9895c82d744c7237be8847347bdd1b07c6643 ]]; then
    echo 'Unreviewed ESP-IDF commit' >&2; exit 1
fi
"$AMPVE_TOOL_PYTHON" "$AMPVE_ROOT/firmware/tools/prepare.py" --work "$AMPVE_WORK"
"$AMPVE_TOOL_PYTHON" "$AMPVE_ROOT/firmware/tools/assets.py" --output "$AMPVE_WORK/main/ampve/brand_assets.c"
# ESP-IDF exports its own pinned Python environment and toolchain.
set +u
. "$AMPVE_IDF_PATH/export.sh"
set -u
cd "$AMPVE_WORK"
export SOURCE_DATE_EPOCH=1789257600
python scripts/gen_lang.py --language en-US --output main/assets/lang_config.h
export SDKCONFIG_DEFAULTS='sdkconfig.defaults;sdkconfig.defaults.esp32p4;sdkconfig.ampve'
if [[ ! -d components/78__esp-wifi-connect ]]; then
    idf.py -DIDF_TARGET=esp32p4 reconfigure
    "$AMPVE_TOOL_PYTHON" "$AMPVE_ROOT/firmware/tools/provisioning.py" --work "$AMPVE_WORK"
fi
idf.py -DIDF_TARGET=esp32p4 reconfigure
python "$AMPVE_ROOT/firmware/tools/check_lock.py" "$AMPVE_WORK/dependencies.lock"
nice -n 10 ninja -C build -j2
