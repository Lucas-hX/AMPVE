#include "image_identity.h"
#include "esp_ota_ops.h"
#include "esp_image_format.h"
#include "sodium.h"
#include <algorithm>
#include <memory>

namespace ampve {
bool running_image_identity(std::string& sha256, size_t& image_size) {
    sha256.clear(); image_size = 0;
    const auto* running = esp_ota_get_running_partition();
    if (!running || running->encrypted || sodium_init() < 0) return false;
    esp_partition_pos_t position = {running->address, running->size};
    esp_image_metadata_t metadata = {};
    if (esp_image_verify(ESP_IMAGE_VERIFY_SILENT, &position, &metadata) != ESP_OK ||
        metadata.image_len < 24 || metadata.image_len > running->size || !metadata.image.hash_appended) return false;
    std::unique_ptr<unsigned char[]> buffer(new (std::nothrow) unsigned char[4096]);
    if (!buffer) return false;
    crypto_hash_sha256_state digest;
    if (crypto_hash_sha256_init(&digest) != 0) return false;
    for (size_t offset = 0; offset < metadata.image_len;) {
        size_t count = std::min(static_cast<size_t>(metadata.image_len) - offset, static_cast<size_t>(4096));
        if (esp_partition_read(running, offset, buffer.get(), count) != ESP_OK ||
            crypto_hash_sha256_update(&digest, buffer.get(), count) != 0) return false;
        offset += count;
    }
    unsigned char result[crypto_hash_sha256_BYTES]; char hex[65];
    if (crypto_hash_sha256_final(&digest, result) != 0) return false;
    sodium_bin2hex(hex, sizeof(hex), result, sizeof(result));
    sha256 = hex; image_size = metadata.image_len;
    return true;
}
}
