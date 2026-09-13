# Browser installation and stock-preserving review

Implementation: browser audit, local backup/import, signed-release gate, exact plan/recovery preparation, bounded app-first writer and pairing handoff. **Physical browser reads/writes are not yet tested. No release is approved for this unit.** See [ADR 0004](../decisions/0004-stock-preserving-browser-installation.md).

Current preparation and remaining exact-unit evidence: [FIRST_INSTALLATION.md](FIRST_INSTALLATION.md).

## Owner test flow

1. Open `https://ampve.com/devices/add/` in desktop Chrome or Edge and connect the programming USB port. **Connect and check device** selects the port and performs the temporary read-only inspection. Confirm the suggested printed board name; a shared chip/USB identifier does not establish the complete model.
2. Choose **Save a backup to my computer**, or **I already have a backup** and select the two saved copies plus their capture record. New captures use two independent reads and rehash the saved files automatically. Existing imports skip capture and rehash locally. Keep a separate-storage copy. **I already started setup** exposes the resume route without claiming a fresh hardware check.
3. After backup verification, AMPVE automatically checks the release and prepares the supported option. **Check installation again** retries availability when a new release is published. This 7B profile currently supports only keeping the original software while AMPVE becomes the running application. Replacement is not offered. A missing approved release is an explicit unavailable state, not an instruction to manually flash a candidate.
4. **Save return-to-original files** saves and rehashes the generated private recovery files. When the engineering review and signed release are available, confirm the displayed installation and **Install AMPVE**. It rechecks current hardware, signed approval and the complete flash against the backup, writes/readbacks the app, then changes boot selection. Keep stable power and leave the tab/cable connected. A stock boot may change backup bytes and require fresh capture.
5. After actual AMPVE startup, use the board's Wi-Fi screen and the browser Wi-Fi controls (or the protected local portal). Enter the board's temporary AMPVE pairing code to open its dashboard. Only an authenticated heartbeat establishes online status. Native voice and physical OTA remain separate acceptance milestones.

Ordinary users do not need a terminal, candidate ZIP, hash interpretation or JSON sharing. Optional **Technical details and support** contains persistent downloadable backup/installation summaries for the initial engineering review. If browser download handling blocks a click, use **Save link as** on the same link. Summaries stay local until explicitly shared; raw backups are never uploaded. The developer-reported earlier missing download was not reproduced in fixtures; persistent links replace the transient click/revoke flow and repeated downloads are covered.

If startup/write verification fails, keep the original private backups and generated recovery files. Use the exact reviewed USB recovery procedure. Do not erase the whole chip or improvise a partition/bootloader rewrite. Automatic rollback on the stock bootloader is not yet established.

## Complete the local review without uploading flash

The browser flow above is the normal owner route. The following offline commands are optional engineering tools, not required onboarding steps.

The candidate ZIP is available through the authenticated review download after selecting verified backups. Extract it into a new private directory alongside the completed audit. From this branch's checkout, use the existing pinned firmware-tools Python on Windows (replace paths with the actual private directories):

```powershell
& 'PATH_TO_FIRMWARE_TOOLS\Scripts\python.exe' firmware/tools/compare.py --audit 'PRIVATE_AUDIT_DIRECTORY' --candidate 'EXTRACTED_REVIEW_DIRECTORY'
& 'PATH_TO_FIRMWARE_TOOLS\Scripts\python.exe' firmware/tools/installation_plan.py --audit 'PRIVATE_AUDIT_DIRECTORY' --candidate 'EXTRACTED_REVIEW_DIRECTORY' --output 'NEW_PRIVATE_PLAN_DIRECTORY'
```

Both commands are offline and contain no hardware writes. The second rechecks actual candidate/generated-table/SDK hashes, stock images, empty target slot and boot selection. It generates exact proposed writes, corresponding recovery regions, and a sanitized `review-summary.json` suitable for sharing after local inspection. Keep every `.bin`, `installation-plan-private.json` and original audit private. If the tool refuses the actual subtype/flags or boot-selection state, report the sanitized failure and review it; never weaken the validator.

