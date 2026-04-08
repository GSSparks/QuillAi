import ast
import os


class ContextEngine:
    def __init__(self, memory_manager, estimate_tokens_fn):
        self.memory_manager = memory_manager
        self.estimate_tokens = estimate_tokens_fn

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def build(self, user_text: str, active_code: str, file_path=None,
              open_tabs=None, cursor_pos=None, lsp_context: dict = None,
              repo_map: str = None, vector_context=None):
        """
        lsp_context:    optional dict — LSP hover + diagnostics.
        repo_map:       optional str  — structural project map.
        vector_context: optional VectorContext — semantic search results
                        from VectorIndex.query(). Injected after repo_map,
                        before active code.
        """
        TOKEN_BUDGET = 28000
        used = self.estimate_tokens(user_text)

        parts = []

        # ── Memory ────────────────────────────────────────────────
        memory_ctx = self.memory_manager.build_memory_context(query=user_text)
        if memory_ctx:
            parts.append(memory_ctx)
            used += self.estimate_tokens(memory_ctx)

        # ── Intent ────────────────────────────────────────────────
        # Intent is used to adjust context strategy, not just labelled
        intent = self.detect_intent(user_text)

        # ── Repo Map (orientation before implementation) ──────────
        # Filtered to files whose symbols overlap the query, capped at
        # 4000 tokens. Gives the model a structural overview of the
        # whole project without paying the cost of full source.
        if repo_map and used < TOKEN_BUDGET:
            parts.append(repo_map)
            used += self.estimate_tokens(repo_map)

        # ── Vector Context (semantic search across project history) ─────
        # Runs alongside search_project — results are semantically similar
        # code, past conversations, accepted completions, and co-edit pairs.
        # Injected after repo_map so orientation comes before specifics.
        if vector_context and used < TOKEN_BUDGET:
            if isinstance(vector_context, str):                            
                vc_str = vector_context                                    
            else:
                vc_str = vector_context.format()
            if vc_str:
                parts.append(vc_str)
                used += self.estimate_tokens(vc_str)

        # ── LSP Context (injected early — high signal, low token cost) ──
        # Hover gives the model the type signature and docstring for the
        # symbol under the cursor without re-parsing source.
        # Diagnostics are prioritised for debug intent.
        if lsp_context:
            hover_str = (lsp_context.get("hover") or "").strip()
            diag_str  = (lsp_context.get("diagnostics") or "").strip()

            if hover_str and used < TOKEN_BUDGET:
                parts.append(hover_str)
                used += self.estimate_tokens(hover_str)

            if diag_str and used < TOKEN_BUDGET:
                # Always include errors; only include warnings/hints for debug
                if intent == "debug" or "ERROR" in diag_str:
                    parts.append(diag_str)
                    used += self.estimate_tokens(diag_str)

        # ── Active File ───────────────────────────────────────────
        cursor_line = self.get_cursor_line(active_code, cursor_pos) if cursor_pos else None

        symbol_ctx = ""
        called_ctx = ""
        cross_ctx  = ""

        if cursor_line:
            symbol = self.get_symbol_with_parent(active_code, cursor_line)
            symbol_ctx = self.extract_symbol_code(active_code, symbol)

            if symbol_ctx:
                # For debug intent: pull in more of the call stack
                if intent == "debug":
                    called_ctx = self.expand_with_called_functions(active_code, symbol)
                    cross_ctx  = self.expand_cross_file_calls(active_code, symbol, file_path)

                # For refactor: include the full parent class if we're inside a method
                elif intent == "refactor":
                    parent, _ = symbol if (isinstance(symbol, tuple) and len(symbol) == 2) else (None, None)
                    if parent:
                        pname, pstart, pend = parent
                        lines = active_code.splitlines()
                        symbol_ctx = f"# class {pname} (full)\n" + "\n".join(lines[pstart - 1:pend])
                    called_ctx = self.expand_with_called_functions(active_code, symbol)

                # Default: local called functions + cross-file
                else:
                    called_ctx = self.expand_with_called_functions(active_code, symbol)
                    cross_ctx  = self.expand_cross_file_calls(active_code, symbol, file_path)

        # ── Query-based fallback ───────────────────────────────────
        if not symbol_ctx:
            symbols = self.get_relevant_symbols(active_code, user_text)
            if symbols:
                symbol_ctx = self.extract_code_blocks(active_code, symbols)

        # ── Cursor window final fallback ───────────────────────────
        if not symbol_ctx:
            symbol_ctx = self.get_cursor_window(active_code, cursor_pos=cursor_pos)

        # ── Combine context layers ─────────────────────────────────
        combined_ctx = symbol_ctx

        if called_ctx:
            combined_ctx += "\n\n# Called Functions (Local)\n" + called_ctx

        if cross_ctx:
            combined_ctx += "\n\n# Called Functions (External)\n" + cross_ctx

        active_block = f"[Active Code ({intent})]\n```python\n{combined_ctx}\n```"
        parts.append(active_block)
        used += self.estimate_tokens(active_block)

        # ── Imports ───────────────────────────────────────────────
        # Skip for chat — imports are already visible in [Active Code] and
        # the wiki/repo-map context covers inter-file relationships better.
        # Only inject for inline completions where the model needs exact symbols.
        _is_chat_request = not bool(cursor_pos)   # chat has no cursor pos
        if not _is_chat_request and used < TOKEN_BUDGET:
            import_ctx = self.get_all_imports(active_code)
            if import_ctx:
                import_block = "[Imports]\n" + import_ctx
                parts.append(import_block)
                used += self.estimate_tokens(import_block)

        # ── Related Project Code ──────────────────────────────────
        if used < TOKEN_BUDGET and file_path:
            related = self.search_project(file_path, user_text, active_code=active_code)
            if related:
                related_block = "[Related Code]\n" + related
                parts.append(related_block)
                used += self.estimate_tokens(related_block)

        # ── Open Tabs ─────────────────────────────────────────────
        if used < TOKEN_BUDGET and open_tabs:
            tabs_ctx = self.get_tabs_context(open_tabs, user_text)
            if tabs_ctx:
                tabs_block = "[Open Tabs]\n" + tabs_ctx
                parts.append(tabs_block)
                used += self.estimate_tokens(tabs_block)

        return "\n\n".join(parts)

    # ─────────────────────────────────────────────────────────────
    # Intent Detection
    # ─────────────────────────────────────────────────────────────

    def detect_intent(self, text: str) -> str:
        t = text.lower()
        if any(x in t for x in ["error", "bug", "traceback", "exception", "why is", "broken"]):
            return "debug"
        if any(x in t for x in ["refactor", "clean up", "restructure", "simplify"]):
            return "refactor"
        if any(x in t for x in ["add", "create", "implement", "write a", "new"]):
            return "feature"
        return "general"

    # ─────────────────────────────────────────────────────────────
    # AST Symbol Extraction
    # ─────────────────────────────────────────────────────────────

    def get_relevant_symbols(self, code: str, query: str):
        """
        Match function/class names against query words.
        Uses AST symbol names rather than raw text to avoid noise.
        """
        try:
            tree = ast.parse(code)
        except Exception:
            return []

        matches = []
        q = query.lower()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node.name.lower() in q:
                    end = getattr(node, "end_lineno", node.lineno + 20)
                    matches.append((node.name, node.lineno, end))

        return matches

    def extract_code_blocks(self, code: str, blocks):
        lines = code.splitlines()
        chunks = []

        for name, start, end in blocks:
            chunk = "\n".join(lines[start - 1:end])
            chunks.append(f"# {name}\n{chunk}")

        return "\n\n".join(chunks)

    # ─────────────────────────────────────────────────────────────
    # Cursor + AST Helpers
    # ─────────────────────────────────────────────────────────────

    def get_cursor_line(self, code: str, cursor_pos: int) -> int:
        return code[:cursor_pos].count("\n") + 1

    def get_symbol_with_parent(self, code: str, cursor_line: int):
        """
        Walk the full AST (not just tree.body) to handle nested functions
        and classes inside conditionals or other scopes.
        Returns (parent, child) where each is (name, start, end) or None.
        """
        try:
            tree = ast.parse(code)
        except Exception:
            return None, None

        parent = None
        child  = None

        # Walk all nodes, not just tree.body, for robustness
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if hasattr(node, "end_lineno") and node.lineno <= cursor_line <= node.end_lineno:
                    parent = (node.name, node.lineno, node.end_lineno)

                    for sub in node.body:
                        if isinstance(sub, ast.FunctionDef):
                            if hasattr(sub, "end_lineno") and sub.lineno <= cursor_line <= sub.end_lineno:
                                child = (sub.name, sub.lineno, sub.end_lineno)

            elif isinstance(node, ast.FunctionDef):
                if hasattr(node, "end_lineno") and node.lineno <= cursor_line <= node.end_lineno:
                    # Only set as child if not already claimed by a class method walk above
                    if child is None:
                        child = (node.name, node.lineno, node.end_lineno)

        return parent, child

    def extract_symbol_code(self, code: str, symbol):
        if not symbol:
            return ""

        lines = code.splitlines()

        # Case 1: (parent, child) tuple from get_symbol_with_parent
        if isinstance(symbol, tuple) and len(symbol) == 2:
            parent, child = symbol
            chunks = []

            if parent:
                pname, pstart, pend = parent
                pchunk = "\n".join(lines[pstart - 1:pend])
                chunks.append(f"# class {pname}\n{pchunk}")

            if child:
                cname, cstart, cend = child
                cchunk = "\n".join(lines[cstart - 1:cend])
                chunks.append(f"# function {cname}\n{cchunk}")

            return "\n\n".join(chunks)

        # Case 2: single (name, start, end) tuple
        if isinstance(symbol, tuple) and len(symbol) == 3:
            name, start, end = symbol
            chunk = "\n".join(lines[start - 1:end])
            return f"# {name}\n{chunk}"

        return ""

    def get_called_functions(self, code: str, symbol):
        """
        Return names of functions called within the target symbol's body.
        """
        if not symbol:
            return []

        if isinstance(symbol, tuple) and len(symbol) == 2:
            _, child = symbol
            if not child:
                return []
            _, start, end = child
        else:
            _, start, end = symbol

        lines   = code.splitlines()
        snippet = "\n".join(lines[start - 1:end])

        try:
            tree = ast.parse(snippet)
        except Exception:
            return []

        calls = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)

        return list(calls)

    def find_functions_by_name(self, code: str, names: list):
        try:
            tree = ast.parse(code)
        except Exception:
            return []

        matches = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in names:
                end = getattr(node, "end_lineno", node.lineno + 20)
                matches.append((node.name, node.lineno, end))

        return matches

    def expand_with_called_functions(self, code: str, symbol):
        called = self.get_called_functions(code, symbol)
        if not called:
            return ""

        matches = self.find_functions_by_name(code, called)
        if not matches:
            return ""

        return self.extract_code_blocks(code, matches)

    # ─────────────────────────────────────────────────────────────
    # Cursor Window (fallback)
    # ─────────────────────────────────────────────────────────────

    def get_cursor_window(self, code: str, cursor_pos=None, window=100) -> str:
        """
        Return a window of lines centered on the cursor position.
        Falls back to the middle of the file (not top/bottom) when no cursor,
        since chat questions are usually about logic not imports.
        """
        lines = code.splitlines()

        if cursor_pos is None:
            # No cursor — use middle of file as it usually contains more
            # logic than the import-heavy top or trailing boilerplate bottom
            mid   = len(lines) // 2
            start = max(0, mid - window // 2)
            end   = min(len(lines), mid + window // 2)
            return "\n".join(lines[start:end])

        mid   = code[:cursor_pos].count("\n")
        start = max(0, mid - window // 2)
        end   = min(len(lines), mid + window // 2)

        return "\n".join(lines[start:end])

    # ─────────────────────────────────────────────────────────────
    # Imports
    # ─────────────────────────────────────────────────────────────

    def get_all_imports(self, code: str) -> str:
        """
        Return all top-level import statements.
        Replaces the old query-filtered version which dropped too much signal —
        imports are cheap tokens and always relevant context.
        """
        lines = code.splitlines()
        return "\n".join(
            l for l in lines
            if l.strip().startswith(("import", "from"))
        )

    def parse_imports(self, code: str) -> dict:
        """
        Returns: {symbol_name: relative_file_path}
        """
        try:
            tree = ast.parse(code)
        except Exception:
            return {}

        imports = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module
                if not module:
                    continue
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = module.replace(".", "/") + ".py"

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = alias.name.replace(".", "/") + ".py"

        return imports

    def resolve_import_path(self, base_file: str, relative_path: str):
        base_dir  = os.path.dirname(base_file)
        full_path = os.path.join(base_dir, relative_path)
        return full_path if os.path.exists(full_path) else None

    def find_function_in_file(self, file_path: str, func_name: str):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception:
            return None

        try:
            tree = ast.parse(code)
        except Exception:
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                end   = getattr(node, "end_lineno", node.lineno + 20)
                lines = code.splitlines()
                chunk = "\n".join(lines[node.lineno - 1:end])
                return f"# {func_name} ({os.path.basename(file_path)})\n{chunk}"

        return None

    def expand_cross_file_calls(self, code: str, symbol, file_path: str):
        if not file_path:
            return ""

        called = self.get_called_functions(code, symbol)
        if not called:
            return ""

        imports = self.parse_imports(code)
        results = []

        for func in called:
            if func not in imports:
                continue

            full_path = self.resolve_import_path(file_path, imports[func])
            if not full_path:
                continue

            found = self.find_function_in_file(full_path, func)
            if found:
                results.append(found)

        return "\n\n".join(results)

    # ─────────────────────────────────────────────────────────────
    # Project Search
    # ─────────────────────────────────────────────────────────────

    def search_project(self, current_file: str, query: str, active_code: str = "", max_results: int = 3) -> str:
        """
        Score candidate files by AST symbol name matches against the query,
        rather than raw keyword frequency against full file text.
        Falls back to raw word matching only when AST parsing fails.
        Also uses currently-extracted symbol names from active_code as
        additional query signal.
        """
        root    = os.path.dirname(current_file)
        q_words = set(query.lower().split())

        # Augment query with symbol names visible in the active file
        if active_code:
            try:
                tree = ast.parse(active_code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        q_words.add(node.name.lower())
            except Exception:
                pass

        results = []

        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue

                full = os.path.join(dirpath, fname)
                if full == current_file:
                    continue

                try:
                    with open(full, "r", encoding="utf-8") as fh:
                        content = fh.read()
                except Exception:
                    continue

                score = self._score_file(content, q_words)
                if score > 0:
                    # Build a meaningful snippet: top-level definitions rather than raw head
                    snippet = self._extract_definitions_snippet(content, max_chars=800)
                    results.append((score, fname, snippet))

        results.sort(reverse=True)

        formatted = []
        for _, fname, snippet in results[:max_results]:
            formatted.append(f"# {fname}\n{snippet}")

        return "\n\n".join(formatted)

    def _score_file(self, content: str, q_words: set) -> int:
        """
        Score a file by how many query words appear as AST symbol names.
        Falls back to raw word frequency if AST parsing fails.
        """
        try:
            tree    = ast.parse(content)
            symbols = {
                node.name.lower()
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.ClassDef))
            }
            return len(q_words & symbols)
        except Exception:
            # Fallback: raw word match
            low = content.lower()
            return sum(w in low for w in q_words)

    def _extract_definitions_snippet(self, content: str, max_chars: int = 800) -> str:
        """
        Extract top-level class/function signatures instead of raw file head.
        This gives the LLM a better structural overview of what's in the file.
        """
        try:
            tree  = ast.parse(content)
            lines = content.splitlines()
            parts = []

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    # Just the def/class line plus its docstring if present
                    sig = lines[node.lineno - 1]
                    doc = ast.get_docstring(node)
                    entry = sig + (f'\n    """{doc[:80]}"""' if doc else "")
                    parts.append(entry)

                    if sum(len(p) for p in parts) >= max_chars:
                        break

            if parts:
                return "\n".join(parts)
        except Exception:
            pass

        # Fallback to raw head
        return content[:max_chars]

    # ─────────────────────────────────────────────────────────────
    # Tabs Context
    # ─────────────────────────────────────────────────────────────

    def get_tabs_context(self, tabs, query: str) -> str:
        q_words = query.lower().split()
        parts   = []

        for tab in tabs:
            try:
                text = tab.toPlainText()
            except Exception:
                continue

            if not text.strip():
                continue

            if any(word in text.lower() for word in q_words):
                snippet = text[:500]
                parts.append(snippet)

        return "\n\n".join(parts)