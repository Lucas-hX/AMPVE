# AMPVE interface icons v1

Issue: [#94](https://github.com/Lucas-hX/AMPVE/issues/94) · 2026-09-14

AMPVE uses a small repository-native SVG symbol set instead of an icon font or third-party runtime library. The rounded geometry echoes the parent mark without turning every symbol into a logo.

## Construction

- Grid: 24 x 24.
- Default stroke: 1.75 CSS px.
- Caps and joins: round.
- Default fill: none; only optical dots and intentionally solid details use `currentColor`.
- Intended sizes: 16 px for compact metadata, 20 px for controls and 24 px for navigation.
- Default color: graphite. Orange indicates selection or action. Sage indicates normal state. Warnings and failures always include text or another non-color cue.
- Symbols contain no accessible name. Decorative use must be `aria-hidden`; icon-only controls require an explicit `aria-label` on the control.

## Usage in Django templates

```django
{% include 'workspace/icon.html' with name='devices' %}
```

The helper emits an external `<use>` reference to `ampve-icons-v1.svg`. Use `class_name` only for a documented size or state modifier.

## Inventory

Navigation and product: `home`, `devices`, `apps`, `connections`, `settings`, `add-device`, `console`, `diagnostics`, `activity`.

Connectivity and lifecycle: `wifi`, `usb`, `ownership`, `firmware`, `download`, `update`, `backup`, `restore`, `recovery`, `offline`.

Capabilities, input and safety: `microphone`, `speaker`, `camera`, `mute`, `local-control`, `touch`, `mouse`, `keyboard`, `session`, `success`, `attention`.

Utilities: `arrow-right`, `external-link`, `add`, `info`, `sun`, `spark`.

Open `index.html` through the Django static server to review every symbol in default, active, disabled and dark-HUD contexts.
