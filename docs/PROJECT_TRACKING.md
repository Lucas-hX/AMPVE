# ESP32 delivery tracking

The canonical task board is [AMPVE — ESP32 Onboarding and Device Lifecycle](https://github.com/users/Lucas-hX/projects/10), linked to this repository. [Tracking issue #6](https://github.com/Lucas-hX/AMPVE/issues/6) owns the detailed implementation and validation issues. GitHub issues/project fields hold live status; this document explains scope and workflow rather than duplicating the backlog.

## Target outcome

A supported ESP32 can be audited and privately backed up through the browser, receive a reviewed first AMPVE installation, connect to Wi-Fi, pair with its owner, report its capabilities and software, accept dashboard settings, discover eligible releases and update over Wi-Fi with verified startup or recovery.

The first profile is Waveshare ESP32-P4-WIFI6-Touch-LCD-7B revision 1.3. A second precisely identified common ESP32 development board will prove the generic workflow. Selecting that board and confirming physical availability are explicit tasks; an ESP32 chip family is not a compatibility guarantee. A headless board without audio supports management, not an invented Companion voice capability. Raspberry Pi/Linux runtimes, arbitrary application marketplaces, camera and robotic motion are future scope.

## Workstreams

| Stage | Milestone | Issues |
| --- | --- | --- |
| M1 | P4 baseline, compatibility and recoverable first installation | #7–#12 |
| M2 | Browser audit, private backups, installation and Wi-Fi provisioning | #13–#18 |
| M3 | Enrollment, heartbeat, settings acknowledgement and diagnostics | #19–#23 |
| M4 | Signed releases, deployment tracking, app-only OTA and dashboard updates | #24–#28 |
| M5 | Select and validate one second common ESP32 profile | #29–#30 |
| M6 | XiaoZhi–Pipecat adapter and native Companion experience | #35–#36 |
| M7 | Measured resource budgets, footprint, scheduling and regression checks | #31–#34 |
| M8 | Physical end-to-end acceptance and operating/recovery documentation | #37–#38 |

Stage is a workstream, not a strict calendar sequence. Follow the dependencies in each issue: release trust precedes installer/OTA enablement, and performance measurements should begin early. There are no invented completion dates or promised optimization percentages.

## Agent and maintainer workflow

1. Read AGENTS.md, current product/implementation documents and device/native runbooks; inspect current code, branches, PRs and the issue before starting. PR #5 is the native candidate baseline at board creation, not a permanent assumption about the latest code.
2. Select work whose prerequisites are met. Readiness is separate from Status: Todo does not mean a blocked or hardware-dependent issue is ready to execute. Use the parent tracker and native blocking relationships.
3. Use an issue-linked branch/PR. Record scope adjustments, evidence, discovered blockers and results in the corresponding issue. Keep code, UI, documentation and task content in English.
4. Set In Progress only for actual work. Hardware required and Needs decision are explicit readiness states. Lucas reports two completed matching Windows reads and confirms stock startup after reset. Separate-storage confirmation is still pending; those facts do not establish a physical restore. The stock-preserving/browser implementation is tracked in ADR 0004 and the browser installation runbook.
5. Close a task only when its acceptance criteria and appropriate validation pass and its implementation is merged, or a non-code result is accepted. Do not use automatic closing keywords to bypass pending physical tests. Update project readiness when prerequisites change.

The Project provides Status, Stage, Priority, Area and Readiness fields. P0 denotes a safety or critical lifecycle gate; P1 denotes a required product capability. P2 is reserved for optional follow-up work. All work, Delivery board, Hardware gates and Ready to start views expose different slices of the same issues.

## Safety and evidence

Reuse XiaoZhi, ESP-IDF, ESP Web Tools/Improv and Pipecat. Keep Django/PostgreSQL, the audio service and existing Cloudflare tunnel appropriate to one VPS. A broker or external fleet platform is not an assumed dependency.

- Browser audit and backup tasks require visible phases, measured byte progress, throughput, honest ETA/unknown states, cancellation and partial-file handling. Sensitive flash/NVS data stays local.
- Initial installation requires exact profile/security/layout checks, verified backups, a reviewed write/restore plan and the owner's applicable hardware-write approval. Task creation, assignment or PR merge is not that approval.
- No generic full-chip erase, automatic destructive NVS reset, eFuse provisioning, Secure Boot activation or flash-encryption provisioning is included.
- Firmware OTA uses authentic compatible app releases, an inactive app slot, verified startup and physically tested recovery. A stock partition-map replacement is not ordinary app OTA.
- Keep owner isolation, revocable identity, local mute/stop and secret redaction. Provider/device credentials and raw audio never belong in issues, logs or firmware examples.
- Label fixture/simulation evidence separately from actual hardware results. Compilation proves a build, not screen/audio/Wi-Fi operation, safe installation or recovery.
- Optimize against measured boot/UI latency, internal heap/PSRAM, stack headroom, CPU, traffic, NVS writes and app size. Retain recovery and security; measure electrical power only with appropriate hardware.
