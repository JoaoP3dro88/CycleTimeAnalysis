# -*- coding: utf-8 -*-
"""
Runtime hook do PyInstaller — executa ANTES de qualquer import no bundle.
Adiciona os diretórios de DLLs do mediapipe ao search path do Windows
para que o _framework_bindings.pyd encontre suas dependências.

Usa DOIS mecanismos:
  1. os.add_dll_directory() — API nova (Windows 8+), respeitada por LoadLibraryEx
  2. os.environ['PATH']    — API antiga, usada por opencv interno via LoadLibrary
"""
import os
import sys

if sys.platform == "win32":
    _internal = getattr(sys, "_MEIPASS", None)
    if _internal:
        _dirs = [
            _internal,
            os.path.join(_internal, "mediapipe", "python"),
            os.path.join(_internal, "cv2"),
        ]
        # API nova
        for d in _dirs:
            if os.path.isdir(d):
                os.add_dll_directory(d)

        # API antiga (PATH) — para DLLs que usam LoadLibrary internamente
        existing = os.environ.get("PATH", "")
        extra = os.pathsep.join(d for d in _dirs if os.path.isdir(d))
        os.environ["PATH"] = extra + os.pathsep + existing
