# ADR 0001 — Private platform architecture

Date: 2026-09-13
Status: Accepted by the owner

## Product and scope

AMPVE brings useful applications and AI to supported hardware. Companion is the first application; Waveshare ESP32-P4-WIFI6-Touch-LCD-7B is the first target. All initial UI copy is English. Public signup, billing, arbitrary firmware, camera streaming, and additional runtime platforms are deferred.

The first delivery is the Django platform foundation: a reference-inspired responsive frontend, real accounts and sessions, profile/password settings, private administration, and truthful device/application/connection states. It is a subset of MVP milestone 1, not completion of the provider or hardware journey. Create Lucas (lucas@ampve.com) as a normal demo user; write random demo credentials to a private JSON outside Git. Administration remains a separate identity.

## Decisions

- Django with server-rendered templates and small progressive JavaScript owns accounts, authorization, catalog, settings, and management. Use Django authentication, sessions, password validation, CSRF, ORM, migrations, and admin; do not invent authentication primitives.
- FastAPI + Pipecat will own on-demand audio sessions and the XiaoZhi adapter. Do not add an empty service before audio work starts. Authorize browser audio through a short-lived single-use ticket; device credentials remain distinct.
- Reuse the VPS PostgreSQL server with a dedicated AMPVE database and least-privileged login role. A separate database avoids mixing Django migrations with NEUROSIS tables. Never reuse another application's credentials. Sharing the server introduces a shared availability/backup dependency.
- Use the existing ampve.com Cloudflare Tunnel. Its configured origin is loopback port 3000. Keep the database and application origin private.
- Docker Compose remains the portable deployment direction. For this first delivery, a dedicated Python virtual environment and systemd services reuse the existing Unix-socket database and tunnel without installing Docker or restarting unrelated services. Record this operational adaptation and provide reproducible dependencies and service configuration.
- No Redis, broker, Kubernetes, or additional IoT platform. Persist durable future deployment jobs in PostgreSQL and reconcile against device acknowledgements after restart. Audio sessions are ephemeral and must release resources on stop/disconnect/revocation.
- Preserve XiaoZhi as a small pinned fork, ESP Web Tools as the USB installer, Pipecat for Gemini Live/OpenAI Realtime, and ESP-IDF for OTA. Firmware artifacts will be immutable and traceable; builds run locally or in CI, not on user requests.

## Alternative considered

Next.js/React + FastAPI offers a strong component ecosystem and richer browser state, but requires another runtime, explicit cross-backend identity integration, and custom administration. Django reduces initial account and administration work. It does not remove object ownership checks or the audio adapter. A later React frontend can consume explicit management contracts without replacing the domain model.

## Integration risks and gates

1. XiaoZhi JSON events and binary Opus are not directly compatible with Pipecat/provider audio. Pin protocol versions; test codec conversion, packet pacing, bounded buffers, interruption and stale-audio cancellation using software fixtures before hardware integration.
2. Enrollment needs a per-device random bootstrap secret, expiring human code, atomic claiming, rate limits and revocable credentials. MAC addresses are metadata. Test two normal users, replay, expiration and concurrent claims.
3. Reconfirm chip revision, 32 MiB flash/PSRAM, display/touch/audio/C6 radio and partitions on the actual board. An upstream 7B profile is not proof of compatible firmware. OV5647 configuration does not validate the USB Kiyo.
4. Configure OTA slots and rollback deliberately. Require authenticated releases, essential startup checks and device acknowledgement. Prepare exact write regions and the owner's private recovery backup before requesting hardware-write approval. No generic erase or eFuse/security changes.
5. Test Cloudflare WSS timeout/reconnection behavior. Never assume generic WebRTC/UDP support through the tunnel.
6. Keep provider keys encrypted with a separate server key, never in firmware/browser storage/logs. Raw audio/video retention is off; transcript history requires explicit settings. API quota and model access require real account tests.

## Sequence and acceptance

1. Platform foundation: real login/logout, normal/admin separation, editable own profile/password, persisted catalog, responsive English UI, no fake devices or working-provider claims; secure production settings and deployment checks.
2. Provider path 1A: encrypted connections and a real three-turn conversation through one provider using a development client. Verify replacement/deletion, useful errors and user isolation.
3. Provider path 1B: second provider and an initial software XiaoZhi/Opus adapter test. Record presets, versions, latency and resources during a proposed 15-minute run. Simulated errors are explicitly marked. This completes milestone 1 only when advertised providers pass.
4. Firmware/enrollment: reproducible build, recovery review, approved USB flash and staged peripheral/network bring-up.
5. Companion: actual voice/face, local stop/mute, provider changes without reflash, offline/reconnect behavior.
6. Lifecycle: two verified releases, acknowledged success, demonstrated rollback, restart reconciliation and revocation.
7. Experimental camera validation separately from the working voice MVP.

The VPS can validate persistence, authorization, encrypted storage, real provider calls with test audio, software protocol contracts and build reproducibility. A local browser is needed for human audio testing; USB, peripheral coexistence, full-path latency and actual rollback require the owner's board. Fixtures never become production devices.

## Repository layout

`apps/platform/` holds Django; future `apps/audio/` holds FastAPI/Pipecat. Shared contracts can enter `packages/contracts/` when needed. `firmware/` will track the pinned fork, manifests and recovery metadata, not private dumps. `infra/` holds service/deployment definitions; `docs/decisions/` and `docs/runbooks/` record decisions and operations. Preserve the original `images/` assets.

## References

- https://docs.djangoproject.com/en/5.2/topics/auth/default/
- https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- https://docs.pipecat.ai/api-reference/server/services/transport/fastapi-websocket
- https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md
- https://esphome.github.io/esp-web-tools/
- https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/system/ota.html
- https://developers.cloudflare.com/network/websockets/
