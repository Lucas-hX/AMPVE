"""Reject registry resolution drift after applying the local provisioning override."""
import sys
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[2]
expected = yaml.safe_load((root/'firmware/xiaozhi/dependencies.lock').read_text())['dependencies']
actual = yaml.safe_load(Path(sys.argv[1]).read_text())['dependencies']
if set(expected) != set(actual):
    raise SystemExit('Resolved component set changed; review and repin explicitly')
for name, item in expected.items():
    if name == '78/esp-wifi-connect':
        if actual[name]['version'] != '3.3.1' or actual[name]['source']['type'] != 'local':
            raise SystemExit('Protected local provisioning override is missing')
    elif (any(item.get(key) != actual[name].get(key) for key in ['version', 'component_hash'])
          or item['source']['type'] != actual[name]['source']['type']
          or item['source'].get('registry_url', '').rstrip('/') != actual[name]['source'].get('registry_url', '').rstrip('/')):
        raise SystemExit('Resolved dependency changed: '+name)
print('All registry versions and component hashes match the pinned baseline.')
