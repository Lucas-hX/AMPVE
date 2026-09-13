"""Apply bounded, non-aborting audio diagnostics to the pinned BoxAudioCodec."""
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
                     '    // AMPVE diagnostics never enable microphone RX DMA.')
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
    start = source.index('void BoxAudioCodec::EnableInput(bool enable) {')
    end = source.index('\nvoid BoxAudioCodec::EnableOutput', start)
    source = source[:start] + '''void BoxAudioCodec::EnableInput(bool enable) {
    // Capture is outside the native management/diagnostic milestone.
    if (enable) ESP_LOGW(TAG, "Microphone capture is unavailable in this shell");
}
''' + source[end:]
    for signature in ['void BoxAudioCodec::SetOutputVolume(int volume) {', 'void BoxAudioCodec::EnableOutput(bool enable) {']:
        source = replace(source, signature, signature + '\n    if (ampve_codec_failed) return;')
    start = source.index('int BoxAudioCodec::Read(int16_t* dest, int samples) {')
    source = source[:start] + '''int BoxAudioCodec::Read(int16_t*, int) { return 0; }

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
        if target.read_text() not in [original, previous, updated]:
            raise ValueError('Refusing to overwrite unrelated audio changes: ' + path)
        if target.read_text() != updated:
            target.write_text(updated)
