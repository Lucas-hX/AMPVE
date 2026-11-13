# AMPVE Reader

AMPVE Reader is the active application for the first supported Waveshare 7B. The private web library separates collections, books and ordered PDF parts, including virtual page ranges that leave the original source unchanged.

Source PDFs remain private on the AMPVE server. The platform records a SHA-256 digest and stores each upload under a randomized path. Device content is a later deterministic derivative with its own signed manifest; the original PDF is not an application package.

## First device storage boundary

The first Reader has no microSD or SD-card support. Core Lite omits the FAT and SDMMC driver surface. Prepared books will use a strict quota in the board's existing 5 MiB internal `storage` partition (`0x1AF0000`–`0x1FEFFFF`, inclusive). That partition belongs to the preserved stock layout, so Reader must not mount, format or write it until its current bytes have been privately audited and backed up and the exact migration has been approved.

Internal space is deliberately limited. The preparation pipeline must generate compact display-sized derivatives, reserve room for an interrupted transfer, verify every file before activation and evict content without losing server-side library metadata or reading progress. Actual usable quota remains pending a reproducible firmware build and physical storage validation.

## Current status

Implemented now: authenticated PDF upload, private download, collections, books, ordered parts, virtual ranges, stable progress records and later device-selection revisions.

Pending: sandboxed PDF inspection, deterministic derivatives, signed content manifests, internal-flash synchronization, on-device rendering and physical acceptance. No Core Lite or Reader firmware artifact has been built, signed or deployed.
