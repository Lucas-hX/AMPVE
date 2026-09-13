"""Bounded, device-reported capabilities; never treat these as hardware attestation."""
CAPABILITIES = {'display': 'Display', 'touch': 'Touch', 'speaker': 'Speaker',
                'microphone': 'Microphone', 'wifi': 'Wi-Fi'}
STATES = {'unknown': 'Not checked', 'configured': 'Expected by profile',
          'initialized': 'Driver initialized', 'passed': 'Functional test passed',
          'failed': 'Test failed', 'unavailable': 'Unavailable'}


def validate_report(value):
    if not isinstance(value, dict) or set(value) != {'schema', 'flash_bytes', 'psram_bytes', 'display', 'capabilities'}:
        raise ValueError()
    if type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError()
    for name in ['flash_bytes', 'psram_bytes']:
        if value[name] is not None and (type(value[name]) is not int or not 0 <= value[name] <= 2**30):
            raise ValueError()
    screen = value['display']
    if screen is not None:
        if not isinstance(screen, dict) or set(screen) != {'width', 'height'}:
            raise ValueError()
        if any(type(v) is not int or not 1 <= v <= 4096 for v in screen.values()):
            raise ValueError()
    caps = value['capabilities']
    if not isinstance(caps, dict) or set(caps) != set(CAPABILITIES):
        raise ValueError()
    if any(not isinstance(v, str) or v not in STATES for v in caps.values()):
        raise ValueError()
    return value


def display_report(report):
    if not report:
        return []
    return [{'name': label, 'state': STATES[report['capabilities'][key]]}
            for key, label in CAPABILITIES.items()]
