"""pdf-tool CLI — Safe PDF reading, filling, and signing for AI agents."""

import typer

app = typer.Typer(
    name="pdf-tool",
    help="Safe PDF reading, filling, and signing for AI agents.",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit."),
) -> None:
    if version:
        from pdf_tool import __version__

        typer.echo(f"pdf-tool {__version__}")
        raise typer.Exit()


# --- Register subcommands ---

from pdf_tool.commands.info import info as info_cmd  # noqa: E402

app.command(name="info", help="Show PDF file structure: pages, dimensions, and form fields.")(
    info_cmd
)

from pdf_tool.commands.read import read as read_cmd  # noqa: E402

app.command(
    name="read",
    help=(
        "Extract text with positions from PDF pages. Scattered reads in ONE call: "
        "--pages 0,2,5 for sparse page sets, --fields Company,Date for named form "
        "values only (add --values-only for a flat value map) — never loop per item."
    ),
)(read_cmd)

from pdf_tool.commands.find import find as find_cmd  # noqa: E402

app.command(
    name="find",
    help=(
        "Locate text or form fields: case-insensitive line-level search plus "
        "AcroForm name/value matches in ONE call — never page-dump + grep. "
        "Then: read --fields <name> or write at the reported bbox."
    ),
)(find_cmd)

from pdf_tool.commands.field_info import field_info as field_info_cmd  # noqa: E402

app.command(
    name="field-info",
    help=(
        "Show fill-planning metadata per form field: type, page, rect, checkbox "
        "on/off values, radio options, choice options. Run BEFORE fill."
    ),
)(field_info_cmd)

from pdf_tool.commands.fill import fill as fill_cmd  # noqa: E402

app.command(name="fill", help="Fill AcroForm fields by name.")(fill_cmd)

from pdf_tool.commands.write import write as write_cmd  # noqa: E402

app.command(name="write", help="Write text at x,y coordinates (overlay).")(write_cmd)

from pdf_tool.commands.sign import sign as sign_cmd  # noqa: E402

app.command(name="sign", help="Place signature image and optionally apply crypto signature.")(
    sign_cmd
)

from pdf_tool.commands.batch import batch as batch_cmd  # noqa: E402

app.command(name="batch", help="Combined fill + write + sign in one operation.")(batch_cmd)

from pdf_tool.commands.merge import merge as merge_cmd  # noqa: E402

app.command(name="merge", help="Merge multiple PDFs into a single file.")(merge_cmd)

from pdf_tool.commands.split import split as split_cmd  # noqa: E402

app.command(
    name="split",
    help=(
        "Split PDF into individual pages or extract a page selection — "
        "0-indexed like read/find: '0,2,5' or '0-3,7'."
    ),
)(split_cmd)

from pdf_tool.commands.create import create as create_cmd  # noqa: E402

app.command(name="create", help="Create a new PDF from Markdown with an embedded font.")(create_cmd)

from pdf_tool.commands.system import capabilities as capabilities_cmd  # noqa: E402
from pdf_tool.commands.system import doctor as doctor_cmd  # noqa: E402
from pdf_tool.commands.system import schema as schema_cmd  # noqa: E402
from pdf_tool.commands.system import version as version_cmd  # noqa: E402

app.command(name="capabilities", help="Describe the stable automation contract.")(capabilities_cmd)
app.command(name="doctor", help="Check runtime requirements without opening a PDF.")(doctor_cmd)
app.command(name="schema", help="Print a bundled JSON Schema.")(schema_cmd)
app.command(name="version", help="Show version and contract information.")(version_cmd)
