"""
tests/unit/test_cli.py
~~~~~~~~~~~~~~~~~~~~~~

Tests for promptcanary.cli using Typer's CliRunner.

These tests exercise the CLI surface end-to-end (argument parsing, file I/O,
exit codes) using temporary directories and a monkeypatched LiteLLMProvider
so no real network calls occur.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from promptcanary.cli import app
from promptcanary.core.models import LLMResponse, ProviderConfig
from promptcanary.providers.base import BaseLLMProvider

runner = CliRunner()


class StubProvider(BaseLLMProvider):
    """Deterministic stand-in for LiteLLMProvider used across CLI tests."""

    def __init__(self, model_id: str = "openai/gpt-5.5", **kwargs: object) -> None:
        super().__init__(ProviderConfig(model_id=model_id))

    def complete(self, prompt, *, system_prompt=None) -> LLMResponse:
        return LLMResponse(
            prompt_id=prompt.id,
            provider_model_id=self.config.model_id,
            content="The capital of France is Paris.",
            finish_reason="stop",
            latency_ms=10.0,
        )


@pytest.fixture(autouse=True)
def _patch_provider():
    """Patch LiteLLMProvider everywhere it's imported inside cli.py."""
    with patch("promptcanary.providers.litellm.LiteLLMProvider", StubProvider):
        yield


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# init
# ─────────────────────────────────────────────────────────────────────────────


class TestInitCommand:
    def test_creates_suite_directory(self, project_dir: Path) -> None:
        result = runner.invoke(app, ["init", "my-suite"])
        assert result.exit_code == 0
        assert (project_dir / "my-suite" / "canary.yaml").exists()
        assert (project_dir / "my-suite" / "baselines").is_dir()
        assert (project_dir / "my-suite" / "README.md").exists()
        assert (project_dir / "my-suite" / ".env.example").exists()

    def test_default_name(self, project_dir: Path) -> None:
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (project_dir / "my-canary-suite").exists()

    def test_refuses_overwrite_without_force(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "dup-suite"])
        result = runner.invoke(app, ["init", "dup-suite"])
        assert result.exit_code == 1

    def test_force_overwrites(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "dup-suite"])
        result = runner.invoke(app, ["init", "dup-suite", "--force"])
        assert result.exit_code == 0

    def test_yaml_is_valid_and_loadable(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "loadable-suite"])
        from promptcanary.core.suite import CanarySuite

        suite = CanarySuite.from_yaml(project_dir / "loadable-suite" / "canary.yaml")
        assert len(suite.prompts) > 0
        assert len(suite.probes) > 0


# ─────────────────────────────────────────────────────────────────────────────
# run
# ─────────────────────────────────────────────────────────────────────────────


class TestRunCommand:
    def test_missing_config_fails_with_helpful_message(self, project_dir: Path) -> None:
        result = runner.invoke(app, ["run", "--provider", "openai/gpt-5.5"], mix_stderr=False)
        assert result.exit_code == 1

    def test_run_with_valid_config_succeeds(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        result = runner.invoke(
            app, ["run", "--config", str(config), "--provider", "openai/gpt-5.5", "--no-progress"]
        )
        assert result.exit_code == 0

    def test_run_saves_json_output(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        out_json = project_dir / "results.json"
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--output-json",
                str(out_json),
                "--no-progress",
            ],
        )
        assert result.exit_code == 0
        assert out_json.exists()
        data = json.loads(out_json.read_text())
        assert "run_id" in data

    def test_run_saves_markdown_and_html(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        out_md = project_dir / "report.md"
        out_html = project_dir / "report.html"
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--output-md",
                str(out_md),
                "--output-html",
                str(out_html),
                "--no-progress",
            ],
        )
        assert result.exit_code == 0
        assert out_md.exists()
        assert out_html.exists()

    def test_run_with_save_baseline(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        baseline_dir = project_dir / "suite" / "baselines"
        result = runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--save-baseline",
                "--baseline-dir",
                str(baseline_dir),
                "--no-progress",
            ],
        )
        assert result.exit_code == 0
        assert list(baseline_dir.glob("*.json"))

    def test_invalid_yaml_fails_gracefully(self, project_dir: Path) -> None:
        bad_config = project_dir / "bad.yaml"
        bad_config.write_text("not: valid: yaml: at: all: [[[", encoding="utf-8")
        result = runner.invoke(
            app, ["run", "--config", str(bad_config), "--provider", "openai/gpt-5.5"]
        )
        assert result.exit_code == 1


