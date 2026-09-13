# Signed firmware publication and trust

## USB-assisted commissioning update — 2026-09-13

[ADR 0005](../decisions/0005-usb-assisted-commissioning.md) supersedes the mandatory pre-install C6 check **only for an explicitly signed USB-assisted initial-install release**. The platform prepares the same exact stock-preserving write/recovery plan, then checks the installed core over USB before network provisioning. A failed C6 version query remains a diagnostic finding, not proof of incompatibility or a mandatory gate for this mode. Core confirmation, Wi-Fi initialization, actual network operation, pairing and physical recovery are separate evidence. The browser now exposes explicit original-backup restoration with fresh full-flash comparison; it is not yet physically validated. Other releases retain their existing gates.

The publisher supports schema-2 signed **initial-install** and **OTA** policies. Sequence 1 now has a signed USB-assisted development first-install release for the exact 7B stock profile. Its engineering approval deliberately defers physical startup/recovery and C6/Wi-Fi acceptance; it is not an OTA or production approval. The runtime selection and evidence are recorded in FIRST_INSTALLATION.md. See [FIRST_INSTALLATION.md](FIRST_INSTALLATION.md). Device deployment APIs and the native OTA client are implemented as development work; see [FIRMWARE_DEPLOYMENTS.md](FIRMWARE_DEPLOYMENTS.md) and [NATIVE_OTA.md](NATIVE_OTA.md). Physical OTA/rollback remains unvalidated, and preparing a policy does not authorize installation.

## Identity, ordering and evidence

A release ID is the SHA-256 of its exact canonical signed JSON payload. The payload binds the publisher key ID, a positive monotonic sequence, development channel, delivery purpose, hardware contract, app bytes/version and exact build/review provenance. Changing any signed field produces a different ID. Duplicate/unknown JSON fields, noncanonical payloads, malformed or expired approvals, wrong profiles, changed app/archive hashes and unknown/revoked keys are rejected. Only UTC timestamps of the form `YYYY-MM-DDTHH:MM:SSZ` are accepted; promotion approvals last at most 31 days.

The human-readable firmware version is descriptive; never sort it lexicographically for updates. A single private SQLite publisher ledger serializes publication sequences for each compatibility tuple/channel. Reusing an equal/lower sequence fails even with a different output directory or simultaneous publishers. A failed/interrupted attempt can consume a sequence; retain that reservation and use a higher one. This is an offline tool ledger, not a second platform database or a device-management service. Keep using the same ledger, back it up with the publisher records, and never delete it to bypass ordering.

Published output uses a new, exclusive directory, contains read-only app/provenance files, and exposes the signed envelope only after artifacts exist. Filesystem modes prevent accidental editing, not changes by a privileged operator. Signatures and hashes detect such changes when the server next reads the release. Preserve old directories for evidence; do not replace an existing release in place. Back up the original review bundle and source/dependency/license evidence as well as the ledger.

The publisher verifies the actual P4 image through pinned esptool, its version and reviewed digest, archived manifest/app/configuration/lock hashes, build reproduction evidence and third-party notices. New review ZIPs use sorted entries, fixed timestamps and normalized modes. Repacking the exact same tree produces identical ZIP bytes despite different file mtimes. Bundles from separate build paths can still differ because provenance contains actual paths; the independently compiled binary comparison remains a separate check.

## Prepare and verify after engineering review

Use the **firmware-tools Python**, installed from `firmware/tools/requirements.txt` (esptool 5.4.0, Pillow 12.1.1, cryptography 50.0.1). The Django server keeps its existing cryptography dependency. Keep signing keys, release output and the ledger outside every Git checkout. No command below accesses hardware or activates a release.

