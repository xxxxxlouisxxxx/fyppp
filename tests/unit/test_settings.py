from __future__ import annotations

from pathlib import Path

import pytest

from geo_research.config.settings import Settings


def test_settings_precedence_defaults_yaml_environment_then_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        "log_level: WARNING\nduckdb_path: yaml.duckdb\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GEO_RESEARCH_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("DUCKDB_PATH", "environment.duckdb")

    settings = Settings.load(
        config_file=config_file,
        overrides={"log_level": "DEBUG"},
    )

    assert settings.app_name == "geo-research"
    assert settings.log_level == "DEBUG"
    assert settings.duckdb_path == Path("environment.duckdb")


def test_credentials_are_optional_and_redacted_from_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAFORSEO_LOGIN", "test-login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "test-password")

    settings = Settings.load()

    assert settings.dataforseo_login is not None
    assert settings.dataforseo_password is not None
    assert "test-login" not in repr(settings)
    assert "test-password" not in repr(settings)


def test_dotenv_loads_credentials_without_overriding_shell_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "DATAFORSEO_LOGIN=dotenv-login\nDATAFORSEO_PASSWORD=dotenv-password\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATAFORSEO_LOGIN", "shell-login")

    settings = Settings.load(dotenv_file=dotenv_file)

    assert settings.dataforseo_login is not None
    assert settings.dataforseo_login.get_secret_value() == "shell-login"
    assert settings.dataforseo_password is not None
    assert settings.dataforseo_password.get_secret_value() == "dotenv-password"


def test_yaml_rejects_credentials(tmp_path: Path) -> None:
    config_file = tmp_path / "settings.yaml"
    config_file.write_text("dataforseo_password: unsafe\n", encoding="utf-8")

    with pytest.raises(ValueError, match="credentials"):
        Settings.load(config_file=config_file)
