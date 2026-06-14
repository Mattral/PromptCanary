#!/usr/bin/env python3
"""
docs/sync_root_docs.py
~~~~~~~~~~~~~~~~~~~~~~

Regenerates docs/decision-log.md, docs/contributing.md, and docs/changelog.md
from their root-level source files (DECISION_LOG.md, CONTRIBUTING.md,
CHANGELOG.md).

Why this exists:
    MkDocs requires all content to live under docs/, but we want a single
    source of truth at the repo root (where GitHub renders these files
    natively without any build step). Symlinks aren't used because they
    don't survive zip/Windows-based distribution reliably. Instead, this
    script copies content with a clear header pointing back to the source.

Usage:
    python docs/sync_root_docs.py

Run this after editing DECISION_LOG.md, CONTRIBUTING.md, or CHANGELOG.md,
and before building docs (`mkdocs build`). CI can also run this as a
pre-build step to guarantee the docs site is never stale.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"

_MIRRORS = [
    ("DECISION_LOG.md", "decision-log.md", "Decision Log"),
    ("CONTRIBUTING.md", "contributing.md", "Contributing"),
    ("CODE_OF_CONDUCT.md", "code-of-conduct.md", "Code of Conduct"),
    ("CHANGELOG.md", "changelog.md", "Changelog"),
]

# Root-level filenames that these mirrored docs cross-reference, mapped to
# their docs-site page name. Applied to every mirrored file's content so a
# link like "See CODE_OF_CONDUCT.md" resolves correctly both on GitHub
# (root-relative) and won't break mkdocs --strict (docs-relative) -- we
# rewrite only within the mirrored copy, never the root source file.
_CROSS_REFERENCES = {source: dest for source, dest, _ in _MIRRORS}


def _header(source_name: str, title: str) -> str:
    return (
        f"---\ntitle: {title}\n---\n\n"
        f"<!--\n"
        f"  This page mirrors the repository root {source_name}.\n"
        f"  Source of truth: /{source_name} -- edit there, not here.\n"
        f"  Regenerate with: python docs/sync_root_docs.py\n"
        f"-->\n\n"
    )


def main() -> None:
    for source_file, dest_file, title in _MIRRORS:
        source_path = REPO_ROOT / source_file
        dest_path = DOCS_DIR / dest_file

        if not source_path.exists():
            print(f"Skipping {dest_file}: source {source_file} not found.")
            continue

        content = source_path.read_text(encoding="utf-8")

        # Rewrite links to other mirrored root docs (e.g. "CODE_OF_CONDUCT.md")
        # so they resolve to the docs-site page name (e.g. "code-of-conduct.md").
        # Only applied to the mirrored copy -- the root source file is untouched
        # and keeps its correct root-relative links for GitHub rendering.
        for ref_source, ref_dest in _CROSS_REFERENCES.items():
            if ref_source == source_file:
                continue  # don't rewrite self-references
            content = content.replace(f"]({ref_source})", f"]({ref_dest})")

        dest_path.write_text(_header(source_file, title) + content, encoding="utf-8")
        print(f"Synced {source_file} -> docs/{dest_file}")


if __name__ == "__main__":
    main()
