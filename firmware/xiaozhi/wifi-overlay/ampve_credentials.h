#pragma once
#include "ssid_manager.h"
namespace ampve_wifi {
// Read-only legacy import. Corrupt/unreadable state must never become an empty replacement.
bool load(std::vector<SsidItem>& entries);
// One bounded NVS blob keeps both candidate and previous credentials together.
bool save(const std::vector<SsidItem>& entries,const std::vector<SsidItem>& previous);
}
