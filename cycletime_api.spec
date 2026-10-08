# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — CycleTime Analysis API (servidor).

Gerar (na máquina de desenvolvimento, com o venv do backend ativo):
    pyinstaller cycletime_api.spec --noconfirm --clean

Saída:  dist/cycletime_api/
            cycletime_api.exe
            _internal/
            python_worker/      <- Python portátil que roda o MediaPipe

Mudanças em relação ao CycleTimeAnalysis.spec:
  - Frontend NÃO é mais embutido (vai para o IIS)
  - Pasta data/ NÃO é mais embutida (fica ao lado do exe, persiste entre deploys)
  - console=True
  - Removido o PreprocessWorker.exe (nenhum código o chama; o preprocess usa
    python_worker/python.exe + worker_entry.py)
  - Caminhos do Python base e do venv não são mais fixos (ver variáveis abaixo)

Variáveis de ambiente opcionais no momento do build:
    CTA_BASE_PYTHON  pasta do Python base  (padrão: sys.base_prefix)
    CTA_VENV         pasta do venv         (padrão: backend/.venv)
"""

import os
import shutil
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPECPATH)

_base_python = Path(os.environ.get('CTA_BASE_PYTHON', sys.base_prefix))
_venv_dir    = Path(os.environ.get('CTA_VENV', project_root / 'backend' / '.venv'))
_site        = _venv_dir / 'Lib' / 'site-packages'

assert _site.exists(), f"site-packages do venv não encontrado: {_site} (defina CTA_VENV)"
assert (_base_python / 'python.exe').exists(), f"python.exe base não encontrado: {_base_python} (defina CTA_BASE_PYTHON)"

# ── MediaPipe ─────────────────────────────────────────────────────────────────
mediapipe_datas = collect_data_files('mediapipe', include_py_files=False)

# NÃO usar collect_dynamic_libs: _framework_bindings.pyd precisa achar
# opencv_world*.dll no MESMO diretório (mediapipe/python/).
_mp_python_src = _site / 'mediapipe' / 'python'
mediapipe_binaries = [
    (str(dll), 'mediapipe/python')
    for dll in _mp_python_src.glob('*.dll')
]
print(f"[spec] mediapipe DLLs: {[d.name for d in _mp_python_src.glob('*.dll')]}")

# ── Arquivos .py físicos para o python_worker/python.exe importar ─────────────
b = project_root / 'backend'
extra_datas = [
    (str(b / 'worker_entry.py'),                           'worker'),
    (str(b / '__init__.py'),                               'backend'),
    (str(b / 'config.py'),                                 'backend'),
    (str(b / 'models' / '__init__.py'),                    'backend/models'),
    (str(b / 'models' / 'model.py'),                       'backend/models'),
    (str(b / 'models' / 'schemas.py'),                     'backend/models'),
    (str(b / 'services' / '__init__.py'),                  'backend/services'),
    (str(b / 'services' / '_preprocess_worker.py'),        'backend/services'),
    (str(b / 'services' / 'analytics_service.py'),         'backend/services'),
    (str(b / 'services' / 'preprocess_service.py'),        'backend/services'),
    (str(b / 'services' / 'storage_service.py'),           'backend/services'),
    (str(b / 'services' / 'glove_detector.py'),            'backend/services'),
]

a = Analysis(
    [str(b / 'run.py')],
    pathex=[str(project_root)],
    binaries=mediapipe_binaries,
    datas=mediapipe_datas + extra_datas,
    hiddenimports=[
        # FastAPI / Uvicorn
        'uvicorn.logging',
        'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        # Upload de arquivos
        'multipart', 'python_multipart',
        'starlette.datastructures', 'starlette.formparsers',
        # Pydantic
        'pydantic', 'pydantic.deprecated.decorator',
        # Backend (uvicorn importa "backend.main:app" por string)
        'backend', 'backend.main', 'backend.config',
        'backend.api.routers.projects',
        'backend.api.routers.analytics',
        'backend.api.routers.preprocess',
        'backend.services.storage_service',
        'backend.services.analytics_service',
        'backend.services.preprocess_service',
        'backend.services._preprocess_worker',
        'backend.services.glove_detector',
        'backend.models.schemas',
        # OpenCV / MediaPipe
        'cv2',
        'mediapipe',
        'mediapipe.python',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.hands',
        'mediapipe.python.solutions.drawing_utils',
        'mediapipe.python.solution_base',
        'mediapipe.framework.formats.landmark_pb2',
        'mediapipe.calculators.core',
        'mediapipe.calculators.image',
        'mediapipe.calculators.util',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / 'pyi_hooks' / 'rthook_mediapipe.py')],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='cycletime_api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,       # servidor: precisa de stdout (NSSM / logs)
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='cycletime_api',
)

# ── Pós-build: python_worker/ (Python portátil com mediapipe) ─────────────────
# O PyInstaller não coloca arquivos fora de _internal/, então copiamos à mão.
# Usa o python.exe BASE (não o do venv) para evitar "DLL init failed".
_dist_dir   = project_root / 'dist' / 'cycletime_api'
_worker_dir = _dist_dir / 'python_worker'

print("[spec] copiando python_worker para dist...", flush=True)
_worker_dir.mkdir(exist_ok=True)

for _f in [
    _base_python / 'python.exe',
    _base_python / 'python3.dll',
    _base_python / f'python{sys.version_info.major}{sys.version_info.minor}.dll',
    _base_python / 'vcruntime140.dll',
    _base_python / 'vcruntime140_1.dll',
]:
    if _f.exists():
        shutil.copy2(str(_f), str(_worker_dir / _f.name))
        print(f"  copiado: {_f.name}", flush=True)
    else:
        print(f"  AVISO: não encontrado: {_f}", flush=True)

_stdlib_dst = _worker_dir / 'Lib'
if _stdlib_dst.exists():
    shutil.rmtree(str(_stdlib_dst))
shutil.copytree(
    str(_base_python / 'Lib'), str(_stdlib_dst),
    ignore=shutil.ignore_patterns('site-packages', '__pycache__', 'test', 'tests', 'idlelib', 'turtledemo'),
)
print("  copiado: Lib/ (stdlib)", flush=True)

_dlls_dst = _worker_dir / 'DLLs'
if _dlls_dst.exists():
    shutil.rmtree(str(_dlls_dst))
shutil.copytree(str(_base_python / 'DLLs'), str(_dlls_dst))
print("  copiado: DLLs/", flush=True)

_sp_dst = _stdlib_dst / 'site-packages'
shutil.copytree(
    str(_site), str(_sp_dst),
    ignore=shutil.ignore_patterns('__pycache__', 'pip*', 'pyinstaller*', '_pytest', 'pytest*'),
)
print("  copiado: site-packages (venv)", flush=True)
print("[spec] python_worker pronto!", flush=True)
