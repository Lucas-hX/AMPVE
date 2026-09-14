# AMPVE browser device tools

These tools power the guided USB inspection, setup and recovery experience served by AMPVE. They use Web Serial and a pinned `esptool-js` dependency without loading code from a third-party CDN.

## Build and test

```bash
npm ci --ignore-scripts
npm test
npm run build
```

The generated bundles are collected by Django and served as local static assets. Dependency versions and integrity hashes are recorded in `package-lock.json`; applicable notices are included beside the bundles.

## Device boundaries

- Selecting a serial port does not establish device ownership or compatibility.
- Inspection and backup happen locally in the browser.
- Raw flash contents, serial logs and device identifiers are not uploaded by the browser tools.
- Installation requires a matching supported profile and authenticated release metadata.
- Security configuration, eFuses and full-chip erase are outside the browser flow.

See [Supported hardware](../../docs/SUPPORTED_HARDWARE.md), [Architecture](../../docs/ARCHITECTURE.md) and [Security](../../SECURITY.md).

Third-party references and notices:

- [Web Serial](https://developer.chrome.com/docs/capabilities/serial)
- [esptool-js](https://github.com/espressif/esptool-js)
- [ESP Web Tools](https://esphome.github.io/esp-web-tools/)
- `ESPTOOL-LICENSE`, `PAKO-LICENSE` and `ZLIB-NOTICE`
