#!/usr/bin/env python3
"""
scripts/validate_notebooks.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Validates every notebook under notebooks/ as both well-formed JSON and a
schema-valid Jupyter notebook (nbformat), so a corrupted notebook is caught
before it ships rather than discovered by a user's Colab session.

This exists because of a real incident: an early release of
notebooks/custom_probes.ipynb contained a stray artifact left over from
manual editing that made the file invalid JSON. It opened fine in some
tools and failed outright in Google Colab with an opaque parser error.
See CHANGELOG.md and DECISION_LOG.md for the full account.

Usage:
    python scripts/validate_notebooks.py

Exit code 0 if every notebook is valid; exit code 1 otherwise, with a
specific error message per failing file. Intended to run in CI on any
change under notebooks/, and locally before committing a hand-edited
.ipynb file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import nbformat
except ImportError:
    print(
        "This script requires nbformat. Install with: pip install nbformat",
        file=sys.stderr,
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).parent.parent
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"


def validate_notebook(path: Path) -> list[str]:
    """Return a list of human-readable error messages; empty list means valid."""
    errors: list[str] = []

    # Step 1: must be well-formed JSON at all. This is the check that would
    # have caught the custom_probes.ipynb incident directly.
    try:
        raw = path.read_text(encoding="utf-8")
        json.loads(raw)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {e}")
        return errors  # no point continuing if it isn't even valid JSON

    # Step 2: must be a schema-valid notebook (correct nbformat structure,
    # required fields present, cell ids present per nbformat >=4.5, etc.)
    try:
        nb = nbformat.read(path, as_version=4)
        nbformat.validate(nb)
    except Exception as e:  # noqa: BLE001 - we want to report any validation failure
        errors.append(f"nbformat validation failed: {e}")

    # Step 3: no duplicate cell ids within the notebook.
    try:
        with path.open(encoding="utf-8") as f:
            raw_nb = json.load(f)
        ids = [c.get("id") for c in raw_nb.get("cells", []) if "id" in c]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            errors.append(f"Duplicate cell id(s): {sorted(dupes)}")
    except Exception as e:  # noqa: BLE001
        errors.append(f"Could not check for duplicate cell ids: {e}")

    return errors


def main() -> int:
    if not NOTEBOOKS_DIR.exists():
        print(f"No notebooks/ directory found at {NOTEBOOKS_DIR}")
        return 0

    notebooks = sorted(NOTEBOOKS_DIR.glob("*.ipynb"))
    if not notebooks:
        print("No notebooks found to validate.")
        return 0

    any_failed = False
    for nb_path in notebooks:
        errors = validate_notebook(nb_path)
        if errors:
            any_failed = True
            print(f"FAIL  {nb_path.relative_to(REPO_ROOT)}")
            for err in errors:
                print(f"      - {err}")
        else:
            print(f"OK    {nb_path.relative_to(REPO_ROOT)}")

    if any_failed:
        print("\nOne or more notebooks failed validation.")
        return 1

    print(f"\nAll {len(notebooks)} notebook(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
