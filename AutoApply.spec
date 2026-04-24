# -*- mode: python ; coding: utf-8 -*-
#
# AutoApply PyInstaller spec
#
# Build command:  pyinstaller AutoApply.spec
# Output:         dist/AutoApply/AutoApply.exe
#
# Notes:
# - torch / sentence-transformers are excluded to keep the package size reasonable.
#   The app falls back to keyword-only scoring when they are absent.
# - Playwright manages its own Chromium install separately.
#   The installer runs "playwright install chromium" post-install via install_browsers.py.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


hidden = []

# GUI
hidden += collect_submodules("customtkinter")
hidden += collect_submodules("tkinter")
hidden += ["PIL", "PIL._imagingtk", "PIL._tkinter_finder"]
hidden += collect_submodules("pystray")

# Config / env
hidden += collect_submodules("yaml")
hidden += ["dotenv", "dotenv.main"]

# HTTP / API
hidden += ["anthropic", "anthropic._base_client", "anthropic.resources"]
hidden += collect_submodules("httpx")
hidden += collect_submodules("httpcore")
hidden += ["certifi", "charset_normalizer", "idna", "urllib3"]
hidden += collect_submodules("requests")

# Office / documents
hidden += collect_submodules("docx")
hidden += collect_submodules("openpyxl")

# Job scraping
hidden += collect_submodules("jobspy")
hidden += collect_submodules("pandas")
hidden += ["tls_client", "markdownify", "regex"]

# Browser automation
hidden += collect_submodules("playwright")
hidden += ["playwright.sync_api", "playwright.async_api", "playwright._impl._driver"]

# Notifications
hidden += collect_submodules("plyer")
hidden += ["plyer.platforms.win.notification"]

# PDF conversion (optional; requires Microsoft Word)
hidden += ["docx2pdf"]

datas = [
    ("config.yaml", "."),
    ("questions.yaml", "."),
    (".env.example", "."),
    ("install_browsers.py", "."),
    ("assets/icon.ico", "assets"),
]

datas += collect_data_files("customtkinter")

excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "tensorflow",
    "scipy",
    "sklearn",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "setuptools",
    "pip",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoApply",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/icon.ico" if __import__("os").path.exists("assets/icon.ico") else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime140.dll", "python*.dll"],
    name="AutoApply",
)
