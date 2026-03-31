import ast
import os


class ContextEngine:
    def __init__(self, memory_manager, estimate_tokens_fn):
        self.memory_manager = memory_manager
        self.estimate_tokens = estimate_tokens_fn

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def build(self, user_text: str, active_code: str, file_path=None, open_tabs=None, cursor_pos=None):
        TOKEN_BUDGET = 28000
        used = self.estimate_tokens(user_text)

        parts = []

        # ── Memory ────────────────────────────────────────────────
        memory_ctx = self.memory_manager.build_memory_context(query=user_text)
        if memory_ctx:
            parts.append(memory_ctx)
            used += self.estimate_tokens(memory_ctx)

        # ── Intent ────────────────────────────────────────────────
        intent = self.detect_intent(user_text)
        parts.append(f"[User Intent]\n{intent}")

        # ── Active File ───────────────────────────────────
        cursor_line = self.get_cursor_line(active_code, cursor_pos) if cursor_pos else None
        
        symbol_ctx = ""
        called_ctx = ""
        cross_ctx = ""
        
        if cursor_line:
            symbol = self.get_symbol_with_parent(active_code, cursor_line)
            symbol_ctx = self.extract_symbol_code(active_code, symbol)
        
            # expand context
            called_ctx = self.expand_with_called_functions(active_code, symbol)
            
            # Cross-file calls
            cross_ctx = self.expand_cross_file_calls(
                active_code,
                symbol,
                file_path
            )
        
        # fallback to query-based matching
        if not symbol_ctx:
            symbols = self.get_relevant_symbols(active_code, user_text)
            if symbols:
                symbol_ctx = self.extract_code_blocks(active_code, symbols)
        
        # final fallback
        if not symbol_ctx:
            symbol_ctx = self.get_cursor_window(active_code)

        # ── Combine all context layers ─────────────────────────────
        
        combined_ctx = ""
        
        if symbol_ctx:
            combined_ctx += symbol_ctx
        
        if called_ctx:
            combined_ctx += "\n\n# Called Functions (Local)\n" + called_ctx
        
        if cross_ctx:
            combined_ctx += "\n\n# Called Functions (External)\n" + cross_ctx
        
        # safety fallback (should rarely hit now)
        if not combined_ctx:
            combined_ctx = self.get_cursor_window(active_code)
        
        # ── Append to prompt ───────────────────────────────────────
        
        parts.append(f"[Active Code]\n```python\n{combined_ctx}\n```")
        used += self.estimate_tokens(combined_ctx)

        # ── Imports (filtered) ────────────────────────────────────
        if used < TOKEN_BUDGET:
            import_ctx = self.get_relevant_imports(active_code, user_text)
            if import_ctx:
                parts.append("[Relevant Imports]\n" + import_ctx)
                used += self.estimate_tokens(import_ctx)

        # ── Related Project Code ──────────────────────────────────
        if used < TOKEN_BUDGET and file_path:
            related = self.search_project(file_path, user_text)
            if related:
                parts.append("[Related Code]\n" + related)
                used += self.estimate_tokens(related)

        # ── Open Tabs ─────────────────────────────────────────────
        if used < TOKEN_BUDGET and open_tabs:
            tabs_ctx = self.get_tabs_context(open_tabs, user_text)
            if tabs_ctx:
                parts.append("[Open Tabs]\n" + tabs_ctx)

        return "\n\n".join(parts)

    # ─────────────────────────────────────────────────────────────
    # Intent Detection
    # ─────────────────────────────────────────────────────────────

    def detect_intent(self, text: str) -> str:
        t = text.lower()
        if any(x in t for x in ["error", "bug", "traceback", "exception"]):
            return "debug"
        if "refactor" in t:
            return "refactor"
        if any(x in t for x in ["add", "create", "implement"]):
            return "feature"
        return "general"

    # ─────────────────────────────────────────────────────────────
    # AST Symbol Extraction
    # ─────────────────────────────────────────────────────────────

    def get_relevant_symbols(self, code: str, query: str):
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
            chunk = "\n".join(lines[start-1:end])
            chunks.append(f"# {name}\n{chunk}")

        return "\n\n".join(chunks)
        
    # ─────────────────────────────────────────────
    # Cursor + AST helpers
    # ─────────────────────────────────────────────

    def get_cursor_line(self, code: str, cursor_pos: int) -> int:
        return code[:cursor_pos].count("\n") + 1

    def get_symbol_with_parent(self, code, cursor_line):
        try:
            tree = ast.parse(code)
        except:
            return None, None
    
        parent = None
        child = None
    
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if node.lineno <= cursor_line <= node.end_lineno:
                    parent = (node.name, node.lineno, node.end_lineno)
    
                    for sub in node.body:
                        if isinstance(sub, ast.FunctionDef):
                            if sub.lineno <= cursor_line <= sub.end_lineno:
                                child = (sub.name, sub.lineno, sub.end_lineno)
    
            elif isinstance(node, ast.FunctionDef):
                if node.lineno <= cursor_line <= node.end_lineno:
                    child = (node.name, node.lineno, node.end_lineno)
    
        return parent, child

    def extract_symbol_code(self, code: str, symbol):
        if not symbol:
            return ""
    
        lines = code.splitlines()
    
        # Case 1: (parent, child)
        if isinstance(symbol, tuple) and len(symbol) == 2:
            parent, child = symbol
            chunks = []
    
            if parent:
                pname, pstart, pend = parent
                pchunk = "\n".join(lines[pstart-1:pend])
                chunks.append(f"# class {pname}\n{pchunk}")
    
            if child:
                cname, cstart, cend = child
                cchunk = "\n".join(lines[cstart-1:cend])
                chunks.append(f"# function {cname}\n{cchunk}")
    
            return "\n\n".join(chunks)
    
        # Case 2: single symbol (fallback compatibility)
        if isinstance(symbol, tuple) and len(symbol) == 3:
            name, start, end = symbol
            chunk = "\n".join(lines[start-1:end])
            return f"# {name}\n{chunk}"
    
        return ""
 
    def get_called_functions(self, code: str, symbol):
        """
        Given a function/class symbol, return function names it calls.
        """
        if not symbol:
            return []
    
        # Handle (parent, child)
        if isinstance(symbol, tuple) and len(symbol) == 2:
            _, child = symbol
            if not child:
                return []
            _, start, end = child
        else:
            _, start, end = symbol
    
        lines = code.splitlines()
        snippet = "\n".join(lines[start-1:end])
    
        try:
            tree = ast.parse(snippet)
        except:
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
        except:
            return []
    
        matches = []
    
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name in names:
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

    def get_cursor_window(self, code: str, window=200) -> str:
        lines = code.splitlines()
        return "\n".join(lines[-window:])  # simple fallback for now

    # ─────────────────────────────────────────────────────────────
    # Imports
    # ─────────────────────────────────────────────────────────────

    def get_relevant_imports(self, code: str, query: str) -> str:
        lines = code.splitlines()
        q_words = query.lower().split()

        imports = [
            l for l in lines
            if l.strip().startswith("import") or l.strip().startswith("from")
        ]

        filtered = [
            l for l in imports
            if any(word in l.lower() for word in q_words)
        ]

        return "\n".join(filtered)

    def parse_imports(self, code: str):
        """
        Returns: {symbol_name: file_path}
        """
        try:
            tree = ast.parse(code)
        except:
            return {}
    
        imports = {}
    
        for node in ast.walk(tree):
            # from x import y
            if isinstance(node, ast.ImportFrom):
                module = node.module
                if not module:
                    continue
    
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = module.replace(".", "/") + ".py"
    
            # import x
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = alias.name.replace(".", "/") + ".py"
    
        return imports
        
    def resolve_import_path(self, base_file, relative_path):
        base_dir = os.path.dirname(base_file)
        full_path = os.path.join(base_dir, relative_path)
    
        if os.path.exists(full_path):
            return full_path
    
        return None
        
    def find_function_in_file(self, file_path, func_name):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except:
            return None
    
        try:
            tree = ast.parse(code)
        except:
            return None
    
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                end = getattr(node, "end_lineno", node.lineno + 20)
                lines = code.splitlines()
                chunk = "\n".join(lines[node.lineno-1:end])
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
    
            rel_path = imports[func]
            full_path = self.resolve_import_path(file_path, rel_path)
    
            if not full_path:
                continue
    
            found = self.find_function_in_file(full_path, func)
            if found:
                results.append(found)
    
        return "\n\n".join(results)
        
    # ─────────────────────────────────────────────────────────────
    # Project Search (basic v1)
    # ─────────────────────────────────────────────────────────────

    def search_project(self, current_file, query, max_results=3):
        root = os.path.dirname(current_file)
        results = []
        q_words = query.lower().split()

        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if not f.endswith(".py"):
                    continue

                full = os.path.join(dirpath, f)
                if full == current_file:
                    continue

                try:
                    with open(full, "r", encoding="utf-8") as fh:
                        content = fh.read()
                except Exception:
                    continue

                score = sum(word in content.lower() for word in q_words)
                if score > 0:
                    snippet = content[:800]
                    results.append((score, f, snippet))

        results.sort(reverse=True)

        formatted = []
        for _, fname, snippet in results[:max_results]:
            formatted.append(f"# {fname}\n{snippet}")

        return "\n\n".join(formatted)

    # ─────────────────────────────────────────────────────────────
    # Tabs Context
    # ─────────────────────────────────────────────────────────────

    def get_tabs_context(self, tabs, query):
        q_words = query.lower().split()
        parts = []
    
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