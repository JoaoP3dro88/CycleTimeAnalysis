# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec para CycleTimeAnalysis.
Empacota: FastAPI + Uvicorn + MediaPipe + OpenCV + frontend React (dist).

Gerar o executável:
    pyinstaller CycleTimeAnalysis.spec
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

project_root = Path(SPECPATH)

# Forçar PyInstaller a usar o venv do backend (tem mediapipe 0.10.21 + multipart)
_venv_site = str(project_root / 'backend' / '.venv' / 'Lib' / 'site-packages')
if _venv_site not in sys.path:
    sys.path.insert(0, _venv_site)

# ── Coletar dados do mediapipe ────────────────────────────────────────────────
mediapipe_datas = collect_data_files('mediapipe')

# ── Venv site-packages relevantes para o subprocess de preprocess ─────────────
# Empacotamos somente as pastas que o worker precisa: mediapipe, cv2, numpy.
# Ficam em _internal/venv_site_packages/ e são passadas via PYTHONPATH.
_site = project_root / 'backend' / '.venv' / 'Lib' / 'site-packages'
_worker_packages = ['mediapipe', 'cv2', 'numpy', 'opencv_python_headless-*']
venv_site_datas = []
for pkg in ['mediapipe', 'cv2', 'numpy']:
    pkg_dir = _site / pkg
    if pkg_dir.exists():
        venv_site_datas.append((str(pkg_dir), f'venv_site_packages/{pkg}'))
# .dist-info e .pth não são necessários para o subprocess funcionar

# worker script
_worker_py = str(project_root / 'backend' / 'services' / '_preprocess_worker.py')

# ── Dados extras: frontend build + pasta de dados + worker script ─────────────
extra_datas = [
    # Frontend React compilado
    (str(project_root / 'backend' / 'frontend_dist'), 'backend/frontend_dist'),
    # Pasta de dados (videos, project.json)
    (str(project_root / 'data'), 'data'),
    # Worker script (chamado como subprocess pelo preprocess_service)
    (_worker_py, 'worker'),
    # pyvenv.cfg: informa ao preprocess_service qual Python base usar
    (str(project_root / 'backend' / '.venv' / 'pyvenv.cfg'), '.'),
]

a = Analysis(
    [str(project_root / 'backend' / 'run.py')],
    pathex=[str(project_root), _venv_site],
    binaries=[],
    datas=mediapipe_datas + venv_site_datas + extra_datas,
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
    name='CycleTimeAnalysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # Sem janela de terminal
    icon=None,       # Adicione: icon='caminho/icone.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CycleTimeAnalysis',
)
