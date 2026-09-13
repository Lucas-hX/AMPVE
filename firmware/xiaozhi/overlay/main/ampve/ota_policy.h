#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ampve {
// Independently provisioned public trust. Never populate this from an update response.
struct OtaPublisher {
    std::string id;
    unsigned char public_key[32];
    bool development_ota = false;
    bool revoked = false;
};
struct OtaContext {
    std::vector<OtaPublisher> publishers;
    std::vector<std::string> revoked_releases;
    uint32_t minimum_sequence = 0;
    uint32_t confirmed_sequence = 0;
    int64_t now_utc = 0;
    std::string profile, profile_id, layout_id, lineage;
    uint32_t profile_version = 0, chip_revision = 0, flash_bytes = 0;
    size_t slot_capacity = 0;
    std::string running_app_sha256, bootloader_sha256, table_sha256;
};
struct OtaPolicy {
    std::string release_id, app_sha256, firmware_version;
    uint32_t sequence = 0;
    size_t app_size = 0;
    int64_t expires_at = 0;
};
// Read-only, bounded validation. On failure output is cleared. Does not authorize a flash write.
bool verify_ota_policy(const std::string& envelope_json, const std::string& expected_release_id,
                       const OtaContext& context, OtaPolicy& output);
}
