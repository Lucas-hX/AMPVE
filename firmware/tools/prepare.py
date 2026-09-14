"""Apply the reviewed integration to an isolated pinned XiaoZhi checkout; never flash."""
import argparse
import os
from improv_integration import prepare as prepare_improv
from credential_guard import prepare as prepare_credentials
from wifi_guard import prepare as prepare_wifi
from board_guard import prepare as prepare_board
from audio_guard import prepare as prepare_audio
from native_trust import generate as generate_native_trust
import json
import shutil
import subprocess
from pathlib import Path
from profile_contract import PROFILE, native_header

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = json.loads((ROOT/'firmware/xiaozhi/upstream.json').read_text())
PIN = UPSTREAM['commit']


def replace(path, old, new):
    data = path.read_text()
    if old not in data:
        raise RuntimeError('Upstream contract changed: '+str(path))
    path.write_text(data.replace(old, new))


def stage_overlay(source, destination):
    # Restaging changed bytes must invalidate existing compiler objects even when
    # the repository source timestamp predates the last compilation. copy2 can
    # otherwise preserve an old timestamp and silently reuse a stale object.
    shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=shutil.copyfile)


def prepare(work, mode='usb-assisted'):
    if mode not in {'usb-assisted', 'ota'}:
        raise ValueError('Firmware mode must be usb-assisted or ota')
    if PROFILE['source']['commit'] != PIN or PROFILE['id'] != UPSTREAM['hardware_profile']:
        raise RuntimeError('Hardware profile and pinned firmware source differ')
    if work.is_relative_to(ROOT) or any((parent/'.git').exists() for parent in work.parents):
        raise RuntimeError('Build workspaces must stay outside AMPVE and every enclosing Git checkout')
    if not work.exists():
        subprocess.run(['git','clone','--filter=blob:none','--no-checkout',
            'https://github.com/78/xiaozhi-esp32.git',str(work)],check=True)
        subprocess.run(['git','-C',str(work),'checkout','--detach',PIN],check=True)
    if subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD']).decode().strip() != PIN:
        raise RuntimeError('Checkout must be detached at '+PIN)
    marker=work/'.ampve-prepared'
    if not marker.exists():
        if subprocess.check_output(['git','-C',str(work),'diff','--name-only']).strip():
            raise RuntimeError('Refusing to patch modified upstream checkout.')
        cmake=work/'CMakeLists.txt'
        replace(cmake,'set(PROJECT_VER "2.5.0")','set(PROJECT_VER "0.1.0-dev")')
        replace(work/'main/CMakeLists.txt','set(SOURCES "audio/audio_codec.cc"',
            'set(SOURCES "ampve/runtime.cc" "ampve/brand_assets.c" "audio/audio_codec.cc"')
        replace(work/'main/CMakeLists.txt','PRIV_REQUIRES\n','PRIV_REQUIRES\n                        esp_http_client esp-tls espressif__cjson esp_timer esp_psram\n')
        replace(work/'main/audio/codecs/box_audio_codec.cc',
            '    ESP_ERROR_CHECK(i2s_channel_enable(rx_handle_));',
            '    // AMPVE shell: leave the RX DMA channel disabled; no microphone capture.')
        wifi=work/'main/boards/common/wifi_board.cc'
        replace(wifi,'config.ssid_prefix = "Xiaozhi";','config.ssid_prefix = "AMPVE";')
        replace(wifi,'config.show_ota_config = true;','config.show_ota_config = false;')
        replace(wifi,'config.show_sleep_config = true;','config.show_sleep_config = false;')
        # The native shell owns lifecycle; never enter the upstream application/audio state machine.
        s=wifi.read_text();a=s.index('    // Transition to wifi configuring state');b=s.index('\n}\n',a)
        s=s[:a]+'''#ifdef CONFIG_USE_HOTSPOT_WIFI_PROVISIONING
    WifiManager::GetInstance().StartConfigAp();
#endif'''+s[b:]
        a=s.index('    ESP_LOGI(TAG, "EnterWifiConfigMode called");');b=s.index('\n}\n',a)
        s=s[:a]+'''    esp_timer_stop(connect_timer_);
    WifiManager::GetInstance().StopStation();
    StartWifiConfigMode();'''+s[b:]
        s=s.replace('ESP_LOGI(TAG, "Connected to WiFi: %s", data.c_str());','ESP_LOGI(TAG, "WiFi connected");')
        s=s.replace('ESP_LOGI(TAG, "WiFi connecting to %s", data.c_str());','ESP_LOGI(TAG, "WiFi connecting");')
        wifi.write_text(s)
        marker.write_text(PIN+'\n')
    overlay=ROOT/'firmware/xiaozhi/overlay'
    cmake=work/'CMakeLists.txt'
    if 'set(PROJECT_VER "0.1.12-startup-fix-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.12-startup-fix-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')

    cmake=work/'CMakeLists.txt'
    if 'set(PROJECT_VER "0.1.0-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.0-dev")','set(PROJECT_VER "0.1.1-stock-dev")')
    if 'set(PROJECT_VER "0.1.1-stock-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.1-stock-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.2-profile-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.2-profile-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.3-ota-verify-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.3-ota-verify-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.4-ota-client-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.4-ota-client-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.5-ota-recovery-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.5-ota-recovery-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.6-audio-guard-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.6-audio-guard-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.7-boot-guard-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.7-boot-guard-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.8-display-guard-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.8-display-guard-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.8-startup-guard-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.8-startup-guard-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.9-wifi-storage-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.9-wifi-storage-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.10-improv-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.10-improv-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.11-usb-setup-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.11-usb-setup-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.13-scheduler-fix-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.13-scheduler-fix-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.14-touch-fix-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.14-touch-fix-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.15-touch-ota-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.15-touch-ota-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.16-touch-ota-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.16-touch-ota-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.17-visual-console-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.17-visual-console-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if 'set(PROJECT_VER "0.1.18-companion-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.18-companion-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    for previous in ('0.1.19-companion-aec-dev', '0.1.19-companion-face-dev'):
        if f'set(PROJECT_VER "{previous}")' in cmake.read_text():
            replace(cmake, f'set(PROJECT_VER "{previous}")',
                    f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")' not in cmake.read_text():
        raise RuntimeError('Prepared project version differs from the candidate version')
    component=work/'main/idf_component.yml'
    if 'espressif/libsodium:' not in component.read_text():
        replace(component,'dependencies:\n','dependencies:\n  espressif/libsodium: "==1.0.22~1"\n')
    if '78/uart-uhci:' not in component.read_text():
        # This transitive range has newer registry releases. Keep the reviewed
        # transport bytes fixed when Component Manager must resolve again.
        replace(component,'dependencies:\n','dependencies:\n  78/uart-uhci: "==0.3.2"\n')
    commissioning_kconfig=work/'main/Kconfig.projbuild'
    if 'config AMPVE_USB_COMMISSIONING' not in commissioning_kconfig.read_text():
        with commissioning_kconfig.open('a') as stream:
            stream.write('\nconfig AMPVE_USB_COMMISSIONING\n    bool "AMPVE initial USB commissioning"\n    default n\n')
    component_cmake=work/'main/CMakeLists.txt'
    if '"ampve/ota_policy.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES "ampve/runtime.cc"',
                'set(SOURCES "ampve/image_identity.cc" "ampve/ota_policy.cc" "ampve/runtime.cc"')
        replace(component_cmake,'PRIV_REQUIRES\n','PRIV_REQUIRES\n                        espressif__libsodium\n')
    if '"ampve/image_identity.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES "ampve/ota_policy.cc"',
                'set(SOURCES "ampve/image_identity.cc" "ampve/ota_policy.cc"')
    if '"ampve/ota_client.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES ', 'set(SOURCES "ampve/ota_client.cc" "ampve/ota_platform.cc" ')
    if '"ampve/companion.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES ', 'set(SOURCES "ampve/companion.cc" ')
    if '"ampve/companion_face.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES ', 'set(SOURCES "ampve/companion_face.cc" ')
    if '"ampve/boot_guard.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES ', 'set(SOURCES "ampve/boot_guard.cc" ')
    wifi_board=work/'main/boards/common/wifi_board.cc'
    if '#include "ampve/runtime.h"' not in wifi_board.read_text():
        replace(wifi_board,'#include "wifi_board.h"','#include "wifi_board.h"\n#include "ampve/runtime.h"')
    if '    wifi_manager.Initialize(config);' in wifi_board.read_text():
        replace(wifi_board,'    wifi_manager.Initialize(config);',
            '    ampve_wifi_initialized = wifi_manager.Initialize(config);\n    if (!ampve_wifi_initialized) { ESP_LOGE(TAG, "Wi-Fi driver initialization failed; startup remains unconfirmed"); return; }')
    if '"ampve/improv_service.cc"' not in component_cmake.read_text():
        replace(component_cmake,'set(SOURCES ', 'set(SOURCES "ampve/improv_service.cc" "ampve/improv_platform.cc" ')
        replace(component_cmake,'PRIV_REQUIRES\n','PRIV_REQUIRES\n                        ampve_improv_sdk esp_driver_uart\n')
    prepare_wifi(work)
    prepare_credentials(work)
    prepare_improv(work)
    if 'SsidManager::GetInstance().IsStorageReady()' not in wifi_board.read_text():
        replace(wifi_board,'    // Set unified event callback',
            '    if (!SsidManager::GetInstance().IsStorageReady()) { ampve_wifi_initialized = false; ESP_LOGE(TAG, "Wi-Fi credentials unavailable; data preserved"); return; }\n\n    // Set unified event callback')
    prepare_board(work, PIN)
    prepare_audio(work, PIN)
    stage_overlay(overlay,work)
    (work/'main/ampve/profile.h').write_text(native_header())
    trust_header,trust_metadata=generate_native_trust(os.environ.get('AMPVE_NATIVE_TRUST'))
    (work/'main/ampve/publisher_trust.h').write_text(trust_header)
    (work/'native-public-trust.json').write_bytes(trust_metadata)
    shutil.copyfile(ROOT/'firmware/xiaozhi/sdkconfig.ampve',work/'sdkconfig.ampve')
    if mode == 'ota':
        replace(work/'sdkconfig.ampve', 'CONFIG_AMPVE_USB_COMMISSIONING=y',
                '# CONFIG_AMPVE_USB_COMMISSIONING is not set')
    shutil.copytree(ROOT/'firmware/xiaozhi/partitions',work/'partitions/ampve',dirs_exist_ok=True)
    lock=ROOT/'firmware/xiaozhi/dependencies.lock'
    if lock.exists() and not (work/'dependencies.lock').exists():shutil.copyfile(lock,work/'dependencies.lock')
    print('Prepared AMPVE sources. No device access or flash commands.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--mode', choices=['usb-assisted', 'ota'], default='usb-assisted')
    args=parser.parse_args();prepare(args.work.resolve(),args.mode)
