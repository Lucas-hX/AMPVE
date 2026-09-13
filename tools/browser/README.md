# USB chip inspection

Build with Node.js and npm: `npm ci --ignore-scripts && npm run build` in this directory, then Django collectstatic. Exact dependency versions/integrity are locked. The generated bundle and linked legal comments are served locally, never from a third-party CDN. esptool-js's Apache-2.0 notice is retained in ESPTOOL-LICENSE; bundled dependency notices remain in the generated legal file. No project license is implied.

The pinned esptool-js 0.6.1 implementation performs ROM sync, chip magic/register reads and reset. AMPVE calls `connect`, the P4 chip description reader, and `after('hard_reset')`; it does not call `main`, `runStub`, erase, flash writes, or eFuse/security configuration. A separate explicit browser checkbox acknowledges a temporary reset/download-mode transition. Failed inspection can require physical RESET/power reconnection. USB selection alone does not open the port.

Chip-family detection is distinct from board-model confirmation, firmware compatibility, ownership and network connectivity. No serial data is uploaded or retained. The physical P4 path still requires Lucas's local test. ESP Web Tools remains the selected installer once verified artifacts and recovery details exist.

References: [Web Serial](https://developer.chrome.com/docs/capabilities/serial), [esptool-js](https://github.com/espressif/esptool-js), [ESP Web Tools](https://esphome.github.io/esp-web-tools/).
