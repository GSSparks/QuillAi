import json
import os
try:
    from core.keyring_store import store_api_key, load_api_key
    _KEYRING_OK = True
except Exception:
    _KEYRING_OK = False
    def store_api_key(p, v): pass
    def load_api_key(p): return ""


class SettingsManager:
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/quillai")
        self.config_path = os.path.join(self.config_dir, "settings.json")

        self.defaults = {
            "local_llm_url":     "http://192.168.1.189:11435/v1/chat/completions",
            "cloud_llm_url":     "https://api.openai.com/v1/chat/completions",
            "cloud_api_key":     "__keyring__",
            "anthropic_api_key": "__keyring__",
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

    def get_anthropic_key(self) -> str:
        return load_api_key('anthropic')

    def get_openai_key(self) -> str:
        return load_api_key('openai')

    def set_api_key(self, provider: str, value: str):
        """Store API key securely in keyring."""
        store_api_key(provider, value)
        # Keep placeholder in JSON so we know it's set
        if provider == 'anthropic':
            self.settings['anthropic_api_key'] = '__keyring__'
        else:
            self.settings['cloud_api_key'] = '__keyring__'
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
        """Return the API key for the current backend."""
        backend = self.get_backend()
        if backend == 'claude':
            stored = self.settings.get('anthropic_api_key', '')
            if stored in ('', '__keyring__'):
                return load_api_key('anthropic')
            # Migrate plain text to keyring
            store_api_key('anthropic', stored)
            self.settings['anthropic_api_key'] = '__keyring__'
            self.save_settings()
            return stored
        else:
            stored = self.settings.get('cloud_api_key', '')
            if stored in ('', '__keyring__'):
                return load_api_key('openai')
            # Migrate plain text to keyring
            store_api_key('openai', stored)
            self.settings['cloud_api_key'] = '__keyring__'
            self.save_settings()
            return stored
        # unreachable but satisfies linter
        return ''  # noqa

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
        """Model for chat requests — backend-aware, reads correct key per backend."""
        backend = self.get_backend()
        if backend == "claude":
            return self.get("claude_chat_model") or "claude-sonnet-4-6"
        if backend == "openai":
            return self.get("openai_chat_model") or "gpt-4o-mini"
        # llama / local — use active_model (the local model name field)
        return self.get("active_model") or ""

    def get_inline_model(self):
        """Model for inline completions — backend-aware, reads correct key per backend."""
        backend = self.get_backend()
        if backend == "claude":
            return self.get("claude_inline_model") or "claude-haiku-4-5-20251001"
        if backend == "openai":
            return self.get("openai_chat_model") or "gpt-4o-mini"
        # llama / local
        return self.get("active_model") or ""
