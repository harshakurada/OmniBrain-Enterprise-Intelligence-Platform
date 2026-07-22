import pytest
from backend.app.config.settings import Settings
from backend.app.core.startup_validation import (
    StartupValidationError,
    _validate_database_url,
    _validate_required_directories,
    _warn_on_insecure_production_settings,
    validate_startup_configuration,
)

# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------


def test_settings_accepts_valid_environment_values():
    for env in ("development", "staging", "production", "PRODUCTION", " Staging "):
        settings = Settings(ENVIRONMENT=env)
        assert settings.ENVIRONMENT in ("development", "staging", "production")


def test_settings_rejects_invalid_environment_value():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="not-a-real-environment")


def test_settings_is_production_property():
    assert Settings(ENVIRONMENT="production").is_production is True
    assert Settings(ENVIRONMENT="development").is_production is False
    assert Settings(ENVIRONMENT="staging").is_production is False


def test_settings_accepts_valid_log_format_values():
    assert Settings(LOG_FORMAT="text").LOG_FORMAT == "text"
    assert Settings(LOG_FORMAT="JSON").LOG_FORMAT == "json"


def test_settings_rejects_invalid_log_format_value():
    with pytest.raises(ValueError):
        Settings(LOG_FORMAT="xml")


def test_settings_default_app_version_present():
    assert Settings().APP_VERSION


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------


def test_validate_required_directories_creates_missing_dirs(tmp_path, monkeypatch):
    from backend.app.config.settings import settings as global_settings

    upload_dir = tmp_path / "uploads"
    assets_dir = tmp_path / "assets"
    faiss_dir = tmp_path / "faiss"
    log_path = tmp_path / "logs" / "app.log"

    monkeypatch.setattr(global_settings, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(global_settings, "ASSETS_DIR", str(assets_dir))
    monkeypatch.setattr(global_settings, "FAISS_STORAGE_PATH", str(faiss_dir))
    monkeypatch.setattr(global_settings, "LOG_FILE_PATH", str(log_path))

    _validate_required_directories()

    assert upload_dir.is_dir()
    assert assets_dir.is_dir()
    assert faiss_dir.is_dir()
    assert log_path.parent.is_dir()


def test_validate_database_url_rejects_empty(monkeypatch):
    from backend.app.config.settings import settings as global_settings

    monkeypatch.setattr(global_settings, "DATABASE_URL", "")
    with pytest.raises(StartupValidationError):
        _validate_database_url()


def test_validate_database_url_creates_sqlite_directory(tmp_path, monkeypatch):
    from backend.app.config.settings import settings as global_settings

    db_path = tmp_path / "nested" / "dir" / "app.db"
    monkeypatch.setattr(global_settings, "DATABASE_URL", f"sqlite:///{db_path}")

    _validate_database_url()

    assert db_path.parent.is_dir()


def test_warn_on_insecure_production_settings_only_applies_in_production(monkeypatch, caplog):
    from backend.app.config.settings import settings as global_settings

    monkeypatch.setattr(global_settings, "ENVIRONMENT", "development")
    with caplog.at_level("WARNING"):
        _warn_on_insecure_production_settings()
    assert "startup-validation" not in caplog.text


def test_warn_on_insecure_production_settings_flags_debug_and_mock_key(monkeypatch, caplog):
    from backend.app.config.settings import settings as global_settings

    monkeypatch.setattr(global_settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(global_settings, "DEBUG", True)
    monkeypatch.setattr(global_settings, "OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(global_settings, "CORS_ORIGINS", ["*"])

    with caplog.at_level("WARNING"):
        _warn_on_insecure_production_settings()

    assert "DEBUG=True in production" in caplog.text
    assert "OPENAI_API_KEY looks like a placeholder" in caplog.text
    assert "CORS_ORIGINS is wildcarded" in caplog.text


def test_validate_startup_configuration_runs_end_to_end(tmp_path, monkeypatch):
    from backend.app.config.settings import settings as global_settings

    monkeypatch.setattr(global_settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(global_settings, "ASSETS_DIR", str(tmp_path / "assets"))
    monkeypatch.setattr(global_settings, "FAISS_STORAGE_PATH", str(tmp_path / "faiss"))
    monkeypatch.setattr(global_settings, "LOG_FILE_PATH", str(tmp_path / "logs" / "app.log"))
    monkeypatch.setattr(global_settings, "DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")

    validate_startup_configuration()  # should not raise
