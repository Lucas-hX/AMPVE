"""Stage and package the exact 7B RAM diagnostic; never flash a device."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'firmware/diagnostics/c6'
IDF_PIN='fff9895c82d744c7237be8847347bdd1b07c6643'


def stage(work):
    if work.is_relative_to(ROOT):raise ValueError('Use an external build directory')
    work.mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE,work,dirs_exist_ok=True,copy_function=shutil.copyfile)


def package(work,idf,output):
    from esptool.bin_image import ESP32P4FirmwareImage
    if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--',str(SOURCE),__file__]).strip():
        raise ValueError('Commit the diagnostic source and packaging checks before packaging')
    if subprocess.check_output(['git','-C',str(idf),'rev-parse','HEAD']).decode().strip()!=IDF_PIN:
        raise ValueError('Unreviewed IDF')
    for source in SOURCE.rglob('*'):
        if source.is_file() and source.read_bytes()!=(work/source.relative_to(SOURCE)).read_bytes():
            raise ValueError('Diagnostic build source differs from checkout')
    config=dict(line.split('=',1) for line in (work/'sdkconfig').read_text().splitlines() if line.startswith('CONFIG_') and '=' in line)
    required={'CONFIG_APP_BUILD_TYPE_RAM':'y','CONFIG_APP_BUILD_TYPE_PURE_RAM_APP':'y','CONFIG_IDF_TARGET':'"esp32p4"',
        'CONFIG_ESP32P4_REV_MIN_FULL':'100','CONFIG_ESP32P4_REV_MAX_FULL':'199','CONFIG_ESP_HOSTED_SDIO_SLOT':'1',
        'CONFIG_CACHE_L2_CACHE_SIZE':'0x20000','CONFIG_COMPILER_OPTIMIZATION_SIZE':'y',
        'CONFIG_ESP_HOSTED_SDIO_PIN_CMD':'19','CONFIG_ESP_HOSTED_SDIO_PIN_CLK':'18','CONFIG_ESP_HOSTED_SDIO_PIN_D0':'14',
        'CONFIG_ESP_HOSTED_SDIO_PIN_D1':'15','CONFIG_ESP_HOSTED_SDIO_PIN_D2':'16','CONFIG_ESP_HOSTED_SDIO_PIN_D3':'17',
        'CONFIG_ESP_HOSTED_SDIO_GPIO_RESET_SLAVE':'54'}
    if any(config.get(k)!=v for k,v in required.items()):raise ValueError('Wrong RAM/profile configuration')
    if any(config.get(k)=='y' for k in ['CONFIG_APP_BUILD_USE_FLASH_SECTIONS','CONFIG_APP_BUILD_BOOTLOADER','CONFIG_SECURE_BOOT','CONFIG_SECURE_FLASH_ENC_ENABLED']):
        raise ValueError('Unexpected flash/security build option')
    build=work/'build';artifact=build/'ampve_c6_probe.bin';elf=build/'ampve_c6_probe.elf'
    if any(p.stat().st_mtime>artifact.stat().st_mtime for p in (work/'main').glob('*') if p.is_file()):raise ValueError('Recompile changed source')
    description=json.loads((build/'project_description.json').read_text())
    nm=description['c_compiler'].replace('gcc','nm')
    symbols=subprocess.check_output([nm,'--defined-only',str(elf)]).decode()
    forbidden=('esp_flash_write','esp_flash_erase','esp_partition_write','esp_partition_erase','nvs_set_','nvs_flash_init','esp_hosted_slave_ota','rpc_ota_','esp_efuse_write')
    for line in symbols.splitlines():
        fields=line.split()
        if len(fields)==3 and fields[1] in ('t','T') and fields[2].startswith(forbidden):raise ValueError('Write-capable entrypoint linked: '+fields[2])
    with artifact.open('rb') as stream:image=ESP32P4FirmwareImage(stream)
    if (image.chip_id!=18 or image.min_rev_full!=100 or image.max_rev_full!=199 or
            not image.append_digest or image.stored_digest!=image.calc_digest or
            image.checksum!=image.calculate_checksum()):raise ValueError('Wrong or corrupt built image')
    ranges=[(0x30100000,0x30102000),(0x4ff00000,0x4ff2bbd0),(0x4ff40000,0x4ffa0000)]
    for segment in image.segments:
        if not any(segment.addr>=a and segment.addr+len(segment.data)<=b for a,b in ranges):raise ValueError('Image has a non-RAM segment')
    if not (0x4ff00000<=image.entrypoint<0x4ff2bbd0 and any(s.addr<=image.entrypoint<s.addr+len(s.data) for s in image.segments)):raise ValueError('Invalid RAM entry')
    data=artifact.read_bytes()
    if len(data)>768*1024:raise ValueError('RAM image too large')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    manifest={'schema':1,'kind':'ampve-c6-ram-probe','chip_revision':103,'flash_writes':False,
        'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'physical_validation':False,
        'idf_commit':IDF_PIN,'source_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()}
    (output/'probe.bin').write_bytes(data)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name in ['sdkconfig','dependencies.lock']:shutil.copyfile(work/name,output/name)
    shutil.copyfile(elf,output/'probe.elf')
    (output/'defined-symbols.txt').write_text(symbols)
    print(json.dumps(manifest))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','package']);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--idf',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    if a.action=='stage':stage(a.work.resolve())
    else:
        if a.idf is None or a.output is None:p.error('package requires --idf and --output')
        package(a.work.resolve(),a.idf.resolve(),a.output.resolve())
