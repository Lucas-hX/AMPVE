#pragma once
#include <cstdint>
using nvs_handle_t=uint32_t;
constexpr int ESP_OK=0,ESP_ERR_NVS_NOT_FOUND=1;
int nvs_get_u32(nvs_handle_t,const char*,uint32_t*);
int nvs_set_u32(nvs_handle_t,const char*,uint32_t);
int nvs_commit(nvs_handle_t);
