"""Package a build for review. This deliberately never produces an installable release."""
import argparse
import hashlib
import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from audit import partition_table, private_directory, image_metadata

ROOT = Path(__file__).resolve().parents[2]
IDF_PIN = 'fff9895c82d744c7237be8847347bdd1b07c6643'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_values(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if line.startswith('CONFIG_') and '=' in line)


def validate_config(values):
    required = {'CONFIG_IDF_TARGET': '"esp32p4"', 'CONFIG_ESP32P4_REV_MIN_FULL': '100',
                'CONFIG_ESP32P4_REV_MAX_FULL': '199', 'CONFIG_ESPTOOLPY_FLASHSIZE': '"32MB"',
                'CONFIG_BOARD_TYPE_WAVESHARE_ESP32_P4_WIFI6_TOUCH_LCD_7B': 'y',
                'CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE': 'y', 'CONFIG_FLASH_NONE_ASSETS': 'y',
                'CONFIG_LANGUAGE_EN_US': 'y', 'CONFIG_APP_REPRODUCIBLE_BUILD': 'y'}
    if any(values.get(key) != value for key, value in required.items()):
        raise ValueError('Build configuration does not match the reviewed profile')
    for forbidden in ['CONFIG_SECURE_BOOT', 'CONFIG_SECURE_FLASH_ENC_ENABLED',
                      'CONFIG_BOOTLOADER_APP_ANTI_ROLLBACK', 'CONFIG_APP_COMPILE_TIME_DATE']:
        if values.get(forbidden) == 'y':
            raise ValueError('Unexpected irreversible/security/time-dependent build option: '+forbidden)


