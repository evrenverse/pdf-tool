"""Reproducible agent workflow eval for pdf-tool."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def run(binary: str, *args: str) -> str:
    result = subprocess.run(
        [binary, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} exited {result.returncode}: {result.stderr or result.stdout}"
        )
    return result.stdout


def create_fixture(path: Path) -> None:
    document = canvas.Canvas(str(path), pagesize=A4)
    document.drawString(72, 740, "Invoice total")
    document.drawString(220, 740, "1000.00")
    document.save()


def main() -> None:
    started = time.monotonic()
    binary = shutil.which("pdf-tool")
    if binary is None:
        raise SystemExit("pdf-tool not found on PATH; run with `uv run python evals/run_evals.py`")

    with tempfile.TemporaryDirectory(prefix="pdf-tool-eval-") as temporary:
        root = Path(temporary)
        source = root / "invoice.pdf"
        output = root / "approved.pdf"
        changes = root / "changes.json"
        create_fixture(source)
        changes.write_text(
            json.dumps([{"page": 0, "x": 72, "y": 140, "text": "Approved"}]),
            encoding="utf-8",
        )

        run(binary, "info", str(source), "--json")
        found = json.loads(run(binary, "find", str(source), "Invoice total", "--json"))
        if found["total"] != 1:
            raise RuntimeError(f"expected one label match, got {found['total']}")
        run(binary, "read", str(source), "--page", "0", "--json")
        run(binary, "write", str(source), str(changes), "--output", str(output))
        final = json.loads(run(binary, "read", str(output), "--page", "0", "--json"))
        words = {word["text"] for word in final["words"]}
        if "Approved" not in words:
            raise RuntimeError(f"overlay text missing from final PDF: {sorted(words)}")

    print(
        json.dumps(
            {
                "schema_version": "1",
                "tool": "pdf-tool",
                "eval": "locate-edit-verify",
                "passed": True,
                "commands": 5,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
