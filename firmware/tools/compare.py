"""Compare a private local audit with a candidate. Never approve or perform writes."""
import argparse
import json
from pathlib import Path
from audit import analyze, digest, security_is_unprotected


def compare(audit_directory, candidate_directory):
    audit = json.loads((audit_directory/'audit-private.json').read_text())
    first = (audit_directory/'backup-a.bin').read_bytes()
    second = (audit_directory/'backup-b.bin').read_bytes()
    actual = analyze(first)
    if digest(first) != digest(second) or actual['sha256'] != audit['sha256']:
        raise ValueError('Private backups no longer match the completed audit')
    hardware = audit['hardware']
    if (hardware['chip'] != 'ESP32-P4' or hardware['revision'] != 103 or
            hardware['flash_bytes'] != len(first) or len(first) != 32*1024*1024 or
            not security_is_unprotected(hardware['security'])):
        raise ValueError('Hardware/security audit does not match the candidate profile')
    candidate = json.loads((candidate_directory/'review-manifest.json').read_text())
    for item in candidate['proposed_regions_not_approved_writes']:
        path = (candidate_directory/item['file']).resolve()
        if not path.is_relative_to(candidate_directory.resolve()) or digest(path.read_bytes()) != item['sha256']:
            raise ValueError('Candidate file missing, outside bundle, or hash mismatch')
    def layout(partitions):
        return [(p['name'], p['type'], p['subtype'], p['offset'], p['size'], p['flags']) for p in partitions]
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
