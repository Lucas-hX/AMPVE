"""Apply the reviewed integration to an isolated pinned XiaoZhi checkout; never flash."""
import argparse
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


def prepare(work):
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
        board=work/'main/boards/waveshare/esp32-p4-wifi6-touch-lcd/esp32-p4-wifi6-touch-lcd.cc'
        replace(board,'#include "wifi_board.h"','#include "wifi_board.h"\n#include "ampve/runtime.h"')
        replace(board,'        InitializeCamera();','        // AMPVE: camera is deliberately not initialized.')
        start=board.read_text();a=start.index('        boot_button_.OnClick(');b=start.index('\n    }',a)
        start=start[:a]+'        boot_button_.OnClick([]() { ampve_request_wifi(); });'+start[b:]
        board.write_text(start)
        replace(board,'ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(i2c_bus_, &tp_io_config, &tp_io_handle));',
            'if (esp_lcd_new_panel_io_i2c(i2c_bus_, &tp_io_config, &tp_io_handle) != ESP_OK) return;')
        replace(board,'ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_gt911(tp_io_handle, &tp_cfg, &tp));',
            'if (esp_lcd_touch_new_i2c_gt911(tp_io_handle, &tp_cfg, &tp) != ESP_OK) return;')
        replace(board,'        lvgl_port_add_touch(&touch_cfg);','        ampve_touch_ready = lvgl_port_add_touch(&touch_cfg) != nullptr;')
        replace(board,'        InitializeTouch();','        InitializeTouch();\n        ampve_codec_present = i2c_device_probe(AUDIO_CODEC_ES8311_ADDR >> 1) == ESP_OK && i2c_device_probe(AUDIO_CODEC_ES7210_ADDR >> 1) == ESP_OK;')
        replace(board,'        static BoxAudioCodec audio_codec(','        if (!ampve_codec_present) return nullptr;\n        static BoxAudioCodec audio_codec(')
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
    if 'set(PROJECT_VER "0.1.0-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.0-dev")','set(PROJECT_VER "0.1.1-stock-dev")')
    if 'set(PROJECT_VER "0.1.1-stock-dev")' in cmake.read_text():
        replace(cmake,'set(PROJECT_VER "0.1.1-stock-dev")',f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")')
    if f'set(PROJECT_VER "{UPSTREAM["candidate_version"]}")' not in cmake.read_text():
        raise RuntimeError('Prepared project version differs from the candidate version')
    shutil.copytree(overlay,work,dirs_exist_ok=True)
    (work/'main/ampve/profile.h').write_text(native_header())
    shutil.copyfile(ROOT/'firmware/xiaozhi/sdkconfig.ampve',work/'sdkconfig.ampve')
    shutil.copytree(ROOT/'firmware/xiaozhi/partitions',work/'partitions/ampve',dirs_exist_ok=True)
    lock=ROOT/'firmware/xiaozhi/dependencies.lock'
    if lock.exists() and not (work/'dependencies.lock').exists():shutil.copyfile(lock,work/'dependencies.lock')
    print('Prepared AMPVE sources. No device access or flash commands.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--work',required=True,type=Path)
    prepare(parser.parse_args().work.resolve())