1. Build/package the exact candidate with the documented `build.sh` and `release.py` commands, including comparison with the second build. Complete stock bootloader/C6/resource/recovery review before promotion. A candidate remains non-installable.
2. `publish_release.py init-key --directory NEW_PRIVATE_KEY_DIRECTORY` creates a private/public Ed25519 pair. Protect a separate private-key backup. No build or test creates a production key automatically.
3. Prepare a private review JSON with exactly `key_id`, `sequence`, `channel` (`development`), `purpose` (`initial-install` or `ota`), `bootloader_sha256`, `table_sha256`, `app_sha256`, `bootloader_review`, `c6_review`, `recovery_review`, and `expires_at`. Reviews must reference completed engineering evidence, not placeholders. Hashes identify actual reviewed bytes. The sequence must exceed the ledger high-water mark.
4. For **OTA**, add `ota_review` documenting completed physical recovery/rollback validation and `from_app_sha256`, a nonempty list of distinct reviewed predecessor app hashes. OTA policy contains only the app's size/hash, **no flash offset** and no ESP Web Tools manifest. The native updater must select its inactive app slot. Initial-install policy instead includes the fixed reviewed USB app offset; it cannot serve as OTA authorization. The browser refuses an OTA policy.
5. Run `publish_release.py publish --approve-reviewed-development-release --candidate REVIEW_DIRECTORY --review REVIEW_JSON --key PRIVATE_KEY --ledger PRIVATE_LEDGER.sqlite3 --output NEW_RELEASE_DIRECTORY`. This signs the reviewed metadata and archives evidence, but changes no server selection or device. The command prints the immutable release ID, never key material.
6. Create a separate trust registry from [`infra/firmware-publisher-trust.example.json`](../../infra/firmware-publisher-trust.example.json). Independently verify the public key and its ID/purpose/channel scope. Do not trust a key merely because a release supplies it. Store this registry privately outside the artifact directory. Set `firmware_publisher_trust` in private platform configuration to its path; the default is `/home/ampve/.config/ampve/firmware-publisher-trust.json`.
7. Run `publish_release.py verify --release RELEASE_DIRECTORY --trust TRUST_JSON`. It verifies the signature, scope, sequence floor, revocations, expiry and app/archive bytes. After review, an initial-install release can be selected with `firmware_release_root` using the ordinary platform check/restart procedure. **No active approved release is configured by default.**

Legacy schema-1 releases and the single `firmware_publisher_public_key` setting cannot authorize installation now. There were no approved real releases to migrate. Retain existing candidate/backups for review, then explicitly publish a schema-2 policy with current engineering evidence; do not edit an old signed payload.

## Rotation, revocation and downgrade policy

The independently administered registry maps key IDs to public keys, allowed channels/purposes and explicit revocation flags. It also lists revoked release IDs and a positive minimum sequence. The platform rereads it for each metadata/artifact operation. Publish registry changes atomically so readers cannot see a partial file.

- **Rotate:** generate/protect a new key separately; add its independently verified public key under a new ID with the narrow intended scopes. Sign the next, higher sequence with that ID and verify it. Keep the old key trusted only while its existing releases must remain eligible, then revoke it. Do not silently substitute new key bytes under an old ID.
- **Revoke a key:** set its `revoked` flag to `true`; all releases signed by it fail new authorization checks. **Revoke one release:** append its immutable release ID to `revoked_releases`. Preserve artifacts and incident evidence.
- **Retire older releases:** raise `minimum_sequence`; never reduce it to force a downgrade. Combined with a device's confirmed sequence and explicit predecessor app hash, an OTA request must advance the sequence. The future deployment service must persist that confirmed sequence; the helper alone is not device attestation or a complete anti-replay system.
- **Recover a failed boot:** ESP-IDF fallback to the retained confirmed app is a local recovery action, separate from authorizing a new older deployment. It must remain possible even if release trust changes during an update. Do not burn eFuses or enable hardware anti-rollback as part of this development policy.

The browser verifies release identity/signature at preparation, at the installation click and again after the full live flash comparison, immediately before writing. Expiry or revocation during a long preflight prevents the first write. Once writes begin, finish app readback and boot selection; a policy change must not interrupt that critical sequence. USB hardware consent and local recovery confirmation remain separate from publisher approval.

Browser trust ultimately depends on the HTTPS platform serving the script and independently configured key. A signature does not defend against a compromised platform that can replace both script and trust response. The native OTA client will need its own authenticated trust/bootstrap/rotation implementation; this policy format does not provide that automatically.

## Validation

