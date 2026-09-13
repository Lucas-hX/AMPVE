#pragma once
#include <string>
void ampve_ota_tick(const std::string& device,const std::string& credential,const std::string& running_hash);
void ampve_cancel_update();
void ampve_ota_status(const char* message);
