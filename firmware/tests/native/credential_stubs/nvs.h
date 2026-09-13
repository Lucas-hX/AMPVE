#pragma once
#include <cstdint>
#include <cstddef>
using nvs_handle_t=uint32_t;
constexpr int ESP_OK=0,ESP_ERR_NVS_NOT_FOUND=1,ESP_FAIL=-1,NVS_READONLY=0,NVS_READWRITE=1;
int nvs_open(const char*,int,nvs_handle_t*);
void nvs_close(nvs_handle_t);
int nvs_get_str(nvs_handle_t,const char*,char*,size_t*);
int nvs_get_u8(nvs_handle_t,const char*,uint8_t*);
int nvs_get_blob(nvs_handle_t,const char*,void*,size_t*);
int nvs_set_blob(nvs_handle_t,const char*,const void*,size_t);
int nvs_commit(nvs_handle_t);
