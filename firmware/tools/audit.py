"""Read-only ESP32-P4 audit and private backup inspection. No flash-write commands."""
import argparse
import contextlib
import hashlib
import json
import os
import struct
from pathlib import Path

MIB = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def image_metadata(data):
    """Bounded offline image verification using the pinned maintained esptool parser."""
    import io
    import esptool
    from esptool.bin_image import ESP32P4FirmwareImage
    if esptool.__version__ != '5.4.0':raise ValueError('Use pinned esptool 5.4.0')
    image=ESP32P4FirmwareImage(io.BytesIO(data))
    if image.chip_id!=18 or not image.append_digest or image.stored_digest!=image.calc_digest or image.checksum!=image.calculate_checksum():
        raise ValueError('Invalid P4 image checksum/digest/header')
    return {'image_bytes':image.data_length+32,'chip_id':image.chip_id,'min_revision':image.min_rev_full,
        'max_revision':image.max_rev_full,'flash_mode':image.flash_mode,'flash_size_frequency':image.flash_size_freq,
        'internal_checksum_verified':True,'appended_sha256_verified':True}


def private_directory(path):
    path = path.resolve()
    if any((parent/'.git').exists() for parent in [path, *path.parents]):
        raise ValueError('Keep private audits and backups outside every Git checkout')
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path


def partition_table(data, address, flash_size):
    sector = data[address:address+4096]
    partitions, entries = [], bytearray()
    for cursor in range(0, min(len(sector), 0xC00), 32):
        entry = sector[cursor:cursor+32]
        if len(entry) != 32:
            raise ValueError('Truncated partition table')
        if entry[:2] == b'\xeb\xeb':
            if entry[2:16] != b'\xff'*14 or hashlib.md5(entries).digest() != entry[16:]:
                raise ValueError('Partition MD5 mismatch')
            if not partitions:
                raise ValueError('Empty partition table')
            return partitions
        magic, kind, subtype, offset, size, label, flags = struct.unpack('<HBBII16sI', entry)
        if magic != 0x50AA:
            raise ValueError('Missing partition MD5 or invalid entry')
        name = label.split(b'\0', 1)[0].decode('ascii')
        if not name or any(ord(c) < 32 or ord(c) > 126 for c in name):
            raise ValueError('Invalid partition name')
        if not size or offset % 4096 or size % 4096 or offset < address+4096 or offset+size > flash_size:
            raise ValueError('Partition outside flash or unaligned')
        if kind == 0 and offset % 65536:
            raise ValueError('App partition is not 64 KiB aligned')
        if any(offset < p['offset']+p['size'] and p['offset'] < offset+size for p in partitions):
            raise ValueError('Overlapping partitions')
        if any(name == p['name'] for p in partitions):
            raise ValueError('Duplicate partition name')
        partitions.append(dict(name=name, type=kind, subtype=subtype, offset=offset, size=size, flags=flags))
        entries.extend(entry)
    raise ValueError('No partition MD5')


def analyze(data):
    size = len(data)
    if size < 2*MIB or size > 64*MIB or size & (size-1):
        raise ValueError('Expected a complete power-of-two flash dump (2–64 MiB)')
    candidates = []
    for address in range(0, size-4095, 4096):
        if data[address:address+2] != b'\xaa\x50':
            continue
        try:
            partitions = partition_table(data, address, size)
        except (ValueError, UnicodeDecodeError):
            continue
        candidates.append((address, partitions))
    if len(candidates) != 1:
        raise ValueError(f'Expected one unambiguous MD5-verified partition table; found {len(candidates)}')
    address, partitions = candidates[0]
    for partition in partitions:
        start, length = partition['offset'], partition['size']
        partition['sha256'] = digest(data[start:start+length])
        if partition['type'] == 0:
            # ESP image header (24), first segment header (8), then app descriptor.
            desc = data[start+32:start+288]
            if data[start] == 0xE9 and desc[:4] == b'\x32\x54\xcd\xab':
                def field(offset, count):
                    raw = desc[offset:offset+count].split(b'\0', 1)[0]
                    return ''.join(chr(c) if 32 <= c <= 126 else '?' for c in raw)
                partition['app_metadata'] = {'version': field(16, 32), 'project': field(48, 32), 'idf': field(112, 32)}
    return {'schema': 1, 'flash_bytes': size, 'sha256': digest(data),
            'partition_table_offset': address, 'partition_table_md5_verified': True,
            'partitions': partitions, 'installable': False,
            'limitations': ['Offline bytes do not prove board identity or security state.',
                           'Partition discovery does not verify the stock bootloader address or restore procedure.']}


