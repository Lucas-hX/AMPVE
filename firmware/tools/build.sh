#!/usr/bin/env bash
# Build only. No serial port, flash, erase, security provisioning or deployment.
set -euo pipefail
AMPVE_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
: "${AMPVE_IDF_PATH:?Set AMPVE_IDF_PATH to the pinned ESP-IDF checkout}"
: "${AMPVE_WORK:?Set AMPVE_WORK to an isolated XiaoZhi checkout outside the repository}"
: "${AMPVE_TOOL_PYTHON:?Set AMPVE_TOOL_PYTHON to the firmware tooling virtualenv Python}"
: "${AMPVE_BUILD_MODE:=usb-assisted}"
if [[ "$AMPVE_BUILD_MODE" != usb-assisted && "$AMPVE_BUILD_MODE" != ota ]]; then
    echo 'AMPVE_BUILD_MODE must be usb-assisted or ota' >&2; exit 1
fi
if [[ $(git -C "$AMPVE_IDF_PATH" rev-parse HEAD) != fff9895c82d744c7237be8847347bdd1b07c6643 ]]; then
    echo 'Unreviewed ESP-IDF commit' >&2; exit 1
fi
"$AMPVE_TOOL_PYTHON" "$AMPVE_ROOT/firmware/tools/prepare.py" --work "$AMPVE_WORK" --mode "$AMPVE_BUILD_MODE"
"$AMPVE_TOOL_PYTHON" "$AMPVE_ROOT/firmware/tools/assets.py" --output "$AMPVE_WORK/main/ampve/brand_assets.c"
# ESP-IDF exports its own pinned Python environment and toolchain.
set +u
. "$AMPVE_IDF_PATH/export.sh"
set -u
cd "$AMPVE_WORK"
export SOURCE_DATE_EPOCH=1789257600
python scripts/gen_lang.py --language en-US --output main/assets/lang_config.h
export SDKCONFIG_DEFAULTS='sdkconfig.defaults;sdkconfig.defaults.esp32p4;sdkconfig.ampve'
# A prior generated configuration overrides defaults. Refuse silently reusing the old layout.
if [[ -f sdkconfig ]] && ! grep -q 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions/ampve/7b-stock-v1.csv"' sdkconfig; then
    cp sdkconfig sdkconfig.pre-stock-profile
    rm sdkconfig
fi
# Generated sdkconfig wins over defaults, including on existing development workdirs.
if [[ -f sdkconfig ]] && grep -q '^CONFIG_PM_SLEEP_CLK_ICG_ENABLE=y$' sdkconfig; then
    cp sdkconfig sdkconfig.pre-startup-retention-fix
    sed -i 's/^CONFIG_PM_SLEEP_CLK_ICG_ENABLE=y$/# CONFIG_PM_SLEEP_CLK_ICG_ENABLE is not set/' sdkconfig
fi
# Preserve AMPVE's runtime stack, but allocate it only after IDF reclaims startup RAM.
if [[ -f sdkconfig ]] && grep -q '^CONFIG_ESP_MAIN_TASK_STACK_SIZE=16384$' sdkconfig; then
    cp sdkconfig sdkconfig.pre-scheduler-stack-fix
    sed -i 's/^CONFIG_ESP_MAIN_TASK_STACK_SIZE=16384$/CONFIG_ESP_MAIN_TASK_STACK_SIZE=4096/' sdkconfig
fi
# Do not let an existing generated configuration silently change the release purpose.
if [[ -f sdkconfig && "$AMPVE_BUILD_MODE" == ota ]] && grep -q '^CONFIG_AMPVE_USB_COMMISSIONING=y$' sdkconfig; then
    sed -i 's/^CONFIG_AMPVE_USB_COMMISSIONING=y$/# CONFIG_AMPVE_USB_COMMISSIONING is not set/' sdkconfig
fi
if [[ -f sdkconfig && "$AMPVE_BUILD_MODE" == usb-assisted ]] && grep -q '^# CONFIG_AMPVE_USB_COMMISSIONING is not set$' sdkconfig; then
    sed -i 's/^# CONFIG_AMPVE_USB_COMMISSIONING is not set$/CONFIG_AMPVE_USB_COMMISSIONING=y/' sdkconfig
fi
if [[ ! -d components/78__esp-wifi-connect ]]; then
    idf.py -DIDF_TARGET=esp32p4 reconfigure
    "$AMPVE_TOOL_PYTHON" "$AMPVE_ROOT/firmware/tools/provisioning.py" --work "$AMPVE_WORK"
fi
idf.py -DIDF_TARGET=esp32p4 reconfigure
python "$AMPVE_ROOT/firmware/tools/check_lock.py" "$AMPVE_WORK/dependencies.lock"
nice -n 10 ninja -C build -j2
