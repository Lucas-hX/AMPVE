# Authenticated visual device console

Date: 2026-09-14

The visual console gives a signed-in device owner a short-lived browser view of AMPVE's native device controls. It uses an outbound HTTPS device channel and a bounded semantic screen model. It does not expose the device's private network address, stream framebuffer pixels, retain media, or provide a terminal or arbitrary code execution.

## Implemented flow

1. The owner opens **My devices → device → Open visual console** and explicitly starts a ten-minute session. Starting a new session ends earlier browser sessions for the same owner and device.
2. The authenticated browser reconstructs the 1024 × 600 AMPVE screen from a fixed set of pages: Home, Wi-Fi, My device, Settings and Companion. Mouse and touch activations include integer coordinates bounded to the physical 1024 × 600 profile. Keyboard navigation uses named targets.
3. A normal 30-second heartbeat tells console-capable firmware whether a session is waiting. During an active session, the enrolled device temporarily POSTs semantic state to `/api/devices/v1/{device_id}/console/sync/` every 600 ms using its own bearer credential. The server never treats the browser cookie as device authentication.
4. The device reports only page, physical/virtual display mode, local remote-control permission, a monotonic in-memory revision and an optional command acknowledgement. The response contains at most one named action. Unknown pages, actions, fields and coordinates are rejected.
5. Input is accepted only while the device has synchronized within six seconds. This accommodates the measured roughly 2.5-second HTTPS exchange while remaining below the eight-second command expiry. Commands are discarded across a longer synchronization gap and are dispatched once. A lost response may drop a pointer action; it cannot replay that action after reconnection. Client sequence numbers reject stale or repeated browser requests.
6. The physical screen shows when remote control is active. Its **Remote active · tap to stop** control remains locally available and blocks later browser input until a person enables remote control again. Remote input cannot enable microphone capture or confirm that a speaker tone was heard.

The current named actions are navigation, opening the local Wi-Fi setup flow, starting local pairing, requesting the existing quiet speaker diagnostic, keeping the microphone muted and cancelling an update before restart. The console cannot change credentials, release policy, partitions, security fuses or unrestricted device state.

## Physical and virtual modes

`physical` means a device reports that the semantic view corresponds to its local display controller. It is not a video mirror and does not prove the panel currently shows every pixel in the browser reconstruction. Local touch remains authoritative.

`virtual` uses the same screen schema for a managed device without an initialized physical display. It is a UI surface backed by device state, not an invented hardware capability. A headless profile can expose only the controls its firmware actually implements. The first firmware implementation remains restricted to the Waveshare 7B profile and reports `physical`.

The first registered 7B now runs the signed `0.1.17-visual-console-dev` sequence-8 release and reports `physical` mode. Other enrolled devices without a console-capable release remain in an authenticated preview until compatible firmware joins the session. A virtual view alone does not establish a physical capability.

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

The release-sequence-8 ESP32-P4 OTA build of `0.1.17-visual-console-dev` succeeded with IDF 6.1 and the pinned dependencies. Two separate workspaces produced byte-identical app, bootloader, partition-table and initial-otadata artifacts from merged source `4daaa45`. The app is 2,881,536 bytes, SHA-256 `ebe00e7fd5327efa57b797b4d921d17e8a8a253e214c7e60c06fdef383075cc6`, leaving 1,312,768 bytes (30%) in either 4 MiB application slot. Both configurations disable USB commissioning. This establishes compilation, reproduction and fit; the physical results below are separate runtime evidence.

Signed release `3f9eeca4be7306b37c9052292ad66792e6e30e34bf68b1974499080244823b0c` was restricted to the device's confirmed sequence-7 app hash. Deployment `63ce7b90-2618-4a60-942a-ed2eb15f2b88` completed 15 ordered device reports, all 2,881,536 bytes, exact target identity and sequence-8 startup confirmation with no attention flag. A live browser session then joined in physical mode. After correcting the server's two-second assumption to a measured-latency six-second window, four separate Settings/Home/Companion/Home inputs from mouse, keyboard, touch and keyboard were each dispatched once and acknowledged `applied` by the device. The browser stopped the session and reported no JavaScript errors. This validates the nominal authenticated remote-control path; a person still needs to compare the physical panel, exercise local stop and observe outage/recovery and heap behavior.

## Next acceptance pass

After a signed compatible release is deliberately published and deployed, start one console session and verify that the device joins within the heartbeat interval. Exercise every page from mouse, touch and keyboard; compare browser state with the physical panel; stop control locally; confirm the browser becomes read-only; re-enable locally; and confirm a fresh session works without replaying earlier actions. Leave local touch active during the session and test browser/network loss.

Measure internal heap before, during and after ten minutes, actual request/response bytes, command latency, CPU scheduling effects and NVS writes. No console input should write NVS. Keep the known speaker failure recorded independently in #23.
