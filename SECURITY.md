# Security policy

## Supported versions

Security fixes are provided for the latest released version.

## Report a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open
a public issue containing exploit details, certificates, passphrases, or
sensitive documents. Include the affected version, impact, reproduction steps,
and any suggested mitigation.

## Trust model

PDFs are complex, attacker-controlled inputs. This CLI delegates parsing,
rendering, form handling, and signing to maintained open-source libraries.
Run untrusted documents with the least filesystem access practical and keep the
locked dependencies current. `read --image` also trusts the installed Poppler
utilities.

The CLI has no telemetry and performs no runtime network requests. Mutating
commands write a same-directory temporary file and atomically replace the
destination after success.

Certificate passphrases are never accepted as command arguments or in batch
JSON. Supply them through a mode-0600 file, a secret environment variable, or
an interactive hidden prompt. Environment variables may still be observable
to privileged local processes; use an appropriate secret store and short-lived
execution environment.
