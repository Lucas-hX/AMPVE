"""Authenticated encryption with a dedicated, externally stored key ring."""
import json
from pathlib import Path
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings


def cipher():
    # First key encrypts new values; remaining keys support a deliberate rotation.
    keys = getattr(settings, 'PROVIDER_ENCRYPTION_KEYS', None)
    if keys is None:
        path = Path(settings.CONFIG.get('provider_key_file', '/home/ampve/.config/ampve/provider-encryption.json'))
        keys = json.loads(path.read_text())['keys']
    return MultiFernet([Fernet(key.encode()) for key in keys])


def encrypt_key(connection, value):
    payload = {'connection': str(connection.pk), 'owner': connection.owner_id,
               'provider': connection.provider, 'key': value}
    return cipher().encrypt(json.dumps(payload).encode()).decode()


def decrypt_key(connection):
    payload = json.loads(cipher().decrypt(connection.encrypted_key.encode()))
    if (payload['connection'], payload['owner'], payload['provider']) != (
            str(connection.pk), connection.owner_id, connection.provider):
        raise InvalidToken('Credential context mismatch')
    return payload['key']
