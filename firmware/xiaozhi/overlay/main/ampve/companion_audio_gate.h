#pragma once

#include <cstddef>

namespace ampve {

// Keeps provider-side turn detection away from speaker echo while preserving
// deliberate user interruptions detected after local echo cancellation.
class CompanionAudioGate {
public:
    enum class Decision { Hold, Forward, InterruptAndForward };

    static constexpr size_t kSpeechFramesForInterruption = 6;  // 120 ms at 20 ms/frame.

    Decision Observe(bool playback_active, bool local_speech) {
        if (!playback_active || interruption_latched_) {
            speech_frames_ = 0;
            return Decision::Forward;
        }
        if (!local_speech) {
            speech_frames_ = 0;
            return Decision::Hold;
        }
        if (++speech_frames_ < kSpeechFramesForInterruption) {
            return Decision::Hold;
        }
        speech_frames_ = 0;
        interruption_latched_ = true;
        return Decision::InterruptAndForward;
    }

    void PlaybackStarted() {
        speech_frames_ = 0;
        interruption_latched_ = false;
    }

    void Reset() {
        speech_frames_ = 0;
        interruption_latched_ = false;
    }

private:
    size_t speech_frames_ = 0;
    bool interruption_latched_ = false;
};

}  // namespace ampve
