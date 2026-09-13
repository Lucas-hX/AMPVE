"""Public build-input validation; no production signing keys or hardware writes."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from native_trust import generate

class NativeTrustTests(unittest.TestCase):
    def config(self):
        return {'schema':1,'build_sequence':7,'trust':{'schema':1,'minimum_sequence':1,'revoked_releases':[],
            'keys':{'fixture-key':{'public_key':'a'*64,'channels':['development'],'purposes':['ota'],'revoked':False}}}}

    def test_default_build_has_no_publisher_or_sequence(self):
        header,public=generate()
        self.assertIn('AMPVE_BUILD_SEQUENCE 0',header)
        self.assertNotIn('push_back',header)
        self.assertIsNone(json.loads(public)['trust'])

    def test_public_trust_is_deterministic_and_binds_build_sequence(self):
        config=self.config();header,public=generate(config=config)
        self.assertIn('AMPVE_BUILD_SEQUENCE 7',header)
        self.assertIn('fixture-key',header)
        self.assertEqual(generate(config=json.loads(public)),(header,public))

    def test_invalid_or_non_updatable_builds_fail_closed(self):
        for value in [0,-1,True,7.0,2147483648]:
            config=self.config();config['build_sequence']=value
            with self.subTest(value=value),self.assertRaises(ValueError):generate(config=config)
        mutations=[lambda c:c['trust'].update(minimum_sequence=8),lambda c:c['trust'].update(keys={}),
            lambda c:c['trust']['keys']['fixture-key'].update(revoked=True),
            lambda c:c['trust']['keys']['fixture-key'].update(purposes=['initial-install']),
            lambda c:c['trust']['keys']['fixture-key'].update(public_key='invalid'),
            lambda c:c['trust'].update(revoked_releases=['invalid'])]
        for mutate in mutations:
            config=self.config();mutate(config)
            with self.assertRaises(ValueError):generate(config=config)
