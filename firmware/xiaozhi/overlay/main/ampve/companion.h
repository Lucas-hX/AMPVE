#pragma once

#include <cstdint>
#include <string>

namespace ampve {

enum class CompanionState : uint8_t { Idle, Connecting, Listening, Error };

bool companion_start(const std::string& url, const std::string& ticket, int volume);
void companion_stop();
void companion_poll();
void companion_toggle_mute();
void companion_mute();
bool companion_active();
bool companion_muted();
CompanionState companion_state();
const char* companion_status();

}  // namespace ampve
