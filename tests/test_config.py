from zenie_code.config_manager import DEFAULT_CONFIG


def test_default_config_has_model_endpoint():
    assert DEFAULT_CONFIG["base_url"].endswith("/v1")
    assert DEFAULT_CONFIG["model"]
