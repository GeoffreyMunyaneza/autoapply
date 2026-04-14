"""
gui/tray.py — System tray icon for AutoApply.

Creates a tray icon using pystray + Pillow.
Menu: Show/Hide · Run Pipeline · Run + Submit · ─── · Quit
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from gui.main_window import MainWindow


def _make_icon_image():
    """Generate a simple blue circle 'AA' icon as a PIL Image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Blue filled circle
        draw.ellipse([2, 2, size - 2, size - 2], fill=(37, 99, 235, 255))
        # 'AA' text (white)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), "AA", font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            ((size - tw) // 2, (size - th) // 2 - 1),
            "AA",
            fill=(255, 255, 255, 255),
            font=font,
        )
        return img
    except ImportError:
        return None


class TrayApp:
    """
    Wraps pystray.Icon; bridges tray actions → main window callbacks.
    """

    def __init__(
        self,
        on_show: Callable,
        on_run: Callable,
        on_run_submit: Callable,
        on_quit: Callable,
    ):
        self._on_show = on_show
        self._on_run = on_run
        self._on_run_submit = on_run_submit
        self._on_quit = on_quit
        self._icon = None

    def start(self) -> None:
        """Starts the tray icon in a daemon thread (non-blocking)."""
        try:
            import pystray
            from pystray import MenuItem as Item, Menu

            img = _make_icon_image()
            if img is None:
                return  # Pillow not available — skip tray

            menu = Menu(
                Item("Show / Hide Window", self._toggle_window, default=True),
                Menu.SEPARATOR,
                Item("▶  Run Pipeline", self._run_pipeline),
                Item("▶  Run + Submit", self._run_submit),
                Menu.SEPARATOR,
                Item("Quit AutoApply", self._quit),
            )

            self._icon = pystray.Icon(
                name="AutoApply",
                icon=img,
                title="AutoApply",
                menu=menu,
            )
            self._icon.run_detached()
        except ImportError:
            pass  # pystray not installed — run without tray

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def update_tooltip(self, text: str) -> None:
        if self._icon:
            try:
                self._icon.title = text
            except Exception:
                pass

    # ── Menu callbacks ────────────────────────────────────────────────────────

    def _toggle_window(self, icon=None, item=None) -> None:
        self._on_show()

    def _run_pipeline(self, icon=None, item=None) -> None:
        self._on_run()

    def _run_submit(self, icon=None, item=None) -> None:
        self._on_run_submit()

    def _quit(self, icon=None, item=None) -> None:
        self._on_quit()
