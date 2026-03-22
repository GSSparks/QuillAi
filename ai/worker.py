import requests
import json
from PyQt6.QtCore import QObject, pyqtSignal

def clean_code(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  
        text = "\n".join(lines)

    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]

    return text.strip()

class AIWorker(QObject):
    update_ghost = pyqtSignal(str)     
    function_ready = pyqtSignal(str)   
    chat_update = pyqtSignal(str) # [NEW] Signal for chat streaming
    finished = pyqtSignal()

    def __init__(
        self,
        prompt: str,
        editor_text: str,
        cursor_pos: int,
        generate_function: bool = False,
        is_edit: bool = False,
        is_chat: bool = False, 
        model: str = "qwen2.5-coder-7b",
        api_url: str = "http://192.168.1.189:11435/v1/chat/completions",
    ):
        super().__init__()

        self.prompt = prompt
        self.editor_text = editor_text
        self.cursor_pos = int(cursor_pos)
        self.generate_function = generate_function
        self.is_edit = is_edit
        self.is_chat = is_chat
        self.model = model
        self.api_url = api_url

        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def build_messages(self):
        # [NEW] Chat Mode Prompt
        if self.is_chat:
            return [
                {
                    "role": "system",
                    "content": "You are QuillAi, a helpful programming assistant built directly into the user's IDE. Be concise, friendly, and use markdown for code blocks."
                },
                {
                    "role": "user",
                    "content": self.prompt
                }
            ]

        before = self.editor_text[max(0, self.cursor_pos - 1000):self.cursor_pos]
        after = self.editor_text[self.cursor_pos:self.cursor_pos + 300]

        if self.is_edit:
            return [
                {
                    "role": "system",
                    "content": "You are a coding assistant. Return ONLY clean Python code. Do not wrap it in markdown blockticks. Do not explain.",
                },
                {
                    "role": "user",
                    "content": self.prompt, 
                },
            ]
        elif self.generate_function:
            return [
                {
                    "role": "system",
                    "content": "You are a Python coding assistant. Return only clean Python code.",
                },
                {
                    "role": "user",
                    "content": f"""
Generate a complete Python function for this request.
Context BEFORE cursor:
{before}
Context AFTER cursor:
{after}
Request:
{self.prompt}
Rules:
- Return ONLY Python code
- No markdown
- No explanations
""",
                },
            ]
        else:
            return [
                {
                    "role": "system",
                    "content": "You are an ultra-strict inline code completion engine. Return ONLY the exact missing characters to be inserted at the cursor. Do NOT use markdown code blocks.",
                },
                {
                    "role": "user",
                    "content": f"""
<context_before>
{before}
</context_before>
<context_after>
{after}
</context_after>

Output ONLY the exact missing code that connects the before and after context.
CRITICAL RULE: You must NOT generate any code that already exists in the <context_after> block! Stop generating immediately if the context naturally connects."""
                },
            ]

    def run(self):
        raw_output = ""
        last_emitted = ""

        try:
            # 1. Determine if we are doing a Chat/Edit or a native FIM Completion
            is_inline_completion = not self.generate_function and not self.is_edit and not self.is_chat

            if is_inline_completion:
                # ==========================================
                # LLAMA.CPP NATIVE FIM (/infill)
                # ==========================================
                # Convert http://.../v1/chat/completions -> http://.../infill
                target_url = self.api_url.replace("/v1/chat/completions", "/infill")
                
                before = self.editor_text[max(0, self.cursor_pos - 1000):self.cursor_pos]
                after = self.editor_text[self.cursor_pos:self.cursor_pos + 300]
                
                payload = {
                    "input_prefix": before,
                    "input_suffix": after,
                    "temperature": 0.1,
                    "stream": True,
                    "n_predict": 60, # llama.cpp uses n_predict instead of max_tokens here
                    "stop": ["\n\n"] # Keep it from rambling down the page
                }
            else:
                # ==========================================
                # STANDARD CHAT / EDIT
                # ==========================================
                target_url = self.api_url
                payload = {
                    "model": self.model,
                    "messages": self.build_messages(),
                    "temperature": 0.2 if not self.is_chat else 0.7,
                    "stream": True,
                }

            # 2. Fire the Request
            response = requests.post(
                target_url,
                json=payload,
                stream=True,
                timeout=60,
            )

            # 3. Parse the Stream
            for line in response.iter_lines():
                if self._cancelled:
                    break
                if not line:
                    continue
                try:
                    decoded = line.decode("utf-8")
                except Exception:
                    continue
                if not decoded.startswith("data: "):
                    continue
                    
                data = decoded[6:]
                if data.strip() == "[DONE]":
                    break
                    
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                # [CRITICAL UPDATE] 
                # llama.cpp's /infill endpoint puts content at the root of the JSON, 
                # while OpenAI chat puts it inside choices[0].delta!
                if is_inline_completion:
                    content = chunk.get("content")
                else:
                    delta_dict = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta_dict.get("content")

                if not content:
                    continue

                raw_output += content

                # -----------------------------
                # ROUTE THE OUTPUT
                # -----------------------------
                if self.is_chat:
                    self.chat_update.emit(content)
                    continue

                cleaned = clean_code(raw_output)

                if self.generate_function or self.is_edit:
                    if cleaned.startswith(last_emitted):
                        delta = cleaned[len(last_emitted):]
                    else:
                        delta = cleaned  
                    last_emitted = cleaned
                    self.function_ready.emit(delta)
                else:
                    recent_typed = self.editor_text[max(0, self.cursor_pos - 100):self.cursor_pos]
                    overlap_length = 0
                    max_overlap = min(len(recent_typed), len(cleaned))
                    
                    for i in range(max_overlap, 0, -1):
                        if recent_typed.endswith(cleaned[:i]):
                            overlap_length = i
                            break
                    
                    ghost = cleaned[overlap_length:]
                    self.update_ghost.emit(ghost)

        except Exception as e:
            print("Worker error:", e)
        finally:
            self.finished.emit()