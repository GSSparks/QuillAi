import json
import os

class SettingsManager:
    def __init__(self):
        # Standard Linux config path: ~/.config/quillai/settings.json
        self.config_dir = os.path.expanduser("~/.config/quillai")
        self.config_path = os.path.join(self.config_dir, "settings.json")

        self.defaults = {
            "local_llm_url": "http://192.168.1.189:11435/v1/chat/completions",
            "cloud_llm_url": "https://api.openai.com/v1/chat/completions",
            "cloud_api_key": "",
            "active_model": "qwen2.5-coder-7b",
            "use_cloud_for_chat": False,
            "theme": "dark"
        }
        self.settings = self.load_settings()

    def load_settings(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    loaded = json.load(f)
                    # Merge loaded with defaults in case we add new settings later
                    return {**self.defaults, **loaded}
            except:
                return self.defaults
        return self.defaults

    def save_settings(self):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()
