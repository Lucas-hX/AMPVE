#pragma once
#include "ota_policy.h"
#include <cstddef>
#include <cstdint>
#include <string>

namespace ampve {
// Capability API v1: these values describe built-in UI/actions, never code to execute.
struct AppPackage {
    std::string id, name, version, kind, title, body;
    uint32_t duration_s = 0;
    bool start_muted = true;
};
bool verify_app_package(const std::string& envelope, const std::string& expected_id,
                        const OtaContext& context, size_t psram_bytes, AppPackage& output);
}
