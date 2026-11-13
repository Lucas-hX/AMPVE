"""Clean and previously prepared checkouts must link the same AMPVE modules."""
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'firmware/tools'))
from prepare import configure_lean_sources, normalize_ampve_sources  # noqa: E402


class PrepareLinkOrderTests(unittest.TestCase):
    def test_historical_and_clean_source_orders_converge(self):
        common=['diagnostics.cc','app_runtime.cc','app_package.cc','board_base.cc','improv_service.cc',
                'improv_platform.cc','boot_guard.cc',
                'ota_client.cc','ota_platform.cc','image_identity.cc','ota_policy.cc',
                'runtime.cc','brand_assets.c']
        historical=common[:3]+['companion_face.cc','companion.cc']+common[3:]
        histories=[historical,common[3:5]+common[:3]+common[5:]]
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

    def test_core_lite_boundary_excludes_upstream_runtime_and_media(self):
        with tempfile.TemporaryDirectory(prefix='ampve-lean-sources-') as directory:
            path=Path(directory)/'CMakeLists.txt'
            path.write_text('set(SOURCES "audio/audio_codec.cc" "application.cc")\n'
                            'idf_component_register(SRCS ${SOURCES}\n'
                            '  EMBED_FILES ${LANG_SOUNDS} ${COMMON_SOUNDS}\n'
                            '                        esp_driver_i2s\n'
                            '                        esp_driver_jpeg\n'
                            '                        esp_driver_ppa\n'
                            '                        esp_driver_tsens\n'
                            '                        esp_driver_sdmmc\n'
                            '                        sdmmc\n'
                            '                        console\n'
                            '                        bt\n'
                            '                        fatfs\n'
                            '                        xiaozhi-fonts\n)\n')
            configure_lean_sources(path)
            prepared=path.read_text()
            boundary=prepared.split('# AMPVE Core Lite source boundary',1)[1]
            self.assertIn('"ampve/runtime.cc"',boundary)
            self.assertIn('${BOARD_SOURCES}',boundary)
            for omitted in ('audio/audio_codec.cc','application.cc','protocols/websocket_protocol.cc'):
                self.assertNotIn(omitted,boundary)
            for dependency in ('esp_driver_i2s','esp_driver_jpeg','esp_driver_ppa',
                               'esp_driver_tsens','esp_driver_sdmmc','sdmmc',
                               'fatfs','xiaozhi-fonts'):
                self.assertNotIn(dependency,boundary)
            configure_lean_sources(path)
