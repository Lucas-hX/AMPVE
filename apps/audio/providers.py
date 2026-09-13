"""Pinned Pipecat 1.10.0 provider hooks; no provider payload logging."""
import asyncio
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime import events
from workspace.provider_config import PROVIDERS

INSTRUCTIONS = ('You are AMPVE Companion, a friendly and helpful voice companion. '
                'Keep spoken answers concise and respond in the language the person uses. '
                'You are being tested in a browser; do not claim to control physical devices.')


class ObservableOpenAI(OpenAIRealtimeLLMService):
    # These two hooks are intentionally isolated and pinned: the public service
    # interface does not expose a session-configuration-accepted event.
    async def _handle_evt_session_updated(self, event):
        await super()._handle_evt_session_updated(event)
        self.ampve_ready.set()


class ObservableGemini(GeminiLiveLLMService):
    async def _handle_session_ready(self, session):
        await super()._handle_session_ready(session)
        self.ampve_ready.set()


def make_provider(provider, api_key, ready):
    preset = PROVIDERS[provider]
    if provider == 'openai':
        service = ObservableOpenAI(api_key=api_key, settings=OpenAIRealtimeLLMService.Settings(
            model=preset['model'], system_instruction=INSTRUCTIONS,
            session_properties=events.SessionProperties(output_modalities=['audio'], max_output_tokens=512,
                audio=events.AudioConfiguration(
                    input=events.AudioInput(turn_detection=events.TurnDetection()),
                    output=events.AudioOutput(voice=preset['voice'])))))
    else:
        service = ObservableGemini(api_key=api_key, inference_on_context_initialization=False,
            settings=GeminiLiveLLMService.Settings(model=preset['model'], voice=preset['voice'],
                system_instruction=INSTRUCTIONS))
    service.ampve_ready = ready
    return service


def error_code(error):
    # Never send or log the exception/message: providers may echo request data.
    value = str(error).lower()
    if any(word in value for word in ['429', 'quota', 'resource_exhausted', 'rate_limit']):
        return 'quota'
    if any(word in value for word in ['401', '403', 'api key', 'api_key', 'unauthorized', 'permission_denied']):
        return 'auth'
    if any(word in value for word in ['model_not_found', '404', 'not found', 'not supported']):
        return 'model'
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return 'timeout'
    return 'provider'
