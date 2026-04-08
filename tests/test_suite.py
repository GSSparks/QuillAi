"""
tests/test_suite.py — QuillAI pre-release test suite

Tests core logic that doesn't require a running Qt application.
Run from the project root:

    python3 tests/test_suite.py

All tests are self-contained. Pass/fail summary printed at the end.
Exit code 0 = all passed, 1 = failures exist.
"""

import ast
import os
import sys
import json
import tempfile
import traceback
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Test runner ───────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def test(name: str):
    """Decorator — registers a test function."""
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
        except AssertionError as e:
            _results.append((name, False, str(e)))
        except Exception as e:
            _results.append((name, False, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"))
        return fn
    return decorator


def eq(a, b, msg=""):
    assert a == b, msg or f"\n  expected: {b!r}\n  got:      {a!r}"


def ok(val, msg=""):
    assert val, msg or f"Expected truthy, got {val!r}"


def no(val, msg=""):
    assert not val, msg or f"Expected falsy, got {val!r}"


# ─────────────────────────────────────────────────────────────────────────────
# wiki_context_builder tests
# ─────────────────────────────────────────────────────────────────────────────

from core.wiki_context_builder import (
    _query_tokens, _module_tokens, _relevance_score, _extract_symbol_names
)


@test("query_tokens: splits CamelCase")
def _():
    tokens = _query_tokens("How does RepoMap work?")
    ok("repo" in tokens)
    ok("map" in tokens)
    # "how" is 3 chars — passes the len > 2 filter, not a stop word in this impl
    ok("how" in tokens)
    # Short words (1-2 chars) are filtered
    no("a" in tokens)
    no("to" in tokens)


@test("query_tokens: splits snake_case")
def _():
    tokens = _query_tokens("wiki_context_builder")
    ok("wiki" in tokens)
    ok("context" in tokens)
    ok("builder" in tokens)


@test("module_tokens: parses file path correctly")
def _():
    tokens = _module_tokens("core/wiki_context_builder.py")
    ok("wiki" in tokens)
    ok("context" in tokens)
    ok("builder" in tokens)


@test("module_tokens: parses ai/repo_map.py")
def _():
    tokens = _module_tokens("ai/repo_map.py")
    ok("repo" in tokens)
    ok("map" in tokens)


@test("relevance_score: repo_map scores high for RepoMap query")
def _():
    qt = _query_tokens("How does RepoMap work with the Wiki system?")
    score = _relevance_score(qt, "ai/repo_map.py", "builds a structural map")
    ok(score >= 4, f"expected score >= 4, got {score}")


@test("relevance_score: irrelevant file scores zero")
def _():
    qt = _query_tokens("How does RepoMap work?")
    score = _relevance_score(qt, "ui/theme.py", "builds stylesheets")
    eq(score, 0)


@test("extract_symbol_names: finds def foo")
def _():
    syms = _extract_symbol_names("What does def _extract_definitions_snippet() look like?")
    ok("_extract_definitions_snippet" in syms, f"got: {syms}")


@test("extract_symbol_names: finds CamelCase class")
def _():
    syms = _extract_symbol_names("How does WikiContextBuilder work?")
    ok("WikiContextBuilder" in syms, f"got: {syms}")


@test("extract_symbol_names: finds snake_case method")
def _():
    syms = _extract_symbol_names("what does _call_llm do?")
    ok("_call_llm" in syms, f"got: {syms}")


@test("extract_symbol_names: filters stop words")
def _():
    syms = _extract_symbol_names("how does the class work?")
    no("how" in syms)
    no("the" in syms)
    no("does" in syms)


@test("WikiContextBuilder: trims to budget")
def _():
    class FakeWM:
        _wiki_dir = Path("/nonexistent")
        def context_for(self, path, include_deps=True): return "x" * 10000
        def all_summaries(self): return {}
        def _read_page(self, rel): return None

    from core.wiki_context_builder import WikiContextBuilder
    builder = WikiContextBuilder(FakeWM(), char_budget=500, include_index=False)
    result = builder.for_file(Path("anything.py"))
    ok(len(result) <= 550, f"result too long: {len(result)}")


@test("WikiContextBuilder: returns empty when no wiki")
def _():
    class FakeWM:
        _wiki_dir = Path("/nonexistent")
        def context_for(self, path, include_deps=True): return ""
        def all_summaries(self): return {}
        def _read_page(self, rel): return None

    from core.wiki_context_builder import WikiContextBuilder
    builder = WikiContextBuilder(FakeWM(), char_budget=6000, include_index=False)
    result = builder.for_file(Path("anything.py"))
    eq(result, "")


# ─────────────────────────────────────────────────────────────────────────────
# context_engine tests
# ─────────────────────────────────────────────────────────────────────────────

from ai.context_engine import ContextEngine


class FakeMemory:
    def build_memory_context(self, query=""): return ""


def _engine():
    return ContextEngine(FakeMemory(), lambda t: len(t) // 4)


@test("context_engine: detect_intent debug")
def _():
    eq(_engine().detect_intent("why is this broken?"), "debug")


@test("context_engine: detect_intent refactor")
def _():
    eq(_engine().detect_intent("refactor this function"), "refactor")


@test("context_engine: detect_intent feature")
def _():
    eq(_engine().detect_intent("add a new method"), "feature")


@test("context_engine: detect_intent general")
def _():
    eq(_engine().detect_intent("how does this work?"), "general")


@test("context_engine: get_cursor_line")
def _():
    code = "line1\nline2\nline3\n"
    eq(_engine().get_cursor_line(code, 6), 2)


@test("context_engine: get_cursor_window centered")
def _():
    code = "\n".join(f"line{i}" for i in range(200))
    result = _engine().get_cursor_window(code, cursor_pos=None, window=10)
    lines = result.splitlines()
    ok(len(lines) <= 10, f"window too large: {len(lines)}")


@test("context_engine: get_relevant_symbols finds match")
def _():
    code = "def my_function():\n    pass\n"
    matches = _engine().get_relevant_symbols(code, "what does my_function do?")
    ok(len(matches) > 0, "should find my_function")
    eq(matches[0][0], "my_function")


@test("context_engine: get_relevant_symbols no match")
def _():
    code = "def unrelated():\n    pass\n"
    matches = _engine().get_relevant_symbols(code, "what does other_thing do?")
    eq(matches, [])


@test("context_engine: get_symbol_with_parent handles empty code")
def _():
    parent, child = _engine().get_symbol_with_parent("", 1)
    eq(parent, None)
    eq(child, None)


@test("context_engine: get_called_functions handles (None, None) symbol")
def _():
    # (None, None) comes from get_symbol_with_parent when cursor not in any symbol
    result = _engine().get_called_functions("def foo(): pass", (None, None))
    eq(result, [], "should return empty list, not crash")


@test("context_engine: get_called_functions handles None symbol")
def _():
    result = _engine().get_called_functions("def foo(): pass", None)
    eq(result, [])


@test("context_engine: get_symbol_with_parent finds class method")
def _():
    code = "class Foo:\n    def bar(self):\n        pass\n"
    parent, child = _engine().get_symbol_with_parent(code, 2)
    ok(parent is not None, "should find class Foo")
    ok(child is not None, "should find method bar")
    eq(parent[0], "Foo")
    eq(child[0], "bar")


@test("context_engine: get_all_imports extracts imports")
def _():
    code = "import os\nfrom pathlib import Path\nx = 1\n"
    imports = _engine().get_all_imports(code)
    ok("import os" in imports)
    ok("from pathlib import Path" in imports)
    no("x = 1" in imports)


@test("context_engine: build chat mode skips active code for generic query")
def _():
    eng = _engine()
    result = eng.build(
        user_text="how does the memory system work?",
        active_code="import os\ndef some_function():\n    pass\n",
        file_path="/fake/main.py",
        cursor_pos=None,  # chat mode
    )
    no("[Active Code" in result, "chat mode should not inject active code for unrelated query")


@test("context_engine: build editor mode injects active code")
def _():
    eng = _engine()
    code = "def my_func():\n    pass\n"
    result = eng.build(
        user_text="explain this",
        active_code=code,
        file_path="/fake/editor.py",
        cursor_pos=10,  # editor mode
    )
    ok("[Active Code" in result, "editor mode should inject active code")


@test("context_engine: _extract_definitions_snippet")
def _():
    code = 'def foo():\n    """docstring"""\n    pass\n\ndef bar():\n    pass\n'
    result = _engine()._extract_definitions_snippet(code, max_chars=200)
    ok("def foo" in result)


@test("context_engine: _score_file by symbol match")
def _():
    # _score_file matches whole AST symbol names against q_words
    # so q_words must contain the full symbol name (lowercased)
    content = "def search_project():\n    pass\nclass ContextEngine:\n    pass\n"
    score = _engine()._score_file(content, {"search_project", "contextengine"})
    ok(score >= 2, f"expected score >= 2, got {score}")


@test("context_engine: _score_file zero score for no match")
def _():
    content = "def search_project():\n    pass\n"
    score = _engine()._score_file(content, {"unrelated", "words"})
    eq(score, 0)


# ─────────────────────────────────────────────────────────────────────────────
# patch_applier tests
# ─────────────────────────────────────────────────────────────────────────────

from core.patch_applier import (
    apply_function, apply_full, undo_last, has_undo,
    _top_level_name, _leading_indent, _reindent
)


@test("patch_applier: _top_level_name finds function")
def _():
    code = "def my_func():\n    pass\n"
    eq(_top_level_name(code), "my_func")


@test("patch_applier: _top_level_name finds class")
def _():
    code = "class MyClass:\n    pass\n"
    eq(_top_level_name(code), "MyClass")


@test("patch_applier: _top_level_name returns None for non-code")
def _():
    eq(_top_level_name("x = 1\n"), None)


@test("patch_applier: _leading_indent")
def _():
    eq(_leading_indent("    def foo():"), "    ")
    eq(_leading_indent("def foo():"), "")
    eq(_leading_indent("        x = 1"), "        ")


@test("patch_applier: apply_function replaces existing function")
def _():
    original = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
    new_func  = "def add(a, b):\n    return a + b + 1\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(original)
        tmp = f.name

    try:
        ok_, msg = apply_function(tmp, new_func)
        ok(ok_, f"apply_function failed: {msg}")
        result = Path(tmp).read_text()
        ok("return a + b + 1" in result, "new function body not found")
        ok("def sub" in result, "sub function should still be present")
        ok(has_undo(tmp), "undo should be available")
    finally:
        os.unlink(tmp)


@test("patch_applier: apply_function appends new function")
def _():
    original = "def existing():\n    pass\n"
    new_func  = "def brand_new():\n    return 42\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(original)
        tmp = f.name

    try:
        ok_, msg = apply_function(tmp, new_func)
        ok(ok_, f"apply_function failed: {msg}")
        result = Path(tmp).read_text()
        ok("def existing" in result, "original function should remain")
        ok("def brand_new" in result, "new function should be appended")
    finally:
        os.unlink(tmp)


@test("patch_applier: apply_function rejects bad syntax")
def _():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("def foo():\n    pass\n")
        tmp = f.name

    try:
        ok_, msg = apply_function(tmp, "def foo(:\n    broken\n")
        no(ok_, "should fail on syntax error")
    finally:
        os.unlink(tmp)


@test("patch_applier: undo_last restores original")
def _():
    original = "def foo():\n    return 1\n"
    new_func  = "def foo():\n    return 2\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(original)
        tmp = f.name

    try:
        apply_function(tmp, new_func)
        eq(Path(tmp).read_text(), new_func)
        ok_, msg = undo_last(tmp)
        ok(ok_, f"undo failed: {msg}")
        eq(Path(tmp).read_text(), original)
        no(has_undo(tmp), "undo stack should be empty after undo")
    finally:
        os.unlink(tmp)


@test("patch_applier: undo_last fails gracefully when no undo")
def _():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("x = 1\n")
        tmp = f.name

    try:
        ok_, msg = undo_last(tmp)
        no(ok_, "should fail when no undo available")
        ok("No undo" in msg, f"unexpected message: {msg}")
    finally:
        os.unlink(tmp)


@test("patch_applier: apply_function file not found")
def _():
    ok_, msg = apply_function("/nonexistent/file.py", "def foo():\n    pass\n")
    no(ok_)
    ok("not found" in msg.lower())


@test("patch_applier: apply_full creates new file")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        new_file = os.path.join(tmpdir, "new_file.py")
        ok_, msg = apply_full(new_file, "x = 1\n")
        ok(ok_, f"apply_full failed: {msg}")
        ok(Path(new_file).exists())
        eq(Path(new_file).read_text(), "x = 1\n")


# ─────────────────────────────────────────────────────────────────────────────
# chat_renderer tests (pure logic, no Qt)
# ─────────────────────────────────────────────────────────────────────────────

# Import only the pure functions — not the class (needs Qt)
from ui.chat_renderer import (
    _extract_file_changes, _autodetect_changes, _summarise_change
)


@test("chat_renderer: _extract_file_changes strips tag")
def _():
    text = 'Some text\n<file_change path="ai/foo.py" mode="function">def foo():\n    pass\n</file_change>\nMore text'
    cleaned, changes = _extract_file_changes(text)
    no("<file_change" in cleaned)
    ok("Some text" in cleaned)
    ok("More text" in cleaned)
    eq(len(changes), 1)
    eq(changes[0][0], "ai/foo.py")
    eq(changes[0][1], "function")
    ok("def foo" in changes[0][2])


@test("chat_renderer: _extract_file_changes no tags")
def _():
    text = "Just regular text with ```code blocks```"
    cleaned, changes = _extract_file_changes(text)
    eq(cleaned, text)
    eq(changes, [])


@test("chat_renderer: _extract_file_changes multiple tags")
def _():
    text = (
        '<file_change path="a.py" mode="function">def a(): pass</file_change>'
        '<file_change path="b.py" mode="full">x = 1</file_change>'
    )
    _, changes = _extract_file_changes(text)
    eq(len(changes), 2)
    eq(changes[0][0], "a.py")
    eq(changes[1][0], "b.py")


@test("chat_renderer: _autodetect_changes Python function")
def _():
    text = "Here's a fix:\n```python\ndef my_func():\n    return 42\n```\n"
    changes = _autodetect_changes(text, "/fake/script.py")
    eq(len(changes), 1)
    eq(changes[0][1], "function")
    ok("def my_func" in changes[0][2])


@test("chat_renderer: _autodetect_changes Python multi-function uses full mode")
def _():
    text = "```python\ndef foo():\n    pass\ndef bar():\n    pass\n```"
    changes = _autodetect_changes(text, "/fake/script.py")
    eq(len(changes), 1)
    eq(changes[0][1], "full")


@test("chat_renderer: _autodetect_changes YAML")
def _():
    # Must be > 3 lines to trigger full mode
    text = "```yaml\n- name: Install Apache\n  hosts: webservers\n  become: yes\n  tasks:\n    - name: apt\n      apt:\n        name: apache2\n        state: latest\n```"
    changes = _autodetect_changes(text, "/fake/playbook.yml")
    eq(len(changes), 1)
    eq(changes[0][1], "full")


@test("chat_renderer: _autodetect_changes Perl sub")
def _():
    text = "```perl\nsub my_handler {\n    my ($self) = @_;\n    return 1;\n}\n```"
    changes = _autodetect_changes(text, "/fake/script.pl")
    eq(len(changes), 1)
    eq(changes[0][1], "perl_function")


@test("chat_renderer: _autodetect_changes no match for short block")
def _():
    text = "```python\nx = 1\n```"
    changes = _autodetect_changes(text, "/fake/script.py")
    eq(changes, [])


@test("chat_renderer: _autodetect_changes txt file full mode")
def _():
    # .txt is in _FULL_EXTS — should apply if block > 3 lines
    text = "```\nline1\nline2\nline3\nline4\nline5\n```"
    changes = _autodetect_changes(text, "/fake/readme.txt")
    eq(len(changes), 1)
    eq(changes[0][1], "full")


@test("chat_renderer: _summarise_change single function")
def _():
    code = "def search_project(self):\n    pass\n"
    result = _summarise_change(code, "function")
    ok("search_project" in result)
    ok("function" in result.lower() or "Replace" in result)


@test("chat_renderer: _summarise_change full mode")
def _():
    result = _summarise_change("anything", "full")
    ok("full" in result.lower() or "rewrite" in result.lower())


@test("chat_renderer: _summarise_change class")
def _():
    code = "class MyClass:\n    pass\n"
    result = _summarise_change(code, "function")
    ok("MyClass" in result)


@test("chat_renderer: _summarise_change fallback")
def _():
    result = _summarise_change("not valid python!!!", "function")
    ok(len(result) > 0, "should return fallback string")


# ─────────────────────────────────────────────────────────────────────────────
# memory_manager tests
# ─────────────────────────────────────────────────────────────────────────────

from ui.memory_manager import (
    _make_fact, _fact_text, _migrate_facts,
    _decay_confidence, _is_prunable, MemoryManager
)
from datetime import date, timedelta


@test("memory_manager: _make_fact creates correct structure")
def _():
    f = _make_fact("test fact", ["file.py"])
    eq(f["text"], "test fact")
    eq(f["source_files"], ["file.py"])
    eq(f["confidence"], 1.0)
    ok("added" in f)
    ok("last_seen" in f)


@test("memory_manager: _fact_text handles dict")
def _():
    eq(_fact_text({"text": "hello"}), "hello")


@test("memory_manager: _fact_text handles legacy string")
def _():
    eq(_fact_text("legacy fact"), "legacy fact")


@test("memory_manager: _migrate_facts converts strings")
def _():
    facts = ["old string fact", {"text": "new dict fact", "source_files": [], "added": "2025-01-01", "last_seen": "2025-01-01", "confidence": 1.0}]
    migrated = _migrate_facts(facts)
    eq(len(migrated), 2)
    eq(migrated[0]["text"], "old string fact")
    ok("confidence" in migrated[0])
    eq(migrated[1]["text"], "new dict fact")


@test("memory_manager: _decay_confidence reduces over time")
def _():
    old_date = (date.today() - timedelta(days=40)).isoformat()
    fact = _make_fact("old fact")
    fact["last_seen"] = old_date
    fact["confidence"] = 1.0
    result = _decay_confidence(fact)
    ok(result["confidence"] < 1.0, f"confidence should decay, got {result['confidence']}")


@test("memory_manager: _decay_confidence no decay for recent fact")
def _():
    fact = _make_fact("recent fact")
    result = _decay_confidence(fact)
    eq(result["confidence"], 1.0)


@test("memory_manager: _is_prunable low confidence")
def _():
    fact = _make_fact("weak fact")
    fact["confidence"] = 0.1
    ok(_is_prunable(fact))


@test("memory_manager: _is_prunable healthy fact")
def _():
    fact = _make_fact("healthy fact")
    no(_is_prunable(fact))


@test("memory_manager: _is_prunable old fact")
def _():
    fact = _make_fact("old fact")
    fact["added"] = (date.today() - timedelta(days=200)).isoformat()
    ok(_is_prunable(fact))


@test("memory_manager: add_fact and retrieve")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch MEMORY_DIR temporarily
        import ui.memory_manager as mm_mod
        original_dir = mm_mod.MEMORY_DIR
        original_global = mm_mod.GLOBAL_MEMORY_FILE
        mm_mod.MEMORY_DIR = tmpdir
        mm_mod.GLOBAL_MEMORY_FILE = os.path.join(tmpdir, "global.json")
        try:
            mm = MemoryManager()
            mm.add_fact("QuillAI uses PyQt6", project_scoped=False)
            facts = mm.get_global_facts()
            ok("QuillAI uses PyQt6" in facts)
        finally:
            mm_mod.MEMORY_DIR = original_dir
            mm_mod.GLOBAL_MEMORY_FILE = original_global


@test("memory_manager: project facts separate from global")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        import ui.memory_manager as mm_mod
        original_dir = mm_mod.MEMORY_DIR
        original_global = mm_mod.GLOBAL_MEMORY_FILE
        mm_mod.MEMORY_DIR = tmpdir
        mm_mod.GLOBAL_MEMORY_FILE = os.path.join(tmpdir, "global.json")
        try:
            mm = MemoryManager(project_path="/fake/project")
            mm.add_fact("global fact", project_scoped=False)
            mm.add_fact("project fact", project_scoped=True)
            eq(mm.get_global_facts(), ["global fact"])
            eq(mm.get_project_facts(), ["project fact"])
        finally:
            mm_mod.MEMORY_DIR = original_dir
            mm_mod.GLOBAL_MEMORY_FILE = original_global


@test("memory_manager: extraction prompt is user-only")
def _():
    import ui.memory_manager as mm_mod
    prompt = mm_mod._FACT_EXTRACTION_PROMPT
    # Prompt should instruct to extract from USER message only
    ok("USER" in prompt, "prompt should reference USER")
    # Should NOT extract from AI/assistant responses
    ok("ONLY" in prompt or "only" in prompt,
       "prompt should say to extract ONLY from user side")


@test("memory_manager: build_memory_context returns string")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        import ui.memory_manager as mm_mod
        original_dir = mm_mod.MEMORY_DIR
        original_global = mm_mod.GLOBAL_MEMORY_FILE
        mm_mod.MEMORY_DIR = tmpdir
        mm_mod.GLOBAL_MEMORY_FILE = os.path.join(tmpdir, "global.json")
        try:
            mm = MemoryManager()
            mm.add_fact("test fact")
            ctx = mm.build_memory_context("test query")
            ok(isinstance(ctx, str))
            ok("test fact" in ctx)
        finally:
            mm_mod.MEMORY_DIR = original_dir
            mm_mod.GLOBAL_MEMORY_FILE = original_global


# ─────────────────────────────────────────────────────────────────────────────
# wiki_manager tests (no LLM calls)
# ─────────────────────────────────────────────────────────────────────────────

@test("wiki_manager: _load_wiki_ignore reads patterns")
def _():
    from core.wiki_manager import _load_wiki_ignore, _is_wiki_ignored
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        quillai_dir = root / ".quillai"
        quillai_dir.mkdir()
        (quillai_dir / "wiki_ignore").write_text(
            "# comment\nplaybooks/vendor\nplaybooks/molecule/*\n"
        )
        patterns = _load_wiki_ignore(root)
        eq(len(patterns), 2)
        ok(_is_wiki_ignored("playbooks/vendor/something.yml", patterns))
        ok(_is_wiki_ignored("playbooks/molecule/test.yml", patterns))
        no(_is_wiki_ignored("playbooks/roles/main.yml", patterns))


@test("wiki_manager: _is_wiki_ignored no patterns")
def _():
    from core.wiki_manager import _is_wiki_ignored
    no(_is_wiki_ignored("anything/at/all.py", []))


@test("wiki_manager: _collect_source_files respects ignore dirs")
def _():
    from core.wiki_manager import _collect_source_files
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create some files
        (root / "main.py").write_text("x = 1")
        vendor = root / "vendor"
        vendor.mkdir()
        (vendor / "lib.py").write_text("y = 2")
        # Create wiki_ignore
        (root / ".quillai").mkdir()
        (root / ".quillai" / "wiki_ignore").write_text("vendor\n")

        files = _collect_source_files(root)
        names = [f.name for f in files]
        ok("main.py" in names, "main.py should be collected")
        no("lib.py" in names, "vendor/lib.py should be ignored")


# ─────────────────────────────────────────────────────────────────────────────
# repo_map tests
# ─────────────────────────────────────────────────────────────────────────────

@test("repo_map: find_symbol returns empty for unknown")
def _():
    from ai.repo_map import RepoMap
    rm = RepoMap("/tmp")
    results = rm.find_symbol("nonexistent_function_xyz")
    eq(results, [])


@test("repo_map: get_symbol_source extracts function")
def _():
    from ai.repo_map import RepoMap
    rm = RepoMap("/tmp")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
        f.write("def hello_world():\n    return 'hello'\n\ndef other():\n    pass\n")
        tmp = f.name

    try:
        rel = os.path.basename(tmp)
        # Temporarily make project_root /tmp
        rm2 = RepoMap("/tmp")
        result = rm2.get_symbol_source(rel, "hello_world")
        ok("def hello_world" in result, f"expected function, got: {result!r}")
        ok("return 'hello'" in result)
        no("def other" in result, "should not include other function")
    finally:
        os.unlink(tmp)


@test("repo_map: get_symbol_source returns empty for missing symbol")
def _():
    from ai.repo_map import RepoMap
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
        f.write("def foo():\n    pass\n")
        tmp = f.name
    try:
        rm = RepoMap("/tmp")
        result = rm.get_symbol_source(os.path.basename(tmp), "nonexistent")
        eq(result, "")
    finally:
        os.unlink(tmp)


@test("repo_map: _tokenise splits CamelCase")
def _():
    from ai.repo_map import _tokenise
    tokens = _tokenise("RepoMap")
    ok("repo" in tokens)
    ok("map" in tokens)


@test("repo_map: _tokenise splits snake_case")
def _():
    from ai.repo_map import _tokenise
    tokens = _tokenise("wiki_context_builder")
    ok("wiki" in tokens)
    ok("context" in tokens)
    ok("builder" in tokens)


# ─────────────────────────────────────────────────────────────────────────────
# patch_applier Perl tests
# ─────────────────────────────────────────────────────────────────────────────

from core.patch_applier import apply_perl_function, _perl_sub_name, _find_perl_sub_range


@test("patch_applier: _perl_sub_name finds sub")
def _():
    code = "sub my_handler {\n    return 1;\n}\n"
    eq(_perl_sub_name(code), "my_handler")


@test("patch_applier: _perl_sub_name returns None for no sub")
def _():
    eq(_perl_sub_name("my $x = 1;\n"), None)


@test("patch_applier: _find_perl_sub_range finds range")
def _():
    source = "sub foo {\n    return 1;\n}\n\nsub bar {\n    return 2;\n}\n"
    result = _find_perl_sub_range(source, "foo")
    ok(result is not None)
    start, end = result
    eq(start, 0)
    eq(end, 2)


@test("patch_applier: apply_perl_function replaces sub")
def _():
    original = "sub greet {\n    print 'hello';\n}\n\nsub bye {\n    print 'bye';\n}\n"
    new_sub   = "sub greet {\n    print 'hi there';\n}\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.pl', delete=False) as f:
        f.write(original)
        tmp = f.name

    try:
        ok_, msg = apply_perl_function(tmp, new_sub)
        ok(ok_, f"apply_perl_function failed: {msg}")
        result = Path(tmp).read_text()
        ok("hi there" in result, "new sub body not found")
        ok("sub bye" in result, "bye sub should still be present")
    finally:
        os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# Run & report
# ─────────────────────────────────────────────────────────────────────────────

def main():
    passed = [r for r in _results if r[1]]
    failed = [r for r in _results if not r[1]]

    print(f"\n{'='*60}")
    print(f"  QuillAI Test Suite — {len(_results)} tests")
    print(f"{'='*60}")

    if failed:
        print(f"\n❌ FAILED ({len(failed)}):")
        for name, _, msg in failed:
            print(f"\n  ✗ {name}")
            for line in msg.splitlines():
                print(f"    {line}")

    print(f"\n✓ Passed: {len(passed)}/{len(_results)}")
    if failed:
        print(f"✗ Failed: {len(failed)}/{len(_results)}")
    print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())