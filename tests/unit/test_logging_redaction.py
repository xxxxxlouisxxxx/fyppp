from __future__ import annotations

import logging

from geo_research.logging_config import configure_logging


def test_logging_redacts_credentials_and_secret_url_parameters(caplog) -> None:
    configure_logging("geo_research.test")
    logger = logging.getLogger("geo_research.test")

    with caplog.at_level(logging.INFO, logger="geo_research.test"):
        logger.info(
            "DATAFORSEO_LOGIN=login DATAFORSEO_PASSWORD=password "
            "Authorization: Basic bG9naW46cGFzc3dvcmQ= "
            "https://example.test/?api_key=api-secret&token=token-secret"
        )

    assert "login" not in caplog.text
    assert "password" not in caplog.text
    assert "bG9naW46cGFzc3dvcmQ=" not in caplog.text
    assert "api-secret" not in caplog.text
    assert "token-secret" not in caplog.text
    assert "[REDACTED]" in caplog.text
