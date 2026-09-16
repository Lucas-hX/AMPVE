"""Sign a curated capability API v1 declaration outside Git; never embeds a key."""
import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'apps/platform'))
from workspace.app_package_contract import validate  # noqa: E402
from workspace.hardware_profiles import CONTRACT, PROFILE  # noqa: E402
from workspace.release_contract import canonical, sha256  # noqa: E402


def create(args):
    destination = args.output.resolve()
    if destination.is_relative_to(ROOT) or not destination.parent.is_dir():
        raise ValueError('Signed packages must be written to an existing private directory outside Git.')
    now = datetime.now(timezone.utc)
    policy = {'schema':1,'api_version':1,'key_id':args.key_id,'name':args.name,
        'version':args.version,'kind':args.kind,'profile_id':CONTRACT['profile_id'],
        'profile_version':CONTRACT['profile_version'],'layout_id':CONTRACT['layout_id'],
        'chip_revision':103,'flash_bytes':PROFILE['resources']['flash_bytes'],
        'minimum_psram_bytes':PROFILE['resources']['minimum_psram_bytes'],
        'expires_at':args.expires_at,'ui':{'title':args.title,'body':args.body},
        'workflow':{'action':{'status':'show_status','timer':'local_timer',
                              'companion':'native_companion'}[args.kind],
                    'duration_s':args.duration_s,
                    'start_muted':args.start_muted or args.kind!='companion'}}
    validate(policy, now)
    payload = canonical(policy)
    key = Ed25519PrivateKey.from_private_bytes(args.private_key.read_bytes())
    envelope = {'payload':base64.b64encode(payload).decode(),
                'signature':base64.b64encode(key.sign(payload)).decode()}
    if destination.exists():
        raise ValueError('Do not replace an already published package identity.')
    destination.write_bytes(canonical(envelope))
    destination.chmod(0o600)
    print(json.dumps({'package_id':sha256(payload),'size':destination.stat().st_size,
                      'name':policy['name'],'version':policy['version']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('key-id','name','version','kind','title','body','expires-at'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--duration-s', type=int, default=0)
    parser.add_argument('--start-muted', action='store_true')
    parser.add_argument('--private-key', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    create(parser.parse_args())
