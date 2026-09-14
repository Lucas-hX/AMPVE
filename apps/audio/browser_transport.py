"""Development browser PCM transport, separate from the future XiaoZhi Opus adapter."""
import json
import time
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, InterruptionFrame


class BrowserPCMSerializer(FrameSerializer):
    def __init__(self):
        super().__init__()
        self.window = time.monotonic()
        self.received = 0

    async def serialize(self, frame):
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, InterruptionFrame):
            return json.dumps({'type': 'clear'})
        # Transcripts, provider payloads and framework metadata never leave this serializer.
        return None

    async def deserialize(self, data):
        if not isinstance(data, bytes) or not data or len(data) > 4096 or len(data) % 2:
            raise ValueError('Invalid browser audio frame')
        now = time.monotonic()
        if now - self.window >= 1:
            self.window, self.received = now, 0
        self.received += len(data)
        if self.received > 96000:
            raise ValueError('Browser audio rate exceeded')
        return InputAudioRawFrame(audio=data, sample_rate=24000, num_channels=1)


class DevicePCMSerializer(BrowserPCMSerializer):
    """Fixed 20 ms, 24 kHz mono PCM contract for the first native Companion."""
    def __init__(self):
        super().__init__()
        self.last_barge_in = 0.0

    async def deserialize(self, data):
        if isinstance(data, str):
            if len(data) > 64:
                raise ValueError('Invalid device control frame')
            try:
                control = json.loads(data)
            except json.JSONDecodeError as exc:
                raise ValueError('Invalid device control frame') from exc
            if control != {'type': 'barge_in'}:
                raise ValueError('Invalid device control frame')
            now = time.monotonic()
            if now - self.last_barge_in < 0.25:
                raise ValueError('Device control rate exceeded')
            self.last_barge_in = now
            return InterruptionFrame()
        if not isinstance(data, bytes) or len(data) != 960:
            raise ValueError('Invalid device audio frame')
        return await super().deserialize(data)
