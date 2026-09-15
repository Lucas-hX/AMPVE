#include "ampve/companion.h"

#include "ampve/companion_audio_gate.h"
#include "ampve/runtime.h"
#include "audio_codec.h"
#if CONFIG_USE_DEVICE_AEC
#include "audio/engines/afe_audio_engine.h"
#endif
#include "board.h"
#include "network_interface.h"
#include "web_socket.h"
#include "cJSON.h"
#if CONFIG_USE_DEVICE_AEC
#include "esp_ae_rate_cvt.h"
#include "esp_audio_types.h"
#include "esp_log.h"
#endif
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include <algorithm>
#include <atomic>
#include <cstring>
#include <deque>
#include <memory>
#include <mutex>
#include <vector>

namespace ampve {
namespace {

constexpr size_t kPcmFrameBytes = 960;  // 20 ms, 24 kHz, signed 16-bit mono.
constexpr size_t kMaximumServerFrameBytes = 1920;
constexpr size_t kPcmFrameSamples = kPcmFrameBytes / sizeof(int16_t);
constexpr size_t kPreRollFrames = 15;  // 300 ms, held only in volatile memory.
constexpr size_t kMaximumPendingUplinkFrames = 24;  // 480 ms hard backlog limit.
constexpr int64_t kPlaybackTailUs = 250000;
constexpr char kBargeInMessage[] = "{\"type\":\"barge_in\"}";
constexpr char kLogTag[] = "AMPVECompanion";
struct PlaybackFrame { size_t size; uint8_t data[kMaximumServerFrameBytes]; };
struct UplinkFrame {
    bool barge_in = false;
    std::vector<int16_t> audio;
};

std::atomic<CompanionState> state{CompanionState::Idle};
std::atomic<bool> muted{true}, stop_requested{false}, task_active{false};
std::atomic<int64_t> last_output_at{0};
std::atomic<bool> response_playback_active{false}, local_speech{false};
std::atomic<uint8_t> output_level{0};
std::unique_ptr<WebSocket> socket;
std::mutex socket_mutex;
QueueHandle_t playback_queue = nullptr;

#if CONFIG_USE_DEVICE_AEC
std::unique_ptr<AfeAudioEngine> audio_processor;
esp_ae_rate_cvt_handle_t input_rate_converter = nullptr;
esp_ae_rate_cvt_handle_t output_rate_converter = nullptr;
std::mutex input_converter_mutex, output_converter_mutex;
std::vector<int16_t> uplink_buffer;
#endif

CompanionAudioGate uplink_gate;
std::deque<std::vector<int16_t>> pre_roll;
std::deque<UplinkFrame> pending_uplink;
std::mutex uplink_mutex;

#if CONFIG_USE_DEVICE_AEC
std::deque<int64_t> capture_times;
std::mutex latency_mutex;
uint64_t latency_total_us = 0;
uint32_t latency_samples = 0;
int64_t latency_max_us = 0;
bool latency_reported = false;
#endif

void fail() {
    output_level = 0; last_output_at = 0;
    state = CompanionState::Error;
    stop_requested = true;
}

uint8_t level(const int16_t* samples, size_t count) {
    if (!samples || !count) return 0;
    uint64_t sum = 0;
    for (size_t index = 0; index < count; ++index) {
        const int32_t sample = samples[index];
        sum += sample < 0 ? -sample : sample;
    }
    const uint64_t average = sum / count;
    return static_cast<uint8_t>(std::min<uint64_t>(255, average * 255 / 4096));
}

bool send_socket(const void* data, size_t length, bool binary) {
    std::lock_guard<std::mutex> lock(socket_mutex);
    return socket && socket->IsConnected() && socket->Send(data, length, binary);
}

bool send_control(const char* data) {
    std::lock_guard<std::mutex> lock(socket_mutex);
    return socket && socket->IsConnected() && socket->Send(data);
}

#if CONFIG_USE_DEVICE_AEC
void record_processed_latency() {
    const int64_t now = esp_timer_get_time();
    std::lock_guard<std::mutex> lock(latency_mutex);
    if (capture_times.empty()) return;
    const int64_t latency = now - capture_times.front();
    capture_times.pop_front();
    if (latency < 0 || latency > 1000000) return;
    latency_total_us += latency;
    latency_max_us = std::max(latency_max_us, latency);
    ++latency_samples;
    if (!latency_reported && latency_samples >= 250) {
        latency_reported = true;
        ESP_LOGW(kLogTag, "AEC calibration: average pipeline %llu ms, maximum %lld ms over %lu frames",
                 static_cast<unsigned long long>(latency_total_us / latency_samples / 1000),
                 static_cast<long long>(latency_max_us / 1000),
                 static_cast<unsigned long>(latency_samples));
    }
}

bool convert_rate(esp_ae_rate_cvt_handle_t converter, const std::vector<int16_t>& input,
                  size_t channels, std::vector<int16_t>& output) {
    if (!converter || channels == 0 || input.empty() || input.size() % channels) return false;
    uint32_t output_samples = 0;
    const uint32_t input_samples = input.size() / channels;
    if (esp_ae_rate_cvt_get_max_out_sample_num(converter, input_samples, &output_samples) !=
            ESP_AE_ERR_OK || output_samples == 0) return false;
    output.resize(output_samples * channels);
    uint32_t actual_output = output_samples;
    if (esp_ae_rate_cvt_process(converter, reinterpret_cast<esp_ae_sample_t>(
            const_cast<int16_t*>(input.data())), input_samples,
            reinterpret_cast<esp_ae_sample_t>(output.data()), &actual_output) != ESP_AE_ERR_OK) {
        output.clear(); return false;
    }
    output.resize(actual_output * channels);
    return true;
}
#endif

void processed_uplink_frame(std::vector<int16_t>&& frame) {
    if (frame.size() != kPcmFrameSamples || muted.load() || stop_requested.load() ||
        state.load() != CompanionState::Listening) return;

    {
        std::lock_guard<std::mutex> lock(uplink_mutex);
        const bool playback = response_playback_active.load();
        const auto decision = uplink_gate.Observe(playback, local_speech.load());
        if (playback && decision != CompanionAudioGate::Decision::Forward) {
            pre_roll.push_back(std::move(frame));
            while (pre_roll.size() > kPreRollFrames) pre_roll.pop_front();
        }
        if (decision == CompanionAudioGate::Decision::Hold) return;
        if (decision == CompanionAudioGate::Decision::InterruptAndForward) {
            if (pending_uplink.size() + pre_roll.size() + 1 > kMaximumPendingUplinkFrames) {
                fail(); return;
            }
            pending_uplink.push_back({.barge_in = true});
            while (!pre_roll.empty()) {
                pending_uplink.push_back({.audio = std::move(pre_roll.front())});
                pre_roll.pop_front();
            }
            if (playback_queue) xQueueReset(playback_queue);
            response_playback_active = false;
        } else {
            pre_roll.clear();
            if (pending_uplink.size() >= kMaximumPendingUplinkFrames) { fail(); return; }
            pending_uplink.push_back({.audio = std::move(frame)});
        }
    }
}

void drain_pending_uplink() {
    std::deque<UplinkFrame> frames;
    {
        std::lock_guard<std::mutex> lock(uplink_mutex);
        frames.swap(pending_uplink);
    }
    for (const auto& frame : frames) {
        const bool sent = frame.barge_in
            ? send_control(kBargeInMessage)
            : send_socket(frame.audio.data(), kPcmFrameBytes, true);
        if (!sent) { fail(); return; }
    }
}

#if CONFIG_USE_DEVICE_AEC
void processed_audio_16k(std::vector<int16_t>&& data) {
    record_processed_latency();
    std::vector<int16_t> converted;
    std::vector<std::vector<int16_t>> complete_frames;
    {
        std::lock_guard<std::mutex> lock(output_converter_mutex);
        if (!convert_rate(output_rate_converter, data, 1, converted)) { fail(); return; }
        uplink_buffer.insert(uplink_buffer.end(), converted.begin(), converted.end());
        while (uplink_buffer.size() >= kPcmFrameSamples) {
            complete_frames.emplace_back(uplink_buffer.begin(),
                                         uplink_buffer.begin() + kPcmFrameSamples);
            uplink_buffer.erase(uplink_buffer.begin(), uplink_buffer.begin() + kPcmFrameSamples);
        }
    }
    // Queue only. WebSocket writes run in audio_task so the AFE fetch task never
    // waits on network I/O.
    for (auto& frame : complete_frames) processed_uplink_frame(std::move(frame));
}

bool open_rate_converter(uint32_t source_rate, uint32_t destination_rate, uint8_t channels,
                         esp_ae_rate_cvt_handle_t* converter) {
    esp_ae_rate_cvt_cfg_t config = {
        .src_rate = source_rate,
        .dest_rate = destination_rate,
        .channel = channels,
        .bits_per_sample = ESP_AUDIO_BIT16,
        .complexity = 1,
        .perf_type = ESP_AE_RATE_CVT_PERF_TYPE_SPEED,
    };
    return esp_ae_rate_cvt_open(&config, converter) == ESP_AE_ERR_OK && *converter;
}

bool initialize_audio_processor(AudioCodec* codec) {
    if (audio_processor) return true;
    if (!codec || !codec->input_reference() || codec->input_channels() != 2 ||
        codec->input_sample_rate() != 24000) {
        ESP_LOGW(kLogTag, "AEC unavailable: the codec must provide 24 kHz microphone/reference input");
        return false;
    }
    esp_ae_rate_cvt_handle_t new_input = nullptr, new_output = nullptr;
    if (!open_rate_converter(24000, 16000, 2, &new_input) ||
        !open_rate_converter(16000, 24000, 1, &new_output)) {
        if (new_input) esp_ae_rate_cvt_close(new_input);
        if (new_output) esp_ae_rate_cvt_close(new_output);
        ESP_LOGW(kLogTag, "AEC unavailable: sample-rate converter allocation failed");
        return false;
    }
    auto candidate = std::make_unique<AfeAudioEngine>();
    const int64_t started = esp_timer_get_time();
    if (!candidate->Initialize(codec, 20, nullptr)) {
        esp_ae_rate_cvt_close(new_input); esp_ae_rate_cvt_close(new_output);
        ESP_LOGW(kLogTag, "AEC unavailable: ESP-SR AFE initialization failed");
        return false;
    }
    candidate->OnOutput(processed_audio_16k);
    candidate->OnVadStateChange([](bool speaking) { local_speech = speaking; });
    input_rate_converter = new_input;
    output_rate_converter = new_output;
    audio_processor = std::move(candidate);
    ESP_LOGW(kLogTag, "AEC initialized in %lld ms", static_cast<long long>(
        (esp_timer_get_time() - started) / 1000));
    return true;
}

void reset_audio_processor_session() {
    local_speech = false;
    {
        std::lock_guard<std::mutex> lock(input_converter_mutex);
        if (input_rate_converter) esp_ae_rate_cvt_reset(input_rate_converter);
    }
    {
        std::lock_guard<std::mutex> lock(output_converter_mutex);
        if (output_rate_converter) esp_ae_rate_cvt_reset(output_rate_converter);
        uplink_buffer.clear();
    }
    {
        std::lock_guard<std::mutex> lock(latency_mutex);
        capture_times.clear(); latency_total_us = 0; latency_samples = 0;
        latency_max_us = 0; latency_reported = false;
    }
    if (audio_processor) {
        audio_processor->EnableDeviceAec(true);
        audio_processor->EnableVoiceProcessing(true);
    }
}

bool feed_audio_processor(std::vector<int16_t>&& captured) {
    if (!audio_processor) return false;
    std::vector<int16_t> resampled;
    {
        std::lock_guard<std::mutex> lock(input_converter_mutex);
        if (!convert_rate(input_rate_converter, captured, 2, resampled)) return false;
    }
    {
        std::lock_guard<std::mutex> lock(latency_mutex);
        capture_times.push_back(esp_timer_get_time());
        while (capture_times.size() > 64) capture_times.pop_front();
    }
    audio_processor->Feed(std::move(resampled));
    return true;
}

void stop_audio_processor() {
    local_speech = false;
    if (audio_processor) audio_processor->EnableVoiceProcessing(false);
}
#else
bool initialize_audio_processor(AudioCodec*) { return false; }
void reset_audio_processor_session() {}
bool feed_audio_processor(std::vector<int16_t>&&) { return false; }
void stop_audio_processor() { local_speech = false; }
#endif

void receive(const char* data, size_t length, bool binary) {
    if (binary) {
        if (!data || !length || length > kMaximumServerFrameBytes || length % sizeof(int16_t)) {
            fail(); return;
        }
        PlaybackFrame frame{}; frame.size = length;
        memcpy(frame.data, data, length);
        if (!playback_queue || xQueueSend(playback_queue, &frame, 0) != pdTRUE) {
            fail(); return;
        }
        if (!response_playback_active.exchange(true)) {
            std::lock_guard<std::mutex> lock(uplink_mutex);
            uplink_gate.PlaybackStarted(); pre_roll.clear();
        }
        return;
    }
    if (!data || !length || length > 512) { fail(); return; }
    auto message = cJSON_ParseWithLength(data, length);
    auto type = message ? cJSON_GetObjectItemCaseSensitive(message, "type") : nullptr;
    if (!cJSON_IsString(type) || !type->valuestring) {
        cJSON_Delete(message); fail(); return;
    }
    if (!strcmp(type->valuestring, "ready")) state = CompanionState::Listening;
    else if (!strcmp(type->valuestring, "clear")) {
        if (playback_queue) xQueueReset(playback_queue);
        response_playback_active = false;
        std::lock_guard<std::mutex> lock(uplink_mutex);
        uplink_gate.Reset(); pre_roll.clear();
    }
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
    const bool processor_ready = initialize_audio_processor(codec);
    if (processor_ready) reset_audio_processor_session();
    const int64_t started = esp_timer_get_time();
    while (!stop_requested && !ampve_codec_failed) {
        if (state == CompanionState::Connecting) {
            if (esp_timer_get_time() - started > 30000000) fail();
            vTaskDelay(pdMS_TO_TICKS(20)); continue;
        }
        if (state != CompanionState::Listening) break;
        drain_pending_uplink();
        if (stop_requested || state != CompanionState::Listening) break;
        const bool should_capture = !muted.load();
        if (should_capture != input_open) {
            codec->EnableInput(should_capture);
            input_open = should_capture && codec->input_enabled() && !ampve_codec_failed;
        }
        PlaybackFrame output{};
        if (playback_queue && xQueueReceive(playback_queue, &output, 0) == pdTRUE) {
            std::vector<int16_t> pcm(output.size / sizeof(int16_t));
            memcpy(pcm.data(), output.data, output.size);
            output_level = level(pcm.data(), pcm.size());
            codec->OutputData(pcm); last_output_at = esp_timer_get_time();
        }
        if (response_playback_active.load() && playback_queue &&
            uxQueueMessagesWaiting(playback_queue) == 0 &&
            esp_timer_get_time() - last_output_at.load() >= kPlaybackTailUs) {
            response_playback_active = false;
        }
        if (!input_open) { vTaskDelay(pdMS_TO_TICKS(20)); continue; }
        const int channels = codec->input_channels();
        if (channels < 1 || channels > 2 || codec->input_sample_rate() != 24000) { fail(); break; }
        std::vector<int16_t> captured(480 * channels);
        if (!codec->InputData(captured)) { fail(); break; }
        if (processor_ready) {
            if (!feed_audio_processor(std::move(captured))) { fail(); break; }
        } else {
            std::vector<int16_t> mono(kPcmFrameSamples);
            for (size_t index = 0; index < kPcmFrameSamples; ++index) {
                mono[index] = captured[index * channels];
            }
            // Safe fallback: uplink remains closed during playback. Touch stop/mute
            // remain available when the board cannot allocate the AEC pipeline.
            processed_uplink_frame(std::move(mono));
        }
        drain_pending_uplink();
    }
    stop_audio_processor();
    if (input_open) codec->EnableInput(false);
    codec->EnableOutput(false);
    output_level = 0; last_output_at = 0;
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
    response_playback_active = false; output_level = 0; last_output_at = 0;
    {
        std::lock_guard<std::mutex> lock(uplink_mutex);
        uplink_gate.Reset(); pre_roll.clear(); pending_uplink.clear();
    }
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
    stop_requested = true; muted = true; response_playback_active = false;
    output_level = 0; last_output_at = 0;
    stop_audio_processor();
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
bool companion_speaking() {
    const int64_t last = last_output_at.load();
    return state == CompanionState::Listening && last > 0 && esp_timer_get_time() - last < 350000;
}
uint8_t companion_output_level() {
    return companion_speaking() ? output_level.load() : 0;
}
const char* companion_status() {
    if (state == CompanionState::Connecting) return "Connecting securely…";
    if (state == CompanionState::Error) return "Session ended. Tap Start to try again.";
    if (state == CompanionState::Listening) {
        if (muted) return "Microphone muted. Companion can finish speaking.";
        if (companion_speaking()) return "Companion is speaking.";
        return "Listening. Tap mute or stop whenever you like.";
    }
    return "Microphone off. Ready when you are.";
}

}  // namespace ampve
