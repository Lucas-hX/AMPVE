"""Publisher administration after documented compatibility review; no hardware access.

Use the pinned firmware-tools environment (esptool and cryptography). Never use this to bypass a
missing bootloader/C6/recovery review. Publishing is not owner hardware-write consent.
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from profile_contract import CONTRACT, PROFILE, matches_contract


def publish(candidate, review_file, key_file, output, ledger_file):
    """Sign a reviewed candidate; output is reserved exclusively and metadata written last."""
    import io
    import zipfile
    from audit import image_metadata
    from native_trust import generate as generate_native_trust
    from workspace.release_contract import canonical, sha256, strict_json, validate_policy

    manifest_bytes=(candidate/'review-manifest.json').read_bytes()
    manifest=strict_json(manifest_bytes,maximum=1024*1024)
    review=strict_json(review_file.read_bytes())
    if manifest.get('installable') is not False or manifest.get('installation_profile')!=PROFILE['installation_id'] or not matches_contract(manifest.get('compatibility')):
        raise ValueError('Expected a non-installable candidate with the exact profile')
    fields={'bootloader_sha256','table_sha256','bootloader_review','c6_review','recovery_review',
            'expires_at','app_sha256','key_id','sequence','channel','purpose'}
    if 'commissioning' in review or 'usb_review' in review:fields|={'commissioning','usb_review'}
    if review.get('purpose')=='ota':fields|={'ota_review','from_app_sha256'}
    if set(review)!=fields:
        raise ValueError('Supply the exact documented review fields for the release purpose')
    public_bytes=(candidate/'native-public-trust.json').read_bytes()
    public_config=strict_json(public_bytes)
    trust_header,canonical_public=generate_native_trust(config=public_config)
    if public_config.get('testing_only') is True or manifest.get('native_ota_testing_only') is not False:
        raise ValueError('Software fixture builds cannot be promoted to firmware releases')
    if public_bytes!=canonical_public or public_config['build_sequence']!=review['sequence'] or public_config['build_sequence']==0 or manifest.get('native_build_sequence')!=review['sequence'] or manifest.get('native_public_trust_sha256')!=sha256(public_bytes):
        raise ValueError('Release sequence must match the independently provisioned native build')
    if (candidate/'publisher_trust.h').read_text()!=trust_header or manifest.get('generated_inputs',{}).get('main/ampve/publisher_trust.h')!=sha256(trust_header.encode()):
        raise ValueError('Native publisher trust differs from the recorded build input')
    sdk=(candidate/'sdkconfig').read_bytes()
    if sha256(sdk)!=manifest['sdkconfig_sha256']:raise ValueError('Candidate SDK configuration changed')
    usb_build='CONFIG_AMPVE_USB_COMMISSIONING=y' in sdk.decode().splitlines()
    if usb_build != (review.get('commissioning')=='usb-assisted-v1') or (usb_build and review.get('purpose')!='initial-install'):
        raise ValueError('USB commissioning must match the actual build and initial-install policy')
    if usb_build and manifest.get('commissioning')!='usb-assisted-v1':raise ValueError('Missing commissioning build provenance')
    app=(candidate/'xiaozhi.bin').read_bytes()
    recorded=manifest['proposed_regions_not_approved_writes']
    if len(recorded)!=1 or recorded[0]['sha256']!=sha256(app) or review['app_sha256']!=sha256(app) or recorded[0]['offset']!=0xe00000 or not 24<=len(app)<=0x3f0000:
        raise ValueError('Review does not match the actual candidate app')
    image=image_metadata(app)
    if image['image_bytes']!=len(app) or image['min_revision']>103 or image['max_revision'] not in (0,65535) and image['max_revision']<103:
        raise ValueError('Candidate image is not compatible with P4 1.3')
    if app[32:36]!=b'\x32\x54\xcd\xab' or app[48:80].split(b'\0')[0].decode('ascii')!=manifest['firmware_version']:
        raise ValueError('App descriptor version differs from the reviewed metadata')
    if manifest.get('bit_reproducibility',{}).get('verified') is not True:
        raise ValueError('Archive verified build reproduction evidence before promotion')
    archive_path=candidate.parent/(candidate.name+'.zip')
    if archive_path.stat().st_size>64*1024*1024:
        raise ValueError('Review archive too large')
    archive=archive_path.read_bytes()
    # Read only bounded members; never extract an untrusted archive to disk.
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        entries=bundle.infolist();names=[item.filename for item in entries]
        if len(set(names))!=len(names) or sum(item.file_size for item in entries)>64*1024*1024 or any(name.startswith('/') or '..' in Path(name).parts or '\\' in name for name in names):
            raise ValueError('Invalid review archive structure')
        if bundle.read('native-public-trust.json')!=public_bytes or bundle.read('publisher_trust.h')!=trust_header.encode():
            raise ValueError('Archived native trust differs from the build')
        if bundle.read('review-manifest.json')!=manifest_bytes or bundle.read('xiaozhi.bin')!=app:
            raise ValueError('Review archive does not describe the actual candidate')
        if not any(name.startswith('LICENSE') for name in names) or not any(name.startswith('provisioning-component/') and 'LICENSE' in name.upper() for name in names):
            raise ValueError('Preserve third-party license notices in the release archive')
        for filename,field in [('sdkconfig','sdkconfig_sha256'),('dependencies.lock','dependency_lock_sha256')]:
            if sha256(bundle.read(filename))!=manifest[field]:
                raise ValueError('Archived build provenance differs from the review')
    from workspace.release_notes import archived_notes
    notes=archived_notes(archive) # Validate before reserving a publisher sequence.
    if notes is not None:
        raw=notes.encode('utf-8')
        if manifest.get('release_notes')!={'file':'release-notes.txt','size':len(raw),'sha256':sha256(raw)} or (candidate/'release-notes.txt').read_bytes()!=raw:
            raise ValueError('Archived release notes differ from candidate provenance')
    elif manifest.get('release_notes') is not None:
        raise ValueError('Declared release notes are missing from the review archive')
    app_metadata={'sha256':sha256(app),'size':len(app)}
    if review['purpose']=='initial-install':app_metadata['offset']=0xe00000
    policy={'schema':2,**{k:v for k,v in review.items() if k!='app_sha256'},
        'installable':review['purpose']=='initial-install','profile':PROFILE['installation_id'],
        'compatibility':CONTRACT,'chip_revision':103,'flash_bytes':32*1024*1024,
        'repository_commit':manifest['repository_commit'],'firmware_version':manifest['firmware_version'],
        'app':app_metadata,'provenance':{'review_manifest_sha256':sha256(manifest_bytes),
            'archive_sha256':sha256(archive),'sdkconfig_sha256':manifest['sdkconfig_sha256'],
            'dependency_lock_sha256':manifest['dependency_lock_sha256'],
            'xiaozhi_commit':manifest['xiaozhi_commit'],'esp_idf_commit':manifest['esp_idf_commit']}}
    validate_policy(policy)
    expiry=datetime.fromisoformat(policy['expires_at'].replace('Z','+00:00'))
    if (expiry-datetime.now(timezone.utc)).total_seconds()>31*86400:
        raise ValueError('Approval must expire within 31 days')
    payload=canonical(policy)
    key=Ed25519PrivateKey.from_private_bytes(key_file.read_bytes())
    envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(key.sign(payload)).decode()}
    if output.exists():
        raise FileExistsError('Publish to a new immutable directory')
    release_id=sha256(payload)
    # The publisher's local ledger serializes sequence assignment across processes.
    # Reserve before touching output; failed/interrupted attempts consume a sequence.
    ledger_file.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with closing(sqlite3.connect(ledger_file,timeout=10)) as ledger, ledger:
        ledger_file.chmod(0o600)
        ledger.execute('CREATE TABLE IF NOT EXISTS releases (profile TEXT NOT NULL, channel TEXT NOT NULL, sequence INTEGER NOT NULL, release_id TEXT NOT NULL UNIQUE, PRIMARY KEY(profile,channel,sequence))')
        ledger.execute('BEGIN IMMEDIATE')
        scope=canonical(CONTRACT).decode()
        latest=ledger.execute('SELECT MAX(sequence) FROM releases WHERE profile=? AND channel=?',(scope,policy['channel'])).fetchone()[0]
        if latest is not None and policy['sequence']<=latest:
            raise ValueError('Use a sequence above the publisher ledger high-water mark')
        ledger.execute('INSERT INTO releases VALUES (?,?,?,?)',(scope,policy['channel'],policy['sequence'],release_id))
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    try:
        (output/'xiaozhi.bin').write_bytes(app)
        (output/'review.zip').write_bytes(archive)
        if policy['purpose']=='initial-install':
            (output/'esp-web-tools-reference.json').write_bytes(canonical({'name':'AMPVE','version':policy['firmware_version'],
                'new_install_prompt_erase':False,'builds':[{'chipFamily':'ESP32-P4','parts':[{'path':'xiaozhi.bin','offset':0xe00000}]}],
                'ampve_requires_guarded_installer':True}))
        # The signed envelope is the publication marker and appears only after artifacts exist.
        temporary=output/'envelope.pending'
        temporary.write_bytes(canonical(envelope))
        temporary.replace(output/'approved-release.json')
        for path in output.iterdir():path.chmod(0o444)
        output.chmod(0o555)
    except Exception:
        output.chmod(0o700)
        shutil.rmtree(output)
        raise
    print('Signed release '+release_id+' prepared. Nothing activated or flashed.')
    return policy


def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__);commands=p.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init-key');init.add_argument('--directory',type=Path,required=True)
    pub=commands.add_parser('publish')
    pub.add_argument('--approve-reviewed-development-release',action='store_true',required=True,
        help='Explicit publisher approval after completing the documented engineering review')
    for name in ['candidate','review','key','output','ledger']:pub.add_argument('--'+name,type=Path,required=True)
    verify=commands.add_parser('verify')
    verify.add_argument('--release',type=Path,required=True)
    verify.add_argument('--trust',type=Path,required=True)
    args=p.parse_args()
    if args.command=='init-key':
        directory=args.directory.resolve()
        if any((parent/'.git').exists() for parent in [directory,*directory.parents]):raise ValueError('Keep publisher keys outside Git')
        directory.mkdir(mode=0o700,parents=True,exist_ok=False)
        key=Ed25519PrivateKey.generate()
        (directory/'publisher-private.key').write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        (directory/'publisher-public.key').write_text(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()+'\n')
        print('Publisher key files created privately. No values printed; no release activated.')
    elif args.command=='verify':
        from workspace.release_contract import read_release
        policy,release_id,_,_,floor=read_release(args.release,args.trust)
        print(json.dumps({'release_id':release_id,'sequence':policy['sequence'],'purpose':policy['purpose'],
                          'minimum_sequence':floor,'verified':True,'activated':False}))
    else:
        for path in (args.output,args.key,args.ledger):
            if any((parent/'.git').exists() for parent in [path.resolve(),*path.resolve().parents]):raise ValueError('Keep release output, signing keys and the publisher ledger outside Git')
        publish(args.candidate,args.review,args.key,args.output,args.ledger)

if __name__=='__main__':main()