def package(work, idf, destination, comparison=None):
    upstream = json.loads((ROOT/'firmware/xiaozhi/upstream.json').read_text())
    for checkout, pin in [(work, upstream['commit']), (idf, IDF_PIN)]:
        if subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD']).decode().strip() != pin:
            raise ValueError('Unreviewed source revision')
    build = work/'build'
    image=image_metadata((build/'xiaozhi.bin').read_bytes())
    if image['min_revision']>103 or image['max_revision'] not in (0,65535) and image['max_revision']<103:
        raise ValueError('App image does not support P4 revision 1.3')
    validate_config(config_values(work/'sdkconfig'))
    for source in (ROOT/'firmware/xiaozhi/overlay').rglob('*'):
        if source.is_file():
            prepared=work/source.relative_to(ROOT/'firmware/xiaozhi/overlay')
            if not prepared.is_file() or source.read_bytes()!=prepared.read_bytes():
                raise ValueError('Prepared overlay differs from repository source')
            if prepared.stat().st_mtime > (build/'xiaozhi.bin').stat().st_mtime:
                raise ValueError('Overlay changed after the app build; rebuild before packaging')
    args = json.loads((build/'flasher_args.json').read_text())
    planned = []
    for offset, relative in args['flash_files'].items():
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Artifact filenames must be safe relative paths')
        path = (build/relative).resolve()
        if not path.is_relative_to(build.resolve()) or not path.is_file():
            raise ValueError('Artifact outside the build directory or missing')
        planned.append({'offset': int(offset, 0), 'size': path.stat().st_size,
                        'file': relative, 'sha256': sha(path)})
    planned.sort(key=lambda item: item['offset'])
    for index, item in enumerate(planned):
        if item['offset']+item['size'] > 32*1024*1024:
            raise ValueError('Artifact exceeds target flash')
        if index and planned[index-1]['offset']+planned[index-1]['size'] > item['offset']:
            raise ValueError('Overlapping artifact writes')
    # Read the generated table independently; all offsets remain proposals.
    table_path = build/'partition_table/partition-table.bin'
    table_offset = int(config_values(work/'sdkconfig')['CONFIG_PARTITION_TABLE_OFFSET'], 0)
    partitions = partition_table(b'\xff'*table_offset+table_path.read_bytes(), table_offset, 32*1024*1024)
    app = next(item for item in planned if item['file'] == 'xiaozhi.bin')
    slots = [p for p in partitions if p['type'] == 0 and p['subtype'] in [16, 17]]
    if len(slots) != 2 or any(app['size'] > p['size'] for p in slots):
        raise ValueError('App does not fit both OTA slots')
    expected = [(0xA10000, 0x3F0000), (0xE00000, 0x3F0000)]
    if [(p['offset'],p['size']) for p in slots] != expected or table_offset != 0x8000:
        raise ValueError('Expected the stock-preserving 7B development layout')
    # IDF's general flash target may select factory. It is NEVER an AMPVE install plan.
    proposed = [{**app, 'offset': slots[1]['offset']}]
    reproducibility={'verified': False, 'scope': 'Not compared with a second build'}
    if comparison is not None:
        for item in planned:
            other=comparison/'build'/item['file']
            if not other.is_file() or sha(other)!=item['sha256']:
                raise ValueError('Independent build artifact mismatch: '+item['file'])
        reproducibility={'verified': True, 'scope': 'Two separately compiled project directories on this VPS; shared pinned IDF/toolchain and registry sources. Cross-machine reproduction not tested.'}
    destination = private_directory(destination)
    for item in planned:
        output = destination/item['file']; output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(build/item['file'], output)
    for source, name in [(work/'sdkconfig', 'sdkconfig'), (work/'dependencies.lock', 'dependencies.lock'),
                         (build/'project_description.json', 'project_description.json')]:
        shutil.copyfile(source, destination/name)
    for notice in work.glob('LICENSE*'):
        if notice.is_file():shutil.copyfile(notice,destination/(notice.name+'.xiaozhi'))
    patch = subprocess.check_output(['git', '-C', str(work), 'diff', '--no-ext-diff', '--binary'])
    (destination/'xiaozhi-integration.patch').write_bytes(patch)
    # Keep the modified third-party component and its original license reproducible outside Git.
    shutil.copytree(work/'components/78__esp-wifi-connect', destination/'provisioning-component')
    inputs = {}
    for base in [ROOT/'firmware', ROOT/'images/ampve-brand-kit-v1/brand', ROOT/'images/ampve-brand-kit-v1/apps']:
        for path in sorted(base.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                inputs[str(path.relative_to(ROOT))] = sha(path)
    overlay_inputs = {str(p.relative_to(work)): sha(p) for p in sorted((work/'main/ampve').glob('*')) if p.is_file()}
    description=json.loads((build/'project_description.json').read_text())
    compiler=subprocess.check_output([description['c_compiler'], '--version']).decode().splitlines()[0]
    tools_path=Path(os.environ.get('IDF_TOOLS_PATH', str(Path.home()/'.espressif')))
    idf_python=tools_path/'python_env/idf6.1_py3.13_env/bin/python'
    if not idf_python.is_file():
        raise ValueError('Expected recorded IDF 6.1 / Python 3.13 build environment')
    for executable, name in [(idf_python, 'idf-python-freeze.txt'), (Path(sys.executable), 'tooling-python-freeze.txt')]:
        (destination/name).write_bytes(subprocess.check_output([str(executable), '-m', 'pip', 'freeze']))
    manifest = {'schema': 1, 'installable': False, 'status': 'development-candidate-awaiting-local-audit',
                'hardware_profile': upstream['hardware_profile'], 'runtime_revision_guard': 103,
                'xiaozhi_commit': upstream['commit'], 'esp_idf_commit': IDF_PIN, 'compiler': compiler,
                'repository_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip(),
                'repository_inputs': inputs, 'generated_inputs': overlay_inputs,
                'sdkconfig_sha256': sha(work/'sdkconfig'), 'dependency_lock_sha256': sha(work/'dependencies.lock'),
                'installation_profile': 'waveshare-7b-stock-v1',
                'app_image': image,
                'build_artifacts_not_installation_plan': planned,
                'proposed_regions_not_approved_writes': proposed, 'partitions': partitions,
                'boot_selection': 'Generate locally from verified stock otadata; not the IDF initial otadata file',
                'preserve_at_install': ['bootloader', 'partition table', 'factory', 'ota_0', 'nvsfactory', 'nvs', 'phy_init', 'assets', 'storage'],
                'runtime_data_changes': ['AMPVE boot counters/identity/settings and Wi-Fi state change shared NVS after boot', 'Bootloader/app startup can change otadata'],
                'required_reviews': ['Exact local board/security audit and two matching private backup reads',
                    'Stock bootloader and C6 ESP-Hosted compatibility', 'Partition/data preservation and exact USB restore route',
                    'Explicit owner approval for the reviewed write plan', 'Physical startup/display/touch/Wi-Fi/audio/recovery tests'],
                'bit_reproducibility': reproducibility}
    (destination/'review-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    archive=shutil.make_archive(str(destination), 'zip', root_dir=destination)
    Path(archive).chmod(0o600)
    print('Review bundle created; installable=false. No ESP Web Tools manifest or hardware writes.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['work', 'idf', 'output']: parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--comparison-work', type=Path)
    args = parser.parse_args(); package(args.work.resolve(), args.idf.resolve(), args.output, args.comparison_work)