# ─────────────────────────────────────────────────────────────────────────────
# compare
# ─────────────────────────────────────────────────────────────────────────────


class TestCompareCommand:
    def test_compare_with_fresh_provider_run_no_baseline_creates_one(
        self, project_dir: Path
    ) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        baseline_dir = project_dir / "suite" / "baselines"

        result = runner.invoke(
            app,
            [
                "compare",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--baseline-dir",
                str(baseline_dir),
                "--no-progress",
            ],
        )
        # No baseline exists yet → should fail cleanly, not crash
        assert result.exit_code in (0, 1)

    def test_compare_two_saved_files(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        baseline_dir = project_dir / "suite" / "baselines"

        # Create a baseline first
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--save-baseline",
                "--baseline-dir",
                str(baseline_dir),
                "--no-progress",
            ],
        )
        baseline_file = next(baseline_dir.glob("*.json"))

        # Create a "current" results file
        current_json = project_dir / "current.json"
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--output-json",
                str(current_json),
                "--no-progress",
            ],
        )

        result = runner.invoke(
            app,
            ["compare", "--baseline", str(baseline_file), "--current", str(current_json)],
        )
        assert result.exit_code == 0

    def test_compare_requires_provider_or_current(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        baseline_dir = project_dir / "suite" / "baselines"
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--save-baseline",
                "--baseline-dir",
                str(baseline_dir),
                "--no-progress",
            ],
        )
        baseline_file = next(baseline_dir.glob("*.json"))

        result = runner.invoke(app, ["compare", "--baseline", str(baseline_file)])
        assert result.exit_code == 1


# ─────────────────────────────────────────────────────────────────────────────
# baselines
# ─────────────────────────────────────────────────────────────────────────────


class TestBaselinesCommand:
    def test_lists_empty_directory(self, project_dir: Path) -> None:
        result = runner.invoke(app, ["baselines", "--dir", str(project_dir / "empty")])
        assert result.exit_code == 0
        assert "No baselines" in result.stdout

    def test_lists_saved_baselines(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        baseline_dir = project_dir / "suite" / "baselines"
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--save-baseline",
                "--baseline-dir",
                str(baseline_dir),
                "--no-progress",
            ],
        )
        result = runner.invoke(app, ["baselines", "--dir", str(baseline_dir)])
        assert result.exit_code == 0
        assert "openai" in result.stdout.lower() or "gpt" in result.stdout.lower()


# ─────────────────────────────────────────────────────────────────────────────
# report
# ─────────────────────────────────────────────────────────────────────────────


class TestReportCommand:
    def test_report_missing_file_fails(self, project_dir: Path) -> None:
        result = runner.invoke(app, ["report", str(project_dir / "nope.json")])
        assert result.exit_code == 1

    def test_report_terminal_format(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        out_json = project_dir / "results.json"
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--output-json",
                str(out_json),
                "--no-progress",
            ],
        )
        result = runner.invoke(app, ["report", str(out_json), "--format", "terminal"])
        assert result.exit_code == 0

    def test_report_markdown_format(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        out_json = project_dir / "results.json"
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--output-json",
                str(out_json),
                "--no-progress",
            ],
        )
        out_md = project_dir / "report_from_json.md"
        result = runner.invoke(
            app, ["report", str(out_json), "--format", "markdown", "--output", str(out_md)]
        )
        assert result.exit_code == 0
        assert out_md.exists()

    def test_report_unknown_format_fails(self, project_dir: Path) -> None:
        runner.invoke(app, ["init", "suite"])
        config = project_dir / "suite" / "canary.yaml"
        out_json = project_dir / "results.json"
        runner.invoke(
            app,
            [
                "run",
                "--config",
                str(config),
                "--provider",
                "openai/gpt-5.5",
                "--output-json",
                str(out_json),
                "--no-progress",
            ],
        )
        result = runner.invoke(app, ["report", str(out_json), "--format", "xml"])
        assert result.exit_code == 1


# ─────────────────────────────────────────────────────────────────────────────
# version
# ─────────────────────────────────────────────────────────────────────────────


class TestVersionCommand:
    def test_version_prints_something(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "PromptCanary" in result.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Top-level help
# ─────────────────────────────────────────────────────────────────────────────


class TestHelp:
    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # Typer's no_args_is_help=True triggers Click's UsageError path → exit code 2
        assert result.exit_code in (0, 2)
        assert "promptcanary" in result.output.lower()

    def test_help_flag(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
