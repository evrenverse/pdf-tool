# Contributing

Issues and focused pull requests are welcome.

## Development

1. Install Python 3.12 or newer and uv. Install Poppler (`pdftoppm` on `PATH`,
   package `poppler-utils`) to exercise page rendering; those tests skip
   without it.
2. Create a branch and add tests for behavior changes.
3. Run the same local gate used by CI:

   ```bash
   make install
   make check
   make build
   make audit
   ```

4. Update `README.md`, the bundled skill, and `CHANGELOG.md` for user-facing
   changes.

Preserve stable JSON fields, bounded output, zero-indexed pages, useful exit
codes, and atomic writes. Fixtures must be synthetic or redistributable and
must not contain personal, customer, certificate, or company data.

## Pull requests

Keep changes focused and explain the user or agent workflow they improve. Add
tests for behavior, error paths, and limits. A contract change also needs
updated schemas and eval coverage. Prefer conventional commit subjects such as
`feat:`, `fix:`, `docs:`, `test:`, or `chore:`.

By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
