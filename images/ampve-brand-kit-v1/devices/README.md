# AMPVE device-card visual language v1

Roadmap item: E38 / GitHub issue #95.

## Portraits

- `waveshare-p4-profile-v1.svg` is the production portrait for the reported `waveshare-esp32-p4-wifi6-touch-lcd-7b` profile. It is a UI illustration, not a product photograph or hardware attestation. The exposed sage board, touch display and compact connector shapes distinguish it from polished conceptual enclosures.
- `future-device-concept-v1.svg` is intentionally incomplete and dashed. It may appear only beside explicit “Concept” or “Future hardware” language; it must never represent an enrolled device.

Both portraits are text-free, responsive SVGs. Product names and verification caveats remain semantic HTML next to the artwork.

## Card hierarchy

1. Connection state and ownership context.
2. User-defined device name and reported profile family.
3. Assigned application and last authenticated contact.
4. One primary management action.
5. Exact profile ID, transport, firmware and trust caveat inside progressive disclosure.

An unavailable assignment is written as “No application assigned”; the interface never guesses an application from the hardware profile.

## State grammar

| State | Icon | Surface/accent | Meaning |
|---|---|---|---|
| Online | `success` | Sage / green | Authenticated heartbeat received within 90 seconds. |
| Offline | `offline` | Neutral / graphite | A prior contact exists but is older than 90 seconds. |
| Updating | `update` | Peach / orange | A verified deployment is actively progressing. Never infer from firmware mismatch. |
| Attention | `attention` | Warm cream / ochre | Owner action or review is required. “Awaiting device” uses this grammar. |
| Recovery | `recovery` | Pale blue-grey / blue | Recovery is available or confirmed as the next action; it is not success. |
| Revoked | `attention` | Pale red / dark red | The device credential can no longer authenticate. |

Every state includes visible text and an AMPVE icon. Color and animation are supporting signals only. A pulse may run only for a currently authenticated Online or Updating state and is removed under `prefers-reduced-motion`.

## Timestamp and truth rules

- Show relative time for fast scanning, plus an exact UTC timestamp through the native `title` and accessible label on `<time>`.
- “Online” comes only from the model’s authenticated-heartbeat window. Pairing, USB selection, desired settings and browser activity do not modify it.
- Empty, loading and unavailable states must not render a profile portrait or placeholder capability as if a device exists.
- Detailed capability and compatibility reports remain on the device detail page.

Open `index.html` through a local HTTP server to review the two portraits and five-state grammar at desktop or mobile widths.
