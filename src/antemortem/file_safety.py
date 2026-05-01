# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Privacy and resource guardrails for files sent to the LLM provider.

`run` reads files listed in the Recon protocol and includes them in the
provider payload. Without guardrails, a user who lists `config/` could
ship `.env`, credential fixtures, or customer dumps to an external LLM
service. This module supplies opt-out / opt-in checks:

  * deny-glob:     hard refuse listed paths (default: secrets-ish files)
  * gitignore:     refuse anything `.gitignore` would hide
  * max-bytes:     skip files over a per-file size budget
  * secret redact: pattern-based scrub of likely secrets in file text

The defaults are conservative — secret-shaped filenames refuse, large
files skip with a warning. Secret redaction is OPT-IN because regex
substitution can mask real code the model is supposed to analyze;
the user has to consciously enable it.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

# Filenames that almost always contain secrets and should never be sent
# to an external LLM provider unless the user explicitly removes the
# default deny list. Format: shell glob, matched against forward-slash
# paths relative to repo root.
DEFAULT_DENY_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/secrets/**",
    "**/credentials/**",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/id_rsa.pub",
    "**/id_ed25519",
    "**/id_ed25519.pub",
    "**/.ssh/**",
    "**/.aws/credentials",
    "**/.netrc",
    "**/known_hosts",
)

DEFAULT_MAX_FILE_BYTES: int = 200_000  # ~50k tokens worst-case


# Patterns for opt-in secret redaction. Keep narrow — over-broad regexes
# silently scrub real code. Each pattern produces a token replacement
# that preserves the secret's structural location in the file.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # AWS access key id
    ("[REDACTED:AWS_ACCESS_KEY]", re.compile(r"AKIA[0-9A-Z]{16}")),
    # AWS secret access key (40 char base64-ish)
    (
        "[REDACTED:AWS_SECRET]",
        re.compile(
            r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"
        ),
    ),
    # GitHub PAT (classic + fine-grained)
    (
        "[REDACTED:GITHUB_TOKEN]",
        re.compile(r"gh[pousr]_[A-Za-z0-9]{36,255}"),
    ),
    # Slack tokens
    (
        "[REDACTED:SLACK_TOKEN]",
        re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,72}"),
    ),
    # Anthropic / OpenAI API key shapes
    (
        "[REDACTED:ANTHROPIC_KEY]",
        re.compile(r"sk-ant-(?:api\d+-)?[A-Za-z0-9_\-]{32,}"),
    ),
    (
        "[REDACTED:OPENAI_KEY]",
        re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{40,}"),
    ),
    # Generic bearer header on its own line
    (
        "[REDACTED:BEARER]",
        re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{20,}"),
    ),
    # PEM blocks
    (
        "[REDACTED:PEM_BLOCK]",
        re.compile(
            r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"
        ),
    ),
)


@dataclass(frozen=True)
class FileSafetyConfig:
    """Caller-supplied policy applied to every file `run` would send."""

    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    deny_globs: tuple[str, ...] = DEFAULT_DENY_GLOBS
    respect_gitignore: bool = True
    redact_secrets: bool = False


@dataclass(frozen=True)
class FileSafetyOutcome:
    """Per-file decision plus optional redaction count."""

    allowed: bool
    reason: str = ""             # populated when allowed=False
    redactions_applied: int = 0   # populated only when redact_secrets=True


def _normalize(rel_path: str) -> str:
    return rel_path.replace("\\", "/")


def _matches_any(rel_path: str, patterns: tuple[str, ...]) -> str | None:
    """Return the matching pattern, or None."""
    norm = _normalize(rel_path)
    for pattern in patterns:
        # fnmatch matches against the full string. To make leading-dir
        # patterns like "**/*.pem" work for top-level files (e.g.
        # "key.pem"), check both the path and its basename.
        if fnmatch.fnmatch(norm, pattern):
            return pattern
        if fnmatch.fnmatch(norm.split("/")[-1], pattern):
            return pattern
    return None


def load_gitignore_patterns(repo_root: Path) -> tuple[str, ...]:
    """Read `.gitignore` at repo root and return non-comment patterns.

    Nested `.gitignore` files are NOT walked — keeping behavior simple
    and predictable. A future revision can add full gitignore semantics
    via the `pathspec` library; the conservative subset here covers the
    common case (top-level `.gitignore` listing `.env`, `node_modules`,
    `__pycache__`, build dirs).
    """
    gi = repo_root / ".gitignore"
    if not gi.is_file():
        return ()
    out: list[str] = []
    try:
        text = gi.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Drop git-specific negation; we only deny, not include.
        if line.startswith("!"):
            continue
        # Anchor leading slash → match from repo root, drop the slash.
        if line.startswith("/"):
            line = line[1:]
        # Trailing slash signals directory; promote to **/ glob.
        if line.endswith("/"):
            line = line[:-1] + "/**"
        # Patterns without slashes match anywhere in the tree.
        if "/" not in line and not line.startswith("*"):
            out.append(line)
            out.append(f"**/{line}")
            out.append(f"**/{line}/**")
        else:
            out.append(line)
    return tuple(out)


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace common secret shapes with `[REDACTED:...]` markers.

    Returns (redacted_text, count_of_substitutions). False positives
    are possible — make sure the user opts in via --redact-secrets.
    """
    total = 0
    for replacement, pattern in _SECRET_PATTERNS:
        text, n = pattern.subn(replacement, text)
        total += n
    return text, total


def evaluate_file(
    rel_path: str,
    file_path: Path,
    config: FileSafetyConfig,
    gitignore_patterns: tuple[str, ...],
) -> FileSafetyOutcome:
    """Apply deny-glob, gitignore, and size checks to a single file.

    Does NOT read or redact the content — that happens in load_safe_text
    once a file is allowed.
    """
    deny_hit = _matches_any(rel_path, config.deny_globs)
    if deny_hit:
        return FileSafetyOutcome(
            allowed=False,
            reason=f"matches deny-glob {deny_hit!r} (likely secret)",
        )
    if config.respect_gitignore and gitignore_patterns:
        gi_hit = _matches_any(rel_path, gitignore_patterns)
        if gi_hit:
            return FileSafetyOutcome(
                allowed=False,
                reason=f"ignored by .gitignore pattern {gi_hit!r}",
            )
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        return FileSafetyOutcome(allowed=False, reason=f"cannot stat: {exc}")
    if size > config.max_file_bytes:
        return FileSafetyOutcome(
            allowed=False,
            reason=(
                f"file size {size} bytes exceeds --max-file-bytes "
                f"({config.max_file_bytes}). Raise the limit if intentional."
            ),
        )
    return FileSafetyOutcome(allowed=True)


def load_safe_text(
    file_path: Path, config: FileSafetyConfig
) -> tuple[str, int]:
    """Read a file (UTF-8 with replacement) and apply optional redaction.

    Returns (text, redactions_applied). Caller is expected to have run
    evaluate_file() first.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    if config.redact_secrets:
        return redact_secrets(content)
    return content, 0
