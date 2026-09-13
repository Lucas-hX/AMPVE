# Browser installation and stock-preserving review

Implementation: browser audit, local backup/import, signed-release gate, exact plan/recovery preparation, bounded app-first writer and pairing handoff. **Physical browser reads/writes are not yet tested. No release is approved for this unit.** See [ADR 0004](../decisions/0004-stock-preserving-browser-installation.md).

## Owner test flow

1. Sign in at `https://ampve.com/devices/add/` in desktop Chrome or Edge. Confirm the printed Waveshare 7B label, use its programming port and close other serial tools.
2. Select the port and consent to a temporary RAM reader/reset. **Audit connected board** checks P4 1.3, 32 MiB, disabled security and the table. It does not write flash. Use RESET to return to the original app after a standalone audit.
3. **Create two private backups** selects local storage and creates a new timestamped child directory. Keep it outside Git/shared folders, leave the computer awake and retain stable power. Each read has measured progress/ETA. Completed files are reopened and rehashed. Keep a verified copy on separate storage. After cancellation/failure, no incomplete file counts as a completed backup.
4. Alternatively, expand **Continue with existing backups** and select both 32 MiB `.bin` files plus their completed `audit-private.json`. They remain local. The tool checks full-file hashes, an unambiguous MD5 partition table, bounded P4 image checksums/appended digests and the empty target slot. The imported capture record is owner evidence, not a new physical read.
5. **Check release and prepare installation** currently reports the missing compatibility/approval gates. A review bundle can be downloaded for local comparison. This is expected; do not bypass it by flashing the downloaded app manually.
6. Once a reviewed signed release is actually published, this same action prepares exact app/boot-selection regions. Save the private recovery files, confirm a verified separate copy and ROM access, and approve those specific writes. The final full physical comparison can take another full-read duration. Any changed byte requires fresh backups; a normal stock boot can change NVS/otadata, so do not reboot between fresh capture and installation.
7. The application is written/read back before boot selection is changed. Do not disconnect or close the tab during writes. After a successful readback/reset, physically confirm startup, screen/touch, Wi-Fi setup and the management UI. In Wi-Fi, use the protected local provisioning network and screen-only password. Then select **Pair with my AMPVE account** and enter the temporary code on the web page.
8. Confirm authenticated online status and name/volume acknowledgement. Board voice, microphone capture, camera and Wi-Fi firmware updates are not included in this first installer milestone.

If startup/write verification fails, keep the original private backups and generated recovery files. Use the exact reviewed USB recovery procedure. Do not erase the whole chip or improvise a partition/bootloader rewrite. Automatic rollback on the stock bootloader is not yet established.

## Complete the local review without uploading flash

The candidate ZIP is available through the authenticated review download after selecting verified backups. Extract it into a new private directory alongside the completed audit. From this branch's checkout, use the existing pinned firmware-tools Python on Windows (replace paths with the actual private directories):

```powershell
& 'PATH_TO_FIRMWARE_TOOLS\Scripts\python.exe' firmware/tools/compare.py --audit 'PRIVATE_AUDIT_DIRECTORY' --candidate 'EXTRACTED_REVIEW_DIRECTORY'
& 'PATH_TO_FIRMWARE_TOOLS\Scripts\python.exe' firmware/tools/installation_plan.py --audit 'PRIVATE_AUDIT_DIRECTORY' --candidate 'EXTRACTED_REVIEW_DIRECTORY' --output 'NEW_PRIVATE_PLAN_DIRECTORY'
```

Both commands are offline and contain no hardware writes. The second rechecks actual candidate/generated-table/SDK hashes, stock images, empty target slot and boot selection. It generates exact proposed writes, corresponding recovery regions, and a sanitized `review-summary.json` suitable for sharing after local inspection. Keep every `.bin`, `installation-plan-private.json` and original audit private. If the tool refuses the actual subtype/flags or boot-selection state, report the sanitized failure and review it; never weaken the validator.

The stock bootloader/table hashes, stock image header metadata and C6 compatibility evidence are needed to finish review. P4 backup bytes cannot prove C6 firmware identity or physical restore. Lucas has confirmed the original application boots after the 2026-09-13 audit; separate-storage confirmation is still pending.

## Build and package

Current source: `0.1.2-profile-dev` uses the [shared versioned hardware profile](HARDWARE_PROFILES.md). New candidate/publication manifests must include its exact compatibility tuple. Old signed/candidate manifests cannot be made installable by manually adding a profile flag; rebuild and review the actual candidate. Existing private stock backups are unaffected.

