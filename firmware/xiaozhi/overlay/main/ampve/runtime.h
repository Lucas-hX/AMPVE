#pragma once
#include <atomic>
extern std::atomic<bool> ampve_wifi_initialized;
extern std::atomic<bool> ampve_touch_ready;
void ampve_request_wifi();
bool ampve_initialize_display(void* panel_io, void* panel, int width, int height,
                              int offset_x, int offset_y, bool mirror_x,
                              bool mirror_y, bool swap_xy);
void ampve_runtime_start();

#include <string>
std::string ampve_usb_status(const char* nonce);
