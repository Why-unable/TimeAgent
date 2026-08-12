import os
from email.utils import parseaddr
from pathlib import Path

import yaml


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured for Alertmanager email delivery")
    return value


def render(path: Path) -> None:
    host = _required("EMAIL_HOST")
    port = int(os.getenv("EMAIL_PORT", "587"))
    username = _required("EMAIL_USERNAME")
    password = _required("EMAIL_PASSWORD")
    from_address = parseaddr(os.getenv("EMAIL_FROM_ADDRESS", username))[1] or username
    recipient = os.getenv("ALERTMANAGER_EMAIL_TO", "").strip() or username
    use_starttls = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
    use_implicit_tls = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
    config = {
        "global": {
            "resolve_timeout": "5m",
            "smtp_smarthost": f"{host}:{port}",
            "smtp_from": from_address,
            "smtp_auth_username": username,
            "smtp_auth_password": password,
            "smtp_require_tls": use_starttls or use_implicit_tls,
            "smtp_force_implicit_tls": use_implicit_tls,
        },
        "route": {
            "receiver": "operator-email",
            "group_by": ["alertname", "severity"],
            "group_wait": "30s",
            "group_interval": "5m",
            "repeat_interval": "4h",
        },
        "receivers": [
            {
                "name": "operator-email",
                "email_configs": [
                    {
                        "to": recipient,
                        "send_resolved": True,
                        "headers": {
                            "subject": (
                                "[Time Agent][{{ .Status | toUpper }}] "
                                "{{ .CommonLabels.alertname }}"
                            )
                        },
                    }
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    os.chmod(temporary, 0o600)
    os.chown(temporary, 65534, 65534)
    os.replace(temporary, path)


if __name__ == "__main__":
    render(Path(os.getenv("ALERTMANAGER_CONFIG_OUTPUT", "/generated/alertmanager.yml")))
