"""
Fixtures compartidos para tests de aceptación.
"""
import os
import shutil
import subprocess
import socket
import time
import json
import uuid
import sys
import pytest
from pathlib import Path

# Asegurar que usamos mock DB
os.environ["MOCK_DB"] = "1"

# Directorio base del proyecto
PROJECT_ROOT = Path(__file__).parent.parent
MOCK_DB_DIR = PROJECT_ROOT / "mock_db"
SERVER_SCRIPT = PROJECT_ROOT / "server" / "singletonproxyobserver.py"
CLIENT_SINGLETON = PROJECT_ROOT / "clients" / "singletonclient.py"
CLIENT_OBSERVER = PROJECT_ROOT / "clients" / "observerclient.py"


def cleanup_mock_db():
    """Limpia los archivos JSON del mock DB."""
    if MOCK_DB_DIR.exists():
        for file in MOCK_DB_DIR.glob("*.json"):
            file.unlink()


@pytest.fixture(scope="function")
def clean_mock_db():
    """Fixture que limpia la BD antes y después de cada test."""
    cleanup_mock_db()
    yield
    # cleanup_mock_db()  # Comentado para poder ver los datos después de los tests


@pytest.fixture(scope="function")
def server_process(clean_mock_db):
    """Fixture que inicia el servidor y lo detiene después."""
    # Limpiar BD antes de iniciar
    cleanup_mock_db()
    
    # Iniciar servidor en un puerto disponible
    port = find_free_port()
    
    # Iniciar proceso del servidor
    env = os.environ.copy()
    env["MOCK_DB"] = "1"
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    python_exe = sys.executable
    process = subprocess.Popen(
        [python_exe, str(SERVER_SCRIPT), "-p", str(port), "-v"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT)
    )
    
    # Esperar a que el servidor esté listo
    wait_for_server(port, timeout=5)
    
    yield port, process
    
    # Detener servidor
    try:
        process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except Exception:
        pass


def find_free_port():
    """Encuentra un puerto disponible."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def wait_for_server(port, timeout=5):
    """Espera a que el servidor esté disponible."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)
    raise TimeoutError(f"Servidor no disponible en puerto {port} después de {timeout}s")


def send_request(host, port, payload):
    """Envía una petición al servidor y devuelve la respuesta."""
    from common.net import send_json, recv_json
    
    try:
        with socket.create_connection((host, port), timeout=5) as sock:
            send_json(sock, payload)
            return recv_json(sock)
    except Exception as e:
        return {"OK": False, "Error": str(e)}


def read_corporate_data():
    """Lee el contenido de CorporateData desde el mock DB."""
    data_file = MOCK_DB_DIR / "corporate_data.json"
    if not data_file.exists():
        return []
    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def read_corporate_log():
    """Lee el contenido de CorporateLog desde el mock DB."""
    log_file = MOCK_DB_DIR / "corporate_log.json"
    if not log_file.exists():
        return []
    with open(log_file, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_uuid():
    """Genera un UUID válido de 12 hex."""
    return format(uuid.getnode(), "012x")

