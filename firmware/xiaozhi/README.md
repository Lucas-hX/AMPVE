# XiaoZhi integration baseline

`upstream.json` pins the source review baseline, not a buildable AMPVE release or validated binary. No upstream source is vendored and no firmware has been flashed. The management backend is implemented; the embedded AMPVE client and XiaoZhi audio adapter are still to be written and validated against this baseline.

At commit `563a4f0a70d34eea5547977f2a39efa401c2ea35`, `main/boards/waveshare/esp32-p4-wifi6-touch-lcd/config.json` contains separate `esp32-p4-wifi6-touch-lcd-7b` and `esp32-p4x-wifi6-touch-lcd-7b` builds. The former explicitly sets `CONFIG_ESP32P4_SELECTS_REV_LESS_V3=y`, `CONFIG_ESP32P4_REV_MIN_100=y`, 32 MB flash and `partitions/v2/32m.csv`. This aligns with the *historical* owner report of revision 1.3 but does not certify the connected unit or an upstream binary. The profile also enables OV5647 camera options; that is not Kiyo support and camera options need review for the voice-first build.

## Next firmware work

1. Obtain a local chip/flash/partition audit and preserve the owner's existing full backup outside Git. Compare the pinned partition CSV to the actual device. Record the exact ESP-IDF/toolchain and component lock; no toolchain is accepted by this baseline alone.
2. Prepare a tracked fork or small patch series with original license notices. Replace upstream activation/OTA/voice destinations with AMPVE endpoints. Do not leave third-party fallback registration enabled.
3. Add the AMPVE management client as a task inside XiaoZhi firmware, using ESP-IDF HTTPS, certificate validation, cJSON and NVS. It is separate from the conversational model and never executes model-generated shell/management commands.
4. Generate pairing proof/credential state as specified in [the device contract](../../docs/runbooks/DEVICES.md). Show the server's expiring code locally. Save the client-generated 32-byte credential in NVS *before* exchanging it, so retry after a lost HTTP response is safe. After expiry without a usable credential, require local pairing restart.
5. Poll every 30 seconds with backoff/jitter; apply settings locally then acknowledge the exact version. Local microphone mute wins over remote configuration. A device credential authenticates a client, not its reported board identity. Never send provider keys to firmware.
6. Implement the selected XiaoZhi WebSocket/Opus adapter and bounded cancellation. The current heartbeat explicitly advertises audio and OTA as unavailable.
7. Build reproducible artifacts and an ESP Web Tools manifest only after exact write regions, digests, authenticated release metadata and USB recovery are reviewable. Configure and test OTA slots/rollback/startup confirmation. Obtain hardware-write approval before flashing.

The public web UI currently performs optional ROM chip inspection only. It does not read the original flash backup, upload a stub, install an application, modify eFuses, or publish a firmware manifest. Raspberry Pi and a permanent USB bridge remain separate future runtimes.

Sources: [pinned board configuration](https://github.com/78/xiaozhi-esp32/blob/563a4f0a70d34eea5547977f2a39efa401c2ea35/main/boards/waveshare/esp32-p4-wifi6-touch-lcd/config.json), [pinned WebSocket protocol](https://github.com/78/xiaozhi-esp32/blob/563a4f0a70d34eea5547977f2a39efa401c2ea35/docs/websocket.md).
