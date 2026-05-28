from __future__ import annotations

import importlib
import subprocess

from typer.testing import CliRunner

cli_app = importlib.import_module("hinge.frontends.cli.app")


def test_export_reports_dbt_capability_failure_without_traceback(tmp_path, monkeypatch):
    output = tmp_path / "mentions.gml"

    def fail_export(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            1,
            ["dbt", "run"],
            output=(
                "Compilation Error in model user_mention_user\n"
                "  Cannot build `user_mention_user` from this adapter run. "
                "Missing capabilities: has_mentions\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(cli_app.lib, "export", fail_export)

    result = CliRunner().invoke(
        cli_app.app,
        [
            "export",
            "--dataset",
            "dataset-id",
            "--projection",
            "user-user-mention",
            "--format",
            "gml",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert "Cannot build `user_mention_user` from this adapter run." in result.output
    assert "Missing capabilities: has_mentions" in result.output
    assert "Traceback" not in result.output
    assert not output.exists()
