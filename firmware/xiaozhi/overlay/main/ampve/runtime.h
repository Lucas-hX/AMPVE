#pragma once
#include <atomic>
extern std::atomic<bool> ampve_touch_ready;
extern std::atomic<bool> ampve_codec_present;
extern std::atomic<bool> ampve_codec_failed;
void ampve_request_wifi();
void ampve_runtime_start();
