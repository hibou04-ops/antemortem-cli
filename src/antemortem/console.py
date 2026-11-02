"""ASCII terminal rendering; stored evidence and library objects stay unchanged."""
from __future__ import annotations

from typing import Any

import typer


def ascii_text(message: str) -> str:
    """Escape display-only Unicode without changing the source value."""
    return message.encode("ascii", errors="backslashreplace").decode("ascii")


def echo(message: str | None = None, **kwargs: Any) -> None:
    typer.echo(None if message is None else ascii_text(message), **kwargs)


def secho(message: str | None = None, **kwargs: Any) -> None:
    typer.secho(None if message is None else ascii_text(message), **kwargs)
