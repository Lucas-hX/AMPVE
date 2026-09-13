"""Publisher administration after documented compatibility review; no hardware access.

Use the platform Python environment (cryptography). Never use this to bypass a
missing bootloader/C6/recovery review. Publishing is not owner hardware-write consent.
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from profile_contract import CONTRACT, PROFILE, matches_contract


def publish(candidate,review_file,key_file,output):
    manifest=json.loads((candidate/'review-manifest.json').read_text())
    review=json.loads(review_file.read_text())
    if manifest.get('installation_profile')!=PROFILE['installation_id'] or not matches_contract(manifest.get('compatibility')):
        raise ValueError('Wrong or missing versioned candidate profile')
    fields={'bootloader_sha256','table_sha256','bootloader_review','c6_review','recovery_review','expires_at','app_sha256'}
    if set(review)!=fields or any(not isinstance(v,str) or not v.strip() or 'REPLACE' in v for v in review.values()):
        raise ValueError('Supply the complete documented review; placeholders are not approval')
    import re
    for name in ['bootloader_sha256','table_sha256','app_sha256']:
        if not re.fullmatch('[a-f0-9]{64}',review[name]):raise ValueError('Invalid reviewed digest')
    expiry=datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    remaining=(expiry-datetime.now(timezone.utc)).total_seconds()
    if not 0<remaining<=31*86400:raise ValueError('Approval must expire within 31 days')
    app=(candidate/'xiaozhi.bin').read_bytes();digest=hashlib.sha256(app).hexdigest()
    recorded=manifest['proposed_regions_not_approved_writes']
    if len(recorded)!=1 or recorded[0]['sha256']!=digest or digest!=review['app_sha256'] or recorded[0]['offset']!=0xe00000 or not 24<=len(app)<=0x3f0000:
        raise ValueError('Review does not match the actual candidate app')
    if output.exists():raise ValueError('Publish to a new immutable directory, then select it in private platform configuration')
    key=Ed25519PrivateKey.from_private_bytes(key_file.read_bytes())
    policy={'schema':1,'installable':True,'profile':PROFILE['installation_id'],'compatibility':CONTRACT,'chip_revision':103,'flash_bytes':32*1024*1024,
        **{k:v for k,v in review.items() if k!='app_sha256'},'repository_commit':manifest['repository_commit'],
        'firmware_version':manifest['firmware_version'],
        'app':{'sha256':digest,'size':len(app),'offset':0xe00000},
        'physical_validation':'Development first-install approval; peripheral operation and automatic rollback are not certified'}
    payload=json.dumps(policy,sort_keys=True,separators=(',',':')).encode()
    output.mkdir(mode=0o700,parents=True)
    shutil.copyfile(candidate/'xiaozhi.bin',output/'xiaozhi.bin')
    envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(key.sign(payload)).decode()}
    (output/'approved-release.json').write_text(json.dumps(envelope,indent=2)+'\n')
    # Standard ESP Web Tools representation for tooling/interoperability. Never expose
    # the generic install button: AMPVE's wrapper must perform the exact preflight and
    # local dynamic otadata plan, which cannot be encoded by this manifest alone.
    (output/'esp-web-tools-reference.json').write_text(json.dumps({'name':'AMPVE','version':manifest['firmware_version'],'new_install_prompt_erase':False,
        'builds':[{'chipFamily':'ESP32-P4','parts':[{'path':'xiaozhi.bin','offset':0xe00000}]}],
        'ampve_requires_guarded_installer':True},indent=2)+'\n')
    print('Signed development release prepared. Configure the separately trusted public key and review before activation. Nothing flashed.')


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);commands=p.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init-key');init.add_argument('--directory',type=Path,required=True)
    pub=commands.add_parser('publish')
    pub.add_argument('--approve-reviewed-development-release',action='store_true',required=True,
        help='Explicit publisher approval after completing the documented engineering review')
    for name in ['candidate','review','key','output']:pub.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.command=='init-key':
        directory=args.directory.resolve()
        if any((parent/'.git').exists() for parent in [directory,*directory.parents]):raise ValueError('Keep publisher keys outside Git')
        directory.mkdir(mode=0o700,parents=True,exist_ok=False)
        key=Ed25519PrivateKey.generate()
        (directory/'publisher-private.key').write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        (directory/'publisher-public.key').write_text(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()+'\n')
        print('Publisher key files created privately. No values printed; no release activated.')
    else:
        if any((parent/'.git').exists() for parent in [args.output.resolve(),*args.output.resolve().parents]):raise ValueError('Keep release output outside Git')
        publish(args.candidate,args.review,args.key,args.output)

if __name__=='__main__':main()
