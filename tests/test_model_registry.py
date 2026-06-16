from pathlib import Path

from zenie_code.model_manager import ModelManager


def test_model_registry_round_trip(tmp_path: Path):
    manager = ModelManager(tmp_path)
    manager.add(
        "demo",
        {
            "provider": "openai-compatible",
            "base_url": "http://127.0.0.1:9999/v1",
            "model": "demo",
            "api_key": "none",
        },
    )
    assert manager.get()["name"] == "demo"
    assert manager.load()["active_model"] == "demo"
