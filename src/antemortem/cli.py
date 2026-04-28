# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Top-level Typer application for the antemortem CLI."""

import typer

from antemortem import __version__
from antemortem.commands import init as init_cmd
from antemortem.commands import lint as lint_cmd
from antemortem.commands import run as run_cmd

app = typer.Typer(
    name="antemortem",
    help="CLI for the Antemortem pre-implementation reconnaissance discipline.",
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
    """Antemortem ??scaffold, run, and lint pre-implementation recon documents."""


app.command(name="init", help="Scaffold a new antemortem document from a template.")(init_cmd.init)
app.command(name="run", help="Run LLM-assisted classification on an antemortem document.")(run_cmd.run)
app.command(name="lint", help="Validate an antemortem document's schema and citations.")(lint_cmd.lint)


if __name__ == "__main__":
    app()
