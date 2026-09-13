"""Versioned hardware contract shared with browser bundles and native build tooling.

These are compatibility expectations, not device attestation or write approval.
Keep this module independent of Django so offline tooling can use the same contract.
"""
import json
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parents[3] / 'firmware/profiles/waveshare-7b-stock-v1.json'
PROFILE = json.loads(PROFILE_PATH.read_text())
CONTRACT = {
    'profile_id': PROFILE['id'],
    'profile_version': PROFILE['version'],
    'layout_id': PROFILE['layout']['id'],
    'firmware_lineage': PROFILE['firmware_lineage'],
}
PARTITIONS = {item['name']: item for item in PROFILE['layout']['partitions']}


def matches_contract(value):
    return (isinstance(value, dict) and value == CONTRACT
            and type(value.get('profile_version')) is int)


def matches_layout(partitions, offset):
    fields = ('name', 'type', 'subtype', 'offset', 'size', 'flags')
    return (offset == PROFILE['layout']['table_offset']
            and len(partitions) == len(PARTITIONS)
            and all(all(actual.get(k) == expected[k] for k in fields)
                    for actual, expected in zip(partitions, PARTITIONS.values())))


def runtime_reasons(device):
    """Named blockers based only on the owner's record and bounded client reports."""
    report = device.hardware_report or {}
    reasons = []
    if device.hardware_profile != PROFILE['id']:
        reasons.append('model_mismatch')
    if not matches_contract(report.get('compatibility')):
        reasons.append('profile_contract_unverified')
    if device.chip_revision != '1.3':
        reasons.append('chip_revision_unverified')
    if report.get('flash_bytes') != PROFILE['resources']['flash_bytes']:
        reasons.append('flash_capacity_mismatch')
    psram = report.get('psram_bytes')
    if type(psram) is not int or psram < PROFILE['resources']['minimum_psram_bytes']:
        reasons.append('psram_insufficient_or_unverified')
    if device.transport != PROFILE['connectivity']['transport']:
        reasons.append('transport_unverified')
    # These cannot be inferred from a heartbeat or the shared chip family.
    reasons.extend(['security_unverified', 'c6_compatibility_unverified', 'recovery_unverified'])
    return reasons


REASON_LABELS = {
    'model_mismatch': 'The recorded board model does not match this firmware.',
    'profile_contract_unverified': 'The versioned firmware and partition profile has not been reported or does not match.',
    'chip_revision_unverified': 'ESP32-P4 revision 1.3 has not been reported.',
    'flash_capacity_mismatch': 'The required 32 MiB flash capacity has not been reported.',
    'psram_insufficient_or_unverified': 'The required 32 MiB initialized PSRAM has not been reported.',
    'transport_unverified': 'Wi-Fi connectivity has not been reported.',
    'security_unverified': 'A reviewed security-state audit is still required before firmware writes.',
    'c6_compatibility_unverified': 'Compatibility with the installed ESP32-C6 firmware still needs review.',
    'recovery_unverified': 'First installation and recovery still require physical validation.',
}
