"""Prepare a private, stock-preserving installation/recovery proposal. Never write hardware."""
import argparse
import binascii
import json
import struct
from pathlib import Path
from audit import analyze, digest, private_directory, image_metadata
from compare import compare
from profile_contract import CONTRACT, PROFILE, PARTITIONS, matches_contract

SECTOR = 4096
OTA = PARTITIONS['otadata']['offset']


def select_record(data):
    """Use ESP-IDF's otadata sequence/CRC rules; refuse ambiguous states."""
    valid = []
    for i in range(2):
        record = data[i*SECTOR:i*SECTOR+32]
        if len(record) != 32:
            raise ValueError('Incomplete otadata')
        seq, = struct.unpack_from('<I', record)
        state, crc = struct.unpack_from('<II', record, 24)
        if seq != 0xFFFFFFFF and state not in (3,4) and binascii.crc32(record[:4],0xFFFFFFFF) & 0xFFFFFFFF == crc:
            if not seq or state not in (0,1,2,0xFFFFFFFF):
                raise ValueError('Unknown stock OTA selection state')
            valid.append((seq,i,state))
    if not valid:
        # Only an entirely erased selection permits an unambiguous factory fallback.
        if data != b'\xff'*(2*SECTOR):
            raise ValueError('No valid OTA selection; manual bootloader review required')
        return None
    if len(valid)==2 and valid[0][0]==valid[1][0] and valid[0][2]!=valid[1][2]:
        raise ValueError('Ambiguous OTA states')
    current=max(valid)
    if current[2] not in (2,0xFFFFFFFF):
        raise ValueError('Expected a confirmed OTA slot or factory; do not replace an active/pending slot')
    return current


def next_selection(data):
    current=select_record(data)
    sequence=2 if current is None else current[0]+1
    if sequence>=0xFFFFFFFE:
        raise ValueError('OTA sequence exhaustion requires manual review')
    target=0 if current is None else 1-current[1]
    sector=bytearray(data[target*SECTOR:(target+1)*SECTOR])
    record=bytearray(b'\xff'*32)
    struct.pack_into('<I',record,0,sequence)
    struct.pack_into('<I',record,24,0)  # ESP_OTA_IMG_NEW; requires reviewed bootloader behavior.
    struct.pack_into('<I',record,28,binascii.crc32(record[:4],0xFFFFFFFF)&0xFFFFFFFF)
    sector[:32]=record
    return target,bytes(sector),current


def partition_for_sequence(sequence):
    """Return the OTA partition selected by ESP-IDF's sequence mapping."""
    if not sequence or sequence >= 0xFFFFFFFE:
        raise ValueError('Invalid OTA sequence')
    return 'ota_0' if (sequence - 1) % 2 == 0 else 'ota_1'


def inactive_slot_mode(slot, current, target_name):
    """Classify a target slot without ever inferring that an active slot is safe."""
    if slot == b'\xff' * len(slot):
        return 'blank'
    # An erased otadata region means factory fallback and is not enough
    # evidence to replace an occupied application. A pending/unknown record
    # likewise cannot prove which slot is safe to replace.
    if current is None or current[2] not in (2, 0xFFFFFFFF):
        raise ValueError(f'Occupied {target_name} is not proven inactive and confirmed')
    if partition_for_sequence(current[0]) == target_name:
        raise ValueError(f'Refusing to replace active {target_name}')
    return f'replace-confirmed-inactive-{target_name.replace("_", "")}'


