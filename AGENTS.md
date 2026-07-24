# Agent setup

This repository is an independent public Python CLI. Do not install unrelated
document tools when the task only concerns PDF files.

## Install for use

1. Inspect `README.md`, `SECURITY.md`, and `pyproject.toml`.
2. Prefer the published package:

   ```bash
   uv tool install pdf-tool
   pdf-tool --version
   ```

3. Before a PyPI release, install the reviewed checkout with `uv tool install .`.
4. For development, run `uv sync --all-groups --locked` and `make check`.
5. Install the project skill only when requested:

   ```bash
   mkdir -p .agents/skills
   cp -R skills/pdf-tool .agents/skills/pdf-tool
   ```

6. Run `pdf-tool capabilities --json` and `pdf-tool doctor --json` before
   choosing a workflow. Use `pdf-tool schema <name>` instead of guessing
   structured input.
7. Inspect first, make a backup, edit, and verify the output.

## Contributing

Keep stdout machine-readable, stderr diagnostic, page numbering zero-based,
and file writes atomic. Never add telemetry, embedded credentials,
organization-specific workflows, or runtime dependencies on sibling
repositories.

Run `make check`, `make build`, and the dependency audit before submitting.
User-visible contract changes must update schemas, tests, the eval, README,
skill, and changelog together.
