from quantbot.config import Settings, settings


def test_safe_defaults_declared_on_class():

    assert Settings.model_fields["binance_testnet"].default is True
    assert Settings.model_fields["binance_api_key"].default == ""
    assert Settings.model_fields["binance_api_secret"].default == ""
    assert Settings.model_fields["default_market"].default == "spot"


def test_env_can_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BINANCE_TESTNET", "false")
    monkeypatch.setenv("BINANCE_API_KEY", "dummy-key")

    settings = Settings()
    assert settings.binance_testnet is False
    assert settings.binance_api_key == "dummy-key"