"""Strict signed release policies. No device access, database or automatic promotion."""
import base64
import hashlib
import json
import re
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .hardware_profiles import CONTRACT, PARTITIONS, PROFILE, matches_contract

MAX_METADATA = 32768
MAX_SEQUENCE = 2147483647


def strict_json(raw, maximum=MAX_METADATA):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate metadata key')
            result[key] = value
        return result
    if len(raw) > maximum:
        raise ValueError('Metadata exceeds its bound')
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite number')))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def text(value, maximum=1000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum and 'REPLACE' not in value and '\x00' not in value


def sequence(value):
    return type(value) is int and 1 <= value <= MAX_SEQUENCE


def validate_policy(policy, now=None):
    fields = {'schema','key_id','sequence','channel','purpose','installable','profile','compatibility',
              'chip_revision','flash_bytes','expires_at','repository_commit','firmware_version','app',
              'bootloader_sha256','table_sha256','bootloader_review','c6_review','recovery_review','provenance'}
    if not isinstance(policy, dict) or policy.get('purpose') not in ('initial-install', 'ota'):
        raise ValueError('Unknown release purpose')
    if policy['purpose'] == 'ota':
        fields |= {'ota_review', 'from_app_sha256'}
    if set(policy) != fields or type(policy['schema']) is not int or policy['schema'] != 2:
        raise ValueError('Unknown release schema or fields')
    if not isinstance(policy['key_id'], str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', policy['key_id']):
        raise ValueError('Invalid publisher key ID')
    if not sequence(policy['sequence']) or policy['channel'] != 'development':
        raise ValueError('Invalid sequence or unsupported release channel')
    if policy['installable'] is not (policy['purpose'] == 'initial-install'):
        raise ValueError('USB and OTA release purposes cannot be substituted')
    if policy['profile'] != PROFILE['installation_id'] or not matches_contract(policy['compatibility']):
        raise ValueError('Profile contract mismatch')
    if type(policy['chip_revision']) is not int or policy['chip_revision'] != PROFILE['chip']['revision_min'] or policy['flash_bytes'] != PROFILE['resources']['flash_bytes']:
        raise ValueError('Chip revision or flash capacity mismatch')
    if not isinstance(policy['expires_at'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', policy['expires_at']):
        raise ValueError('Expiry must be an explicit UTC timestamp')
    expiry = datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00'))
    if expiry <= (now or datetime.now(timezone.utc)):
        raise ValueError('Release approval expired')
    if not isinstance(policy['repository_commit'], str) or not re.fullmatch('[a-f0-9]{40}', policy['repository_commit']):
        raise ValueError('Missing exact source commit')
    if not isinstance(policy['firmware_version'], str) or not re.fullmatch('[A-Za-z0-9._+-]{1,31}', policy['firmware_version']):
        raise ValueError('Invalid image version')
    for key in ('bootloader_sha256', 'table_sha256'):
        if not digest(policy[key]):
            raise ValueError('Invalid reviewed fingerprint')
    for key in ('bootloader_review','c6_review','recovery_review'):
        if not text(policy[key]):
            raise ValueError('Missing documented engineering review')
    app = policy['app']
    app_fields = {'size', 'sha256', 'offset'} if policy['purpose'] == 'initial-install' else {'size', 'sha256'}
    if not isinstance(app, dict) or set(app) != app_fields or not digest(app['sha256']) or type(app['size']) is not int or not 24 <= app['size'] <= PARTITIONS['ota_1']['size']:
        raise ValueError('Invalid app-only artifact')
    if policy['purpose'] == 'initial-install' and app['offset'] != PARTITIONS['ota_1']['offset']:
        raise ValueError('Initial app must use the reviewed stock slot')
    provenance = policy['provenance']
    hashes = {'review_manifest_sha256','archive_sha256','sdkconfig_sha256','dependency_lock_sha256'}
    if not isinstance(provenance, dict) or set(provenance) != hashes | {'xiaozhi_commit','esp_idf_commit'}:
        raise ValueError('Missing release provenance')
    if any(not digest(provenance[key]) for key in hashes) or any(not isinstance(provenance[key], str) or not re.fullmatch('[a-f0-9]{40}',provenance[key]) for key in ('xiaozhi_commit','esp_idf_commit')):
        raise ValueError('Invalid provenance fingerprints')
    if policy['purpose'] == 'ota':
        previous = policy['from_app_sha256']
        if not text(policy['ota_review']) or not isinstance(previous, list) or not 1 <= len(previous) <= 32 or any(not digest(item) for item in previous) or len(set(previous)) != len(previous) or app['sha256'] in previous:
            raise ValueError('OTA requires reviewed recovery and explicit predecessor app hashes')
    return policy


def verify_envelope(envelope, trust, now=None):
    """Trust comes from private platform configuration, never from the release itself."""
    if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
        raise ValueError('Invalid signed envelope')
    payload = base64.b64decode(envelope['payload'], validate=True)
    policy = validate_policy(strict_json(payload), now)
    if payload != canonical(policy):
        raise ValueError('Signed metadata must be canonical')
    if not isinstance(trust, dict) or set(trust) != {'schema','keys','revoked_releases','minimum_sequence'} or type(trust['schema']) is not int or trust['schema'] != 1:
        raise ValueError('Invalid independent trust registry')
    if not sequence(trust['minimum_sequence']) or policy['sequence'] < trust['minimum_sequence']:
        raise ValueError('Release sequence is below the trusted floor')
    revoked = trust['revoked_releases']
    if not isinstance(revoked, list) or any(not digest(item) for item in revoked):
        raise ValueError('Invalid revocation registry')
    release_id = sha256(payload)
    if release_id in revoked:
        raise ValueError('Release revoked')
    keys = trust['keys']
    if not isinstance(keys, dict) or not 1 <= len(keys) <= 16:
        raise ValueError('Invalid publisher key registry')
    key = keys.get(policy['key_id'])
    if not isinstance(key, dict) or set(key) != {'public_key','channels','purposes','revoked'} or key['revoked'] is not False or not digest(key['public_key']):
        raise ValueError('Unknown or revoked signing key')
    if not isinstance(key['channels'], list) or policy['channel'] not in key['channels'] or not isinstance(key['purposes'], list) or policy['purpose'] not in key['purposes']:
        raise ValueError('Signing key not authorized for release purpose/channel')
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(key['public_key'])).verify(
        base64.b64decode(envelope['signature'], validate=True), payload)
    return policy, release_id, key['public_key']


def eligible_upgrade(policy, installed_sequence, installed_app_sha256):
    """Downgrades are never new deployments; bootloader fallback is a separate action."""
    return (policy['purpose'] == 'ota' and sequence(installed_sequence)
            and policy['sequence'] > installed_sequence
            and installed_app_sha256 in policy['from_app_sha256'])


def read_bounded(path, maximum):
    with path.open('rb') as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError('Release file exceeds its bound')
    return content


def read_release(root, trust_path):
    trust = strict_json(read_bounded(trust_path, MAX_METADATA))
    envelope = strict_json(read_bounded(root/'approved-release.json', MAX_METADATA))
    policy, release_id, public_key = verify_envelope(envelope, trust)
    app = read_bounded(root/'xiaozhi.bin', PARTITIONS['ota_1']['size'])
    archive = read_bounded(root/'review.zip', 64*1024*1024)
    if len(app) != policy['app']['size'] or sha256(app) != policy['app']['sha256'] or sha256(archive) != policy['provenance']['archive_sha256']:
        raise ValueError('Published artifact or provenance was changed')
    return policy, release_id, public_key, envelope, trust['minimum_sequence']
