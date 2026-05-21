# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Top-level Typer application for the antemortem CLI."""

import typer

from antemortem import __version__
from antemortem.commands import doctor as doctor_cmd
from antemortem.commands import evidence as evidence_cmd
from antemortem.commands import eval as eval_cmd
from antemortem.commands import gate as gate_cmd
from antemortem.commands import init as init_cmd
from antemortem.commands import lint as lint_cmd
from antemortem.commands import run as run_cmd

app = typer.Typer(
    name="antemortem",
    help="Pre-diff risk verification against repository evidence.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"antemortem {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(  # noqa: B008
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Antemortem: scaffold, preflight, run, verify, gate, and evaluate artifacts."""


app.command(name="init", help="Create a recon markdown document.")(init_cmd.init)
app.command(name="doctor", help="Preview parsed input and file payload.")(doctor_cmd.doctor)
app.command(name="run", help="Classify traps with a provider and write an artifact.")(run_cmd.run)
app.command(name="lint", help="Validate schema, citations, and evidence bindings.")(lint_cmd.lint)
app.command(name="evidence", help="Inspect or fill artifact evidence hashes.")(evidence_cmd.evidence)
app.command(name="gate", help="Enforce lint and decision policy for CI.")(gate_cmd.gate)
app.command(name="eval", help="Measure offline golden benchmark cases.")(eval_cmd.eval)


if __name__ == "__main__":
    app()
