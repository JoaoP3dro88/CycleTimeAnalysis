"""
worker_entry.py — Entry point do worker de pré-processamento.
Chamado pelo preprocess_service.py como subprocess:
    python_worker/python.exe worker_entry.py <video_path> <out_path>
"""
import sys
import os

# Adicionar _internal/ ao sys.path para que 'backend' seja encontrado.
# O worker_entry.py fica em _internal/worker/, então _internal/ é o pai.
_here = os.path.dirname(os.path.abspath(__file__))          # _internal/worker/
_internal = os.path.dirname(_here)                          # _internal/
if _internal not in sys.path:
    sys.path.insert(0, _internal)

# Registrar diretórios de DLL antes de qualquer import nativo.
# O python_worker/python.exe não tem o rthook do PyInstaller,
# então precisamos fazer isso manualmente aqui.
_worker_root = os.path.dirname(_here.rstrip(os.sep).rsplit(os.sep, 1)[0] if '_internal' in _here else _here)
# Localizar python_worker/ como irmão de _internal/
_dist_root = os.path.dirname(_internal)   # dist/CycleTimeAnalysis/
_worker_mp_python = os.path.join(_dist_root, 'python_worker', 'Lib', 'site-packages', 'mediapipe', 'python')
_worker_cv2       = os.path.join(_dist_root, 'python_worker', 'Lib', 'site-packages', 'cv2')
_internal_mp      = os.path.join(_internal, 'mediapipe', 'python')

for _dll_dir in [_worker_mp_python, _worker_cv2, _internal_mp, _internal, _dist_root]:
    if os.path.isdir(_dll_dir):
        try:
            os.add_dll_directory(_dll_dir)
        except Exception:
            pass
        # Também adicionar ao PATH para DLLs secundárias
        os.environ['PATH'] = _dll_dir + os.pathsep + os.environ.get('PATH', '')


def main():
    if len(sys.argv) < 3:
        print("Uso: python worker_entry.py <video_path> <out_path>", file=sys.stderr)
        sys.exit(1)

    video_path = sys.argv[1]
    out_path   = sys.argv[2]

    print(f"[worker] _internal: {_internal}", flush=True)
    print(f"[worker] sys.path: {sys.path[:3]}", flush=True)

    from backend.services._preprocess_worker import run_worker
    run_worker(video_path, out_path)


if __name__ == "__main__":
    main()
