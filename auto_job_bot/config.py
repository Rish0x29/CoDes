"""Configuration loader for the Auto Job Application Bot."""

import os
import yaml
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def load_config(config_path=None):
    """Load configuration from YAML file with environment variable overrides."""
    path = config_path or os.environ.get("JOB_BOT_CONFIG", DEFAULT_CONFIG_PATH)

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Copy config.example.yaml to config.yaml and fill in your details."
        )

    with open(path, "r") as f:
        config = yaml.safe_load(f)

    # Allow environment variable overrides for secrets
    env_overrides = {
        "email.password": "JOB_BOT_EMAIL_PASSWORD",
        "ai.api_key": "JOB_BOT_AI_API_KEY",
    }

    for key_path, env_var in env_overrides.items():
        env_val = os.environ.get(env_var)
        if env_val:
            _set_nested(config, key_path, env_val)
            logger.debug(f"Overriding {key_path} from environment variable {env_var}")

    _validate_config(config)
    return config


def _set_nested(d, key_path, value):
    """Set a value in a nested dict using dot notation."""
    keys = key_path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _validate_config(config):
    """Validate required config fields."""
    required = [
        ("email", "imap_server"),
        ("email", "username"),
        ("email", "password"),
        ("profile", "first_name"),
        ("profile", "last_name"),
        ("profile", "email"),
        ("profile", "resume_path"),
    ]

    for section, key in required:
        if not config.get(section, {}).get(key):
            raise ValueError(f"Missing required config: {section}.{key}")

    resume_path = config["profile"]["resume_path"]
    if not os.path.exists(resume_path):
        logger.warning(f"Resume file not found: {resume_path}")