The stock bootloader/table hashes, stock image header metadata and C6 compatibility evidence are needed to finish review. P4 backup bytes cannot prove C6 firmware identity or physical restore. Lucas has confirmed the original application boots after the 2026-09-13 audit; the owner now also confirms a separate-disk backup copy.

## Build and package

Current source version is recorded in `firmware/xiaozhi/upstream.json`; it uses the [shared versioned hardware profile](HARDWARE_PROFILES.md). New candidate/publication manifests must include its exact compatibility tuple. Old signed/candidate manifests cannot be made installable by manually adding a profile flag; rebuild and review the actual candidate. Existing private stock backups are unaffected.

Use the existing pinned external toolchain and `firmware/tools/build.sh` from the native runbook. It regenerates stale SDK configuration when moving from the old layout, copies the explicit stock CSV, and builds the recorded candidate version. The runtime rejects the wrong app slots/factory map before NVS/driver initialization.

`release.py` verifies the actual P4 image and produces the review directory plus a private ZIP sibling. The bundle includes generated bootloader/table/initial-otadata files for comparison only. Their presence does not authorize writing them. `proposed_regions_not_approved_writes` names only the app at `0xE00000`; exact otadata is generated locally from the owner's original selection.

The code default is `/home/ampve/.local/state/ampve/firmware-review-stock-v1`; this VPS now explicitly selects `firmware-first-install-review-02`, the current real-key unsigned candidate documented in [FIRST_INSTALLATION.md](FIRST_INSTALLATION.md). Its app and ZIP are accessible only to signed-in users. No upload endpoint exists for device backups. No candidate flag can enable installation.

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


Improv development update (2026-09-13): the onboarding page now offers USB Wi-Fi setup after AMPVE startup, using the pinned Improv browser SDK and the candidate's physically authorized UART service. It shares serial-operation controls with audit/backup/install, clears the password field before sending, and keeps pairing separate. The protected local portal remains available. See [NATIVE_WIFI.md](NATIVE_WIFI.md) for protocol, SDK fixes, simulated tests and required physical P4/C6 validation. This does not enable an unapproved installation release.

## Share review metadata from the browser

After a completed two-backup capture or a verified import, select **Download shareable review summary**. The local `ampve-review-summary.json` contains the configured profile contract, backup/table/bootloader-region hashes, numeric partition/image metadata, layout/empty-slot results and remaining review gates. Inspect the JSON before choosing to share it manually. The page performs no upload and does not include flash bytes, MAC addresses, file paths, Wi-Fi data or application-descriptor strings. Hashes still identify a particular backup state; share only with the intended reviewer.

The summary explicitly distinguishes `live-browser-capture` from `imported-capture-record`. Matching imported files and an owner-supplied capture record are not a new physical read or proof of current chip/security state. Every export remains `installable: false`; it neither approves a release nor supplies ownership proof. It helps the initial fingerprint/layout review without requiring a private dump upload. Exact candidate comparison, private write/recovery preparation, C6 review, separate-storage confirmation and current-unit checks remain required.

Software fixtures exercise a downloaded summary from the actual rendered onboarding page, verify its table/bootloader-region hashes against synthetic backup bytes, and confirm that private identity/path fields do not escape. The parser uses an explicit field allowlist and bounded numeric/hash values; it never spreads the imported capture record into the output. No physical read/write is established by these fixtures.

Review-export evidence (2026-09-13): 28 Node tests, seven Django firmware-delivery tests and the Chromium onboarding fixture passed. The browser fixture downloaded and parsed the real JSON output from synthetic 32 MiB backups, checked the table/bootloader hashes, confirmed private-field exclusion and no uploads, and retained installation gating at three viewport widths. The summary is metadata for manual review, not a completed stock/C6/restore approval.

Browser plan preparation update (2026-09-13): unsigned candidates can now be compared and recovery files generated entirely locally in the browser. The plan export explicitly remains non-installable and includes no raw backup, identity, paths or application descriptor strings. Signed-release verification and final live comparison remain mandatory for writes. Validation: 29 Node tests, seven Django firmware-delivery tests and the actual-template Chromium fixture passed, including candidate comparison, saved/rehashed recovery, exact plan-summary download, blocked unsigned installation and no uploads. These are software fixtures, not physical writes.
