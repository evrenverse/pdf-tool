# pdf-tool

[![CI](https://github.com/evrenverse/pdf-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/evrenverse/pdf-tool/actions/workflows/ci.yml)
[![CodeQL](https://github.com/evrenverse/pdf-tool/actions/workflows/codeql.yml/badge.svg)](https://github.com/evrenverse/pdf-tool/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/evrenverse/pdf-tool/badge)](https://scorecard.dev/viewer/?uri=github.com/evrenverse/pdf-tool)
[![PyPI](https://img.shields.io/pypi/v/pdf-tool.svg)](https://pypi.org/project/pdf-tool/)
[![Python](https://img.shields.io/pypi/pyversions/pdf-tool.svg)](https://pypi.org/project/pdf-tool/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An agent-friendly CLI for inspecting, creating, filling, editing, splitting,
merging, and signing PDF files. Commands favor bounded reads, structured JSON,
useful exit codes, upfront validation, and atomic writes.

The repository is also a skills-only Codex plugin. Its portable Agent Skill is
under [`skills/pdf-tool`](skills/pdf-tool).

## Why agent-native

This is not a thin wrapper branded for AI. The executable exposes a versioned,
machine-readable contract; keeps page and field reads bounded; separates JSON
stdout from diagnostics; limits document and batch input; publishes mutations
atomically; and ships a synthetic locate-edit-verify eval that drives the real
CLI. An agent can discover capabilities without opening a user document:

```bash
pdf-tool capabilities --json
pdf-tool doctor --json
pdf-tool schema batch
pdf-tool version --json
```

## Give this repository to an agent

Copy this prompt:

> Inspect https://github.com/evrenverse/pdf-tool and follow `AGENTS.md`.
> Install `pdf-tool`, verify it with `pdf-tool --version`, install the bundled
> `pdf-tool` skill for this project, then use the CLI instead of writing a
> one-off PDF script.

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install pdf-tool
pdf-tool --version
```

Directly from GitHub before the first PyPI release:

```bash
uv tool install git+https://github.com/evrenverse/pdf-tool
```

From a clone:

```bash
uv sync --all-groups --locked
uv run pdf-tool --version
uv run pytest
```

Python 3.12 or newer is required.

Rendering pages with `read --image` additionally requires Poppler
(`pdftoppm`) on `PATH`. For example, install `poppler-utils` on Debian/Ubuntu
or `poppler` with Homebrew. All other commands work without Poppler.

## Install the Agent Skill

For a project-local Agent Skills installation:

```bash
mkdir -p .agents/skills
cp -R skills/pdf-tool .agents/skills/pdf-tool
```

Codex can also load the repository as a skills-only plugin because
`.codex-plugin/plugin.json` is included. Claude Code users can copy the same
folder to `.claude/skills/pdf-tool`.

## Quick start

```bash
# Discover document structure and fields
pdf-tool info form.pdf --json
pdf-tool field-info form.pdf --json

# Find text or fields without dumping every page
pdf-tool find form.pdf "Invoice total" --pages 0-3 --json

# Read a page range or selected form values
pdf-tool read form.pdf --pages 0,2,5 --json
pdf-tool read form.pdf --fields Company,Date,TermsAccepted --values-only

# Validate and fill an AcroForm
echo '{"Company":"Example LLC","TermsAccepted":true}' \
  | pdf-tool fill form.pdf - --validate-only --json
echo '{"Company":"Example LLC"}' | pdf-tool fill form.pdf -

# Overlay text, split, merge, or create a new document
echo '[{"page":0,"x":200,"y":150,"text":"Approved"}]' \
  | pdf-tool write form.pdf -
pdf-tool split form.pdf --pages 0-2,5 --output extract.pdf
pdf-tool merge a.pdf b.pdf --output merged.pdf
pdf-tool create output.pdf source.md
```

Commands:

| Command | Purpose |
| --- | --- |
| `info` | Show pages, dimensions, metadata, and form fields |
| `field-info` | Show field types, rectangles, and allowed values |
| `find` | Locate text and form fields |
| `read` | Extract text, tables, selected fields, or page images |
| `fill` | Validate and fill AcroForm fields |
| `write` | Add text overlays |
| `sign` | Add a visual and optional cryptographic signature |
| `batch` | Apply fill, overlay, and signature operations transactionally |
| `merge` | Merge PDFs |
| `split` | Split or extract page selections |
| `create` | Create a PDF from a Markdown subset |
| `capabilities` | Print the versioned agent contract |
| `doctor` | Check runtime and optional dependencies |
| `schema` | List or print bundled JSON Schemas |
| `version` | Print tool and contract versions |

Run `pdf-tool <command> --help` for the complete syntax.

## Signing without leaking a passphrase

Never put a certificate passphrase directly in command arguments or batch JSON.
Use a private file:

```bash
chmod 600 certificate-passphrase.txt
pdf-tool sign document.pdf \
  --signature signature.png \
  --certificate signer.p12 \
  --passphrase-file certificate-passphrase.txt \
  --page 0 \
  --position 350,650,150,50
```

For automation, provide `PDF_TOOL_CERT_PASSPHRASE` through the agent or CI
secret store. Use `--no-passphrase` only for a certificate that intentionally
has an empty passphrase.

## Overlay coordinates

`write` accepts an array:

```json
[
  {
    "page": 0,
    "x": 100,
    "y": 200,
    "text": "Value",
    "font": "Helvetica",
    "font_size": 11
  }
]
```

Pages are zero-indexed. Coordinates use a top-left origin by default. Add
`image_width` and `image_height` for rendered-image coordinates, or
`pdf_width` and `pdf_height` for bottom-left PDF coordinates. Rotated pages
produce a warning because viewer and media-box coordinates differ.

Standard overlay fonts are WinAnsi-limited. `create` embeds DejaVu Sans when
available and otherwise ReportLab's bundled Bitstream Vera. Neither option
covers every Unicode script; use `PDF_TOOL_FONT_DIR` to select a complete
DejaVu family.

## Safe automation contract

- JSON goes to stdout; diagnostics go to stderr.
- Pages are zero-indexed across commands.
- Missing searches and all-missing field reads return exit code `1`.
- Mutating commands validate inputs before writing.
- Destination files are replaced atomically only after successful output.
- The tool has no telemetry and performs no runtime network requests.

PDF parsing and rendering libraries process complex, potentially hostile data.
For untrusted files, use operating-system sandboxing and least-privilege
filesystem access. See [SECURITY.md](SECURITY.md).

## Development

```bash
make install
make check
```

The quality gate includes formatting, linting, mypy, branch coverage, package
build, and the real CLI agent eval. CI additionally tests Python 3.12–3.14,
Linux with and without Poppler, known vulnerabilities, CodeQL, and dependency
changes.

## Project documentation

- [Architecture](docs/architecture.md)
- [Agent contract](docs/agent-contract.md)
- [Threat model](docs/threat-model.md)
- [Compatibility](docs/compatibility.md)
- [Release process](docs/release-process.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), and
  [support](SUPPORT.md)

## License

[MIT](LICENSE)
