# Changelog

All notable changes are documented here. This project follows Semantic
Versioning and keeps an [Unreleased] section.

## [Unreleased]

- Raise the `pypdf` security floor to 6.16.1 and lock 6.16.2 to address
  CVE-2026-84309, CVE-2026-84310, and CVE-2026-84311.

## [0.1.0] - 2026-07-24

- Prepare the independent public release.
- Add an Agent Skill and Codex plugin manifest.
- Use a current, maintained PDF dependency stack.
- Accept certificate passphrases only through private files, environment
  secrets, or hidden interactive input.
- Use portable embedded fonts and atomic output for PDF creation.
- Add a versioned, machine-readable Agent Contract with capabilities, doctor,
  version, and bundled JSON Schema commands.
- Add explicit document and JSON/batch limits, property tests, mypy, branch
  coverage enforcement, and a real CLI locate-edit-verify eval.
- Add CI, CodeQL, dependency review, OpenSSF Scorecard, SBOMs, and provenance
  attestations with commit-pinned GitHub Actions.
- Add architecture, threat-model, compatibility, release, support, governance,
  and public-publishing documentation.

[Unreleased]: https://github.com/evrenverse/pdf-tool/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/evrenverse/pdf-tool/releases/tag/v0.1.0
