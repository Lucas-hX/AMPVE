# AMPVE — Your devices. New possibilities.

Visual direction v1 · 2026-09-12

AMPVE brings apps and AI into the world around you. Its identity should remain useful as the product grows from one expressive companion to many applications and supported device types.

This pack contains eight generated raster images: three frontend design references and five reusable brand/marketing assets. It is a proposed visual direction, not an implemented interface.

## Positioning and voice

- Primary line: **Your devices. New possibilities.**
- Supporting line: **Bring apps and AI into your world.**
- Product introduction: **AMPVE gives the devices you already own new ways to help, create, and connect. Start with supported hardware, choose an application, and make it yours.**
- Spanish direction: **Tus dispositivos. Nuevas posibilidades.**
- Tone: approachable, curious, clear, quietly ambitious.
- Lead with applications, usefulness, and personal choice. Keep infrastructure terminology in setup details and developer documentation.
- AMPVE is the parent brand. Companion is its first application; the smiling face is not the parent brand logo.
- Broad device support is the ambition. The first implementation targets Waveshare P4 Touch LCD 7B. Label future applications and integrations clearly.

## Asset inventory

| File | Size | Intended use |
|---|---|---|
| [Primary logo](brand/ampve-logo-primary-v1.png) | 2172 × 724 | Header, README, light-background identity. Real transparent alpha. |
| [Symbol avatar](brand/ampve-symbol-avatar-v1.png) | 1254 × 1254 | Repository avatar and brand tile. Opaque ivory background. |
| [README banner](banners/github-readme-banner-v1.png) | 2172 × 724 | Wide GitHub README header. Contains baked-in English copy. |
| [Hero illustration](illustrations/devices-possibilities-hero-v1.png) | 1536 × 1024 | Text-free landing illustration or promotional card. Opaque warm background. |
| [Companion icon](apps/companion-icon-v1.png) | 1254 × 1254 | Application catalog and companion settings. Opaque warm background. |
| [Workspace home](mockups/01-workspace-home-v1.png) | 1586 × 992 | Signed-in frontend composition reference. |
| [Onboarding](mockups/02-onboarding-activate-v1.png) | 1586 × 992 | Activation step after compatible firmware installation. |
| [Public landing](mockups/03-public-landing-v1.png) | 1586 × 992 | Public-facing frontend composition reference. |

Open [the visual gallery](index.html) in a browser to review the full set.

## Design foundations

| Role | Proposed CSS value | Usage |
|---|---|---|
| Canvas | #F7F5EE | Warm page background |
| Surface | #FFFFFF | Forms and primary content |
| Text | #252823 | Main text and headings |
| Muted text | #62675E | Secondary labels |
| Brand orange | #E7653D | Artwork and decorative highlights |
| Action orange | #B83E1C | Buttons with white text; stronger contrast than illustration orange |
| Sage surface | #E8ECDD | Calm secondary areas |
| Sage text | #47513A | Labels on pale sage |
| Border | #DADDD2 | Quiet separators |
| Focus | #252823 | Visible keyboard focus outline |

The palette is a proposed implementation specification; generated image pixels may differ. Match the design direction rather than sampling every raster shade. Verify contrast in the actual UI, especially small labels and interactive states.

Use a rounded, confident sans-serif heading style and a highly readable sans-serif body style. The generated lettering does not identify an exact font file. Do not assume an existing font will reproduce the logo; the PNG is the current source brand asset.

Recommended spacing scale: 4, 8, 12, 16, 24, 32, 48, 64px. Start with 12–16px control/card radii, 44px minimum primary touch targets, and generous content margins. Avoid turning every section into a floating card.

## Frontend interpretation

The mockups are image references. Build real semantic HTML components for text, inputs, navigation, and buttons. Do not ship a screenshot as the application UI.

- Desktop workspace: slim navigation column, clear page heading, one meaningful primary action, device/app content.
- Small screens: turn the sidebar into a drawer, stack onboarding fields and device illustration, preserve primary controls without horizontal scrolling.
- Use collapsible diagnostics and progressive disclosure for firmware/provider details.
- The public landing can communicate a broader future; the live catalog must contain only available applications or explicitly labeled previews.
- The illustrated devices and enclosures are conceptual. They are not exact photographs of the Waveshare board and do not imply AMPVE sells hardware.
- The avatar shown in mockups is a generated placeholder, not Lucas's photograph.
- Home mockup nuance: it shows a device online while also promoting setup. In implementation, show the setup invitation only for an unconfigured device, or change it to “Open Companion” for an active assignment.
- The activation mockup starts after USB installation and registration. Preserve the complete pairing, ownership, Wi-Fi, and recovery steps from the implementation brief.
- Refine the key-storage copy to “Stored securely on your AMPVE server. Used only to connect to your provider.” A provider key is necessarily sent to its provider to authenticate API requests.
- The parent brand uses the arch-and-square mark. Use the separate face icon for Companion cards even if a generated mockup places the parent mark there.
- Marketing artwork can have expressive texture. Production UI controls, text, and logos should remain crisp and restrained.
- Keep primary/logo use on light surfaces until a separate dark-surface lockup is prepared.

## GitHub README starter

If this folder is copied into the new repository at the same path:

```markdown
![AMPVE — Your devices. New possibilities.](images/ampve-brand-kit-v1/banners/github-readme-banner-v1.png)

Bring apps and AI into your world.

AMPVE helps you give supported devices new possibilities, starting with an expressive AI companion on the Waveshare P4.

**Early MVP:** XiaoZhi firmware · ESP Web Tools onboarding · Pipecat sessions.
```

The banner is suitable for a README. It has not been exported as a dedicated social-preview image or favicon. The brand assets are PNG originals, not SVG master artwork.

## Generation and provenance

Generated with the built-in **image_gen** tool. The exact prompt set, including the hero background revision, is saved in [prompts.json](prompts.json).

The primary logo established the direction; subsequent generations referenced it and selected earlier artwork to maintain consistency. Visually reviewed every delivered output. Verified image dimensions and confirmed the logo has transparent pixels. The final hero intentionally uses an opaque ivory background; unsuccessful checkerboard-background variants are not included in this pack.

This repository includes only the selected final visual pack. Earlier experiments and discarded image variants are not part of the current product baseline.
