# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para CycleTimeAnalysis.
Empacota: FastAPI + Uvicorn + MediaPipe + OpenCV + frontend React (dist).

Modo: PASTA (folder/onedir) — todos os arquivos ficam em dist/CycleTimeAnalysis/
MediaPipe roda no processo principal (sem subprocess), pois em modo pasta os
DLLs ficam acessíveis em _internal/ e o rthook os adiciona ao search path.

Gerar o executável:
    pyinstaller CycleTimeAnalysis.spec --noconfirm
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPECPATH)

# Forçar PyInstaller a usar o venv do backend
_venv_site = str(project_root / 'backend' / '.venv' / 'Lib' / 'site-packages')
if _venv_site not in sys.path:
    sys.path.insert(0, _venv_site)

# ── Coletar dados e binários do mediapipe ─────────────────────────────────────
mediapipe_datas    = collect_data_files('mediapipe', include_py_files=False)

# NÃO usar collect_dynamic_libs — ele move DLLs para _internal/ (raiz),
# mas _framework_bindings.pyd precisa encontrar opencv_world3410.dll no
# MESMO diretório (mediapipe/python/). Copiamos explicitamente.
_mp_python_src = project_root / 'backend' / '.venv' / 'Lib' / 'site-packages' / 'mediapipe' / 'python'
mediapipe_binaries = [
    (str(dll), 'mediapipe/python')
    for dll in _mp_python_src.glob('*.dll')
]
print(f"[spec] mediapipe DLLs copiados para mediapipe/python/: {[d.name for d in _mp_python_src.glob('*.dll')]}")

# ── Dados extras: frontend build + pasta de dados ─────────────────────────────
extra_datas = [
    # Frontend React compilado
    (str(project_root / 'backend' / 'frontend_dist'), 'backend/frontend_dist'),
    # Pasta de dados inicial (videos, project.json)
    (str(project_root / 'data'), 'data'),
    # Worker script (chamado pelo python_worker/python.exe)
    (str(project_root / 'backend' / 'worker_entry.py'), 'worker'),
    # Código-fonte do backend como .py físicos (para o python_worker/python.exe importar)
    (str(project_root / 'backend' / '__init__.py'),              'backend'),
    (str(project_root / 'backend' / 'config.py'),                'backend'),
    (str(project_root / 'backend' / 'models' / '__init__.py'),   'backend/models'),
    (str(project_root / 'backend' / 'models' / 'model.py'),      'backend/models'),
    (str(project_root / 'backend' / 'models' / 'schemas.py'),    'backend/models'),
    (str(project_root / 'backend' / 'services' / '__init__.py'),         'backend/services'),
    (str(project_root / 'backend' / 'services' / '_preprocess_worker.py'),'backend/services'),
    (str(project_root / 'backend' / 'services' / 'analytics_service.py'),'backend/services'),
    (str(project_root / 'backend' / 'services' / 'preprocess_service.py'),'backend/services'),
    (str(project_root / 'backend' / 'services' / 'storage_service.py'),  'backend/services'),
]

