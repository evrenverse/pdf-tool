# Threat model

## Assets

- PDF confidentiality, integrity, and signature intent.
- Certificate keys and passphrases.
- Files available to the invoking user.
- Predictable output and host availability.

## Trust boundaries

PDF input is untrusted. pypdf, pdfplumber/pdfminer, PyPDFForm, ReportLab,
Pillow, and pyHanko are parser or mutation trust boundaries. Poppler joins the
trusted computing base only for page rendering. Local signing material is
trusted but secret.

## Main threats and controls

| Threat | Control |
| --- | --- |
| Parser or decompression resource exhaustion | Input, JSON, operation-count, and scoped-read limits |
| Partial output after failure | Validate first, write temporary output, reopen, sync, atomic replace |
| Secret exposure in process lists or logs | No passphrase CLI argument or batch field; hidden/file/env input |
| Context flooding | Page, field, and search scoping with structured results |
| Dependency compromise | Lockfile, Dependabot, dependency review, CodeQL, pip-audit, pinned Actions |
| Release substitution | PyPI Trusted Publishing, checksums from registries, SPDX SBOM, Sigstore attestations |
| Accidental document disclosure | No telemetry/runtime network; synthetic fixtures and issue policy |

## Out of scope

The CLI is not a malware sandbox, PDF/A validator, redaction guarantee, OCR
engine, or universal font/shaping system. An opaque overlay does not remove
underlying content. Run hostile files in an OS sandbox, use a dedicated
redaction tool for sensitive material, and independently validate important
signatures.

Report vulnerabilities through [SECURITY.md](../SECURITY.md).
