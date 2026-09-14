# AMPVE onboarding microillustrations v1

Roadmap item: E40 / GitHub issue #97.

These four repository-native SVGs describe real interface moments without claiming physical hardware validation. They use a shared 560 × 400 viewBox, matte surfaces, restrained shadows, rounded graphite geometry, illustration orange, sage and a blue-grey recovery accent.

| Asset | Product moment | Usage boundary |
|---|---|---|
| `no-devices-v1.svg` | No enrolled devices | Empty shelf and unplugged cable; it does not render a placeholder device. |
| `usb-connect-v1.svg` | Connect the programming USB port | Shows a cable approaching an illustrated board. Selection alone does not mean connected, read or installed. |
| `device-ready-v1.svg` | A specifically confirmed ready/completed step | Use only after the corresponding software check reports success. It does not certify untested peripherals. |
| `recovery-available-v1.svg` | Verified recovery files or recovery action available | Blue-grey and circular path distinguish recovery from green success. Always pair with explicit instructions and a real action. |

## Motion/state contract

- **Ready**: static neutral surface; no attention animation.
- **Working**: an indeterminate operation orbit may rotate slowly. Copy must state that duration is unknown until measurable progress exists.
- **Progress**: native `<progress>` represents measured bytes only; never animate invented percentages.
- **Success**: one 420 ms check reveal after an explicit confirmed result.
- **Warning**: static ochre treatment with next-step copy.
- **Recoverable error**: one brief 500 ms horizontal settle, then fully static; recovery artwork accompanies instructions and an action.

All motion is decorative, non-blocking and disabled by `prefers-reduced-motion`. Status text remains in `role="status"` or `role="alert"` regions already present in onboarding.

The assets are SVG rather than raster because their simple geometry benefits from crisp scaling, small transfer size and code-native state motion. No AVIF/WebP derivatives are necessary.

Open `index.html` through a local HTTP server for desktop and mobile review.
