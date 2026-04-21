"""`antemortem run` — LLM-assisted classification (Day 3 implementation).

Reads an antemortem document, extracts the spec/traps/files sections,
loads the referenced source files, calls Claude Opus 4.7, and writes
classifications back into the document plus a JSON audit artifact.
"""

from pathlib import Path

import typer


def run(
    document: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the antemortem document to classify.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(),
        "--repo",
        "-r",
        help="Repository root to read cited files from. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
) -> None:
    """Run LLM classification on an antemortem document."""
    _ = document, repo  # will be wired up in Day 3
    typer.secho(
        "antemortem run: not yet implemented in v0.2.0 alpha (Day 3 scope).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    typer.secho(
        "See CHANGELOG.md and the v0.2 milestone for progress.",
        fg=typer.colors.BRIGHT_BLACK,
        err=True,
    )
    raise typer.Exit(code=1)
