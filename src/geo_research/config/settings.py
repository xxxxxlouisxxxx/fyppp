"""Typed configuration loading with explicit source precedence."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Literal

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from geo_research.config.paths import RepositoryPaths
from geo_research.exceptions import ConfigurationError

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Non-secret YAML settings plus environment-only credentials."""

    model_config = SettingsConfigDict(extra="forbid")

    app_name: str = "geo-research"
    log_level: LogLevel = "INFO"
    duckdb_path: Path = Path("data/warehouse/geo_research.duckdb")
    dataforseo_login: SecretStr | None = Field(default=None, repr=False)
    dataforseo_password: SecretStr | None = Field(default=None, repr=False)
    real_api_kill_switch: bool = True

    _yaml_fields: ClassVar[frozenset[str]] = frozenset({"log_level", "duckdb_path"})
    _environment_fields: ClassVar[dict[str, str]] = {
        "GEO_RESEARCH_LOG_LEVEL": "log_level",
        "DUCKDB_PATH": "duckdb_path",
        "DATAFORSEO_LOGIN": "dataforseo_login",
        "DATAFORSEO_PASSWORD": "dataforseo_password",
        "GEO_RESEARCH_REAL_API_KILL_SWITCH": "real_api_kill_switch",
    }
    _secret_fields: ClassVar[frozenset[str]] = frozenset(
        {"dataforseo_login", "dataforseo_password"}
    )

    @classmethod
    def load(
        cls,
        config_file: Path | None = None,
        dotenv_file: Path | None = None,
        overrides: Mapping[str, Any] | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> Settings:
        """Load defaults, YAML, local .env, environment variables, then overrides."""
        values: dict[str, Any] = {}
        if config_file is not None:
            values.update(cls._load_yaml(config_file))

        local_dotenv = dotenv_file or RepositoryPaths.discover().root / ".env"
        values.update(cls._load_dotenv(local_dotenv))
        source_environment = os.environ if environment is None else environment
        for environment_name, field_name in cls._environment_fields.items():
            value = source_environment.get(environment_name)
            if value is not None:
                values[field_name] = value

        if overrides is not None:
            cls._validate_override_keys(overrides)
            values.update(overrides)
        return cls(**values)

    @classmethod
    def _load_dotenv(cls, dotenv_file: Path) -> dict[str, str]:
        """Load supported local environment values without mutating os.environ."""
        if not dotenv_file.exists():
            return {}
        try:
            content = dotenv_file.read_text(encoding="utf-8")
        except OSError as error:
            raise ConfigurationError("Unable to read local .env file") from error

        values: dict[str, str] = {}
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                raise ConfigurationError("Invalid local .env entry")
            environment_name, value = stripped.split("=", maxsplit=1)
            field_name = cls._environment_fields.get(environment_name.strip())
            if field_name is None:
                continue
            values[field_name] = value.strip().strip("\"'")
        return values

    @classmethod
    def _load_yaml(cls, config_file: Path) -> dict[str, Any]:
        try:
            loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        except OSError as error:
            raise ConfigurationError(
                f"Unable to read configuration file: {config_file}"
            ) from error
        except yaml.YAMLError as error:
            raise ConfigurationError(
                f"Invalid YAML configuration: {config_file}"
            ) from error
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigurationError("YAML configuration must be a mapping")
        unknown_fields = set(loaded) - cls._yaml_fields
        if unknown_fields & cls._secret_fields:
            raise ConfigurationError("YAML configuration must not contain credentials")
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise ConfigurationError(
                f"Unsupported YAML configuration fields: {unknown}"
            )
        return dict(loaded)

    @classmethod
    def _validate_override_keys(cls, overrides: Mapping[str, Any]) -> None:
        disallowed = set(overrides) & cls._secret_fields
        if disallowed:
            raise ConfigurationError("Explicit overrides must not contain credentials")
        unknown = set(overrides) - {"log_level", "duckdb_path"}
        if unknown:
            fields = ", ".join(sorted(unknown))
            raise ConfigurationError(f"Unsupported explicit overrides: {fields}")

    def safe_summary(self) -> dict[str, str | bool]:
        """Return diagnostics that intentionally omit secret values."""
        return {
            "app_name": self.app_name,
            "log_level": self.log_level,
            "duckdb_path": str(self.duckdb_path),
            "dataforseo_login_configured": self.dataforseo_login is not None,
            "dataforseo_password_configured": self.dataforseo_password is not None,
            "real_api_kill_switch": self.real_api_kill_switch,
        }
