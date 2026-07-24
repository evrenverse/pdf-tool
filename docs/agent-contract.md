# Agent contract

Contract version `1` makes the CLI self-describing:

```bash
pdf-tool capabilities --json
pdf-tool doctor --json
pdf-tool schema
pdf-tool schema batch
pdf-tool version --json
```

`capabilities` reports commands, mutation behavior, numbering, optional
dependencies, safety properties, bundled schemas, and hard limits. `doctor`
performs read-only runtime checks and can require Poppler with
`--require poppler`. `schema` prints JSON Schema locally.

## Stable conventions

- Contract and schema versions are independent from the package version.
- JSON is written to stdout; diagnostics and warnings go to stderr.
- Pages are zero-based across every command.
- Success exits `0`. A no-match, invalid document operation, or rejected edit
  exits `1`; CLI usage, resource-policy, and failed explicitly required
  dependency checks exit `2`.
- Agents should inspect, scope reads, keep an original, mutate transactionally,
  and verify the output with `info`, `read`, or `field-info`.
- Certificate passphrases belong in a mode-0600 file, a secret environment
  variable, or an interactive prompt—never arguments or batch JSON.

Backward-incompatible changes require a new contract major version. Additive
JSON fields and schemas are allowed in version `1`.

Schemas ship inside the wheel under `pdf_tool.schemas`. Portable agent guidance
is in `skills/pdf-tool`.
