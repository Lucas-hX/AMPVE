# AMPVE Reader

AMPVE Reader is the active application for the first supported Waveshare 7B. The private web library separates collections, books and ordered PDF parts, including virtual page ranges that leave the original source unchanged.

Source PDFs remain private on the AMPVE server. The platform records a SHA-256 digest and stores each upload under a randomized path. Device content is a later deterministic derivative with its own signed manifest; the original PDF is not an application package.

## First device storage boundary

The first Reader has no microSD or SD-card support and Core Lite omits FAT and every removable-storage path. The board's ESP32-C6 Wi-Fi coprocessor is physically connected over ESP-Hosted/SDIO, so the minimal firmware necessarily retains ESP-IDF's SDMMC/SDIO transport component exclusively for Wi-Fi; it is not exposed to Reader and never mounts storage. Prepared books may later use a strict quota in the board's existing 5 MiB internal `storage` partition (`0x1AF0000`–`0x1FEFFFF`, inclusive). That partition belongs to the preserved stock layout, so Reader must not mount, format or write it until its current bytes have been privately audited and backed up and the exact migration has been approved.

Internal space is deliberately limited. The preparation pipeline must generate compact display-sized derivatives, reserve room for an interrupted transfer, verify every file before activation and evict content without losing server-side library metadata or reading progress. Actual usable quota remains pending a reproducible firmware build and physical storage validation.

## Reader MVP

The first deployable slice uses deterministic reflowed text instead of an embedded PDF engine. Preparation is an explicit operator command, outside the upload request. It records small screens with their source-PDF page while leaving the source immutable. The authenticated device API exposes only owner-selected prepared books, one bounded screen at a time, and synchronizes reading progress.

The dashboard supports upload, collections, multi-part books, part order, virtual ranges, device shelf selection and reading notes. The firmware renders a low-glare, e-paper-inspired view with touch navigation. This MVP is online-only and never touches `storage`; a network interruption leaves Core management and recovery available but cannot load a new page.

Prepare pending uploads after deploying migrations:

```bash
.venv/bin/python apps/platform/manage.py prepare_reader_documents --limit 10
```

Pending: a separately reviewed parser sandbox, signed offline content manifests, interrupted-transfer staging, measured internal-flash quota, eviction, richer typography, orientation sensing and physical acceptance of the complete PDF-to-device path.
