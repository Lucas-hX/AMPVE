"""Convert original AMPVE artwork into small LVGL 9 RGB565 assets."""
import argparse
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def generate(destination):
    lines = ['/* Generated from original AMPVE brand assets. */', '#include "lvgl.h"']
    for name, relative, size in [('ampve_symbol', 'brand/ampve-symbol-avatar-v1.png', 32),
                                 ('ampve_companion', 'apps/companion-icon-v1.png', 80)]:
        with Image.open(ROOT/'images/ampve-brand-kit-v1'/relative) as original:
            rgba = original.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
            background = Image.new('RGBA', rgba.size, '#F7F5EE')
            background.alpha_composite(rgba)
            pixels = []
            for r, g, b in background.convert('RGB').getdata():
                value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                pixels.extend([value & 255, value >> 8])
        lines.append(f'static const uint8_t {name}_data[] = {{')
        lines.extend(','.join(str(v) for v in pixels[i:i+32])+',' for i in range(0, len(pixels), 32))
        lines.append('};')
        lines.append(f'const lv_image_dsc_t {name} = {{.header = {{.magic = LV_IMAGE_HEADER_MAGIC, '
                     f'.cf = LV_COLOR_FORMAT_RGB565, .w = {size}, .h = {size}, .stride = {size * 2}}}, '
                     f'.data_size = {len(pixels)}, .data = {name}_data}};')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    generate(parser.parse_args().output)
