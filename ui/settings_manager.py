import json
import os


class SettingsManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/quillai")
        self.config_path = os.path.join(self.config_dir, "settings.json")

        self.defaults = {
            "local_llm_url":    "http://192.168.1.189:11435/v1/chat/completions",
            "cloud_llm_url":    "https://api.openai.com/v1/chat/completions",
            "cloud_api_key":    "",
            "anthropic_api_key": "",
            "active_model":     "qwen2.5-coder-7b",
            "chat_model":       "",   # if blank, falls back to active_model
            "backend":          "llama",
            "use_cloud_for_chat": False,
            "theme":            "dark",
        }

        self.settings = self.load_settings()

    def load_settings(self):
        os.makedirs(self.config_dir, exist_ok=True)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                full_settings = {**self.defaults, **loaded}
                # Migration: infer backend from legacy flag
                if "backend" not in loaded:
                    full_settings["backend"] = (
                        "openai" if full_settings.get("use_cloud_for_chat") else "llama"
                    )
                return full_settings
            except Exception as e:
                print(f"Failed to load settings: {e}")
                return self.defaults.copy()
        return self.defaults.copy()

    def save_settings(self):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

    def get_backend(self):
        return self.get("backend")

    def set_backend(self, backend: str):
        if backend not in ("llama", "openai", "claude"):
            raise ValueError("backend must be 'llama', 'openai', or 'claude'")
        self.set("backend", backend)

    def get_api_url(self):
        backend = self.get_backend()
        if backend == "claude":
            return "https://api.anthropic.com/v1/messages"
        if backend == "openai":
            return self.get("cloud_llm_url") or self.defaults["cloud_llm_url"]
        return self.get("local_llm_url") or self.defaults["local_llm_url"]

    def get_api_key(self):
        backend = self.get_backend()
        if backend == "claude":
            return self.get("anthropic_api_key")
        if backend == "openai":
            return self.get("cloud_api_key")
        return ""

    def get_model(self):
        return self.get("active_model")

    def get_chat_model(self):
        """Returns a separate model for chat, falling back to active_model if unset."""
        return self.get("chat_model") or self.get("active_model")