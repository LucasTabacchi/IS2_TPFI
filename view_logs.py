#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para ver los logs de CorporateLog desde mock_db/corporate_log.json
"""
import json
import sys
from pathlib import Path

# Configurar stdout para UTF-8 en Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOG_FILE = Path(__file__).parent / "mock_db" / "corporate_log.json"

def view_logs():
    """Muestra los logs de CorporateLog."""
    if not LOG_FILE.exists():
        print("[ERROR] El archivo corporate_log.json no existe.")
        print(f"   Ruta esperada: {LOG_FILE}")
        print("\n[TIP] Asegurate de haber ejecutado el servidor con MOCK_DB=1")
        return
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
        
        if not logs:
            print("[INFO] El archivo corporate_log.json esta vacio.")
            print("\n[TIP] Ejecuta algunas acciones (SET, GET, LIST, SUBSCRIBE) para generar logs.")
            return
        
        print(f"[INFO] Total de logs: {len(logs)}\n")
        print("=" * 80)
        
        for i, log in enumerate(logs, 1):
            print(f"\nLog #{i}:")
            print(json.dumps(log, indent=2, ensure_ascii=False))
            print("-" * 80)
            
    except json.JSONDecodeError as e:
        print(f"[ERROR] Error al leer el JSON: {e}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")

if __name__ == "__main__":
    view_logs()

