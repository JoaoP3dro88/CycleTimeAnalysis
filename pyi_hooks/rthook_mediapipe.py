# -*- coding: utf-8 -*-
"""
Runtime hook do PyInstaller — executa ANTES de qualquer import no bundle.
Adiciona os diretórios de DLLs do mediapipe ao search path do Windows
para que o _framework_bindings.pyd encontre suas dependências.
"""
import os
import sys

if sys.platform == "win32":
    _internal = getattr(sys, "_MEIPASS", None)
    if _internal:
        # Adiciona _internal (raiz) ao search path de DLLs
        os.add_dll_directory(_internal)
        # Adiciona mediapipe/python (onde opencv_world*.dll e o .pyd ficam)
        _mp_python = os.path.join(_internal, "mediapipe", "python")
        if os.path.isdir(_mp_python):
            os.add_dll_directory(_mp_python)
