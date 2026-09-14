import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CompanionAudioGateTests(unittest.TestCase):
    def test_preserves_deliberate_interruption(self):
        source = r'''
#include "ampve/companion_audio_gate.h"
#include <cassert>

using Decision = ampve::CompanionAudioGate::Decision;

int main() {
    ampve::CompanionAudioGate gate;
    assert(gate.Observe(false, false) == Decision::Forward);

    gate.PlaybackStarted();
    for (int i = 0; i < 40; ++i) {
        assert(gate.Observe(true, false) == Decision::Hold);
    }

    for (size_t i = 1; i < ampve::CompanionAudioGate::kSpeechFramesForInterruption; ++i) {
        assert(gate.Observe(true, true) == Decision::Hold);
    }
    assert(gate.Observe(true, true) == Decision::InterruptAndForward);
    assert(gate.Observe(true, true) == Decision::Forward);

    gate.PlaybackStarted();
    for (size_t i = 1; i < ampve::CompanionAudioGate::kSpeechFramesForInterruption; ++i) {
        assert(gate.Observe(true, true) == Decision::Hold);
    }
    assert(gate.Observe(true, false) == Decision::Hold);
    assert(gate.Observe(true, true) == Decision::Hold);
}
'''
        with tempfile.TemporaryDirectory(prefix='ampve-audio-gate-') as directory:
            directory = Path(directory)
            cpp = directory / 'gate.cc'
            binary = directory / 'gate'
            cpp.write_text(source)
            subprocess.run([
                'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I' + str(ROOT / 'firmware/xiaozhi/overlay/main'), str(cpp), '-o', str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)
