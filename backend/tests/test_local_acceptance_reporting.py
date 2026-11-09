"""Regression test for the local-acceptance evidence-path reporting.

The acceptance matrix itself is a live-process script (``scripts/run_local_acceptance.py``),
so it is not run here. This focused test pins only the reporting helper that once
crashed after all 38 checks had passed when ``--evidence`` pointed outside the
repository: ``Path.relative_to`` raises ``ValueError`` for external paths, which
must never turn a passing run into a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_local_acceptance import (  # noqa: E402
    REPO_ROOT as SCRIPT_REPO_ROOT,
    display_path,
)


def test_display_path_keeps_repository_paths_relative() -> None:
    evidence = SCRIPT_REPO_ROOT / "docs" / "local_acceptance" / "api_evidence.json"
    assert display_path(evidence) == str(evidence.relative_to(SCRIPT_REPO_ROOT))


def test_display_path_reports_an_external_absolute_path_without_raising(
    tmp_path: Path,
) -> None:
    external = tmp_path / "dd_local_acceptance_evidence.json"
    assert display_path(external) == str(external)
