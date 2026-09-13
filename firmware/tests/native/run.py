"""Compile the actual native verifier against the pinned cJSON/libsodium sources; no board access."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/platform'))
from workspace.hardware_profiles import PROFILE, CONTRACT
from workspace.release_contract import canonical

parser=argparse.ArgumentParser()
parser.add_argument('--work',required=True,type=Path)
parser.add_argument('--sodium-host',required=True,type=Path)
args=parser.parse_args()
component=args.work/'managed_components'
cjson=component/'espressif__cjson/cJSON'
sodium=component/'espressif__libsodium/libsodium/src/libsodium/include'
subprocess.run([sys.executable,str(ROOT/'firmware/tools/check_lock.py'),str(args.work/'dependencies.lock')],check=True)
with tempfile.TemporaryDirectory(prefix='ampve-native-policy-') as directory:
    tmp=Path(directory)
    includes=['-I'+str(cjson),'-I'+str(sodium),'-I'+str(sodium/'sodium'),'-I'+str(args.sodium_host/'src/libsodium/include'),
              '-I'+str(ROOT/'firmware/xiaozhi/overlay/main/ampve')]
    subprocess.run(['cc','-c','-O1','-g','-fsanitize=address,undefined',str(cjson/'cJSON.c'),'-o',str(tmp/'cjson.o')],check=True)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',*includes,
        str(ROOT/'firmware/xiaozhi/overlay/main/ampve/ota_policy.cc'),str(ROOT/'firmware/tests/native/policy_harness.cc'),
        str(tmp/'cjson.o'),str(args.sodium_host/'src/libsodium/.libs/libsodium.a'),'-pthread','-o',str(tmp/'verify')],check=True)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',*includes,
        '-I'+str(ROOT/'firmware/tests/native/idf_stub'),
        str(ROOT/'firmware/xiaozhi/overlay/main/ampve/image_identity.cc'),str(ROOT/'firmware/tests/native/identity_harness.cc'),
        str(args.sodium_host/'src/libsodium/.libs/libsodium.a'),'-pthread','-o',str(tmp/'identity')],check=True)
    subprocess.run([str(tmp/'identity')],check=True)
    key=Ed25519PrivateKey.generate()
    policy=json.loads((ROOT/'tests/fixtures/initial-release-v2.json').read_text())
    policy.update(purpose='ota',installable=False,sequence=2,ota_review='Software fixture only',
                  from_app_sha256=['a'*64],expires_at='2030-01-01T00:00:00Z')
    del policy['app']['offset']
    context={**CONTRACT,'profile':PROFILE['installation_id'],'lineage':CONTRACT['firmware_lineage'],
        'chip_revision':103,'flash_bytes':33554432,'slot_capacity':4194304,'now_utc':1800000000,
        'confirmed_sequence':1,'minimum_sequence':1,'running_app_sha256':'a'*64,
        'bootloader_sha256':policy['bootloader_sha256'],'table_sha256':policy['table_sha256'],
        'key_id':policy['key_id'],'public_key':key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),
        'authorized':1,'revoked':0,'with_key':1,'release_revoked':0}
    count=0
    def run(label, p=None, ctx=None, expected=False, raw=None, envelope_change=None, identity=None):
        global count
        payload=raw if raw is not None else canonical(policy if p is None else p)
        envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(key.sign(payload)).decode()}
        if envelope_change:envelope_change(envelope)
        (tmp/'envelope.json').write_bytes(canonical(envelope))
        (tmp/'context.json').write_bytes(canonical(context if ctx is None else ctx))
        reply=subprocess.check_output([str(tmp/'verify'),str(tmp/'envelope.json'),str(tmp/'context.json'),
                                      identity or hashlib.sha256(payload).hexdigest()],text=True).strip()
        assert reply==('accepted' if expected else 'refused'),(label,reply)
        count+=1
    run('valid signed OTA',expected=True)
    for field,value in [('schema',1),('purpose','initial-install'),('installable',True),('sequence',1),('sequence',True),
        ('sequence',2.5),('sequence',2147483648),('channel','production'),('profile','wrong'),('chip_revision',300),
        ('flash_bytes',16777216),('expires_at','2020-01-01T00:00:00Z'),('expires_at','2030-02-30T00:00:00Z'),
        ('expires_at','2030-01-01T24:00:00Z'),('expires_at','2030-01-01T00:00:60Z'),('key_id','unknown'),
        ('repository_commit','invalid'),('bootloader_sha256','0'*64),('table_sha256','0'*64),
        ('firmware_version','x'*32),('ota_review','REPLACE'),('from_app_sha256',[]),('from_app_sha256',['b'*64]),
        ('from_app_sha256',['a'*64]*2),('from_app_sha256',['a'*64,policy['app']['sha256']])]:
        changed=copy.deepcopy(policy);changed[field]=value;run(field,p=changed)
    for field,value in [('with_key',0),('authorized',0),('revoked',1),('release_revoked',1),('slot_capacity',23),
        ('minimum_sequence',3),('confirmed_sequence',2),('now_utc',0),('public_key','0'*64),('profile_version',2),
        ('layout_id','wrong'),('lineage','wrong'),('profile_id','wrong')]:
        run(field,ctx={**context,field:value})
    for path,value in [('size',23),('size',4194305),('size',True),('sha256','wrong'),('offset',0)]:
        changed=copy.deepcopy(policy);changed['app'][path]=value;run(path,p=changed)
    run('extra field',p={**policy,'url':'https://invalid.example'})
    changed=copy.deepcopy(policy);del changed['recovery_review'];run('missing field',p=changed)
    run('wrong release ID',identity='0'*64)
    run('wrong signature',envelope_change=lambda e:e.update(signature=base64.b64encode(b'\0'*64).decode()))
    run('truncated signature',envelope_change=lambda e:e.update(signature=e['signature'][:-4]))
    run('invalid base64',envelope_change=lambda e:e.update(payload=e['payload']+'!'))
    run('duplicate key',raw=canonical(policy).replace(b'"schema":2',b'"schema":2,"schema":2'))
    run('escaped duplicate key',raw=canonical(policy).replace(b'"schema":2',b'"schema":2,"\\u0073chema":2'))
    run('trailing content',raw=canonical(policy)+b'{}')
    run('noncanonical float',raw=canonical(policy).replace(b'"schema":2',b'"schema":2.0'))
    run('noncanonical whitespace',raw=b' '+canonical(policy))
    run('noncanonical key order',raw=json.dumps(policy,separators=(',',':')).encode())
    run('noncanonical escape',raw=canonical(policy).replace(b'"development"',b'"\\u0064evelopment"'))
    run('deep JSON',raw=b'['*50+b'0'+b']'*50)
    run('metadata bound',raw=b' '*32769)
    run('NUL truncation',raw=canonical(policy).replace(b'"development"',b'"development\\u0000evil"'))
    changed=copy.deepcopy(policy);changed['c6_review']='Reviewed with accented text and emoji: café 😀';run('canonical Unicode review',p=changed,expected=True)
    print(f'{count} native policy cases passed with AddressSanitizer and UndefinedBehaviorSanitizer. Synthetic signatures only.')

    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',*includes,
        str(ROOT/'firmware/xiaozhi/overlay/main/ampve/ota_policy.cc'),str(ROOT/'firmware/xiaozhi/overlay/main/ampve/ota_client.cc'),
        str(ROOT/'firmware/tests/native/client_harness.cc'),str(tmp/'cjson.o'),
        str(args.sodium_host/'src/libsodium/.libs/libsodium.a'),'-pthread','-o',str(tmp/'client')],check=True)
    policy['app']['size']=524288
    payload=canonical(policy)
    (tmp/'envelope.json').write_bytes(canonical({'payload':base64.b64encode(payload).decode(),
        'signature':base64.b64encode(key.sign(payload)).decode()}))
    (tmp/'context.json').write_bytes(canonical(context))
    for scenario in ['success','claim_ack_lost','progress_ack_lost','verify_ack_lost','reboot_ack_lost','outcome_ack_lost',
                     'network','cancel','hash','select','save_fail','save_ack_fail','power_download','power_before_select','rollback','reauthorization_denied','revoked_after_lost_ack','owner_cancel_race','select_uncertain','corrupt_journal','deep_journal','stale_failed_slot','recovery_unreadable','selection_save_fail_target',
                     'selection_save_fail_rollback','legacy_target','legacy_predecessor','legacy_pending','denied_stale_slot']:
        subprocess.run([str(tmp/'client'),str(tmp/'envelope.json'),str(tmp/'context.json'),hashlib.sha256(payload).hexdigest(),scenario],check=True)
