"""Use the platform's pure contract reader from standalone offline tools."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/platform'))
from workspace.hardware_profiles import CONTRACT, PARTITIONS, PROFILE, matches_contract, matches_layout


def native_header():
    """Generate constants and compile-time checks against the pinned board adapter."""
    lines = ['// Generated from firmware/profiles/waveshare-7b-stock-v1.json. Do not edit.', '#pragma once']
    lines.append('#define AMPVE_INSTALLATION_PROFILE '+__import__('json').dumps(PROFILE['installation_id']))
    for key, value in CONTRACT.items():
        import json
        lines.append(f'#define AMPVE_{key.upper()} {json.dumps(value)}')
    for key, value in {
        'FLASH_BYTES': PROFILE['resources']['flash_bytes'],
        'MIN_PSRAM_BYTES': PROFILE['resources']['minimum_psram_bytes'],
        'REVISION_MIN': PROFILE['chip']['revision_min'],
        'REVISION_MAX': PROFILE['chip']['revision_max'],
    }.items():
        lines.append(f'#define AMPVE_{key} {value}')
    for name in ('factory', 'ota_0', 'ota_1'):
        for field in ('offset', 'size'):
            lines.append(f'#define AMPVE_{name.upper()}_{field.upper()} {PARTITIONS[name][field]}')
    lines.append('static constexpr struct { const char* name; unsigned type, subtype, offset, size; } AMPVE_PARTITIONS[] = {')
    for item in PARTITIONS.values():
        lines.append('    {"%s", %d, %d, %d, %d},' % tuple(item[key] for key in ('name','type','subtype','offset','size')))
    lines.append('};')
    display = PROFILE['peripherals']['display']
    expected = {'DISPLAY_WIDTH': display['width'], 'DISPLAY_HEIGHT': display['height'],
                'PIN_NUM_LCD_RST': display['reset_gpio'], 'DISPLAY_BACKLIGHT_PIN': display['backlight_gpio'],
                'BOOT_BUTTON_GPIO': PROFILE['peripherals']['boot_button_gpio']}
    audio = PROFILE['peripherals']['audio']
    for pin in ('MCLK', 'WS', 'BCLK', 'DIN', 'DOUT'):
        expected['AUDIO_I2S_GPIO_' + pin] = audio[pin.lower() + '_gpio']
    expected.update({'AUDIO_CODEC_PA_PIN': audio['pa_gpio'],
                     'AUDIO_CODEC_I2C_SDA_PIN': audio['sda_gpio'], 'AUDIO_CODEC_I2C_SCL_PIN': audio['scl_gpio']})
    for name, value in expected.items():
        lines.append(f'static_assert({name} == {value}, "Board adapter differs from the AMPVE profile: {name}");')
    for pin, value in PROFILE['connectivity']['sdio_pins'].items():
        name = 'CONFIG_ESP_HOSTED_SDIO_' + ('GPIO_RESET_SLAVE' if pin == 'reset' else 'PIN_' + pin.upper())
        lines.append(f'static_assert({name} == {value}, "ESP-Hosted pins differ from the AMPVE profile: {name}");')
    return '\n'.join(lines) + '\n'
