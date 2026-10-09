"""Credential handling for DataForSEO basic authentication."""

from __future__ import annotations

import base64

from pydantic import BaseModel, ConfigDict, SecretStr


class DataForSEOCredentials(BaseModel):
    """Credentials that are never rendered in model representation or errors."""

    model_config = ConfigDict(strict=True)

    login: SecretStr
    password: SecretStr

    def authorization_header(self) -> str:
        """Create a Basic authentication value for an outgoing request only."""
        raw = (
            f"{self.login.get_secret_value()}:{self.password.get_secret_value()}"
        ).encode()
        return f"Basic {base64.b64encode(raw).decode()}"
