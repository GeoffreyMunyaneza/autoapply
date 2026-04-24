"""
install_browsers.py — Install Playwright's Chromium browser engine.

Works in both source (python install_browsers.py) and PyInstaller bundle
(AutoApply.exe --install-browsers) modes.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_playwright_driver() -> Path | None:
    """
    Locate the playwright driver executable.

    In a PyInstaller bundle, node.exe lives at:
        <exe_dir>/_internal/playwright/driver/node.exe

    In a normal install, use playwright's own compute_driver_executable().
    """
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle
        exe_dir = Path(sys.executable).parent
        # onedir: _internal is a sibling of the exe
        candidates = [
            exe_dir / "_internal" / "playwright" / "driver" / "node.exe",
            # sys._MEIPASS is the _internal dir in onedir mode
            Path(getattr(sys, "_MEIPASS", str(exe_dir))) / "playwright" / "driver" / "node.exe",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    # Source mode
    try:
        from playwright._impl._driver import compute_driver_executable
        path = Path(compute_driver_executable())
        if path.exists():
            return path
    except Exception:
        pass

    return None


def _playwright_driver_cli_js() -> Path | None:
    """Return path to playwright's CLI JS file (used with node.exe in bundle)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates = [
            exe_dir / "_internal" / "playwright" / "driver" / "package" / "lib" / "cli" / "cli.js",
            Path(getattr(sys, "_MEIPASS", str(exe_dir))) / "playwright" / "driver" / "package" / "lib" / "cli" / "cli.js",
        ]
        for c in candidates:
            if c.exists():
                return c
    return None


def chromium_is_installed() -> bool:
    """Return True if Playwright can launch Chromium."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def install_chromium(silent: bool = False) -> bool:
    """
    Install the Chromium browser engine for Playwright.
    Returns True on success, False on failure.
    """
    if not silent:
        print("Installing Chromium browser engine (one-time, ~150 MB)...")

    # ── Strategy 1: bundle node.exe + cli.js ──────────────────────────────────
    node = _find_playwright_driver()
    cli  = _playwright_driver_cli_js()

    if node and cli:
        cmd = [str(node), str(cli), "install", "chromium"]
    elif node:
        # Some versions: node.exe <driver_dir>/package <subcommand>
        cmd = [str(node), str(node.parent / "package"), "install", "chromium"]
    else:
        # ── Strategy 2: python -m playwright install (source mode) ────────────
        cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=silent,
            text=True,
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": "0"},  # install next to driver
        )
        if result.returncode == 0:
            if not silent:
                print("Chromium installed successfully.")
            return True
        else:
            if not silent:
                err = result.stderr if silent else ""
                print(f"Chromium install failed (exit {result.returncode}). {err}")
            return False
    except Exception as e:
        if not silent:
            print(f"Could not run install command: {e}")
        return False


def ensure_chromium(silent: bool = False) -> bool:
    """Install Chromium only if not already present."""
    if chromium_is_installed():
        return True
    return install_chromium(silent=silent)


if __name__ == "__main__":
    ok = install_chromium(silent=False)
    sys.exit(0 if ok else 1)
