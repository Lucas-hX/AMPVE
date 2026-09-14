#include "ampve/companion.h"

#include "ampve/runtime.h"
#include "audio_codec.h"
#include "board.h"
#include "network_interface.h"
#include "web_socket.h"
#include "cJSON.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include <algorithm>
#include <atomic>
#include <cstring>
#include <memory>
#include <mutex>
#include <vector>

namespace ampve {
namespace {

constexpr size_t kPcmFrameBytes = 960;  // 20 ms, 24 kHz, signed 16-bit mono.
constexpr size_t kMaximumServerFrameBytes = 1920;
struct PlaybackFrame { size_t size; uint8_t data[kMaximumServerFrameBytes]; };

std::atomic<CompanionState> state{CompanionState::Idle};
std::atomic<bool> muted{true}, stop_requested{false}, task_active{false};
std::atomic<int64_t> last_output_at{0};
std::unique_ptr<WebSocket> socket;
std::mutex socket_mutex;
QueueHandle_t playback_queue = nullptr;

void fail() {
    state = CompanionState::Error;
    stop_requested = true;
}

void receive(const char* data, size_t length, bool binary) {
    if (binary) {
        if (!data || !length || length > kMaximumServerFrameBytes || length % sizeof(int16_t)) {
            fail(); return;
        }
        PlaybackFrame frame{}; frame.size = length;
        memcpy(frame.data, data, length);
        if (!playback_queue || xQueueSend(playback_queue, &frame, 0) != pdTRUE) fail();
        return;
    }
    if (!data || !length || length > 512) { fail(); return; }
    auto message = cJSON_ParseWithLength(data, length);
    auto type = message ? cJSON_GetObjectItemCaseSensitive(message, "type") : nullptr;
    if (!cJSON_IsString(type) || !type->valuestring) {
        cJSON_Delete(message); fail(); return;
    }
    if (!strcmp(type->valuestring, "ready")) state = CompanionState::Listening;
    else if (!strcmp(type->valuestring, "clear")) { if (playback_queue) xQueueReset(playback_queue); }
    else if (!strcmp(type->valuestring, "result") || !strcmp(type->valuestring, "error")) fail();
    else if (strcmp(type->valuestring, "connecting")) fail();
    cJSON_Delete(message);
}

void audio_task(void*) {
    auto codec = Board::GetInstance().GetAudioCodec();
    if (!codec || ampve_codec_failed) { fail(); task_active = false; vTaskDelete(nullptr); return; }
    bool input_open = false;
    codec->SetOutputVolume(std::clamp(codec->output_volume(), 0, 80));
    codec->EnableOutput(true);
    const int64_t started = esp_timer_get_time();
    while (!stop_requested && !ampve_codec_failed) {
        if (state == CompanionState::Connecting) {
            if (esp_timer_get_time() - started > 30000000) fail();
            vTaskDelay(pdMS_TO_TICKS(20)); continue;
        }
        if (state != CompanionState::Listening) break;
        const bool should_capture = !muted.load();
        if (should_capture != input_open) {
            codec->EnableInput(should_capture);
            input_open = should_capture && codec->input_enabled() && !ampve_codec_failed;
        }
        PlaybackFrame output{};
        if (playback_queue && xQueueReceive(playback_queue, &output, 0) == pdTRUE) {
            std::vector<int16_t> pcm(output.size / sizeof(int16_t));
            memcpy(pcm.data(), output.data, output.size);
            codec->OutputData(pcm); last_output_at = esp_timer_get_time();
        }
        if (!input_open) { vTaskDelay(pdMS_TO_TICKS(20)); continue; }
        const int channels = codec->input_channels();
        if (channels < 1 || channels > 2 || codec->input_sample_rate() != 24000) { fail(); break; }
        std::vector<int16_t> captured(480 * channels);
        if (!codec->InputData(captured)) { fail(); break; }
        int16_t mono[480];
        for (size_t index = 0; index < 480; ++index) mono[index] = captured[index * channels];
        std::lock_guard<std::mutex> lock(socket_mutex);
        if (!socket || !socket->IsConnected() || !socket->Send(mono, kPcmFrameBytes, true)) { fail(); break; }
    }
    if (input_open) codec->EnableInput(false);
    codec->EnableOutput(false);
    task_active = false;
    if (state != CompanionState::Error) state = CompanionState::Idle;
    vTaskDelete(nullptr);
}

}  // namespace

bool companion_start(const std::string& url, const std::string& ticket, int volume) {
    if (companion_active() || url.size() > 160 || ticket.size() != 43 ||
        url != "wss://ampve.com/audio/device/ws" || ampve_codec_failed) return false;
    if (!playback_queue) playback_queue = xQueueCreate(6, sizeof(PlaybackFrame));
    if (!playback_queue) return false;
    xQueueReset(playback_queue); stop_requested = false; muted = false;
    state = CompanionState::Connecting;
    auto candidate = Board::GetInstance().GetNetwork()->CreateWebSocket(2);
    if (!candidate) { fail(); return false; }
    candidate->SetReceiveBufferSize(4096);
    candidate->OnData(receive);
    candidate->OnDisconnected([] { if (!stop_requested) fail(); });
    candidate->OnError([](const NetworkError&) { fail(); });
    candidate->OnConnected([ticket] {
        cJSON* payload = cJSON_CreateObject(); cJSON_AddStringToObject(payload, "ticket", ticket.c_str());
        char* raw = cJSON_PrintUnformatted(payload); cJSON_Delete(payload);
        bool sent = raw && socket && socket->Send(raw); cJSON_free(raw);
        if (!sent) fail();
    });
    {
        std::lock_guard<std::mutex> lock(socket_mutex); socket = std::move(candidate);
        if (!socket->Connect(url.c_str())) { socket.reset(); fail(); return false; }
    }
    auto codec = Board::GetInstance().GetAudioCodec();
    if (!codec || ampve_codec_failed) { fail(); socket.reset(); return false; }
    codec->SetOutputVolume(std::clamp(volume, 0, 80));
    task_active = true;
    if (xTaskCreate(audio_task, "ampve_companion", 12288, nullptr, 7, nullptr) != pdPASS) {
        task_active = false; socket.reset(); fail(); return false;
    }
    return true;
}

void companion_stop() {
    stop_requested = true; muted = true;
    std::lock_guard<std::mutex> lock(socket_mutex);
    if (socket) socket->Close();
}

void companion_poll() {
    if (!task_active && socket) {
        std::lock_guard<std::mutex> lock(socket_mutex); socket.reset();
    }
}

void companion_toggle_mute() {
    if (companion_active()) muted = !muted.load();
    else muted = true;
}
void companion_mute() { muted = true; }

bool companion_active() {
    auto value = state.load();
    return task_active || value == CompanionState::Connecting || value == CompanionState::Listening;
}
bool companion_muted() { return muted; }
CompanionState companion_state() { return state; }
const char* companion_status() {
    if (state == CompanionState::Connecting) return "Connecting securely…";
    if (state == CompanionState::Error) return "Session ended. Tap Start to try again.";
    if (state == CompanionState::Listening) {
        if (muted) return "Microphone muted. Companion can finish speaking.";
        if (esp_timer_get_time() - last_output_at.load() < 350000) return "Companion is speaking.";
        return "Listening. Tap mute or stop whenever you like.";
    }
    return "Microphone off. Ready when you are.";
}

}  // namespace ampve
