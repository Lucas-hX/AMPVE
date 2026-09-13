#pragma once
#include <cstdint>
#include "nvs.h"

namespace ampve {
enum class BootAttempt { Ready, Recovery, StorageError };
BootAttempt record_boot_attempt(nvs_handle_t store);
bool reset_boot_attempts(nvs_handle_t store);

// A release followed by a continuous five-second hold permits one write attempt.
// Time comes from the monotonic ESP timer, never the network clock.
class BootRetryHold {
public:
    bool update(bool pressed, int64_t now_us) {
        if (!pressed) { released_=true; start_=-1; attempted_=false; return false; }
        if (!released_ || attempted_) return false;
        if (start_<0 || now_us<start_) { start_=now_us; return false; }
        if (now_us-start_<5000000) return false;
        attempted_=true;
        return true;
    }
private:
    bool released_=false, attempted_=false;
    int64_t start_=-1;
};
}
