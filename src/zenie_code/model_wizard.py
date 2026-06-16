from __future__ import annotations

from pathlib import Path

from .model_manager import ModelManager


def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def choose(prompt, options):
    print(prompt)
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")
    while True:
        raw = input("Choice: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return idx - 1
        except ValueError:
            pass
        print("Invalid choice.")


def add_llamacpp(manager: ModelManager):
    name = ask("Profile name", "qwen-coder")
    server_path = ask("Path to llama-server.exe")
    model_path = ask("Path to GGUF model")
    port = int(ask("Port", "8080"))
    context_size = int(ask("Context size", "16384"))
    gpu_layers = ask("GPU layers", "all")
    profile = {
        "provider": "llama.cpp",
        "server_path": str(Path(server_path).expanduser()),
        "model_path": str(Path(model_path).expanduser()),
        "base_url": f"http://127.0.0.1:{port}/v1",
        "port": port,
        "context_size": context_size,
        "gpu_layers": gpu_layers,
        "flash_attention": True,
        "kv_cache_q8": True,
        "temperature": 0.15,
        "api_key": "none",
        "model": name,
    }
    return manager.add(name, profile, make_active=True)


def add_external(manager: ModelManager, provider):
    default_url = {
        "ollama": "http://127.0.0.1:11434/v1",
        "lmstudio": "http://127.0.0.1:1234/v1",
        "openai-compatible": "http://127.0.0.1:8000/v1",
        "litellm": "http://127.0.0.1:4000/v1",
    }[provider]
    name = ask("Profile name", provider)
    base_url = ask("Base URL", default_url)
    model = ask("Model name", "local-model")
    api_key = ask("API key", "none")
    profile = {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "temperature": 0.15,
    }
    return manager.add(name, profile, make_active=True)


def scan_and_add(manager: ModelManager):
    directory = ask("Directory containing GGUF models", r"C:\ai\models")
    models = manager.scan_gguf(directory)
    if not models:
        print("No GGUF models found.")
        return None
    print("Found GGUF models:")
    for i, path in enumerate(models, start=1):
        print(f"  {i}. {path}")
    selected = int(ask("Select model number", "1")) - 1
    model_path = models[selected]
    server_path = ask("Path to llama-server.exe", r"C:\ai\llama.cpp\llama-server.exe")
    name = ask("Profile name", Path(model_path).stem[:40])
    port = int(ask("Port", "8080"))
    profile = {
        "provider": "llama.cpp",
        "server_path": server_path,
        "model_path": model_path,
        "base_url": f"http://127.0.0.1:{port}/v1",
        "port": port,
        "context_size": 16384,
        "gpu_layers": "all",
        "flash_attention": True,
        "kv_cache_q8": True,
        "temperature": 0.15,
        "api_key": "none",
        "model": name,
    }
    return manager.add(name, profile, make_active=True)


def first_run_wizard(manager: ModelManager):
    options = [
        "Scan for GGUF models",
        "Add llama.cpp model manually",
        "Connect to Ollama",
        "Connect to LM Studio",
        "Connect to an OpenAI-compatible endpoint",
        "Connect to LiteLLM",
        "Exit",
    ]
    choice = choose("No AI model is configured. Select a provider:", options)
    if choice == 0:
        return scan_and_add(manager)
    if choice == 1:
        return add_llamacpp(manager)
    if choice == 2:
        return add_external(manager, "ollama")
    if choice == 3:
        return add_external(manager, "lmstudio")
    if choice == 4:
        return add_external(manager, "openai-compatible")
    if choice == 5:
        return add_external(manager, "litellm")
    return None
