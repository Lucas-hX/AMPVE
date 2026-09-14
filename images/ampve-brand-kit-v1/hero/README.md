# AMPVE public hero assets

Issue: [#93](https://github.com/Lucas-hX/AMPVE/issues/93) · 2026-09-14

This folder contains the generated device layers used by the public landing hero. The orange ribbon, app tiles, atmospheric shapes and Companion eyes remain code-native SVG/CSS so they can animate independently, respond to layout changes and stop under `prefers-reduced-motion`.

Source artwork and browser exports are intentionally separate:

| Asset | Size | Bytes | Use |
| --- | --- | ---: | --- |
| `source/landing-devices-wide-v1.png` | 1536 x 1024 | 1,268,881 | Versioned generated source for desktop/tablet |
| `source/landing-devices-mobile-v1.png` | 1448 x 1086 | 1,023,294 | Versioned generated source for mobile |
| `exports/landing-devices-wide-v1.webp` | 1536 x 1024 | 25,182 | Browser delivery for desktop/tablet |
| `exports/landing-devices-mobile-v1.webp` | 1448 x 1086 | 20,132 | Browser delivery for mobile |

The Django landing template references only `exports/`. The PNG files remain editable provenance and are not requested by the browser. WebP exports use quality 82 with the original pixel dimensions, explicit intrinsic dimensions in HTML and no additional resampling.

Both assets have an opaque warm-ivory field. Built-in image generation produced a painted checkerboard instead of real alpha during two background-extraction attempts, so those outputs were rejected. The accepted assets use a uniform ivory field plus a soft CSS mask; no fake-transparency output is included.

## Generation

Tool: built-in `image_gen`.

### Wide device cluster

Use case: `precise-object-edit`.

Replace the entire painted gray checkerboard background in the supplied device-cluster image with one seamless, perfectly uniform warm ivory field matching `#F7F5EE`. Preserve the mini-computer, blank-screen monitor, stand, round sun display, their geometry, relative arrangement, materials, colors, lighting and crisp edges. Keep only restrained short contact shadows directly beneath the objects. Do not redraw, move, crop, resize or add anything. The monitor screen must remain blank graphite with no eyes or icons. No checkerboard, gray grid, ribbon, app tiles, text, logo, eyes, extra objects, colored gradient or watermark.

### Mobile device cluster

Use case: `precise-object-edit`.

Recompose the supplied three-device cluster for a compact mobile hero while preserving the exact objects and visual identity. Use a seamless, perfectly uniform warm ivory `#F7F5EE` backdrop. Keep the same low ivory mini-computer, blank graphite landscape Companion display on its champagne stand and round cream ambient sun display. Compose a compact near-square 4:3 presentation with the monitor centered slightly high, mini-computer front-left and round display front-right. Keep all devices fully visible with balanced margins and a blank screen for live CSS eyes. Preserve proportions, materials, ports and soft studio lighting. No ribbon, app tiles, text, logos, manufacturer marks, checkerboard, gradient, blue, purple or watermark.

## Motion contract

- Device drift: 5 px over 8 seconds.
- Ribbon breath: 5 px over 9 seconds.
- App-tile drift: 8 px over 6.2 seconds with staggered offsets.
- Companion blink: one short blink within a 7.2-second cycle.
- All motion is decorative and disabled under `prefers-reduced-motion: reduce`.
