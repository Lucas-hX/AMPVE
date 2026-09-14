"""Apply bounded, non-aborting audio diagnostics to the pinned BoxAudioCodec."""
import hashlib
import subprocess

SOURCE = 'main/audio/codecs/box_audio_codec.cc'
HEADER = 'main/audio/codecs/box_audio_codec.h'


def transform(source, header):
    def replace(text, old, new):
        if text.count(old) != 1:
            raise ValueError('Pinned audio contract changed: ' + old[:70])
        return text.replace(old, new)

    header = replace(header, '    void CreateDuplexChannels(', '    void Release();\n    void Fail();\n    void CreateDuplexChannels(')
    source = replace(source, '#include "box_audio_codec.h"', '#include "box_audio_codec.h"\n#include "ampve/runtime.h"')
    source = replace(source, '#define TAG "BoxAudioCodec"', '''#define TAG "BoxAudioCodec"
// Optional diagnostics must never abort management or retry partially initialized hardware.
#define AMPVE_AUDIO_CHECK(call) do { if ((call) != ESP_OK) { Fail(); return; } } while (0)
#define AMPVE_AUDIO_REQUIRE(value) do { if (!(value)) { Fail(); return; } } while (0)''')
    source = source.replace('ESP_ERROR_CHECK(', 'AMPVE_AUDIO_CHECK(').replace('assert(', 'AMPVE_AUDIO_REQUIRE(')
    source = replace(source, '    CreateDuplexChannels(mclk, bclk, ws, dout, din);',
                     '    CreateDuplexChannels(mclk, bclk, ws, dout, din);\n    if (ampve_codec_failed) return;')
    source = replace(source, '    AMPVE_AUDIO_CHECK(i2s_channel_enable(rx_handle_));',
                     '    // Keep RX disabled until a local Companion action explicitly opens the microphone.')
    start = source.index('BoxAudioCodec::~BoxAudioCodec() {')
    end = source.index('\nvoid BoxAudioCodec::CreateDuplexChannels', start)
    source = source[:start] + '''BoxAudioCodec::~BoxAudioCodec() { Release(); }

void BoxAudioCodec::Fail() {
    ampve_codec_failed = true;
    ESP_LOGW(TAG, "Audio unavailable; local management remains active");
    Release();
}

void BoxAudioCodec::Release() {
    // Closing a partially initialized codec is best effort; never abort on cleanup.
    if (output_dev_) { esp_codec_dev_close(output_dev_); esp_codec_dev_delete(output_dev_); output_dev_ = nullptr; }
    if (input_dev_) { esp_codec_dev_close(input_dev_); esp_codec_dev_delete(input_dev_); input_dev_ = nullptr; }
    if (in_codec_if_) { audio_codec_delete_codec_if(in_codec_if_); in_codec_if_ = nullptr; }
    if (in_ctrl_if_) { audio_codec_delete_ctrl_if(in_ctrl_if_); in_ctrl_if_ = nullptr; }
    if (out_codec_if_) { audio_codec_delete_codec_if(out_codec_if_); out_codec_if_ = nullptr; }
    if (out_ctrl_if_) { audio_codec_delete_ctrl_if(out_ctrl_if_); out_ctrl_if_ = nullptr; }
    if (gpio_if_) { audio_codec_delete_gpio_if(gpio_if_); gpio_if_ = nullptr; }
    if (data_if_) { audio_codec_delete_data_if(data_if_); data_if_ = nullptr; }
    if (tx_handle_) { i2s_channel_disable(tx_handle_); i2s_del_channel(tx_handle_); tx_handle_ = nullptr; }
    if (rx_handle_) { i2s_channel_disable(rx_handle_); i2s_del_channel(rx_handle_); rx_handle_ = nullptr; }
    output_enabled_ = false;
    input_enabled_ = false;
}
''' + source[end:]
    start = source.index('void BoxAudioCodec::SetOutputVolume(int volume) {')
    end = source.index('\nvoid BoxAudioCodec::EnableInput', start)
    source = source[:start] + '''void BoxAudioCodec::SetOutputVolume(int volume) {
    if (ampve_codec_failed) return;
    // Remember volume while closed. Some codec revisions reject volume writes
    // before esp_codec_dev_open(), which previously made the speaker test fail.
    AudioCodec::SetOutputVolume(volume);
    if (output_enabled_) AMPVE_AUDIO_CHECK(esp_codec_dev_set_out_vol(output_dev_, volume));
}
''' + source[end:]
    start = source.index('void BoxAudioCodec::EnableInput(bool enable) {')
    end = source.index('\nvoid BoxAudioCodec::EnableOutput', start)
    source = source[:start] + '''void BoxAudioCodec::EnableInput(bool enable) {
    if (ampve_codec_failed) return;
    std::lock_guard<std::mutex> lock(data_if_mutex_);
    if (enable == input_enabled_) return;
    if (enable) {
        esp_codec_dev_sample_info_t fs = {
            .bits_per_sample = 16,
            .channel = 4,
            .channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0),
            .sample_rate = (uint32_t)input_sample_rate_,
            .mclk_multiple = 0,
        };
        if (input_reference_) fs.channel_mask |= ESP_CODEC_DEV_MAKE_CHANNEL_MASK(1);
        AMPVE_AUDIO_CHECK(i2s_channel_enable(rx_handle_));
        AMPVE_AUDIO_CHECK(esp_codec_dev_open(input_dev_, &fs));
        AMPVE_AUDIO_CHECK(esp_codec_dev_set_in_channel_gain(
            input_dev_, ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0), input_gain_));
        if (input_reference_ && reference_gain_channel_ >= 0) {
            AMPVE_AUDIO_CHECK(esp_codec_dev_set_in_channel_gain(input_dev_,
                ESP_CODEC_DEV_MAKE_CHANNEL_MASK(reference_gain_channel_), reference_gain_));
        }
    } else {
        AMPVE_AUDIO_CHECK(esp_codec_dev_close(input_dev_));
        AMPVE_AUDIO_CHECK(i2s_channel_disable(rx_handle_));
    }
    AudioCodec::EnableInput(enable);
}
''' + source[end:]
    source = replace(source, 'void BoxAudioCodec::EnableOutput(bool enable) {',
                     'void BoxAudioCodec::EnableOutput(bool enable) {\n    if (ampve_codec_failed) return;')
    start = source.index('int BoxAudioCodec::Read(int16_t* dest, int samples) {')
    source = source[:start] + '''int BoxAudioCodec::Read(int16_t* data, int samples) {
    if (ampve_codec_failed || !input_enabled_) return 0;
    if (esp_codec_dev_read(input_dev_, (void*)data, samples * sizeof(int16_t)) != ESP_OK) {
        Fail(); return 0;
    }
    return samples;
}

int BoxAudioCodec::Write(const int16_t* data, int samples) {
    if (ampve_codec_failed || !output_enabled_) return 0;
    if (esp_codec_dev_write(output_dev_, (void*)data, samples * sizeof(int16_t)) != ESP_OK) {
        Fail(); return 0;
    }
    return samples;
}
'''
    return source, header


def prepare(work, pin):
    originals = [subprocess.check_output(['git', '-C', str(work), 'show', pin + ':' + path]).decode()
                 for path in [SOURCE, HEADER]]
    transformed = transform(*originals)
    for path, original, updated in zip([SOURCE, HEADER], originals, transformed):
        target = work/path
        previous = original.replace('    ESP_ERROR_CHECK(i2s_channel_enable(rx_handle_));',
                                    '    // AMPVE shell: leave the RX DMA channel disabled; no microphone capture.')
        current = target.read_text()
        legacy = (path == SOURCE and hashlib.sha256(current.encode()).hexdigest() ==
                  'bb80f2db14705187e08fce97242a553febf03f7cf6a9b5822353471f9f5f3219')
        if current not in [original, previous, updated] and not legacy:
            raise ValueError('Refusing to overwrite unrelated audio changes: ' + path)
        if current != updated:
            target.write_text(updated)
