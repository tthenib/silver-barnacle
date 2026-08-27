#!/usr/bin/env python3
"""Repository integrity checks for the research charter.

The checker is intentionally standard-library only so it can run before the
numeric research dependencies are installed. It validates the parts of the repo
that should never silently drift: local Markdown links and generated-result
freshness when the required scientific Python stack is available.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_RESULTS_REQUIRING_SCIENTIFIC_STACK = {
    ROOT / "results" / "return_target_feasibility.md": ROOT
    / "research"
    / "analysis"
    / "return_target_feasibility.py",
    ROOT / "results" / "lot_granularity.md": ROOT / "research" / "analysis" / "lot_granularity.py",
}
GENERATED_RESULTS_STDLIB_ONLY = {
    ROOT / "results" / "research_power.md": ROOT / "research" / "analysis" / "research_power.py",
}
IGNORED_DIRS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache"}
LOCAL_MD_LINK = re.compile(r"(?<!!)\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
REQUIRED_SCIENTIFIC_PACKAGES = ("numpy", "scipy")


class Status(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == Status.FAIL


def iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def check_markdown_links() -> CheckResult:
    missing: list[str] = []
    markdown_files = iter_markdown_files()
    for md_file in markdown_files:
        text = md_file.read_text(encoding="utf-8")
        for match in LOCAL_MD_LINK.finditer(text):
            raw_target = match.group(1).strip()
            target = strip_anchor(raw_target)
            if not target:
                continue
            resolved = (md_file.parent / target).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                missing.append(f"{md_file.relative_to(ROOT)} -> {raw_target} escapes repo")
                continue
            if not resolved.exists():
                missing.append(f"{md_file.relative_to(ROOT)} -> {raw_target}")
    if missing:
        return CheckResult("markdown links", Status.FAIL, "missing links:\n" + "\n".join(missing))
    return CheckResult("markdown links", Status.PASS, f"checked {len(markdown_files)} Markdown files")


def missing_scientific_packages() -> list[str]:
    return [
        package
        for package in REQUIRED_SCIENTIFIC_PACKAGES
        if importlib.util.find_spec(package) is None
    ]


def stale_generated_files(generated_results: dict[Path, Path]) -> list[str]:
    stale: list[str] = []
    for result_path, script_path in generated_results.items():
        completed = subprocess.run(
            [sys.executable, str(script_path.relative_to(ROOT))],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        expected = result_path.read_text(encoding="utf-8")
        if completed.stdout != expected:
            stale.append(f"{result_path.relative_to(ROOT)} is not current with {script_path.relative_to(ROOT)}")
    return stale


def check_generated_results(require_dependencies: bool) -> CheckResult:
    stale = stale_generated_files(GENERATED_RESULTS_STDLIB_ONLY)
    checked_count = len(GENERATED_RESULTS_STDLIB_ONLY)

    missing_packages = missing_scientific_packages()
    if missing_packages:
        if stale:
            return CheckResult("generated results", Status.FAIL, "\n".join(stale))
        detail = (
            f"checked {checked_count} stdlib generated file(s); skipped scientific freshness checks "
            "because required packages are not installed: " + ", ".join(missing_packages)
        )
        status = Status.FAIL if require_dependencies else Status.WARN
        return CheckResult("generated results", status, detail)

    stale.extend(stale_generated_files(GENERATED_RESULTS_REQUIRING_SCIENTIFIC_STACK))
    checked_count += len(GENERATED_RESULTS_REQUIRING_SCIENTIFIC_STACK)
    if stale:
        return CheckResult("generated results", Status.FAIL, "\n".join(stale))
    return CheckResult("generated results", Status.PASS, f"checked {checked_count} generated files")


def run_checks(include_generated: bool, require_generated_dependencies: bool) -> int:
    checks = [check_markdown_links()]
    if include_generated:
        checks.append(check_generated_results(require_dependencies=require_generated_dependencies))

    failed = False
    for check in checks:
        print(f"[{check.status.value}] {check.name}: {check.detail}")
        failed = failed or check.failed
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate repository documentation and generated outputs.")
    parser.add_argument(
        "--skip-generated",
        action="store_true",
        help="only check standard-library documentation integrity",
    )
    parser.add_argument(
        "--require-generated-dependencies",
        action="store_true",
        help="fail instead of warn when numpy/scipy are unavailable for generated-output checks",
    )
    args = parser.parse_args()
    raise SystemExit(
        run_checks(
            include_generated=not args.skip_generated,
            require_generated_dependencies=args.require_generated_dependencies,
        )
    )


if __name__ == "__main__":
    main()
