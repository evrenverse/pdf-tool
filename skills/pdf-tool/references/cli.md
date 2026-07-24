# CLI reference

Use `pdf-tool <command> --help` as the authoritative option reference.

## Agent discovery

```bash
pdf-tool capabilities --json
pdf-tool doctor --json
pdf-tool doctor --json --require poppler
pdf-tool schema
pdf-tool schema batch
pdf-tool version --json
```

Use bundled schemas instead of inferring structured input. The contract reports
hard input limits and whether each command mutates files.

## Inspect

```bash
pdf-tool info document.pdf --json
pdf-tool field-info form.pdf --json
pdf-tool find document.pdf "Invoice total" --pages 0-3 --json
pdf-tool read document.pdf --pages 0,2,5 --json
pdf-tool read form.pdf --fields Company,Date --values-only
```

`read --image` needs Poppler. Page numbers are zero-indexed.

## Modify

```bash
pdf-tool fill form.pdf values.json --validate-only --json
pdf-tool fill form.pdf values.json --output filled.pdf --json
pdf-tool write document.pdf overlays.json --output annotated.pdf
pdf-tool batch form.pdf operations.json --output result.pdf --json
pdf-tool merge first.pdf second.pdf --output merged.pdf
pdf-tool split merged.pdf --pages 0-2,5 --output extract.pdf
```

Mutating commands default to the input path when `--output` is omitted and use
atomic replacement.

## Create and sign

```bash
pdf-tool create output.pdf source.md
pdf-tool sign document.pdf --signature signature.png --page 0 \
  --position 350,650,150,50
pdf-tool sign document.pdf --signature signature.png --certificate signer.p12 \
  --passphrase-file private.txt --page 0 --position 350,650,150,50
```

Do not pass secrets in command arguments or batch JSON.
