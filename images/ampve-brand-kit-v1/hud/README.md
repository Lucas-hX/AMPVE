# AMPVE semantic console HUD v1

Roadmap item: E39 / GitHub issue #96.

The HUD summarizes the authenticated semantic console; it is not telemetry and never displays a framebuffer, shell, terminal, microphone stream or unrestricted device data.

## Status rail

Five stable positions avoid shifting meaning while the session changes:

1. **Device** — the device model’s heartbeat-derived connection label.
2. **Visual channel** — stopped, reconnecting, connected, locally stopped or stale revision.
3. **Browser session** — not started, starting, active or stopped.
4. **Last input** — none, pending, applied, ignored, blocked or rejected, paired with mouse, touch or keyboard input source when known.
5. **Local authority** — always visible; browser control cannot remove local input authority.

The rail uses the AMPVE icon sprite. Added E39 symbols: `touch`, `mouse`, `keyboard` and `session`; it reuses `wifi`, `console`, `activity`, `attention`, `local-control` and `firmware`.

## Truth and motion rules

- Queued browser input is orange and says “Pending”; it never uses the success treatment.
- The sage acknowledgement ring runs once, for 650 ms, only after a new `applied` device acknowledgement.
- `ignored`, `blocked`, request rejection and stale revision use visible text and the attention treatment.
- A missing device poll becomes “Reconnecting”; it does not imply that the underlying device heartbeat is Online.
- Local stop changes the channel label to “Stopped locally” and preserves the local-authority signal.
- Stopped sessions expose the start action; active sessions expose the stop action.
- `prefers-reduced-motion` disables the acknowledgement ring. No motion carries unique information.

The 1024 × 600 semantic frame remains horizontally inspectable on narrow screens. The status rail itself reflows to two columns and then one column, so safety information never hides inside that viewport.

Open `index.html` through a local HTTP server for the state review sheet.
