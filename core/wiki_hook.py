"""
wiki_hook.py — Headless wiki updater invoked by the post-commit git hook.

Called as:
    python3 -m core.wiki_hook --repo /path/to/repo

Runs in the background (the hook fires it with `&`), detects which .py files
changed in the last commit, and updates their wiki pages via WikiManager.

Output goes to `.quillai/wiki_hook.log` so it doesn't interfere with git's
terminal output.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _setup_logging(repo_root: Path) -> logging.Logger:
    log_path = repo_root / ".quillai" / "wiki_hook.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("wiki_hook")
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def _changed_py_files(repo_root: Path) -> list[Path]:
    for cmd in (
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
    ):
        try:
            result = subprocess.run(
                cmd, cwd=repo_root,
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                files = []
                for line in result.stdout.strip().splitlines():
                    p = (repo_root / line.strip()).resolve()
                    if p.suffix == ".py" and p.exists():
                        files.append(p)
                return files
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Absolute path to repo root")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    logger = _setup_logging(repo_root)

    logger.info("post-commit hook fired")

    # Import here so the hook doesn't fail if QuillAI isn't on PYTHONPATH.
    # The hook is fired from the repo root so this should resolve correctly.
    sys.path.insert(0, str(repo_root))
    try:
        from core.wiki_manager import WikiManager
    except ImportError as e:
        logger.error(f"Could not import WikiManager: {e}")
        sys.exit(0)  # Exit cleanly — don't block git

    changed = _changed_py_files(repo_root)
    if not changed:
        logger.info("No .py files changed — nothing to do.")
        return

    logger.info(f"Changed .py files: {[str(f.relative_to(repo_root)) for f in changed]}")

    def on_progress(i, n, label):
        logger.info(f"  [{i}/{n}] {label}")

    wm = WikiManager(repo_root=repo_root, on_progress=on_progress)

    updated: list[str] = []
    for src in changed:
        was_updated = wm.update_file(src)
        if was_updated:
            rel = str(src.relative_to(repo_root))
            updated.append(rel)
            logger.info(f"  ✓ regenerated wiki page for {rel}")
        else:
            logger.info(f"  – {src.name} wiki page already current")

    logger.info(
        f"Done. {len(updated)} page(s) updated: {updated if updated else 'none'}"
    )


if __name__ == "__main__":
    main()