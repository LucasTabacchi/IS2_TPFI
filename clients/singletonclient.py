#!/usr/bin/env python3
# clients/singletonclient.py
import argparse
import json
import socket
import sys
import uuid
import re
from typing import Any, Dict

from common.logging_setup import setup
from common.net import send_json, recv_json

UUID_HEX_RE = re.compile(r"^[0-9a-f]{12}$")
ALLOWED_ACTIONS = {"get", "set", "list"}


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def normalize_payload(raw: Dict[str, Any], log) -> Dict[str, Any]:
    """
    Normaliza el JSON de entrada para hablar con el servidor.
    - Asegura UUID (12 hex); si falta, usa uuid.getnode().
    - Normaliza ACTION (get/set/list).
    - Para SET: si no hay DATA, arma DATA con todos los campos excepto UUID/ACTION/ID/DATA.
      (esto hace compatible el formato 'plano' pedido en la consigna)
    - Para LIST: elimina ID si vino por error.
    """
    req = dict(raw) if isinstance(raw, dict) else {}
    # UUID
    uuid_str = str(req.get("UUID", "")).strip().lower()
    if not uuid_str:
        uuid_str = format(uuid.getnode(), "012x")
        if log:
            log.debug(f"UUID no informado: usando uuid.getnode() => {uuid_str}")
    if not UUID_HEX_RE.fullmatch(uuid_str):
        raise ValueError("UUID inválido: debe ser 12 hex (ej: 'a1b2c3d4e5f6').")
    req["UUID"] = uuid_str

    # ACTION
    action = str(req.get("ACTION", "")).strip().lower()
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"ACTION debe ser uno de {sorted(ALLOWED_ACTIONS)}.")
    req["ACTION"] = action

    # ID (opcional excepto en get/set)
    id_val = req.get("ID")
    if id_val is not None:
        req["ID"] = str(id_val).strip()
        if req["ID"] == "":
            req.pop("ID", None)

    # SET → garantizar DATA
    if action == "set":
        data_obj = req.get("DATA")
        if not isinstance(data_obj, dict):
            # Construimos DATA con todo lo que no sea de control
            data_obj = {}
            for k, v in list(req.items()):
                if k in ("UUID", "ACTION", "ID", "DATA"):
                    continue
                data_obj[k] = v
            req["DATA"] = data_obj

        # ID requerido para set
        if not req.get("ID"):
            # Intentamos extraer de DATA si vino como 'id' o 'ID'
            if isinstance(req["DATA"], dict):
                id_alt = req["DATA"].get("id") or req["DATA"].get("ID")
                if id_alt:
                    req["ID"] = str(id_alt).strip()
            if not req.get("ID"):
                raise ValueError("Missing 'ID' para ACTION 'set'.")

    # GET → ID requerido
    if action == "get":
        if not req.get("ID"):
            raise ValueError("Missing 'ID' para ACTION 'get'.")

    # LIST → ignorar ID si vino
    if action == "list":
        req.pop("ID", None)

    return req


def run_once(server: str, port: int, payload: Dict[str, Any], log, out_path: str | None) -> int:
    """Abre socket TCP, envía payload JSON (framing common.net) y guarda/imprime la respuesta."""
    try:
        with socket.create_connection((server, port), timeout=10.0) as sock:
            if log:
                log.debug(f"Conectado a {server}:{port}")
                log.debug(f"Request: {json.dumps(payload, ensure_ascii=False)}")
            send_json(sock, payload)
            resp = recv_json(sock)

        if resp is None:
            if log:
                log.error("Sin respuesta del servidor (None).")
            print(json.dumps({"OK": False, "Error": "No response"}, ensure_ascii=False))
            return 1

        if out_path:
            save_json(out_path, resp)
        else:
            print(json.dumps(resp, ensure_ascii=False, indent=2))

        if log:
            log.debug(f"Response: {json.dumps(resp, ensure_ascii=False)}")
        return 0

    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        if log:
            log.error(f"Error de conexión: {e}")
        print(json.dumps({"OK": False, "Error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        return 2
    except Exception as e:
        if log:
            log.exception("Fallo inesperado:")
        print(json.dumps({"OK": False, "Error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
        return 3


def main():
    ap = argparse.ArgumentParser(description="SingletonClient (TCP)")
    ap.add_argument("-i", "--input", required=True, help="Archivo JSON de entrada")
    ap.add_argument("-o", "--output", help="Archivo JSON de salida (si se omite, imprime por stdout)")
    # Compatibilidad: permitir configurar host/puerto aunque la consigna no lo muestre explícito
    ap.add_argument("-s", "--server", "-H", "--host", dest="host", default="127.0.0.1",
                    help="Hostname del servidor (default 127.0.0.1)")
    ap.add_argument("-p", "--port", type=int, default=8080, help="Puerto TCP del servidor (default 8080)")
    ap.add_argument("-v", "--verbose", action="store_true", help="Salida detallada")
    args = ap.parse_args()

    log = setup(args.verbose)

    try:
        raw = load_json(args.input)
    except Exception as e:
        print(f"[ERROR] No se pudo leer {args.input}: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        payload = normalize_payload(raw, log)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(2)

    rc = run_once(args.host, args.port, payload, log, args.output)
    sys.exit(rc)


if __name__ == "__main__":
    main()
