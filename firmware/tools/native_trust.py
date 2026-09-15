"""Generate public native OTA trust from independent reviewed build inputs; never create keys."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/platform'))
from workspace.release_contract import canonical, digest, sequence, strict_json, read_bounded


def generate(path=None,config=None):
    if path is not None and config is not None:raise ValueError("Choose one independent trust input")
    default={'schema':1,'build_sequence':0,'trust':None,'testing_only':False}
    if config is None:config=default
    if path:
        path=Path(path).resolve()
        if any((p/'.git').exists() for p in [path.parent,*path.parents]):
            raise ValueError('Keep independent trust configuration outside Git')
        config=strict_json(read_bounded(path,32768))
    if isinstance(config,dict) and 'testing_only' not in config:config={**config,'testing_only':False}
    if not isinstance(config,dict) or type(config.get('testing_only')) is not bool:raise ValueError('Invalid build testing marker')
    if canonical(config)!=canonical(default):
        if not isinstance(config,dict) or set(config)!={'schema','build_sequence','trust','testing_only'} or type(config['schema']) is not int or config['schema']!=1 or not sequence(config['build_sequence']):
            raise ValueError('Invalid native build sequence')
        trust=config['trust']
        if not isinstance(trust,dict) or set(trust)!={'schema','minimum_sequence','keys','revoked_releases'} or type(trust['schema']) is not int or trust['schema']!=1 or not sequence(trust['minimum_sequence']) or trust['minimum_sequence']>config['build_sequence']:
            raise ValueError('Invalid independent trust registry')
        if not isinstance(trust['keys'],dict) or not 1<=len(trust['keys'])<=16 or not isinstance(trust['revoked_releases'],list) or len(trust['revoked_releases'])>128 or any(not digest(v) for v in trust['revoked_releases']):
            raise ValueError('Invalid bounded publisher trust')
        import re
        for key_id,key in trust['keys'].items():
            if not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}',key_id) or not isinstance(key,dict) or set(key)!={'public_key','channels','purposes','revoked'} or not digest(key['public_key']) or type(key['revoked']) is not bool or not isinstance(key['channels'],list) or not isinstance(key['purposes'],list) or any(v!='development' for v in key['channels']) or any(v not in ('initial-install','ota','local-recovery') for v in key['purposes']):
                raise ValueError('Invalid public publisher entry')
        if not any(not key['revoked'] and 'development' in key['channels'] and 'ota' in key['purposes'] for key in trust['keys'].values()):
            raise ValueError('An active OTA publisher is required for a release build')
    lines=['// Generated public build trust. Never obtain this from a device API response.',
           '#pragma once','#include "ota_policy.h"',f'#define AMPVE_BUILD_SEQUENCE {config["build_sequence"]}',
           f'#define AMPVE_OTA_TESTING_ONLY {int(config["testing_only"])}',
           'inline void ampve_publisher_trust(ampve::OtaContext& context) {','    (void)context;']
    if config['trust']:
        trust=config['trust'];lines.append(f'    context.minimum_sequence={trust["minimum_sequence"]};')
        for key_id,key in sorted(trust['keys'].items()):
            values=','.join('0x'+key['public_key'][i:i+2] for i in range(0,64,2))
            allowed='development' in key['channels'] and 'ota' in key['purposes']
            lines.append('    context.publishers.push_back({%s,{%s},%s,%s});'%(json.dumps(key_id),values,str(allowed).lower(),str(key['revoked']).lower()))
        for identity in trust['revoked_releases']:lines.append(f'    context.revoked_releases.push_back("{identity}");')
    lines.append('}')
    return '\n'.join(lines)+'\n',canonical(config)
