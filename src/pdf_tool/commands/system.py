"""Machine-readable capability discovery and runtime diagnostics."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from importlib.resources import files

import typer

from pdf_tool import __version__
from pdf_tool.commands.common import MAX_BATCH_ITEMS, MAX_INPUT_BYTES, MAX_JSON_INPUT_BYTES

CONTRACT_VERSION = "1"
SCHEMA_NAMES = ("batch", "capabilities", "doctor", "version")


def _emit(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _capability_payload() -> dict:
    return {
        "schema_version": CONTRACT_VERSION,
        "tool": "pdf-tool",
        "tool_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "addressing": "zero-based PDF pages and named AcroForm fields",
        "runtime_network_access": False,
        "atomic_writes": True,
        "structured_stdout": True,
        "diagnostics_stderr": True,
        "commands": [
            {"name": "info", "mutates": False, "json": True},
            {"name": "field-info", "mutates": False, "json": True},
            {"name": "find", "mutates": False, "json": True},
            {"name": "read", "mutates": False, "json": True, "optional_dependency": "poppler"},
            {"name": "fill", "mutates": True, "json": True},
            {"name": "write", "mutates": True, "json": False},
            {"name": "sign", "mutates": True, "json": False},
            {"name": "batch", "mutates": True, "json": True},
            {"name": "merge", "mutates": True, "json": False},
            {"name": "split", "mutates": True, "json": False},
            {"name": "create", "mutates": True, "json": False},
            {"name": "capabilities", "mutates": False, "json": True},
            {"name": "doctor", "mutates": False, "json": True},
            {"name": "schema", "mutates": False, "json": True},
            {"name": "version", "mutates": False, "json": True},
        ],
        "optional_dependencies": ["poppler"],
        "schemas": list(SCHEMA_NAMES),
        "limits": {
            "input_pdf_bytes": MAX_INPUT_BYTES,
            "json_input_bytes": MAX_JSON_INPUT_BYTES,
            "batch_items": MAX_BATCH_ITEMS,
        },
    }


def capabilities(
    output_json: bool = typer.Option(False, "--json", help="Output the contract as JSON."),
) -> None:
    """Describe commands, conventions, dependencies, and bundled schemas."""
    payload = _capability_payload()
    if output_json:
        _emit(payload)
        return
    typer.echo(f"pdf-tool {__version__} (agent contract v{CONTRACT_VERSION})")
    typer.echo("Addressing: zero-based PDF pages and named AcroForm fields")
    typer.echo("Writes: validated and atomically published")
    typer.echo("Runtime network access: none")
    typer.echo("Optional dependency: Poppler (page image rendering)")


def version(
    output_json: bool = typer.Option(False, "--json", help="Output version information as JSON."),
) -> None:
    """Show the tool and agent-contract versions."""
    if output_json:
        _emit(
            {
                "schema_version": CONTRACT_VERSION,
                "tool": "pdf-tool",
                "version": __version__,
                "contract_version": CONTRACT_VERSION,
            }
        )
        return
    typer.echo(f"pdf-tool {__version__}")


def _module_check(name: str, import_name: str) -> dict:
    available = importlib.util.find_spec(import_name) is not None
    return {
        "name": name,
        "required": True,
        "ok": available,
        "detail": "available" if available else "not importable",
    }


def doctor(
    output_json: bool = typer.Option(False, "--json", help="Output checks as JSON."),
    require: list[str] | None = typer.Option(
        None,
        "--require",
        help="Require an optional dependency. Repeatable: --require poppler.",
    ),
) -> None:
    """Check runtime requirements without opening a PDF."""
    required = {item.strip().lower() for item in (require or [])}
    unknown = required - {"poppler"}
    if unknown:
        typer.echo(f"Error: unknown optional dependency: {sorted(unknown)[0]}", err=True)
        raise typer.Exit(code=2)

    checks = [
        {
            "name": "python",
            "required": True,
            "ok": sys.version_info >= (3, 12),
            "detail": sys.version.split()[0],
        },
        _module_check("pypdf", "pypdf"),
        _module_check("pdfplumber", "pdfplumber"),
        _module_check("reportlab", "reportlab"),
        _module_check("pyhanko", "pyhanko"),
    ]
    try:
        with tempfile.NamedTemporaryFile(prefix="pdf-tool-doctor-"):
            pass
        temp_check = {
            "name": "temporary-directory",
            "required": True,
            "ok": True,
            "detail": "writable",
        }
    except OSError as exc:
        temp_check = {
            "name": "temporary-directory",
            "required": True,
            "ok": False,
            "detail": str(exc),
        }
    checks.append(temp_check)

    poppler_path = shutil.which("pdftoppm")
    checks.append(
        {
            "name": "poppler",
            "required": "poppler" in required,
            "ok": poppler_path is not None,
            "detail": poppler_path or "not found; required only for page image rendering",
        }
    )
    failed_required = any(check["required"] and not check["ok"] for check in checks)
    missing_optional = any(not check["required"] and not check["ok"] for check in checks)
    status = "error" if failed_required else "degraded" if missing_optional else "ok"
    payload = {
        "schema_version": CONTRACT_VERSION,
        "tool": "pdf-tool",
        "tool_version": __version__,
        "status": status,
        "checks": checks,
    }
    if output_json:
        _emit(payload)
    else:
        for check in checks:
            state = "ok" if check["ok"] else "missing"
            typer.echo(f"{check['name']}: {state} ({check['detail']})")
    if failed_required:
        raise typer.Exit(code=2)


def schema(
    name: str | None = typer.Argument(None, help="Schema name to print."),
) -> None:
    """Print a bundled JSON Schema, or list available schema names."""
    if name is None:
        _emit({"schema_version": CONTRACT_VERSION, "schemas": list(SCHEMA_NAMES)})
        return
    normalized = name.lower()
    if normalized not in SCHEMA_NAMES:
        typer.echo(
            f"Error: unknown schema {name!r}; available: {', '.join(SCHEMA_NAMES)}",
            err=True,
        )
        raise typer.Exit(code=2)
    resource = files("pdf_tool.schemas").joinpath(f"{normalized}.schema.json")
    typer.echo(resource.read_text(encoding="utf-8").rstrip())
