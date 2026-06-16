from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


class ModelManager:
    def __init__(self, zenie_home: Path):
        self.zenie_home = zenie_home
        self.path = zenie_home / "models.json"
        self.pid_dir = zenie_home / "pids"
        self.log_dir = zenie_home / "logs"
        self.zenie_home.mkdir(parents=True, exist_ok=True)
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def load(self):
        if not self.path.exists():
            return {"active_model": None, "models": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Invalid model registry: {self.path}: {exc}") from exc
        data.setdefault("active_model", None)
        data.setdefault("models", {})
        return data

    def save(self, data):
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def has_models(self):
        return bool(self.load()["models"])

    def list_profiles(self):
        data = self.load()
        active = data.get("active_model")
        result = []
        for name, profile in data["models"].items():
            item = dict(profile)
            item["name"] = name
            item["active"] = name == active
            item["status"] = self.status(name)["status"]
            result.append(item)
        return result

    def get(self, name=None):
        data = self.load()
        target = name or data.get("active_model")
        if not target:
            return None
        profile = data["models"].get(target)
        if not profile:
            return None
        result = dict(profile)
        result["name"] = target
        return result

    def add(self, name, profile, make_active=True):
        data = self.load()
        data["models"][name] = profile
        if make_active or not data.get("active_model"):
            data["active_model"] = name
        self.save(data)
        return self.get(name)

    def remove(self, name):
        data = self.load()
        if name not in data["models"]:
            raise KeyError(f"Unknown model profile: {name}")
        self.stop(name)
        del data["models"][name]
        if data.get("active_model") == name:
            data["active_model"] = next(iter(data["models"]), None)
        self.save(data)

    def use(self, name):
        data = self.load()
        if name not in data["models"]:
            raise KeyError(f"Unknown model profile: {name}")
        data["active_model"] = name
        self.save(data)
        return self.get(name)

    def scan_gguf(self, directory):
        root = Path(directory).expanduser()
        if not root.exists():
            raise FileNotFoundError(root)
        return sorted(
            str(path.resolve())
            for path in root.rglob("*.gguf")
            if path.is_file()
        )

    def _pid_path(self, name):
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        return self.pid_dir / f"{safe}.pid"

    def _log_path(self, name):
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        return self.log_dir / f"{safe}.log"

    def _read_pid(self, name):
        path = self._pid_path(name)
        if not path.exists():
            return None
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    def _process_alive(self, pid):
        if not pid:
            return False
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
            )
            return str(pid) in result.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _endpoint_healthy(self, base_url):
        url = base_url.rstrip("/") + "/models"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return 200 <= response.status < 500
        except Exception:
            return False

    def status(self, name=None):
        profile = self.get(name)
        if not profile:
            return {"status": "missing"}
        base_url = profile.get("base_url", "")
        if base_url and self._endpoint_healthy(base_url):
            return {"status": "running", "base_url": base_url}
        pid = self._read_pid(profile["name"])
        if pid and self._process_alive(pid):
            return {"status": "starting", "pid": pid}
        return {"status": "stopped"}

    def start(self, name=None, wait_seconds=120):
        profile = self.get(name)
        if not profile:
            raise RuntimeError("No model profile selected.")
        provider = profile.get("provider")

        if self.status(profile["name"])["status"] == "running":
            return {"status": "running", "message": "Model server is already running."}

        if provider == "llama.cpp":
            server_path = Path(profile["server_path"]).expanduser()
            model_path = Path(profile["model_path"]).expanduser()
            if not server_path.exists():
                raise FileNotFoundError(f"llama-server not found: {server_path}")
            if not model_path.exists():
                raise FileNotFoundError(f"GGUF model not found: {model_path}")

            cmd = [
                str(server_path),
                "-m", str(model_path),
                "-c", str(profile.get("context_size", 16384)),
                "--port", str(profile.get("port", 8080)),
                "--jinja",
            ]

            gpu_layers = profile.get("gpu_layers", "all")
            cmd += ["-ngl", str(gpu_layers)]

            if profile.get("flash_attention", True):
                cmd += ["-fa", "on"]
            if profile.get("kv_cache_q8", True):
                cmd += ["-ctk", "q8_0", "-ctv", "q8_0"]

            extra_args = profile.get("extra_args", [])
            if isinstance(extra_args, list):
                cmd.extend(str(x) for x in extra_args)

            log_path = self._log_path(profile["name"])
            log_file = open(log_path, "a", encoding="utf-8")
            creationflags = 0
            startupinfo = None
            if os.name == "nt":
                creationflags = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    | getattr(subprocess, "DETACHED_PROCESS", 0)
                )
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(server_path.parent),
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
            self._pid_path(profile["name"]).write_text(str(process.pid), encoding="utf-8")

        elif provider in {"ollama", "lmstudio", "openai-compatible", "litellm"}:
            if self._endpoint_healthy(profile["base_url"]):
                return {"status": "running", "message": "Provider endpoint is reachable."}
            raise RuntimeError(
                f"{provider} profile expects an external server at {profile['base_url']}. "
                "Start that provider first."
            )
        else:
            raise RuntimeError(f"Unsupported provider: {provider}")

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self._endpoint_healthy(profile["base_url"]):
                return {
                    "status": "running",
                    "pid": self._read_pid(profile["name"]),
                    "base_url": profile["base_url"],
                    "log": str(self._log_path(profile["name"])),
                }
            pid = self._read_pid(profile["name"])
            if pid and not self._process_alive(pid):
                raise RuntimeError(
                    f"Model server exited before becoming ready. "
                    f"See log: {self._log_path(profile['name'])}"
                )
            time.sleep(1)

        raise TimeoutError(
            f"Model server did not become ready within {wait_seconds} seconds. "
            f"See log: {self._log_path(profile['name'])}"
        )

    def stop(self, name=None):
        profile = self.get(name)
        if not profile:
            return {"status": "missing"}
        pid = self._read_pid(profile["name"])
        if not pid:
            return {"status": "stopped", "message": "No managed process found."}

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )
        else:
            try:
                os.kill(pid, 15)
            except OSError:
                pass

        self._pid_path(profile["name"]).unlink(missing_ok=True)
        return {"status": "stopped", "pid": pid}

    def apply_active_to_config(self, config):
        profile = self.get()
        if not profile:
            return config
        result = dict(config)
        result["base_url"] = profile.get("base_url", result.get("base_url"))
        result["api_key"] = profile.get("api_key", result.get("api_key", "none"))
        result["model"] = profile.get(
            "model",
            profile.get("name", result.get("model", "local-coder")),
        )
        if "temperature" in profile:
            result["temperature"] = profile["temperature"]
        return result
