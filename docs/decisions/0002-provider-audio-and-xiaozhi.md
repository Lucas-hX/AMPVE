# ADR 0002: Encrypted provider connections and the XiaoZhi path

Date: 2026-09-13
Status: Accepted; provider integration is experimental pending live account validation.

## Decision

Lucas reaffirmed XiaoZhi as the only embedded foundation. AMPVE will adapt a small, pinned XiaoZhi fork for Waveshare ESP32-P4-WIFI6-Touch-LCD-7B, retaining upstream audio/display/peripheral work. Do not spend this milestone comparing alternative firmware or building a replacement embedded agent. The exact source commit, ESP-IDF toolchain, chip-revision compatibility and partition layout still need verification before selecting a release.

Django continues to own users, encrypted provider connections, authorization and management. FastAPI/Pipecat now supplies a separate browser audio preview so provider behavior can be checked before coupling it to hardware. This browser client is a development step toward the selected XiaoZhi path, not an alternative device protocol or a completed XiaoZhi adapter.

## Implemented boundaries

- Each connection belongs to one user and selects Gemini Live or OpenAI Realtime. The browser can save, replace and delete keys but cannot retrieve them. Even staff accounts cannot use other users' connection endpoints.
- Cryptography MultiFernet encrypts each key with authenticated connection/user/provider context. Its random encryption key is outside PostgreSQL and Git, separate from the Django secret. A database dump alone cannot decrypt keys; a compromised running VPS can.
- Django authorizes a CSRF-protected, quota-consented action using a random single-use ticket. PostgreSQL stores only its SHA-256 hash, bound to the logged-in session, connection revision and mode, with a 30-second expiry. The browser sends the ticket in the first WSS message, never a URL.
- FastAPI consumes the ticket atomically, verifies the active browser session, and checks authorization every half-second. Replacement/deletion/logout/password changes invalidate access. Device enrollment proofs and revocable device credentials remain separate future work.
- Pipecat 1.10.0 runs provider services and audio processing. A short connection check waits for upstream session configuration acknowledgement; it does not prove a conversation. The experimental voice preview sends mono 24 kHz PCM through Pipecat and plays PCM responses, with local mute/stop and interruption clearing.
- Raw audio, video and transcripts are not persisted by AMPVE. Operational session metadata expires after 30 days, expired grant metadata after one day. Provider retention policies still apply.
- One FastAPI worker, one session per account, two globally, six ticket requests per account per minute, ten saved connections per account, five minutes per voice session. Initial provider readiness has a 20-second timeout. Binary frame sizes, incoming rate and browser output queues are bounded. These are private-instance limits, not distributed admission control or provider spending caps.
- Reuse PostgreSQL, the existing Cloudflare tunnel and systemd. Two isolated Python environments avoid making the platform depend on Pipecat's larger dependency graph. FastAPI reuses Django's models internally; no internal HTTP management API, message broker or new database service is introduced.

## Compatibility and limits

Pinned provider presets: OpenAI `gpt-realtime` / `alloy`; Gemini `gemini-2.5-flash-native-audio-preview-12-2025` / `Charon`. Private configuration can override model IDs. Model availability, account access, quota and latency must be checked with the owner's actual API account. No real provider key was supplied during implementation and no successful live provider conversation is claimed.

Pipecat readiness hooks are isolated in `apps/audio/providers.py` because session configuration acknowledgement is not exposed by a common public service event. Upgrades require reviewing these hooks and repeating actual connection/conversation checks. Fixture tests instantiate both current SDK-backed services and exercise the real Pipecat browser transport with an explicitly substituted echo processor; they do not test upstream provider behavior.

## Next implementation sequence

1. Lucas tests each provider with his own API key: setup acknowledgement, at least three spoken turns, interruption, mute, stop, replacement/deletion during an active session and useful quota/authentication failures. Record results and resource use without recording keys or conversation content.
2. Pin XiaoZhi source and document its actual WebSocket hello/listen/abort/audio contract. Implement the XiaoZhi-to-Pipecat adapter with Opus decoding/encoding, negotiated rates, bounded queues and stale-audio cancellation. Software fixtures validate this single selected path; no alternative-firmware exploration is needed.
3. Implement enrollment: short-lived claim proof, authenticated owner confirmation, separate revocable device credential, replay prevention, reconnect and ownership isolation. A MAC address is not identity proof.
4. On the owner's local computer, reconfirm the physical chip revision and peripherals, preserve the private backup, and prepare reproducible firmware/manifests plus exact write regions and USB recovery. Obtain explicit approval before flashing.
5. Validate real microphone/speaker/display/touch together, then Companion configuration acknowledgements and OTA with explicit rollback and power-loss/recovery tests. Camera support stays separate.

## References consulted

- [Pipecat FastAPI WebSocket transport](https://docs.pipecat.ai/api-reference/server/transport/fastapi-websocket)
- [Pipecat OpenAI realtime service](https://docs.pipecat.ai/api-reference/server/services/s2s/openai)
- [Pipecat Gemini Live service](https://docs.pipecat.ai/api-reference/server/services/s2s/gemini-live)
- [OpenAI gpt-realtime model](https://developers.openai.com/api/docs/models/gpt-realtime)
- [Gemini Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)
- [Cryptography Fernet and rotation](https://cryptography.io/en/latest/fernet/)


Validation update (2026-09-13): Lucas reports successful OpenAI API-key setup and a real browser voice conversation. Gemini and physical hardware remain unvalidated. The revised Companion instructions discourage prompt disclosure; this is behavioral guidance, not a security guarantee. Provider keys remain outside model context and the model has no device-management tools.
