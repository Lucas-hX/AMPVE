#pragma once
#include <cstddef>
#include <string>
namespace ampve {
// Hashes the complete verified application file, including its appended ESP image digest.
// This is deliberately different from esp_partition_get_sha256's embedded-image digest.
bool running_image_identity(std::string& sha256, size_t& image_size);
}
