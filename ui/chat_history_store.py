import json
import os
from datetime import datetime, timedelta

CHAT_FILE = os.path.join(os.path.expanduser("~"), ".config", "quillai", "chat_history.json")
MAX_AGE_DAYS = 7
MAX_MESSAGES = 200


def load_chat_history() -> str:
    """Returns saved chat text or empty string."""
    if not os.path.exists(CHAT_FILE):
        return ""
    try:
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Check age
        saved_date = datetime.fromisoformat(data.get("date", "2000-01-01"))
        if datetime.now() - saved_date > timedelta(days=MAX_AGE_DAYS):
            return ""
        return data.get("text", "")
    except Exception:
        return ""


def save_chat_history(text: str):
    """Persists the current chat text to disk."""
    os.makedirs(os.path.dirname(CHAT_FILE), exist_ok=True)
    try:
        # Trim to last MAX_MESSAGES exchanges to keep it manageable
        lines = text.strip().split('\n')
        if len(lines) > MAX_MESSAGES * 4:
            lines = lines[-(MAX_MESSAGES * 4):]
        with open(CHAT_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "date": datetime.now().isoformat(),
                "text": "\n".join(lines),
            }, f)
    except Exception as e:
        print(f"Could not save chat history: {e}")