# Firmware build reproduction evidence

Reproduction applies to one exact firmware revision, configuration and trust input. A new firmware revision does not inherit an older artifact's evidence. This check never signs a release, accesses a device or approves installation.

Use `firmware/tools/build.sh` with the pinned external ESP-IDF/tooling paths from [NATIVE_FIRMWARE.md](NATIVE_FIRMWARE.md), and a new `AMPVE_WORK` directory outside every Git repository. An absent directory is cloned at the pinned XiaoZhi revision and receives the integration from source. Retain the complete build log and exit result. Use a different directory for the second build; never copy the first `build/` directory, object files or artifacts into it. For an OTA-enabled software fixture, both builds must use the same public-only testing trust input; production signing secrets are unnecessary.

The normal build checks the resolved component set/version/hash against the lockfile. Exact patch anchors and source pins reject unsupported upstream changes. IDF checks application capacity against the real partition table, and the review packager checks that the image fits both OTA slots. These checks establish static compatibility/capacity, not measured heap, stack, latency or power budgets. Those remain physical tasks #31–#33.

After both builds finish, package the current source with a fresh output directory:

```bash
"$AMPVE_TOOL_PYTHON" firmware/tools/release.py \
  --work /private/first-project \
  --comparison-work /private/second-project \
  --idf "$AMPVE_IDF_PATH" \
  --output /private/new-review-bundle
```

The comparison rejects the same project, symlink aliases, nested projects, a build directory outside its project, copied CMake configuration pointing to another source, shared/hard-linked artifacts, escaping artifact paths, missing files and hash differences in either build. It compares all artifacts listed by the packager, including the app, generated bootloader, table and initial otadata. Generated boot metadata remains review material, not permission to flash it.

`bit_reproducibility.verified` means those bytes matched across distinct configured directories. It does not prove that a compiler ran; an intentional file copy can recreate matching bytes. Keep build logs and source/configuration provenance as separate evidence. Two builds on this VPS still share the pinned ESP-IDF/compiler and registry cache. Cross-machine/toolchain reproduction and supply-chain authenticity are separate claims.

The synthetic tests in `firmware/tests/test_reproducibility.py` cover intentional path/configuration/hash failures without invoking a compiler. Run them with the firmware tooling virtualenv as part of `python -m unittest discover -s firmware/tests`. No PR workflow receives production signing/device/provider secrets; this local check only produces non-installable review packages.
