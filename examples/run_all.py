#!/usr/bin/env python3
"""Run every example's runner scripts against their live APIs and report.

Each runner is expected to exit:
    0  pass  — all assertions held
    2  skip  — the live API was unreachable / returned a server error
    *  fail  — anything else (a real client/serialization bug)

A *skip* never fails the suite (a public API being down is not our bug); a
*fail* does. Runners are executed via `uv run`, which resolves each generated
library through the editable path source declared in the runner's pyproject.

Usage:
    python examples/run_all.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent


def discover() -> list[tuple[str, Path, Path]]:
    """Yield (label, runners_dir, runner_file) for every runner script."""
    found: list[tuple[str, Path, Path]] = []
    for example in sorted(
        p for p in EXAMPLES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")
    ):
        for runners_dir in sorted(example.glob("*_runners")):
            for runner in sorted(runners_dir.glob("*.py")):
                if runner.name.startswith("_"):
                    continue
                found.append((f"{example.name}/{runner.name}", runners_dir, runner))
    return found


def main() -> int:
    runners = discover()
    if not runners:
        print("No runners found under", EXAMPLES_DIR)
        return 0

    results: list[tuple[str, str, int]] = []
    for label, runners_dir, runner in runners:
        print(f"\n{'#' * 72}\n# {label}\n{'#' * 72}")
        proc = subprocess.run(
            ["uv", "run", "--quiet", "python", runner.name],
            cwd=runners_dir,
        )
        status = {0: "PASS", 2: "SKIP"}.get(proc.returncode, "FAIL")
        results.append((label, status, proc.returncode))

    width = max(len(label) for label, _, _ in results)
    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}")
    for label, status, code in results:
        print(f"  {status:4}  {label:<{width}}  (exit {code})")

    passed = sum(s == "PASS" for _, s, _ in results)
    skipped = sum(s == "SKIP" for _, s, _ in results)
    failed = sum(s == "FAIL" for _, s, _ in results)
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
