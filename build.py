#!/usr/bin/env python3
"""Build a standalone app with PyInstaller. Run it on the OS you are building for:

    pip install pyinstaller
    python build.py

macOS   -> dist/TranscribeIt.app
Windows -> dist/TranscribeIt/TranscribeIt.exe  (ship the whole folder, or zip it)

PyInstaller cannot cross-compile, so build on a Mac for the Mac app and on Windows for the .exe.
"""
import platform
import sys

import PyInstaller.__main__

NAME = "TranscribeIt"

# Packages that carry data files or native libraries PyInstaller can't discover by itself.
COLLECT = ["customtkinter", "faster_whisper", "ctranslate2", "onnxruntime", "av"]
if sys.platform == "darwin" and platform.machine() == "arm64":
    COLLECT += ["mlx", "mlx_whisper"]  # Apple GPU engine

args = [
    "app.py",
    "--name", NAME,
    "--windowed",  # no console window; produces a .app bundle on macOS
    "--noconfirm",
    "--clean",
    # torch is only pulled in by mlx-whisper's optional converter, never at transcription time.
    "--exclude-module", "torch",
]
for pkg in COLLECT:
    args += ["--collect-all", pkg]

PyInstaller.__main__.run(args)
