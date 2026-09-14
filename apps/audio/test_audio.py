"""Fixture-only gateway tests: provider calls and persistence are replaced in-process."""
import asyncio
import contextlib
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

os.environ['AMPVE_TESTING'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parent))
import server
from fastapi.testclient import TestClient
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, InterruptionFrame
from browser_transport import BrowserPCMSerializer, DevicePCMSerializer
from providers import error_code, make_provider


class EchoFixture(FrameProcessor):
    def __init__(self, ready):
        super().__init__(); self.ready = ready

    async def setup(self, setup):
        await super().setup(setup); self.ready.set()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self.push_frame(OutputAudioRawFrame(audio=frame.audio, sample_rate=24000, num_channels=1))
        else:
            await self.push_frame(frame, direction)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        server.active_users.clear()
        self.client = TestClient(server.app)
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.connection = SimpleNamespace(pk='fixture-connection', provider='openai')
        self.session = SimpleNamespace(pk='fixture-session', owner_id=42)
        self.grant = SimpleNamespace(mode='check', revision=1)
        self.consume = self.stack.enter_context(patch.object(server, 'consume_grant', return_value=(self.grant,self.connection,self.session)))
        self.authorized = self.stack.enter_context(patch.object(server,'still_authorized',return_value=True))
        self.stack.enter_context(patch.object(server,'decrypt_key',return_value='TEST-FIXTURE-NOT-A-PROVIDER-KEY'))
        self.finish = self.stack.enter_context(patch.object(server,'finish_session'))
        self.record = self.stack.enter_context(patch.object(server,'record_check'))
        self.stack.enter_context(patch.object(server,'AudioSession'))
        self.provider = self.stack.enter_context(patch.object(server,'make_provider',side_effect=lambda provider,key,ready,mode:EchoFixture(ready)))

    def connect(self):
        return self.client.websocket_connect('/audio/ws',headers={'origin':'https://ampve.com'})

    def connect_device(self):
        return self.client.websocket_connect('/audio/device/ws')

    def test_check_waits_for_pipeline_ready_and_records_result(self):
        with self.connect() as ws:
            ws.send_json({'ticket':'fixture'})
            self.assertEqual(ws.receive_json()['type'],'connecting')
            result=ws.receive_json()
            self.assertEqual(result['code'],'accepted')
        self.record.assert_called_once_with(self.connection.pk,1,'accepted')
        self.assertFalse(server.active_users)

    def test_voice_uses_real_pipecat_pipeline_with_echo_fixture(self):
        self.grant.mode='voice'
        with self.connect() as ws:
            ws.send_json({'ticket':'fixture'})
            self.assertEqual(ws.receive_json()['type'],'connecting')
            self.assertEqual(ws.receive_json()['type'],'ready')
            samples=b'\x01\x00'*480
            ws.send_bytes(samples)
            received=ws.receive_bytes()
            self.assertEqual(received,samples)
            self.authorized.return_value=False
            self.assertEqual(ws.receive_json()['code'],'revoked')
        self.record.assert_not_called()

    def test_voice_disconnect_releases_user_slot(self):
        self.grant.mode = 'voice'
        with self.connect() as ws:
            ws.send_json({'ticket': 'fixture'})
            ws.receive_json()
            self.assertEqual(ws.receive_json()['type'], 'ready')
            ws.close()
            import time
            deadline = time.monotonic() + 4
            while server.active_users and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(server.active_users)
        self.record.assert_not_called()

    def test_device_audio_uses_no_browser_origin_and_fixed_pcm_frames(self):
        self.grant.mode = 'device'
        with self.connect_device() as ws:
            ws.send_json({'ticket': 'fixture'})
            self.assertEqual(ws.receive_json()['type'], 'connecting')
            self.assertEqual(ws.receive_json()['type'], 'ready')
            samples = b'\x02\x00' * 480
            ws.send_bytes(samples)
            self.assertEqual(ws.receive_bytes(), samples)
            self.authorized.return_value = False
            self.assertEqual(ws.receive_json()['code'], 'revoked')
        self.consume.assert_called_with('fixture', 'device')

    def test_device_audio_rejects_browser_origin_and_browser_route_rejects_device_grant(self):
        self.grant.mode = 'device'
        with self.assertRaises(Exception):
            with self.client.websocket_connect('/audio/device/ws', headers={'origin': 'https://ampve.com'}):
                pass
        self.consume.assert_not_called()
        self.consume.return_value = None
        with self.connect() as ws:
            ws.send_json({'ticket': 'device-fixture'})
            self.assertEqual(ws.receive_json()['type'], 'error')
        self.consume.assert_called_with('device-fixture', 'browser')

    def test_revocation_closes_without_provider_success(self):
        self.authorized.return_value=False
        with self.connect() as ws:
            ws.send_json({'ticket':'fixture'})
            ws.receive_json()
            self.assertEqual(ws.receive_json()['code'],'revoked')
        self.record.assert_not_called()

    def test_wrong_origin_never_consumes_grant(self):
        with self.assertRaises(Exception):
            with self.client.websocket_connect('/audio/ws',headers={'origin':'https://evil.example'}):pass
        self.consume.assert_not_called()

    def test_invalid_grant_never_opens_provider(self):
        self.consume.return_value=None
        with self.connect() as ws:
            ws.send_json({'ticket':'bad'})
            self.assertEqual(ws.receive_json()['type'],'error')
        self.provider.assert_not_called()

    def test_same_user_concurrency_is_rejected(self):
        server.active_users.add(42)
        with self.connect() as ws:
            ws.send_json({'ticket':'fixture'})
            self.assertEqual(ws.receive_json()['type'],'error')
        self.provider.assert_not_called()
        self.finish.assert_called_once_with(self.session.pk,'busy')


class SerializerTests(unittest.IsolatedAsyncioTestCase):
    async def test_format_validation_and_interruption(self):
        serializer=BrowserPCMSerializer()
        for invalid in ['{"api_key":"fixture"}',b'\x00',b'\x00'*5000,b'']:
            with self.assertRaises(ValueError):await serializer.deserialize(invalid)
        frame=await serializer.deserialize(b'\x01\x00'*480)
        self.assertEqual(frame.sample_rate,24000)
        self.assertEqual(json.loads(await serializer.serialize(InterruptionFrame()))['type'],'clear')

    async def test_input_rate_limit(self):
        serializer=BrowserPCMSerializer()
        with self.assertRaises(ValueError):
                for _ in range(30):await serializer.deserialize(b'\x00'*4096)

    async def test_device_serializer_requires_one_twenty_ms_frame(self):
        serializer = DevicePCMSerializer()
        frame = await serializer.deserialize(b'\x00' * 960)
        self.assertEqual((len(frame.audio), frame.sample_rate, frame.num_channels), (960, 24000, 1))
        for invalid in [b'', b'\x00' * 958, b'\x00' * 962, 'control']:
            with self.assertRaises(ValueError):
                await serializer.deserialize(invalid)

    async def test_provider_constructors_and_sanitized_errors(self):
        for provider in ['openai','gemini']:
            event=asyncio.Event();service=make_provider(provider,'TEST-FIXTURE-ONLY',event)
            self.assertIs(service.ampve_ready,event)
        self.assertEqual(error_code(Exception('401 secret TEST-FIXTURE-ONLY')),'auth')
        self.assertEqual(error_code(Exception('429 insufficient_quota')),'quota')
        self.assertEqual(error_code(TimeoutError()),'timeout')