def prepare_plan(audit_dir, candidate_dir, output):
    result=compare(audit_dir,candidate_dir)
    if not result['partition_layout_identical']:
        raise ValueError('Stock and generated partition entries differ; no table migration is permitted')
    manifest=json.loads((candidate_dir/'review-manifest.json').read_text())
    if manifest.get('installation_profile')!=PROFILE['installation_id'] or not matches_contract(manifest.get('compatibility')):
        raise ValueError('Wrong installation profile')
    original=(audit_dir/'backup-a.bin').read_bytes()
    report=analyze(original)
    sector,new_selection,current=next_selection(original[OTA:OTA+2*SECTOR])
    sequence,=struct.unpack_from('<I',new_selection)
    target_name=partition_for_sequence(sequence)
    target=PARTITIONS[target_name]
    slot_offset,slot_size=target['offset'],target['size']
    slot_bytes=original[slot_offset:slot_offset+slot_size]
    slot_mode=inactive_slot_mode(slot_bytes,current,target_name)
    inactive_partition=next((p for p in report['partitions'] if p['name']==target_name and
        p['offset']==slot_offset and p['size']==slot_size),None)
    if not inactive_partition:
        raise ValueError(f'Audited {target_name} partition does not match the installation profile')
    inactive_slot={'name':target_name,'mode':slot_mode,'partition_sha256':digest(slot_bytes),
        'application':inactive_partition.get('app_metadata')}
    if slot_mode!='blank':
        inactive_slot['image']=image_metadata(slot_bytes)
    app=(candidate_dir/'xiaozhi.bin').read_bytes()
    candidate_image=image_metadata(app)
    stock_images=[{'name':'bootloader','offset':0x2000,**image_metadata(original[0x2000:0x8000])}]
    for p in report['partitions']:
        if p['type']==0 and original[p['offset']:p['offset']+p['size']]!=b'\xff'*p['size']:
            stock_images.append({'name':p['name'],'offset':p['offset'],**image_metadata(original[p['offset']:p['offset']+p['size']]),
                'application':p.get('app_metadata',{})})
    proposal=manifest['proposed_regions_not_approved_writes']
    proposed_offsets={PARTITIONS[name]['offset'] for name in ('ota_0','ota_1')}
    if (len(proposal)!=1 or proposal[0]['offset'] not in proposed_offsets or
            proposal[0]['sha256']!=digest(app) or len(app)>slot_size):
        raise ValueError('Unexpected app proposal')
    output=private_directory(output)
    regions=[]
    for name,offset,data in [('ampve-app.bin',slot_offset,app),('select-ampve.bin',OTA+sector*SECTOR,new_selection)]:
        (output/name).write_bytes(data)
        size=((len(data)+SECTOR-1)//SECTOR)*SECTOR
        restore='restore-'+name
        (output/restore).write_bytes(original[offset:offset+size])
        regions.append({'file':name,'offset':offset,'size':len(data),'sha256':digest(data),
            'erase_offset':offset,'erase_size':size,'restore_file':restore,'restore_sha256':digest(original[offset:offset+size])})
    # NVS and both metadata sectors can change after first boot, independently of the installer.
    recovery=[]
    for name,offset,size in [('nvs',0x3B000,0xD2000),('otadata',OTA,2*SECTOR)]:
        content=original[offset:offset+size];filename='restore-after-boot-'+name+'.bin'
        (output/filename).write_bytes(content)
        recovery.append({'file':filename,'offset':offset,'size':size,'sha256':digest(content)})
    plan={'schema':1,'profile':PROFILE['installation_id'],'compatibility':CONTRACT,'installable':False,
        'backup_sha256':report['sha256'],'stock_bootloader_region_sha256':digest(original[0x2000:0x8000]),
        'stock_table_sector_sha256':digest(original[0x8000:0x9000]),
        'current_selection':current,'inactive_slot_before_install':inactive_slot,
        'write_order':regions,'post_boot_recovery_regions':recovery,
        'preserved_at_install':manifest['preserve_at_install'],
        'runtime_data_changes':manifest['runtime_data_changes'],
        'remaining':['Review the exact stock bootloader and C6 compatibility',
            'Verify a separate private storage copy and physical ROM access',
            'Review this exact plan and obtain hardware-write approval',
            'Validate first boot and recovery physically; automatic rollback is unverified'],
        'recovery_notes':['No full-chip erase. Restore boot-selection data to return to the retained stock app.',
            'If shared NVS changed after boot, restoring its private original bytes discards new Wi-Fi/AMPVE identity.',
            'Restore touched ota_1 sectors only if exact original bytes are required. Never overwrite the retained bootloader/table.',
            'Every restore is a separate reviewed hardware-write operation.']}
    (output/'installation-plan-private.json').write_text(json.dumps(plan,indent=2)+'\n')
    summary={'source':'Owner-local offline comparison of two matching backups and actual candidate binaries',
        'installable':False,'partition_layout_identical':True,'backup_sha256':report['sha256'],
        'bootloader_sha256':plan['stock_bootloader_region_sha256'],'table_sha256':plan['stock_table_sector_sha256'],
        'candidate_sha256':digest(app),'candidate_image':candidate_image,'stock_images':stock_images,
        'current_selection':current,'inactive_slot_before_install':inactive_slot,
        'proposed_regions':[{k:v for k,v in r.items() if not k.startswith('restore')} for r in regions],
        'remaining':plan['remaining']}
    (output/'review-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for file in output.iterdir():file.chmod(0o600)
    print('Private proposal and matching recovery regions prepared. installable=false; nothing flashed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['audit','candidate','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    prepare_plan(args.audit.resolve(),args.candidate.resolve(),args.output)