Use the existing pinned external toolchain and `firmware/tools/build.sh` from the native runbook. It regenerates stale SDK configuration when moving from the old layout, copies the explicit stock CSV, and builds version `0.1.2-profile-dev`. The runtime rejects the wrong app slots/factory map before NVS/driver initialization.

`release.py` verifies the actual P4 image and produces the review directory plus a private ZIP sibling. The bundle includes generated bootloader/table/initial-otadata files for comparison only. Their presence does not authorize writing them. `proposed_regions_not_approved_writes` names only the app at `0xE00000`; exact otadata is generated locally from the owner's original selection.

The platform defaults to `/home/ampve/.local/state/ampve/firmware-review-stock-v1` for the candidate. Its app and ZIP are accessible only to signed-in users. No upload endpoint exists for device backups. No candidate flag can enable installation.

## Publisher administration after review

Use the [schema-2 publication/trust runbook](FIRMWARE_RELEASES.md) and the pinned firmware-tools Python. It documents immutable release IDs, the monotonic publisher ledger, independent key trust and revocation, separate USB/OTA purposes, provenance archives and the exact promotion/verification commands. No production key, trust registry or approved release is created automatically. The platform and browser reject legacy signed policies.

The generated `esp-web-tools-reference.json` remains a tooling reference, not a generic install button: it lacks dynamic per-device boot selection and recovery gates. OTA releases never include it or an app flash offset. Use the guarded AMPVE flow.

## Checks and evidence categories

```bash
# From tools/browser: npm ci --ignore-scripts; npm run build; npm test
"$AMPVE_TOOL_PYTHON" -m unittest discover -s firmware/tests -v
AMPVE_TESTING=1 .venv/bin/python apps/platform/manage.py test workspace --noinput
.venv/bin/python tests/browser/onboarding.py
```

Node tests use synthetic flash/serial/storage fixtures, including app-readback failure before boot selection, stale flash, corruption, cancellation, disk failure and signature/expiry rejection. Browser tests render actual templates and import synthetic complete backups while checking no uploads and responsive layouts. Django tests cover authenticated curated downloads, corruption and publisher verification. These tests are not physical ROM, flash, Wi-Fi or recovery evidence.

## Delivery evidence — 2026-09-13

- Implementation source: `217229bb6624acc63d30c3705c6ebd24c59510a9`, [PR #39](https://github.com/Lucas-hX/AMPVE/pull/39), now merged after PR #5 under the owner's PR authorization. The platform was updated with the browser flow; no database migration, audio restart, tunnel change or hardware write was needed.
- Actual `0.1.1-stock-dev` app: **2,652,944 bytes**, SHA-256 `89ad7c9947c4b81f28db3f0d02944992dde74854c8d36854b4e3945c8a068d19`. Both original OTA slots have `0x3F0000` bytes; this leaves **1,475,824 bytes** per slot. The installer proposes only `0xE00000` for the app.
- Two separately compiled external source/build directories produced byte-identical app, bootloader, generated partition table and initial otadata artifacts using the shared pinned IDF/compiler/registry cache. Cross-machine reproduction was not tested.
- Review ZIP: **1,696,059 bytes**, SHA-256 `53066b4a5af86606a8a9e29c1cf8f751f8d3ad74edd24657c0f3dde4a4701ec4`. Its authenticated public download and the app download were rehashed successfully; anonymous ZIP access was refused. The current release response remains `installable: false`.
- Sixteen offline firmware tests passed. Thirteen Node tests passed, including simulated full-flash comparison/write ordering and verification failure. The 45-test Django suite passed, followed by all four firmware-delivery/publisher tests after the final publisher test was added. No real publisher key/release was generated by tests.
- Actual candidate app and bootloader bytes passed the browser image parser's P4 revision, checksum and appended digest checks. The actual bundle plus explicitly synthetic stock bytes passed the offline plan/recovery extraction check; no owner's private backup was accessed by that test.
- Actual-template browser tests passed local synthetic backup import, no-upload behavior, release blocking and 390/768/1440 px layouts. The deployed private-instance software fixture passed USB selection, pairing/exchange, heartbeat, pending settings and revocation; temporary fixture records were removed. Physical Web Serial/flash, native peripherals, C6 and recovery remain unvalidated.
- Existing AMPVE audio/tunnel and NEUROSIS services remained active. Production checks report only the two previously documented HSTS policy warnings.
