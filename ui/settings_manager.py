import json
import os


class SettingsManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/quillai")
        self.config_path = os.path.join(self.config_dir, "settings.json")

        self.defaults = {
            "local_llm_url": "http://192.168.1.189:11435/v1/chat/completions",
            "cloud_llm_url": "https://api.openai.com/v1/chat/completions",
            "cloud_api_key": "",
            "active_model": "qwen2.5-coder-7b",

            # 🔥 NEW (single source of truth)
            "backend": "llama",  # "llama" or "openai"

            # (legacy, still supported but no longer primary)
            "use_cloud_for_chat": False,

            "theme": "dark"
        }

        self.settings = self.load_settings()

    # -------------------------
    # LOAD
    # -------------------------
    def load_settings(self):
        os.makedirs(self.config_dir, exist_ok=True)

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)

                # Merge with defaults
                full_settings = {**self.defaults, **loaded}

                # 🔥 MIGRATION LOGIC
                if "backend" not in loaded:
                    if full_settings.get("use_cloud_for_chat"):
                        full_settings["backend"] = "openai"
                    else:
                        full_settings["backend"] = "llama"

                print(f"DEBUG: Loaded Settings: {full_settings}")
                return full_settings

            except Exception as e:
                print(f"DEBUG: Failed to load settings: {e}")
                return self.defaults.copy()

        return self.defaults.copy()

    # -------------------------
    # SAVE
    # -------------------------
    def save_settings(self):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.settings, f, indent=4)

    # -------------------------
    # GETTERS
    # -------------------------
    def get(self, key):
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

    # -------------------------
    # 🔥 NEW HELPERS
    # -------------------------
    def get_backend(self):
        return self.get("backend")

    def set_backend(self, backend: str):
        if backend not in ["llama", "openai"]:
            raise ValueError("backend must be 'llama' or 'openai'")
        self.set("backend", backend)

    def get_api_url(self):
        if self.get_backend() == "openai":
            url = self.get("cloud_llm_url")
            if not url:
                return self.defaults["cloud_llm_url"]
            return url

        url = self.get("local_llm_url")
        if not url:
            return self.defaults["local_llm_url"]
        return url

    def get_api_key(self):
        if self.get_backend() == "openai":
            return self.get("cloud_api_key")
        return ""

    def get_model(self):
        return self.get("active_model")
