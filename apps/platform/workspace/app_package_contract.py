"""Capability API v1: signed, RAM-sized UI/workflow declarations, never native code."""
import base64
import re
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .hardware_profiles import CONTRACT, PROFILE
from .release_contract import canonical, sha256, strict_json

MAX_PAYLOAD = 1024
MAX_ENVELOPE = 2048
KINDS = {'status': ('show_status', 0), 'timer': ('local_timer', None),
         'companion': ('native_companion', 0)}
FIELDS = {'schema', 'api_version', 'key_id', 'name', 'version', 'kind',
          'profile_id', 'profile_version', 'layout_id', 'chip_revision',
          'flash_bytes', 'minimum_psram_bytes', 'expires_at', 'ui', 'workflow'}


def ascii_text(value, maximum):
    return (isinstance(value, str) and 1 <= len(value) <= maximum and
            bool(re.fullmatch(r'[A-Za-z0-9 .,:!?_+\-/]+', value)))


def validate(policy, now=None):
    if not isinstance(policy, dict) or set(policy) != FIELDS or type(policy['schema']) is not int or policy['schema'] != 1 or type(policy['api_version']) is not int or policy['api_version'] != 1:
        raise ValueError('Unknown capability API or package fields')
    if any(not isinstance(policy[field], str) for field in ('key_id','name','version','kind')) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', policy['key_id']) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,31}', policy['name']) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', policy['version']):
        raise ValueError('Invalid package identity')
    if policy['kind'] not in KINDS or policy['profile_id'] != CONTRACT['profile_id'] or type(policy['profile_version']) is not int or policy['profile_version'] != CONTRACT['profile_version'] or policy['layout_id'] != CONTRACT['layout_id'] or any(type(policy[field]) is not int for field in ('chip_revision','flash_bytes','minimum_psram_bytes')) or policy['chip_revision'] != 103 or policy['flash_bytes'] != PROFILE['resources']['flash_bytes'] or policy['minimum_psram_bytes'] != PROFILE['resources']['minimum_psram_bytes']:
        raise ValueError('Package hardware does not match Core v1')
    if not isinstance(policy['expires_at'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', policy['expires_at']) or datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00')) <= (now or datetime.now(timezone.utc)):
        raise ValueError('Package approval expired')
    ui, workflow = policy['ui'], policy['workflow']
    if not isinstance(ui, dict) or set(ui) != {'title', 'body'} or not ascii_text(ui['title'], 48) or not ascii_text(ui['body'], 96) or not isinstance(workflow, dict) or set(workflow) != {'action', 'duration_s', 'start_muted'} or type(workflow['duration_s']) is not int or type(workflow['start_muted']) is not bool:
        raise ValueError('Package UI or workflow exceeds API v1')
    action, duration = KINDS[policy['kind']]
    if workflow['action'] != action or not (1 <= workflow['duration_s'] <= 3600 if duration is None else workflow['duration_s'] == duration) or (policy['kind'] != 'companion' and workflow['start_muted'] is not True):
        raise ValueError('Unsupported package capability')
    if len(canonical(policy)) > MAX_PAYLOAD:
        raise ValueError('Package exceeds RAM payload bound')
    return policy


def verify(envelope, trust, now=None):
    if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'} or any(not isinstance(envelope[field],str) for field in ('payload','signature')) or len(canonical(envelope)) > MAX_ENVELOPE:
        raise ValueError('Invalid bounded package envelope')
    payload = base64.b64decode(envelope['payload'], validate=True)
    signature = base64.b64decode(envelope['signature'], validate=True)
    if len(payload) > MAX_PAYLOAD or len(signature) != 64:
        raise ValueError('Invalid package signature or size')
    policy = validate(strict_json(payload), now)
    if payload != canonical(policy):
        raise ValueError('Package must use canonical signed JSON')
    key = trust.get('keys', {}).get(policy['key_id']) if isinstance(trust, dict) else None
    if not isinstance(key, dict) or key.get('revoked') is not False or 'development' not in key.get('channels', []) or 'ota' not in key.get('purposes', []):
        raise ValueError('No active development publisher for package')
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(key['public_key'])).verify(signature, payload)
    identity = sha256(payload)
    if identity in trust.get('revoked_releases', []):
        raise ValueError('Package was revoked in trusted registry')
    return policy, identity
