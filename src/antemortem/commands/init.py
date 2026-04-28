# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""`antemortem init` ??scaffold a new antemortem document from a template."""

from datetime import date
from pathlib import Path

import typer

from antemortem.templates import get_template


def _build_frontmatter(
    name: str,
    today: str,
    enhanced: bool,
) -> str:
    template_label = "enhanced" if enhanced else "basic"
    return (
        "---\n"
        f"name: {name}\n"
        f"date: {today}\n"
        "scope: change-local\n"
        "reversibility: high\n"
        "status: draft\n"
        f"template: {template_label}\n"
        "---\n\n"
    )


def init(
    name: str = typer.Argument(  # noqa: B008
        ...,
        help="Short name for the change (used as filename). Example: my-feature, auth-refactor.",
    ),
    enhanced: bool = typer.Option(  # noqa: B008
        False,
        "--enhanced",
        "-e",
        help="Use the enhanced template (calibration dimensions, skeptic pass, decision-first output).",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("antemortem"),
        "--output-dir",
        "-o",
        help="Directory to create the document in. Created if missing.",
        file_okay=False,
        dir_okay=True,
    ),
    force: bool = typer.Option(  # noqa: B008
        False,
        "--force",
        "-f",
        help="Overwrite existing document if present.",
    ),
) -> None:
    """Create antemortem/<name>.md with YAML frontmatter and the chosen template."""
    if not name or any(ch in name for ch in ("/", "\\", "..")):
        typer.secho(
            f"Invalid name {name!r}: use a simple identifier (letters, digits, hyphens).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{name}.md"

    if target.exists() and not force:
        typer.secho(
            f"Refusing to overwrite {target} ??pass --force to replace.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    today = date.today().isoformat()
    content = _build_frontmatter(name, today, enhanced) + get_template(enhanced)
    target.write_text(content, encoding="utf-8")

    label = "enhanced" if enhanced else "basic"
    typer.secho(f"Created {target} ({label} template)", fg=typer.colors.GREEN)
    typer.secho(
        "Next: fill in the spec, enumerate traps, then run `antemortem run` to classify.",
        fg=typer.colors.BRIGHT_BLACK,
    )
