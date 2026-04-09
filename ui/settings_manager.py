import json
import os


class SettingsManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/quillai")
        self.config_path = os.path.join(self.config_dir, "settings.json")

        self.defaults = {
            "local_llm_url":     "http://192.168.1.189:11435/v1/chat/completions",
            "cloud_llm_url":     "https://api.openai.com/v1/chat/completions",
            "cloud_api_key":     "",
            "anthropic_api_key": "",
            "active_model":      "qwen2.5-coder-7b",
            "chat_model":        "",
            "inline_model":      "",
            "backend":           "llama",
            "use_cloud_for_chat": False,
            "theme":             "dark",
            "token_budget":      16000,
        }

        self.settings = self.load_settings()

    def load_settings(self):
        os.makedirs(self.config_dir, exist_ok=True)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    loaded = json.load(f)
                full_settings = {**self.defaults, **loaded}
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

    # ── Backend ───────────────────────────────────────────────────────────
    def get_token_budget(self) -> int:
        return int(self.settings.get('token_budget', 16000))

    def set_token_budget(self, value: int):
        self.settings['token_budget'] = int(value)
        self.save_settings()

    def get_backend(self):
        return self.get("backend")

    def set_backend(self, backend: str):
        if backend not in ("llama", "openai", "claude"):
            raise ValueError("backend must be 'llama', 'openai', or 'claude'")
        self.set("backend", backend)

    # ── URLs & Keys ───────────────────────────────────────────────────────
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

    # ── Models ────────────────────────────────────────────────────────────
    def get_model(self):
        """Active/local model name — used as the base fallback."""
        return self.get("active_model")

    def get_chat_model(self):
        """Model for chat requests. Falls back to a sensible default per backend."""
        explicit = self.get("chat_model")
        if explicit:
            return explicit
        backend = self.get_backend()
        if backend == "openai":
            return "gpt-4o-mini"
        if backend == "claude":
            return "claude-sonnet-4-6"
        return self.get("active_model")

    def get_inline_model(self):
        """Model for inline completions. Prefers a fast/cheap model per backend."""
        explicit = self.get("inline_model")
        if explicit:
            return explicit
        backend = self.get_backend()
        if backend == "openai":
            return "gpt-4o-mini"
        if backend == "claude":
            return "claude-haiku-4-5-20251001"
        return self.get("active_model")
