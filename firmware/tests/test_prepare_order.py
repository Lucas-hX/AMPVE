"""Clean and previously prepared checkouts must link the same AMPVE modules."""
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'firmware/tools'))
from prepare import normalize_ampve_sources  # noqa: E402


class PrepareLinkOrderTests(unittest.TestCase):
    def test_historical_and_clean_source_orders_converge(self):
        common=['diagnostics.cc','app_runtime.cc','app_package.cc','companion_face.cc',
                'companion.cc','improv_service.cc','improv_platform.cc','boot_guard.cc',
                'ota_client.cc','ota_platform.cc','image_identity.cc','ota_policy.cc',
                'runtime.cc','brand_assets.c']
        histories=[common,common[5:7]+common[:5]+common[7:]]
        with tempfile.TemporaryDirectory(prefix='ampve-link-order-') as directory:
            paths=[]
            for index,history in enumerate(histories):
                path=Path(directory)/f'case-{index}.txt'
                path.write_text('set(SOURCES '+ ' '.join(f'"ampve/{name}"' for name in history)+
                                ' "audio/audio_codec.cc"\n  "audio/audio_debugger.cc")\n')
                normalize_ampve_sources(path);paths.append(path)
            self.assertEqual(paths[0].read_bytes(),paths[1].read_bytes())
            paths[1].write_text(paths[1].read_text().replace('"ampve/runtime.cc" ',''))
            with self.assertRaises(RuntimeError):normalize_ampve_sources(paths[1])
