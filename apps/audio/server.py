"""Private-instance audio gateway. One worker; two concurrent sessions maximum."""
import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from loguru import logger
logger.disable('pipecat')
for name in ('httpx', 'httpcore', 'google_genai', 'openai'):
    logging.getLogger(name).setLevel(logging.CRITICAL)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from asgiref.sync import sync_to_async
from django.utils import timezone
from workspace.audio_auth import consume_grant, still_authorized, finish_session, record_check
from workspace.credentials import decrypt_key
from workspace.models import AudioSession
from workspace.provider_config import RESULTS
from pipecat.frames.frames import LLMContextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, PipelineParams
from pipecat.workers.runner import WorkerRunner
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
from providers import make_provider, error_code
from browser_transport import BrowserPCMSerializer

ALLOWED_ORIGINS = {'https://ampve.com', 'https://www.ampve.com'}
active_users = set()
# Bound pre-authentication connections separately from expensive provider sessions.
handshakes = 0


@asynccontextmanager
async def lifespan(app):
    await sync_to_async(lambda: AudioSession.objects.filter(ended_at=None).update(
        status='ended', result_code='restarted', ended_at=timezone.now()))()
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


async def send(ws, kind, **payload):
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_json({'type': kind, **payload})


async def run_provider(ws, grant, connection, session):
    ready, failed, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
    failure = 'provider'
    api_key = await sync_to_async(decrypt_key)(connection)
    llm = make_provider(connection.provider, api_key, ready)
    del api_key
    if grant.mode == 'voice':
        transport = FastAPIWebsocketTransport(ws, FastAPIWebsocketParams(
            serializer=BrowserPCMSerializer(), audio_in_enabled=True, audio_out_enabled=True,
            audio_in_sample_rate=24000, audio_out_sample_rate=24000, audio_out_10ms_chunks=2, audio_out_auto_silence=False,
            add_wav_header=False, allowed_origins=list(ALLOWED_ORIGINS)))
        context = LLMContext([])
        aggregators = LLMContextAggregatorPair(context, realtime_service_mode=True)
        processors = [transport.input(), aggregators.user(), llm, transport.output(), aggregators.assistant()]
    else:
        processors = [llm]
    task = PipelineWorker(Pipeline(processors), params=PipelineParams(
        audio_in_sample_rate=24000, audio_out_sample_rate=24000),
        enable_rtvi=False, enable_turn_tracking=False, enable_tracing=False,
        idle_timeout_secs=None, cancel_timeout_secs=3)

    @task.event_handler('on_pipeline_error')
    async def pipeline_error(task, frame):
        nonlocal failure
        failure = error_code(frame.exception or frame.error)
        failed.set()

    if grant.mode == 'voice':
        @transport.event_handler('on_client_connected')
        async def client_connected(transport, client):
            await task.queue_frames([LLMContextFrame(context)])

        @transport.event_handler('on_client_disconnected')
        async def client_disconnected(transport, client):
            disconnected.set()

    async def check_disconnect():
        # Check mode has no Pipecat transport reading from the browser.
        try:
            while True:
                message = await ws.receive()
                if message['type'] == 'websocket.disconnect':
                    break
                # A check must never accept audio or further application messages.
                break
        finally:
            disconnected.set()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(task)
    running = asyncio.create_task(runner.run())
    receiver = asyncio.create_task(check_disconnect()) if grant.mode == 'check' else None
    start = asyncio.get_running_loop().time()
    announced = False
    code = 'disconnected'
    try:
        while True:
            if not await sync_to_async(still_authorized)(grant, connection):
                code = 'revoked'; break
            if failed.is_set():
                code = failure; break
            if disconnected.is_set():
                code = 'disconnected'; break
            if running.done():
                code = 'provider'; break
            elapsed = asyncio.get_running_loop().time() - start
            if not ready.is_set() and elapsed > 20:
                code = 'timeout'; break
            if ready.is_set() and not announced:
                announced = True
                if grant.mode == 'check':
                    code = 'accepted'; break
                await sync_to_async(lambda: AudioSession.objects.filter(pk=session.pk).update(status='active'))()
                await send(ws, 'ready', sample_rate=24000, max_seconds=300)
            if elapsed > 300:
                code = 'limit'; break
            await asyncio.sleep(0.5)
    finally:
        if grant.mode == 'voice':
            with contextlib.suppress(Exception):
                await send(ws, 'result', code=code, message=RESULTS[code])
        if receiver:
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receiver
        if not running.done():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(task.cancel(), timeout=5)
        # cancel() queues a frame; allow normal transport cleanup before cancelling the runner.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(asyncio.shield(running), timeout=8)
        if not running.done():
            running.cancel()
    return code


@app.websocket('/audio/ws')
async def audio(ws: WebSocket):
    global handshakes
    if ws.headers.get('origin') not in ALLOWED_ORIGINS or handshakes >= 8:
        await ws.close(code=1008)
        return
    handshakes += 1
    claimed = None
    try:
        await ws.accept()
        raw = await asyncio.wait_for(ws.receive_text(), timeout=5)
        if len(raw) > 256:
            raise ValueError('Invalid grant message')
        import json
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {'ticket'}:
            raise ValueError('Invalid grant message')
        claimed = await sync_to_async(consume_grant)(payload['ticket'])
    except Exception:
        pass
    finally:
        handshakes -= 1
    if not claimed:
        with contextlib.suppress(Exception):
            await send(ws, 'error', message='This audio permission expired or is invalid. Start again.')
            await ws.close(code=1008)
        return
    grant, connection, session = claimed
    if session.owner_id in active_users or len(active_users) >= 2:
        await sync_to_async(finish_session)(session.pk, 'busy')
        await send(ws, 'error', message=RESULTS['busy'])
        await ws.close(code=1013)
        return
    active_users.add(session.owner_id)
    code = 'provider'
    try:
        await send(ws, 'connecting', message='Connecting to your provider…')
        code = await run_provider(ws, grant, connection, session)
    except WebSocketDisconnect:
        code = 'disconnected'
    except Exception as exc:
        code = error_code(exc)
    finally:
        active_users.discard(session.owner_id)
        if grant.mode == 'check' and code not in ('revoked', 'disconnected', 'busy'):
            await sync_to_async(record_check)(connection.pk, grant.revision, code)
        await sync_to_async(finish_session)(session.pk, code)
        with contextlib.suppress(Exception):
            await send(ws, 'result', code=code, message=RESULTS[code])
            await ws.close(code=1000)
