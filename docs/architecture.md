# Architecture

`pdf-tool` is a local Python CLI with no server, telemetry, or runtime network
dependency.

```text
agent or developer
        |
        v
Typer command layer  ------> JSON stdout / diagnostics stderr
        |
        v
validation + bounded page/JSON selection
        |
        +--> pypdf / pdfplumber / PyPDFForm / pyHanko
        |
        v
same-directory temporary file -> reopen/check -> fsync -> atomic replace
```

`src/pdf_tool/cli.py` registers commands. `commands/common.py` owns shared file,
size, atomic-write, and parser guards. Individual command modules keep their
input and output contracts local. Bundled schemas live in
`src/pdf_tool/schemas`. `evals` invokes the real CLI through a synthetic
locate-edit-verify workflow.

`read --image` is the only command that requires an external executable:
Poppler's `pdftoppm`. Cryptographic signing uses local certificate material and
pyHanko; secrets are never accepted as command-line values.

## Design constraints

- One independent tool for one file format.
- Machine-readable capability discovery before document access.
- Zero-based page addressing everywhere.
- Bounded inputs and atomic mutation.
- No organization-specific services, paths, or sibling-tool dependencies.
