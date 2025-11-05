#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para ver los datos generados por los tests en los archivos JSON.
Útil para debuggear y verificar qué datos crean los tests.
"""
import json
import sys
import time
from pathlib import Path

# Configurar stdout para UTF-8 en Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
MOCK_DB_DIR = PROJECT_ROOT / "mock_db"
CORPORATE_DATA_FILE = MOCK_DB_DIR / "corporate_data.json"
CORPORATE_LOG_FILE = MOCK_DB_DIR / "corporate_log.json"


def read_json_file(file_path):
    """Lee un archivo JSON y retorna su contenido."""
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"[ERROR] Error al leer {file_path}: {e}")
        return None


def view_test_data():
    """Muestra los datos en los archivos JSON del mock DB."""
    print("=" * 80)
    print("[DATOS GENERADOS POR TESTS]")
    print("=" * 80)
    
    # Verificar CorporateData
    print("\n[CorporateData]")
    print("-" * 80)
    data = read_json_file(CORPORATE_DATA_FILE)
    if data is None:
        print("   Archivo no existe o está vacío")
    elif not data:
        print("   Array vacío []")
    else:
        print(f"   Total de items: {len(data)}")
        for i, item in enumerate(data, 1):
            print(f"\n   Item #{i}:")
            print(json.dumps(item, indent=4, ensure_ascii=False))
    
    # Verificar CorporateLog
    print("\n\n[CorporateLog]")
    print("-" * 80)
    log = read_json_file(CORPORATE_LOG_FILE)
    if log is None:
        print("   Archivo no existe o está vacío")
    elif not log:
        print("   Array vacío []")
    else:
        print(f"   Total de logs: {len(log)}")
        
        # Resumen por acción
        actions = {}
        for entry in log:
            action = entry.get("action", "unknown")
            actions[action] = actions.get(action, 0) + 1
        
        print(f"\n   Resumen por acción:")
        for action, count in sorted(actions.items()):
            print(f"      {action}: {count}")
        
        # Mostrar los últimos 10 logs
        print(f"\n   Últimos 10 logs:")
        for i, entry in enumerate(log[-10:], 1):
            print(f"\n   Log #{i}:")
            print(json.dumps(entry, indent=4, ensure_ascii=False))
    
    print("\n" + "=" * 80)
    print("[TIP] Los tests limpian los archivos después de ejecutarse.")
    print("      Para ver los datos durante los tests, ejecuta este script")
    print("      en otra terminal mientras los tests se ejecutan.")
    print("=" * 80)


def watch_mode():
    """Modo watch: actualiza automáticamente cada segundo."""
    print("=" * 80)
    print("[MODO WATCH] Actualizando cada segundo...")
    print("Presiona Ctrl+C para salir")
    print("=" * 80)
    
    try:
        while True:
            # Limpiar pantalla (compatible con Windows y Unix)
            import os
            os.system('cls' if os.name == 'nt' else 'clear')
            
            view_test_data()
            print(f"\n[Última actualización: {time.strftime('%H:%M:%S')}]")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[INFO] Modo watch detenido")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch_mode()
    else:
        view_test_data()