a = Analysis(
    [str(project_root / 'backend' / 'run.py')],
    pathex=[str(project_root), _venv_site],
    binaries=mediapipe_binaries,
    datas=mediapipe_datas + extra_datas,
    hiddenimports=[
        # FastAPI / Uvicorn
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # Multipart (obrigatório para upload de arquivos no FastAPI)
        'multipart',
        'python_multipart',
        'starlette.datastructures',
        'starlette.formparsers',
        # Pydantic
        'pydantic',
        'pydantic.deprecated.decorator',
        # Backend modules
        'backend',
        'backend.main',
        'backend.config',
        'backend.api.routers.projects',
        'backend.api.routers.analytics',
        'backend.api.routers.preprocess',
        'backend.services.storage_service',
        'backend.services.analytics_service',
        'backend.services.preprocess_service',
        'backend.services._preprocess_worker',
        'backend.models.schemas',
        # OpenCV
        'cv2',
        # MediaPipe internals
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

# ── Analysis separada para o worker (só precisa de mediapipe + cv2 + numpy) ───
worker_a = Analysis(
    [str(project_root / 'backend' / 'worker_entry.py')],
    pathex=[str(project_root), _venv_site],
    binaries=mediapipe_binaries,
    datas=mediapipe_datas,
    hiddenimports=[
        'backend.services._preprocess_worker',
        'mediapipe',
        'mediapipe.python',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.hands',
        'mediapipe.python.solution_base',
        'mediapipe.framework.formats.landmark_pb2',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(project_root / 'pyi_hooks' / 'rthook_mediapipe.py')],
    excludes=[],
    noarchive=False,
)
worker_pyz = PYZ(worker_a.pure)

# ── EXE principal (servidor + UI) ─────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CycleTimeAnalysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,      # Sem janela de terminal
    icon=None,
)

# ── EXE worker (pré-processamento MediaPipe Python) ───────────────────────────
worker_exe = EXE(
    worker_pyz,
    worker_a.scripts,
    [],
    exclude_binaries=True,
    name='PreprocessWorker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    worker_exe,
    a.binaries,
    worker_a.binaries,
    a.datas,
    worker_a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CycleTimeAnalysis',
)

# ── Pós-build: copiar Python portátil para dist/CycleTimeAnalysis/python_worker/
# O PyInstaller não suporta colocar arquivos fora de _internal/, então fazemos
# manualmente. O python_worker/python.exe é o mesmo Python que tem mediapipe
# instalado e funciona — sem os problemas de DLL init do PyInstaller.
import shutil

_dist_dir    = project_root / 'dist' / 'CycleTimeAnalysis'
_worker_dir  = _dist_dir / 'python_worker'
_base_python = Path("C:/Users/klj1ct/AppData/Local/Programs/Python/Python312")
_venv_dir    = project_root / 'backend' / '.venv'
_site        = _venv_dir / 'Lib' / 'site-packages'

print("[spec] copiando python_worker para dist...", flush=True)
_worker_dir.mkdir(exist_ok=True)

# python.exe e DLLs necessárias
# IMPORTANTE: usar o python.exe BASE (não o do venv). O venv python.exe
# depende do pyvenv.cfg para encontrar DLLs, o que causa "DLL init failed".
# O python.exe base carrega python312.dll da própria pasta — funciona standalone.
for _f in [
    _base_python / 'python.exe',      # base python (não o wrapper do venv)
    _base_python / 'python3.dll',
    _base_python / 'python312.dll',
    _base_python / 'vcruntime140.dll',
    _base_python / 'vcruntime140_1.dll',
]:
    if _f.exists():
        shutil.copy2(str(_f), str(_worker_dir / _f.name))
        print(f"  copiado: {_f.name}", flush=True)

# Stdlib do Python base
_stdlib_dst = _worker_dir / 'Lib'
if _stdlib_dst.exists():
    shutil.rmtree(str(_stdlib_dst))
shutil.copytree(str(_base_python / 'Lib'), str(_stdlib_dst))
print("  copiado: Lib/ (stdlib)", flush=True)

# Site-packages: mediapipe, cv2, numpy
_sp_dst = _stdlib_dst / 'site-packages'
_sp_dst.mkdir(exist_ok=True)
for _pkg in ['mediapipe', 'cv2', 'numpy', 'numpy.libs']:
    _src = _site / _pkg
    _dst = _sp_dst / _pkg
    if _src.exists():
        if _dst.exists():
            shutil.rmtree(str(_dst))
        shutil.copytree(str(_src), str(_dst))
        print(f"  copiado: site-packages/{_pkg}", flush=True)

# Sem pyvenv.cfg — python.exe base não precisa dele e encontra DLLs na própria pasta

print("[spec] python_worker pronto!", flush=True)
