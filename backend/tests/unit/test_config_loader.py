"""Unit tests for provider config reload behavior."""

from app import config_loader


def _fake_dotenv_values(path):
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _configure_loader_for_tmp_env(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    missing_backend_env = tmp_path / "backend.env"
    missing_config = tmp_path / "providers.yaml"

    monkeypatch.setattr(config_loader, "_PROJECT_ROOT_ENV", env_path)
    monkeypatch.setattr(config_loader, "_BACKEND_DIR_ENV", missing_backend_env)
    monkeypatch.setattr(config_loader, "_CONFIG_PATH", missing_config)
    monkeypatch.setattr(config_loader, "_PROCESS_ENV_KEYS", frozenset())
    monkeypatch.setattr(config_loader, "_DOTENV_MANAGED_VALUES", {})
    monkeypatch.setattr(config_loader, "_dotenv_values", _fake_dotenv_values)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config_loader.reset_config()
    return env_path


def test_reset_config_reloads_updated_dotenv_values(monkeypatch, tmp_path):
    env_path = _configure_loader_for_tmp_env(monkeypatch, tmp_path)
    env_path.write_text("OPENAI_API_KEY=first-key\n", encoding="utf-8")

    config_loader.reset_config()
    assert config_loader.get_config().openai.api_key == "first-key"

    env_path.write_text("OPENAI_API_KEY=second-key\n", encoding="utf-8")
    config_loader.reset_config()
    assert config_loader.get_config().openai.api_key == "second-key"


def test_reset_config_preserves_runtime_env_overrides(monkeypatch, tmp_path):
    env_path = _configure_loader_for_tmp_env(monkeypatch, tmp_path)
    env_path.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")

    config_loader.reset_config()
    assert config_loader.get_config().openai.api_key == "dotenv-key"

    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")
    env_path.write_text("OPENAI_API_KEY=updated-dotenv-key\n", encoding="utf-8")

    config_loader.reset_config()
    assert config_loader.get_config().openai.api_key == "runtime-key"
