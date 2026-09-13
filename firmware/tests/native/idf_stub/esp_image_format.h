#pragma once
#include <cstdint>
struct esp_partition_pos_t { uint32_t offset; uint32_t size; };
struct esp_image_metadata_t { uint32_t image_len; struct { bool hash_appended; } image; };
constexpr int ESP_IMAGE_VERIFY_SILENT=0;
int esp_image_verify(int,const esp_partition_pos_t*,esp_image_metadata_t*);
