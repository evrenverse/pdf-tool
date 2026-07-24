---
name: pdf-tool
description: Inspect, search, read, render, create, fill, overlay, merge, split, batch-edit, and sign PDF files with the pdf-tool CLI. Use when an agent must work with PDF text, pages, tables, AcroForm fields, coordinates, or signatures while keeping reads bounded, emitting JSON, validating operations, and verifying the result.
---

# PDF Tool

Use `pdf-tool` instead of writing a one-off PDF manipulation script.

## Prepare

1. Run `command -v pdf-tool`.
2. If missing and this repository is available, run `uv tool install .`.
   Otherwise run `uv tool install git+https://github.com/evrenverse/pdf-tool`.
3. Run `pdf-tool --version`.
4. Run `pdf-tool capabilities --json` and `pdf-tool doctor --json`.
5. Use `pdf-tool schema <name>` when constructing structured input.
6. Work on a copy unless the user explicitly wants an in-place edit.

## Inspect before editing

1. Run `pdf-tool info <file> --json`.
2. For forms, run `pdf-tool field-info <file> --json`.
3. Use `find`, `read --pages`, or `read --fields`; avoid dumping the complete
   document when a scoped read is enough.

## Edit and verify

1. Use `fill --validate-only` before filling a form.
2. Prefer `batch` when fill, overlay, and signature operations belong in one
   transaction.
3. Never put a certificate passphrase in arguments or JSON. Use
   `--passphrase-file` or the `PDF_TOOL_CERT_PASSPHRASE` secret environment
   variable.
4. Run `info`, `read`, or `field-info` on the output.
5. Report the output path and any font, rendering, or signature limitation.

Use zero-indexed page numbers. Keep an untouched copy of important documents.

Read [references/cli.md](references/cli.md) when exact syntax, dependencies, or
exit behavior is needed.
