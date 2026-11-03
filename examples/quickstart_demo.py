"""Compact offline replay; each label follows the real citation gate result."""
from reproduce_citation_traps import reproduce


def main() -> None:
    for row in reproduce():
        accepted = row["deployment_authorized"]
        prefix = "+ [PASS]" if accepted else "- [BLOCKED]"
        print(f"{prefix} {row['case']}: gate_exit_code={row['gate_exit_code']}")


if __name__ == "__main__":
    main()