def security_is_unprotected(info):
    flags = info.get('parsed_flags', {})
    return (type(info.get('flash_crypt_cnt')) is int and info['flash_crypt_cnt'] == 0
            and all(flags.get(key) is False for key in
                    ['SECURE_BOOT_EN', 'SECURE_DOWNLOAD_ENABLE', 'SECURE_BOOT_AGGRESSIVE_REVOKE']))


def capture(port, output, baud, use_ram_stub):
    import esptool
    from esptool import cmds
    if esptool.__version__ != '5.4.0':
        raise ValueError('Use the pinned esptool 5.4.0 environment')
    output = private_directory(output)
    esp = None
    # esptool may print identifiers; keep all diagnostics in the private directory.
    with (output/'serial-private.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            esp = cmds.detect_chip(port=port, baud=115200)
            if esp.CHIP_NAME != 'ESP32-P4' or esp.get_chip_revision() != 103:
                raise ValueError('Expected ESP32-P4 revision 1.3; stop and review this unit')
            info = esp.get_security_info()
            if not security_is_unprotected(info):
                raise ValueError('Security state enabled or unknown; stop for a separate recovery review')
            cmds.attach_flash(esp)
            flash_id = esp.flash_id()
            capacity = (flash_id >> 16) & 255
            if capacity != 25:
                raise ValueError('Expected 32 MiB JEDEC capacity; do not guess a flash size')
            metadata = {'schema': 1, 'chip': esp.CHIP_NAME, 'revision': 103,
                        'flash_bytes': 1 << capacity, 'jedec_id': flash_id, 'security': info,
                        'ram_stub': use_ram_stub, 'esptool': esptool.__version__}
            (output/'hardware-private.json').write_text(json.dumps(metadata, indent=2)+'\n')
            if use_ram_stub:
                esp = cmds.run_stub(esp)
                cmds.attach_flash(esp)
            if baud != 115200:
                esp.change_baud(baud)
            hashes = []
            for name in ['backup-a.bin', 'backup-b.bin']:
                cmds.read_flash(esp, 0, 1 << capacity, str(output/name), flash_size='32MB', no_progress=True)
                data = (output/name).read_bytes()
                if len(data) != 1 << capacity:
                    raise ValueError('Incomplete backup; never use it for restoration')
                hashes.append(digest(data))
            if hashes[0] != hashes[1]:
                raise ValueError('Independent flash reads differ; neither is approved for restoration')
            report = analyze(data)
            report['independent_reads_match'] = True
            report['hardware'] = metadata
            (output/'audit-private.json').write_text(json.dumps(report, indent=2)+'\n')
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        finally:
            if esp is not None:
                esp._port.close()
            for path in output.iterdir():
                path.chmod(0o600)
    print('Two matching reads and an offline audit saved privately. Nothing flashed. Reset the board manually.')
    print('Keep another copy on separate storage. This report does not authorize installation.')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('ports')
    inspect = commands.add_parser('inspect'); inspect.add_argument('backup', type=Path)
    grab = commands.add_parser('capture'); grab.add_argument('--port', required=True)
    grab.add_argument('--output', required=True, type=Path)
    grab.add_argument('--baud', choices=[115200, 460800], type=int, default=115200)
    grab.add_argument('--ram-stub', action='store_true', help='Opt in to a temporary RAM reader; no flash writes')
    args = parser.parse_args()
    if args.command == 'ports':
        from serial.tools.list_ports import comports
        for port in comports():
            print(json.dumps({'port': port.device, 'vid': port.vid, 'pid': port.pid}))
    elif args.command == 'inspect':
        # Contains partition names/app metadata; inspect locally, never upload a flash dump.
        print(json.dumps(analyze(args.backup.read_bytes()), indent=2))
    else:
        capture(args.port, args.output, args.baud, args.ram_stub)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Audit stopped ({type(error).__name__}). Review the private log locally; no installation approved.')
