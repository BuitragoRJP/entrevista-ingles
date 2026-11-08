"""Prepara la skill: crea .venv en la raíz del proyecto, instala dependencias y descarga el modelo.

Se ejecuta con cualquier Python del sistema y solo usa la biblioteca estándar. Se puede
repetir sin problema: lo que ya está instalado no se vuelve a instalar.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = SKILL_DIR.parents[2]
VENV_DIR = PROJECT_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
# faster-whisper depende de paquetes compilados; 3.12 es la versión con mejor soporte.
PREFERRED_PYTHON = "3.12"


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True)


def create_venv() -> None:
    if VENV_PYTHON.exists():
        print(f"Entorno existente: {VENV_DIR}", flush=True)
        return
    launcher = shutil.which("py")
    if launcher is None:
        raise SystemExit("No se encontró el lanzador 'py'. Instala Python 3.12 desde python.org.")
    run([launcher, f"-{PREFERRED_PYTHON}", "-m", "venv", str(VENV_DIR)])


def install_requirements() -> None:
    run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "-r",
         str(Path(__file__).with_name("requirements.txt"))])


def has_nvidia_gpu() -> bool:
    tool = shutil.which("nvidia-smi")
    if tool is None:
        return False
    try:
        return subprocess.run([tool, "-L"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_gpu_libraries() -> None:
    """Con gráfica, una respuesta corta se transcribe en 0,3 s en lugar de unos 2 s."""
    if not has_nvidia_gpu():
        print("Sin gráfica NVIDIA: el reconocimiento usará el procesador.", flush=True)
        return
    run([str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "--no-deps", "-r",
         str(Path(__file__).with_name("requirements-gpu.txt"))])


def download_model() -> None:
    config = json.loads((SKILL_DIR / "data" / "config.json").read_text(encoding="utf-8"))
    model = config["whisper_model"]
    print(f"Descargando el modelo de reconocimiento '{model}'...", flush=True)
    code = (
        "import sys; from faster_whisper import WhisperModel; "
        "WhisperModel(sys.argv[1], device='cpu', compute_type='int8')"
    )
    run([str(VENV_PYTHON), "-c", code, model])


def main() -> None:
    create_venv()
    install_requirements()
    install_gpu_libraries()
    download_model()
    print("Entorno listo.", flush=True)


if __name__ == "__main__":
    main()
