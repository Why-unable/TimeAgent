import json
import logging
from pathlib import Path

import pytest
import yaml

from apps.observability.alertmanager_config import render
from config.observability import SafeJsonFormatter


def test_safe_json_formatter_emits_valid_allowlisted_context() -> None:
    record = logging.LogRecord(
        name="time_agent.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=12,
        msg='failed with "quotes"',
        args=(),
        exc_info=None,
    )
    record.request_id = "request-1"
    record.error_code = "model_timeout"
    record.total_tokens = 321
    record.memory_prompt_ratio = 0.125
    record.user_id = "must-not-be-exported"

    payload = json.loads(SafeJsonFormatter().format(record))

    assert payload["message"] == 'failed with "quotes"'
    assert payload["request_id"] == "request-1"
    assert payload["error_code"] == "model_timeout"
    assert payload["total_tokens"] == 321
    assert payload["memory_prompt_ratio"] == 0.125
    assert "user_id" not in payload


def test_alertmanager_config_uses_runtime_smtp_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.test")
    monkeypatch.setenv("EMAIL_PORT", "587")
    monkeypatch.setenv("EMAIL_USERNAME", "mailer@example.test")
    monkeypatch.setenv("EMAIL_PASSWORD", "runtime-only-password")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "Time Agent <alerts@example.test>")
    monkeypatch.setenv("EMAIL_USE_TLS", "true")
    monkeypatch.setenv("EMAIL_USE_SSL", "false")
    monkeypatch.setenv("ALERTMANAGER_EMAIL_TO", "operator@example.test")
    monkeypatch.setattr("apps.observability.alertmanager_config.os.chown", lambda *args: None)
    output = tmp_path / "alertmanager.yml"

    render(output)

    config = yaml.safe_load(output.read_text())
    assert config["global"]["smtp_smarthost"] == "smtp.example.test:587"
    assert config["global"]["smtp_auth_password"] == "runtime-only-password"
    assert config["global"]["smtp_require_tls"] is True
    assert config["global"]["smtp_force_implicit_tls"] is False
    assert config["receivers"][0]["email_configs"][0]["to"] == "operator@example.test"
    assert output.stat().st_mode & 0o777 == 0o600


def test_alertmanager_config_forces_implicit_tls_for_ssl_smtp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.test")
    monkeypatch.setenv("EMAIL_PORT", "465")
    monkeypatch.setenv("EMAIL_USERNAME", "mailer@example.test")
    monkeypatch.setenv("EMAIL_PASSWORD", "runtime-only-password")
    monkeypatch.setenv("EMAIL_USE_TLS", "false")
    monkeypatch.setenv("EMAIL_USE_SSL", "true")
    monkeypatch.setattr("apps.observability.alertmanager_config.os.chown", lambda *args: None)
    output = tmp_path / "alertmanager.yml"

    render(output)

    config = yaml.safe_load(output.read_text())
    assert config["global"]["smtp_smarthost"] == "smtp.example.test:465"
    assert config["global"]["smtp_require_tls"] is True
    assert config["global"]["smtp_force_implicit_tls"] is True
