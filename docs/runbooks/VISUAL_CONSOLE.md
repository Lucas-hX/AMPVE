# Authenticated visual device console

Date: 2026-09-14

The visual console gives a signed-in device owner a short-lived browser view of AMPVE's native device controls. It uses an outbound HTTPS device channel and a bounded semantic screen model. It does not expose the device's private network address, stream framebuffer pixels, retain media, or provide a terminal or arbitrary code execution.

## Implemented flow

1. The owner opens **My devices → device → Open visual console** and explicitly starts a ten-minute session. Starting a new session ends earlier browser sessions for the same owner and device.
2. The authenticated browser reconstructs the 1024 × 600 AMPVE screen from a fixed set of pages: Home, Wi-Fi, My device, Settings and Companion. Mouse and touch activations include integer coordinates bounded to the physical 1024 × 600 profile. Keyboard navigation uses named targets.
3. A normal 30-second heartbeat tells console-capable firmware whether a session is waiting. During an active session, the enrolled device temporarily POSTs semantic state to `/api/devices/v1/{device_id}/console/sync/` every 600 ms using its own bearer credential. The server never treats the browser cookie as device authentication.
4. The device reports only page, physical/virtual display mode, local remote-control permission, a monotonic in-memory revision and an optional command acknowledgement. The response contains at most one named action. Unknown pages, actions, fields and coordinates are rejected.
5. Input is accepted only while the device has synchronized within two seconds. Commands expire after eight seconds, are discarded across a synchronization gap, and are dispatched once. A lost response may drop a pointer action; it cannot replay that action after reconnection. Client sequence numbers reject stale or repeated browser requests.
6. The physical screen shows when remote control is active. Its **Remote active · tap to stop** control remains locally available and blocks later browser input until a person enables remote control again. Remote input cannot enable microphone capture or confirm that a speaker tone was heard.

The current named actions are navigation, opening the local Wi-Fi setup flow, starting local pairing, requesting the existing quiet speaker diagnostic, keeping the microphone muted and cancelling an update before restart. The console cannot change credentials, release policy, partitions, security fuses or unrestricted device state.

## Physical and virtual modes

`physical` means a device reports that the semantic view corresponds to its local display controller. It is not a video mirror and does not prove the panel currently shows every pixel in the browser reconstruction. Local touch remains authoritative.

`virtual` uses the same screen schema for a managed device without an initialized physical display. It is a UI surface backed by device state, not an invented hardware capability. A headless profile can expose only the controls its firmware actually implements. The first firmware implementation remains restricted to the Waveshare 7B profile and reports `physical`.

The installed `0.1.16-touch-ota-dev` predates this channel. The web console therefore remains an authenticated virtual preview until the board receives a separately published `0.1.17-visual-console-dev` or later compatible OTA release. A successful compile does not authorize or perform that update.

## Authorization and bounds

- Owner lookup applies on the console page, session creation, state, input and stop routes. Staff status does not bypass ownership.
- Browser mutations require Django session authentication and CSRF. Device synchronization requires the revocable enrolled-device bearer credential and an active owner.
- Sessions expire after ten minutes. Input is capped at 180 events per minute per session; device synchronization is capped at 180 requests per minute per device. At the 600 ms active cadence, the nominal channel uses 100 requests per minute.
- Browser requests are limited to 768 bytes and device requests retain the 2,048-byte management limit. No free-form device text, HTML, logs, transcripts, pixels, audio or video are accepted.
- Database rows retain session timing, fixed semantic state and bounded command metadata for diagnostics. Sessions and their commands are removed 30 days after expiry by the existing device-metadata maintenance job. They contain no provider secret, device bearer token or raw media.

The initial P4 build produces request bodies below 256 bytes and typical responses below 400 bytes. At the maximum active cadence this is under roughly 65 KiB/minute in JSON payloads before TLS/HTTP overhead. The exact on-device heap, scheduling delay and network overhead still require physical measurement; the HTTP client shares the existing management worker and does not open another inbound port or persistent socket.

## Verification

Run the platform contract and full workspace suites:

```bash
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace.test_console --noinput
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
```

The contract tests cover authentication separation, owner isolation, CSRF, session expiry/stop, heartbeat discovery, one-time dispatch, acknowledgement, replay rejection, local stop, schema bounds, invalid coordinates, revocation and oversized requests. These are software fixtures.

The ESP32-P4 OTA build of `0.1.17-visual-console-dev` succeeded with IDF 6.1 and the pinned dependencies. Its app is 2,805,776 bytes, SHA-256 `ac6aedaf15622dc3770f4a3c4d8631d41b4591732e9339e0b778b98005dd1fd7`, leaving 1,323,376 bytes (32%) in either 4 MiB application slot. This proves compilation and fit only. Physical remote navigation, local interruption, 600 ms cadence, heap stability and outage recovery remain acceptance work in #84.

## Next acceptance pass

After a signed compatible release is deliberately published and deployed, start one console session and verify that the device joins within the heartbeat interval. Exercise every page from mouse, touch and keyboard; compare browser state with the physical panel; stop control locally; confirm the browser becomes read-only; re-enable locally; and confirm a fresh session works without replaying earlier actions. Leave local touch active during the session and test browser/network loss.

Measure internal heap before, during and after ten minutes, actual request/response bytes, command latency, CPU scheduling effects and NVS writes. No console input should write NVS. Keep the known speaker failure recorded independently in #23.
