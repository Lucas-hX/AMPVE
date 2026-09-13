"""Verify a downloaded public vendor artifact against curated source fingerprints.

This offline check neither consumes private backups nor approves hardware writes.
"""
import argparse
import hashlib
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / 'profiles/stock-baselines.json'


def verify(path, baseline_id):
    catalog = json.loads(CATALOG.read_text())
    entry = next(item for item in catalog['baselines'] if item['id'] == baseline_id)
    if path.stat().st_size != entry['source_bytes']:
        raise ValueError('Vendor artifact size differs from the recorded source')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry['source_sha256']:
        raise ValueError('Vendor artifact hash differs from the recorded source')
    for region in entry['regions']:
        content = data[region['offset']:region['offset'] + region['size']]
        if len(content) != region['size'] or hashlib.sha256(content).hexdigest() != region['sha256']:
            raise ValueError('Vendor artifact region differs from the catalog')
    return {'baseline': entry['id'], 'source_and_regions_verified': True,
            'installable': False, 'c6_identity_verified': False,
            'bootloader_behavior_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--baseline', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.artifact, args.baseline), indent=2))
