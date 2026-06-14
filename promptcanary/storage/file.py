"""
promptcanary.storage
~~~~~~~~~~~~~~~~~~~~~

Baseline storage: save and load :class:`BaselineSnapshot` objects.

MVP: Local JSON file storage.
Post-MVP hooks: S3, GCS, database backends.

Usage::

    from promptcanary.storage import FileBaselineStore

    store = FileBaselineStore("baselines/")

    # Save a baseline
    snapshot = store.save(run_result)
    print(snapshot.snapshot_id)

    # Load most recent baseline for a suite+provider combo
    snapshot = store.load_latest(suite_name="my-suite", model_id="openai/gpt-4o")

    # List all saved baselines
    for meta in store.list_baselines():
        print(meta)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from promptcanary.core.models import BaselineSnapshot, CanaryRunResult


class FileBaselineStore:
    """Stores and retrieves :class:`BaselineSnapshot` objects as JSON files.

    Args:
        directory: Directory where baseline JSON files are stored.
                   Created automatically if it doesn't exist.

    File naming: ``{suite_name}__{model_slug}__{timestamp}.json``
    (URL-safe, avoiding characters that cause shell issues)

    Example::

        store = FileBaselineStore("baselines/")
        snapshot = store.save(run_result)
        loaded = store.load(snapshot.snapshot_id)
        latest = store.load_latest("my-suite", "openai/gpt-4o")
    """

    def __init__(self, directory: str | Path = "baselines") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    # ── Save ────────────────────────────────────────────────────────────────

    def save(
        self,
        run_result: CanaryRunResult,
        *,
        note: str = "",
        snapshot_id: str | None = None,
    ) -> BaselineSnapshot:
        """Save a :class:`CanaryRunResult` as a baseline snapshot.

        Args:
            run_result:  The run to persist.
            note:        Optional human note (stored in the JSON).
            snapshot_id: Override the auto-generated ID (useful for testing).

        Returns:
            The saved :class:`BaselineSnapshot`.
        """
        snapshot = BaselineSnapshot(
            suite_name=run_result.suite_name,
            provider=run_result.provider,
            run_result=run_result,
        )
        if snapshot_id:
            # Pydantic frozen model — rebuild with custom ID
            snapshot = snapshot.model_copy(update={"snapshot_id": snapshot_id})

        filename = self._filename(
            suite_name=run_result.suite_name,
            model_id=run_result.provider.model_id,
            ts=snapshot.created_at,
            snap_id=snapshot.snapshot_id,
        )

        data: dict[str, Any] = snapshot.model_dump(mode="json")
        if note:
            data["_note"] = note

        path = self.directory / filename
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

        return snapshot

    # ── Load ────────────────────────────────────────────────────────────────

    def load(self, snapshot_id: str) -> BaselineSnapshot:
        """Load a snapshot by its ID.

        Args:
            snapshot_id: The UUID of the snapshot to load.

        Raises:
            FileNotFoundError: If no snapshot with that ID exists.
        """
        matches = list(self.directory.glob(f"*_{snapshot_id[:8]}*.json"))
        if not matches:
            # Try full scan
            matches = [
                f
                for f in self.directory.glob("*.json")
                if snapshot_id in f.read_text(encoding="utf-8")
            ]
        if not matches:
            raise FileNotFoundError(
                f"No baseline snapshot found with ID starting with '{snapshot_id[:8]}'. "
                f"Available baselines: {[f.name for f in self.directory.glob('*.json')]}"
            )
        return self._load_file(matches[0])

    def load_from_path(self, path: str | Path) -> BaselineSnapshot:
        """Load a snapshot directly from a JSON file path."""
        return self._load_file(Path(path))

    def load_latest(
        self,
        suite_name: str,
        model_id: str | None = None,
    ) -> BaselineSnapshot:
        """Load the most recently saved baseline for a given suite and provider.

        Args:
            suite_name: Name of the canary suite.
            model_id:   Optional model ID filter (e.g. ``"openai/gpt-4o"``).

        Raises:
            FileNotFoundError: If no matching baseline exists.
        """
        candidates = self._list_files(suite_name=suite_name, model_id=model_id)
        if not candidates:
            raise FileNotFoundError(
                f"No baseline found for suite={suite_name!r}"
                + (f", model={model_id!r}" if model_id else "")
                + f". Store directory: {self.directory}"
            )
        # Most recent first (filename has ISO timestamp)
        candidates.sort(reverse=True)
        return self._load_file(candidates[0])

    # ── List ────────────────────────────────────────────────────────────────

    def list_baselines(
        self,
        suite_name: str | None = None,
        model_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List stored baselines with lightweight metadata (no full deserialization).

        Returns a list of dicts with keys: path, snapshot_id, suite_name,
        model_id, created_at.
        """
        files = self._list_files(suite_name=suite_name, model_id=model_id)
        results = []
        for f in sorted(files, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append(
                    {
                        "path": str(f),
                        "snapshot_id": data.get("snapshot_id", "?"),
                        "suite_name": data.get("suite_name", "?"),
                        "model_id": data.get("provider", {}).get("model_id", "?"),
                        "created_at": data.get("created_at", "?"),
                        "note": data.get("_note", ""),
                    }
                )
            except Exception:
                continue
        return results

    def delete(self, snapshot_id: str) -> bool:
        """Delete a baseline by snapshot ID. Returns True if deleted."""
        matches = list(self.directory.glob(f"*{snapshot_id[:8]}*.json"))
        if not matches:
            return False
        for m in matches:
            m.unlink(missing_ok=True)
        return True

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _filename(suite_name: str, model_id: str, ts: datetime, snap_id: str) -> str:
        """Build a deterministic, shell-safe filename."""
        suite_slug = suite_name.replace("/", "-").replace(" ", "_")[:40]
        model_slug = model_id.replace("/", "-").replace(":", "-")[:40]
        ts_str = ts.strftime("%Y%m%dT%H%M%S")
        id_short = snap_id[:8]
        return f"{suite_slug}__{model_slug}__{ts_str}_{id_short}.json"

    def _list_files(
        self,
        suite_name: str | None = None,
        model_id: str | None = None,
    ) -> list[Path]:
        """Return matching JSON files from the store directory."""
        all_files = list(self.directory.glob("*.json"))
        if not suite_name and not model_id:
            return all_files

        results = []
        suite_slug = suite_name.replace("/", "-").replace(" ", "_") if suite_name else None
        model_slug = model_id.replace("/", "-").replace(":", "-") if model_id else None

        for f in all_files:
            name = f.name
            if suite_slug and not name.startswith(suite_slug[:20]):
                # Fall back to reading file for edge cases
                pass
            if suite_slug and suite_slug[:20] not in name:
                continue
            if model_slug and model_slug[:20] not in name:
                continue
            results.append(f)
        return results

    def _load_file(self, path: Path) -> BaselineSnapshot:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Remove internal metadata before parsing
        data.pop("_note", None)
        return BaselineSnapshot.model_validate(data)
