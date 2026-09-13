#pragma once
#include <cstddef>
#include <cstdint>
constexpr int ESP_OK=0;
struct esp_partition_t { uint32_t address; uint32_t size; bool encrypted; };
const esp_partition_t* esp_ota_get_running_partition();
int esp_partition_read(const esp_partition_t*, size_t, void*, size_t);
