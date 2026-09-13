"""Compare a private local audit with a candidate. Never approve or perform writes."""
import argparse
import json
from pathlib import Path
from audit import analyze, digest, security_is_unprotected, partition_table
from profile_contract import PROFILE, matches_contract, matches_layout


def compare(audit_directory, candidate_directory):
    audit = json.loads((audit_directory/'audit-private.json').read_text())
    first = (audit_directory/'backup-a.bin').read_bytes()
    second = (audit_directory/'backup-b.bin').read_bytes()
    actual = analyze(first)
    if digest(first) != digest(second) or actual['sha256'] != audit['sha256']:
        raise ValueError('Private backups no longer match the completed audit')
    hardware = audit['hardware']
    if (hardware['chip'] != PROFILE['chip']['name'] or
            not PROFILE['chip']['revision_min'] <= hardware['revision'] <= PROFILE['chip']['revision_max'] or
            hardware['flash_bytes'] != len(first) or len(first) != PROFILE['resources']['flash_bytes'] or
            not security_is_unprotected(hardware['security'])):
        raise ValueError('Hardware/security audit does not match the candidate profile')
    candidate = json.loads((candidate_directory/'review-manifest.json').read_text())
    if not matches_contract(candidate.get('compatibility')):
        raise ValueError('profile_contract_mismatch: candidate lacks the reviewed versioned contract')
    if not matches_layout(actual['partitions'], actual['partition_table_offset']):
        raise ValueError('layout_mismatch: local stock table differs from the canonical profile')
    for item in candidate.get('build_artifacts_not_installation_plan', [])+candidate['proposed_regions_not_approved_writes']:
        path = (candidate_directory/item['file']).resolve()
        if not path.is_relative_to(candidate_directory.resolve()) or path.stat().st_size != item['size'] or digest(path.read_bytes()) != item['sha256']:
            raise ValueError('Candidate file missing, outside bundle, or hash mismatch')
    def layout(partitions):
        return [(p['name'], p['type'], p['subtype'], p['offset'], p['size'], p['flags']) for p in partitions]
    if candidate.get('installation_profile') == 'waveshare-7b-stock-v1':
        from release import config_values, validate_config
        config=candidate_directory/'sdkconfig'
        if digest(config.read_bytes())!=candidate['sdkconfig_sha256']:
            raise ValueError('SDK configuration hash mismatch')
        validate_config(config_values(config))
        table=(candidate_directory/'partition_table/partition-table.bin').read_bytes()
        generated=partition_table(b'\xff'*0x8000+table,0x8000,len(first))
        if layout(generated)!=layout(candidate['partitions']):
            raise ValueError('Manifest does not describe the generated partition binary')
    return {'installable': False, 'backup_hashes_verified': True,
            'partition_layout_identical': layout(actual['partitions']) == layout(candidate['partitions']),
            'stock_partition_table_offset': actual['partition_table_offset'],
            'stock_partitions': actual['partitions'], 'candidate_partitions': candidate['partitions'],
            'remaining': ['Review stock bootloader location/version, C6 firmware and board label',
                          'Review preservation of original data and exact files/regions for USB restoration',
                          'Explicit hardware-write approval; physical recovery test is still pending']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.audit, args.candidate), indent=2))
