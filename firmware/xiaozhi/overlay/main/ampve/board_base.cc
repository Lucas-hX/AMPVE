// Minimal implementations required by the upstream board interface.
#include "board.h"
#include "esp_random.h"
#include <cstdio>

Board::Board() : uuid_(GenerateUuid()) {}

std::string Board::GenerateUuid() {
    uint8_t value[16];
    esp_fill_random(value, sizeof(value));
    value[6] = (value[6] & 0x0f) | 0x40;
    value[8] = (value[8] & 0x3f) | 0x80;
    char text[37];
    snprintf(text, sizeof(text),
             "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
             value[0], value[1], value[2], value[3], value[4], value[5], value[6], value[7],
             value[8], value[9], value[10], value[11], value[12], value[13], value[14], value[15]);
    return text;
}

bool Board::GetBatteryLevel(int&, bool&, bool&) { return false; }
bool Board::GetTemperature(float&) { return false; }
Display* Board::GetDisplay() { return nullptr; }
Camera* Board::GetCamera() { return nullptr; }
Led* Board::GetLed() { return nullptr; }
std::string Board::GetSystemInfoJson() { return "{}"; }
