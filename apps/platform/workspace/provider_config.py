from django.conf import settings

PROVIDERS = {
    'gemini': {
        'name': 'Gemini Live',
        'model': settings.CONFIG.get('gemini_live_model', 'gemini-2.5-flash-native-audio-preview-12-2025'),
        'voice': 'Charon',
    },
    'openai': {
        'name': 'OpenAI Realtime',
        'model': settings.CONFIG.get('openai_realtime_model', 'gpt-realtime'),
        'voice': 'alloy',
    },
}
RESULTS = {
    'accepted': 'The provider accepted a realtime session. A voice conversation still needs testing.',
    'auth': 'The provider rejected this API key. Check its value and permissions.',
    'quota': 'The provider reported a quota or billing limit. Check your API account.',
    'model': 'This realtime model is unavailable for your account. Check model access or contact the administrator.',
    'timeout': 'The provider did not respond in time. Please try again.',
    'provider': 'The provider could not start this session. Check your API account and try again.',
    'revoked': 'This session ended because the connection or account access changed.',
    'limit': 'The five-minute preview limit was reached.',
    'stopped': 'Session stopped.',
    'disconnected': 'The browser disconnected.',
    'restarted': 'The audio service restarted. Start a new session when ready.',
    'busy': 'An audio test is already running. Stop it before starting another.',
    'audio': 'Audio could not be processed. Please stop and try again.',
}
