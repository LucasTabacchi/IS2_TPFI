#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para ver los logs de CorporateLog desde AWS DynamoDB.
Requiere: boto3 instalado y credenciales AWS configuradas.
"""
import json
import sys
import os
from decimal import Decimal
from typing import Any, Dict, List

# Configurar stdout para UTF-8 en Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    import boto3
except ImportError:
    print("[ERROR] boto3 no esta instalado.")
    print("   Instalalo con: pip install boto3")
    sys.exit(1)


def _to_native(obj):
    """
    Convierte recursivamente Decimal -> int/float para JSON.
    """
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, list):
        return [_to_native(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    return obj


def view_logs_dynamodb():
    """Muestra los logs de CorporateLog desde DynamoDB."""
    # Verificar credenciales AWS
    try:
        dynamodb = boto3.resource("dynamodb")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a AWS DynamoDB: {e}")
        print("\n[TIP] Verifica que tengas configuradas las variables de entorno:")
        print("   - AWS_ACCESS_KEY_ID")
        print("   - AWS_SECRET_ACCESS_KEY")
        print("   - AWS_DEFAULT_REGION")
        return
    
    # Obtener nombre de la tabla
    table_name = os.getenv("CORPORATELOG_TABLE", "CorporateLog")
    print(f"[INFO] Leyendo logs de la tabla: {table_name}")
    
    try:
        table = dynamodb.Table(table_name)
        
        # Verificar que la tabla existe
        try:
            table.load()
        except Exception as e:
            print(f"[ERROR] No se pudo acceder a la tabla '{table_name}': {e}")
            print("\n[TIP] Verifica que:")
            print("   1. La tabla existe en DynamoDB")
            print("   2. Tu usuario tiene permisos para leer la tabla")
            print("   3. Estas en la region correcta")
            return
        
        # Escanear todos los items
        # print("[INFO] Escaneando tabla...")
        logs: List[Dict[str, Any]] = []
        scan_kwargs: Dict[str, Any] = {}
        
        while True:
            response = table.scan(**scan_kwargs)
            items = response.get("Items", [])
            logs.extend(items)
            
            if "LastEvaluatedKey" in response:
                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            else:
                break
        
        if not logs:
            print("[INFO] La tabla CorporateLog esta vacia.")
            print("\n[TIP] Ejecuta algunas acciones (SET, GET, LIST, SUBSCRIBE) para generar logs.")
            return
        
        # Convertir Decimals a tipos nativos
        logs = [_to_native(log) for log in logs]
        
        print(f"[INFO] Total de logs encontrados: {len(logs)}\n")
        
        # Ordenar por timestamp (más recientes primero)
        def get_ts(log):
            ts = log.get("ts", 0)
            if isinstance(ts, int):
                return ts
            elif isinstance(ts, str):
                # Intentar convertir a int si es un número
                try:
                    return int(ts)
                except ValueError:
                    # Si es un string ISO date, convertir a timestamp
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        return int(dt.timestamp() * 1000)
                    except:
                        return 0
            return 0
        logs.sort(key=get_ts, reverse=True)
        
        # Mostrar solo los últimos N logs (por defecto 20)
        limit = 20
        if len(sys.argv) > 1:
            try:
                limit = int(sys.argv[1])
            except ValueError:
                pass
        
        if len(logs) > limit:
            print(f"[INFO] Mostrando los ultimos {limit} logs (de {len(logs)} totales)")
        #     print(f"[TIP] Para ver mas logs: python view_logs_dynamodb.py <numero>\n")
        
        # print("=" * 80)
        for i, log in enumerate(logs[:limit], 1):
            print(f"\nLog #{i}:")
            print(json.dumps(log, indent=2, ensure_ascii=False))
            print("-" * 80)
            
    except Exception as e:
        print(f"[ERROR] Error al leer logs: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    view_logs_dynamodb()

