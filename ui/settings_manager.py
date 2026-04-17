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
            "gemini_api_key":    "__keyring__",
            "active_model":      "qwen2.5-coder-7b",
            "chat_model":        "",
            "inline_model":      "",
            "backend":           "llama",
            "use_cloud_for_chat": False,
            "theme":             "dark",
            "token_budget":      16000,
            "trim_trailing_whitespace": False,
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
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

    def get_backend(self):
        return self.settings.get("backend", "llama")

    def get_trim_trailing_whitespace(self) -> bool:
        return bool(self.settings.get("trim_trailing_whitespace", False))

    def set_trim_trailing_whitespace(self, value: bool):
        self.settings["trim_trailing_whitespace"] = bool(value)
        self.save_settings()

    def get_token_budget(self) -> int:
        return int(self.settings.get("token_budget", 16000))

    def set_token_budget(self, value: int):
        self.settings["token_budget"] = int(value)
        self.save_settings()

    def set_backend(self, backend):
        if backend not in ("llama", "openai", "claude", "gemini"):
            raise ValueError("backend must be 'llama', 'openai', 'claude', or 'gemini'")
        self.settings["backend"] = backend
        self.save_settings()

    def get_anthropic_key(self) -> str:
        return load_api_key('anthropic')

    def get_openai_key(self) -> str:
        return load_api_key('openai')

    def get_gemini_key(self) -> str:
        return load_api_key('gemini')

    def set_api_key(self, provider, key):
        if provider == 'anthropic':
            self.settings['anthropic_api_key'] = '__keyring__'
            store_api_key('anthropic', key)
        elif provider == 'openai':
            self.settings['cloud_api_key'] = '__keyring__'
            store_api_key('openai', key)
        elif provider == 'gemini':
            self.settings['gemini_api_key'] = '__keyring__'
            store_api_key('gemini', key)
        else:
            raise ValueError("Unknown provider for API key storage")
        self.save_settings()

    def get_llm_url(self, backend=None):
        if backend is None:
            backend = self.get_backend()
        if backend == "claude":
            return "https://api.anthropic.com/v1/messages"
        if backend == "openai":
            return self.get("cloud_llm_url")
        if backend == "gemini":
            model = self.get("gemini_chat_model") or "gemini-2.0-flash"
            return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        # Default to local
        return self.get("local_llm_url")

    def get_api_key(self, backend=None):
        if backend is None:
            backend = self.get_backend()
        if backend == "claude":
            stored = self.settings.get('anthropic_api_key', '')
            if stored == "__keyring__":
                return load_api_key('anthropic')
            else:
                store_api_key('anthropic', stored)
                self.settings['anthropic_api_key'] = '__keyring__'
                self.save_settings()
                return load_api_key('anthropic')
        if backend == "openai":
            stored = self.settings.get('cloud_api_key', '')
            if stored == "__keyring__":
                return load_api_key('openai')
            else:
                store_api_key('openai', stored)
                self.settings['cloud_api_key'] = '__keyring__'
                self.save_settings()
                return load_api_key('openai')
        if backend == "gemini":
            stored = self.settings.get('gemini_api_key', '')
            if stored == "__keyring__":
                return load_api_key('gemini')
            else:
                store_api_key('gemini', stored)
                self.settings['gemini_api_key'] = '__keyring__'
                self.save_settings()
                return load_api_key('gemini')
        # Default: no API key needed for local
        return None

    def get_active_model(self, backend=None):
        if backend is None:
            backend = self.get_backend()
        if backend == "claude":
            return self.get("claude_chat_model") or "claude-sonnet-4-6"
        if backend == "openai":
            return self.get("openai_chat_model") or "gpt-4o-mini"
        if backend == "gemini":
            return self.get("gemini_chat_model") or "gemini-2.0-flash"
        # llama / local — use active_model (the local model name field)
        return self.get("active_model")

    def get_inline_model(self, backend=None):
        if backend is None:
            backend = self.get_backend()
        if backend == "openai":
            return self.get("openai_chat_model") or "gpt-4o-mini"
        if backend == "gemini":
            return self.get("gemini_chat_model") or "gemini-2.0-flash"
        # llama / local
        return self.get("inline_model")
    def get_token_budget(self) -> int:
        return int(self.get("token_budget") or 16000)

    def set_token_budget(self, value: int):
        self.settings["token_budget"] = int(value)
        self.save_settings()

import json
import os
try:
    from core.keyring_store import store_api_key, load_api_key
    _KEYRING_OK = True
except Exception:
    _KEYRING_OK = False
    def store_api_key(p, v): pass
    def load_api_key(p): return ""


