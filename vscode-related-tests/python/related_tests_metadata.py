from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class RelatedSource:
    source: str
    tests: tuple[str, ...]
    missing_tests: tuple[str, ...]
    errors: tuple[str, ...]


def parse_related_tests(
    docstring: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not docstring:
        return (), ()

    lines = docstring.splitlines()
    section_started = False
    raw_entries: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not section_started:
            if stripped == "Tests:":
                section_started = True
            continue

        if not stripped:
            if raw_entries:
                break
            continue

        if stripped.startswith("- "):
            raw_entries.append(stripped[2:].strip())
            continue

        if raw_entries:
            break

        return (), ("Tests: must be followed by one or more '- tests/...py' entries.",)

    if not section_started:
        return (), ()

    if not raw_entries:
        return (), ("Tests: must be followed by one or more '- tests/...py' entries.",)

    normalized: list[str] = []
    seen: set[str] = set()
    errors: list[str] = []
    for entry in raw_entries:
        candidate = entry.replace("\\", "/").strip()
        if not candidate:
            errors.append("Blank test entry is not allowed in Tests: metadata.")
            continue
        if candidate.startswith("/"):
            errors.append(f"Related test path must be relative: {entry}")
            continue
        if not candidate.startswith("tests/"):
            errors.append(f"Related test path must stay under tests/: {entry}")
            continue
        if not candidate.endswith(".py"):
            errors.append(f"Related test path must point to a Python file: {entry}")
            continue
        if candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)

    return tuple(normalized), tuple(errors)


def inspect_source_file(path: Path, workspace_root: Path) -> RelatedSource:
    source_path = path.resolve()
    root = workspace_root.resolve()
    relative_source = source_path.relative_to(root).as_posix()

    try:
        module = ast.parse(
            source_path.read_text(encoding="utf-8"), filename=str(source_path)
        )
    except SyntaxError as exc:
        return RelatedSource(
            source=relative_source,
            tests=(),
            missing_tests=(),
            errors=(
                f"Failed to parse module docstring: {exc.msg} (line {exc.lineno}).",
            ),
        )

    tests, errors = parse_related_tests(ast.get_docstring(module, clean=False))
    missing_tests = tuple(
        test_path for test_path in tests if not (root / test_path).is_file()
    )
    return RelatedSource(
        source=relative_source,
        tests=tests,
        missing_tests=missing_tests,
        errors=errors,
    )


def scan_related_sources(workspace_root: Path) -> tuple[RelatedSource, ...]:
    root = workspace_root.resolve()
    discovered: list[RelatedSource] = []
    for file_path in sorted(root.rglob("*.py")):
        if any(
            part in {"__pycache__", ".venv", "venv", "node_modules", ".git"}
            for part in file_path.parts
        ):
            continue
        metadata = inspect_source_file(file_path, root)
        if metadata.tests or metadata.errors:
            discovered.append(metadata)

    return tuple(discovered)


def _to_json(source: RelatedSource) -> dict[str, object]:
    return asdict(source)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect source-file related test metadata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan", help="List source files that declare related tests."
    )
    scan_parser.add_argument(
        "--workspace", default=".", help="Workspace root to inspect."
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect a single source file."
    )
    inspect_parser.add_argument(
        "source", help="Source file path relative to the workspace root."
    )
    inspect_parser.add_argument(
        "--workspace", default=".", help="Workspace root to inspect."
    )

    args = parser.parse_args(argv)
    workspace_root = Path(args.workspace)

    if args.command == "scan":
        results = scan_related_sources(workspace_root)
        print(json.dumps([_to_json(item) for item in results]))
        return 0

    if args.command == "inspect":
        result = inspect_source_file(workspace_root / args.source, workspace_root)
        print(json.dumps(_to_json(result)))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