Run the firmware unittest suite with the pinned firmware-tools Python, the Django workspace suite and `npm test && npm run build` in `tools/browser`. Fixtures exercise signature/key/hash/profile tampering, invalid metadata, purpose substitution, revocations, sequence ordering/concurrency, deterministic ZIP output and revocation during preflight. All signing keys and images in those tests are temporary software fixtures. Physical P4/C6 operation, first installation and interrupted-update recovery remain hardware acceptance gates.

## Delivery evidence — 2026-09-13

Source `3b89760`: 51 Django tests, 26 firmware/tool tests and 17 Node tests passed. Two concurrent fixture publishers admitted exactly one reservation for a sequence. Rendered onboarding fixtures passed backup import/no-upload and three viewport widths. The deployed private-instance fixture passed pairing, schema-2 heartbeat, pending settings and revocation, then removed its temporary records.

The real unsigned candidate was repackaged in `/home/ampve/.local/state/ampve/firmware-review-trust-v2` with the unchanged `0.1.2-profile-dev` app. Repeating ZIP creation over that exact tree produced identical **1,693,914-byte** archives, SHA-256 `a81fccc30c71b7fc248f22bef3e95fc45b07a355b3fc5ada52bab48aa32f2630`. App SHA-256 remains `13e015e52ebe4b75fb83967208423623bbf32e8d0d1021f8dc518574d2222db9`. Authenticated public ZIP/app downloads were rehashed; anonymous ZIP access was refused. The platform selects this review directory through private configuration and still returns `installable: false`. No production signing key, publisher ledger/trust registry, approved release or hardware write was created by delivery.

## Persistent deployment backend

See [FIRMWARE_DEPLOYMENTS.md](FIRMWARE_DEPLOYMENTS.md) for owner requests, release import, authenticated device reports, cancellation, expiry and restart reconciliation. This backend does not establish physical OTA support; the native client and board recovery tests remain pending.

## Native client build inputs

Newly promoted candidates must include the independently provisioned native publisher trust and a build sequence matching the signed review sequence. See [NATIVE_OTA.md](NATIVE_OTA.md) for `AMPVE_NATIVE_TRUST`, public-key rotation, archived input/header hashes and the explicit testing marker. Sequence-zero builds and enabled software fixtures cannot be promoted. Earlier unsigned review bundles without these inputs must be rebuilt before release approval. This does not replace reproduction, local stock/C6/recovery review or owner hardware-write authorization.


## Release notes protected by the signed archive

Before candidate review, supply `--release-notes PATH_TO_NOTES.txt` to `firmware/tools/release.py`, alongside its normal build/comparison/output arguments. The optional file must contain nonempty plain UTF-8 text, at most 8,192 bytes. The packager copies it as the fixed top-level `release-notes.txt`, records its byte size/hash in the review manifest, and includes it in the deterministic review ZIP. Review changes, limitations and recovery requirements before publication.

The existing schema-2 policy signs the complete archive's SHA-256. Notes are therefore authenticated through that signed digest, without changing the native OTA policy or introducing a separate trust source. The publisher checks the notes against candidate provenance and rejects malformed/missing/ambiguous notes before reserving a sequence. Altering notes after publication changes the archive hash and invalidates the release. Use a new reviewed publication; never edit a published ZIP in place.

The dashboard verifies release signature, independent trust/revocation/expiry and app/archive hashes before reading notes. It reads at most 8 KiB from the exact archive member, never extracts paths, and renders plain escaped text with line breaks. Duplicate/oversized/invalid note members are not shown. Older packages without notes remain compatible and show an explicit unavailable message; the signed recovery review remains separately labelled. Invalid optional notes do not establish update permission or bypass any existing gate.

Software evidence (2026-09-13): 43 firmware-tool tests and 77 Django tests (five existing PostgreSQL-only skips) passed. Fixtures cover UTF-8/byte/control limits, duplicate/path cases, invalid-note rejection before ledger reservation, archive modification, key revocation, HTML escaping and releases without notes. Chromium exercised expanded notes across all eight update states and three viewport widths. Test signing keys are temporary fixtures; no production signing material or release was created.

Actual packaging check (2026-09-13): `release.py --release-notes` produced private `firmware-release-notes-software-fixture` from source `70ec494`. The note file, manifest byte-size/hash and archived content matched, and all four firmware artifacts retained the prior two-directory reproduction match. The package remains testing-only/non-installable; this check did not sign or select a production release.
