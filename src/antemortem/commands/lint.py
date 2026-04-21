"""`antemortem lint` — schema and citation validation (Day 2 implementation).

Validates an antemortem document's structured schema (all sections present,
classifications complete) and verifies every `file:line` citation exists
on disk. Exit 0 on pass, 1 on fail. Suitable for CI gates.
"""

from pathlib import Path

import typer


def lint(
    document: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the antemortem document to validate.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    repo: Path = typer.Option(  # noqa: B008
        Path.cwd(),
        "--repo",
        "-r",
        help="Repository root to resolve cited files against. Defaults to current directory.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
) -> None:
    """Validate schema and verify file:line citations."""
    _ = document, repo  # will be wired up in Day 2
    typer.secho(
        "antemortem lint: not yet implemented in v0.2.0 alpha (Day 2 scope).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    typer.secho(
        "See CHANGELOG.md and the v0.2 milestone for progress.",
        fg=typer.colors.BRIGHT_BLACK,
        err=True,
    )
    raise typer.Exit(code=1)
