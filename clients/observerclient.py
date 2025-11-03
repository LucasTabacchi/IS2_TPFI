#!/usr/bin/env python3
# clients/observerclient.py
import argparse
import json
import os
import socket
import sys
import time
import uuid
import re
from typing import Optional

from common.logging_setup import setup
from common.net import send_json, recv_json

UUID_RE = re.compile(r"^[0-9a-f]{12}$")


def append_line(path: Optional[str], line: str) -> None:
    if not path:
        return
    # crea carpeta si no existe
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_once(host: str, port: int, out_path: Optional[str], uuid_str: str, retry_s: int, log) -> None:
    """
    Abre un socket TCP, envía la suscripción, espera el acuse y
    luego queda escuchando notificaciones hasta que el socket se cierre.
    """
    sock = None
    try:
        if log:
            log.debug(f"Conectando a {host}:{port} …")
        sock = socket.create_connection((host, port), timeout=10.0)
        # armamos la solicitud de suscripción
        req = {"UUID": uuid_str, "ACTION": "subscribe"}

        # enviamos y esperamos primer acuse
        send_json(sock, req)
        first = recv_json(sock)
        if not first or not isinstance(first, dict) or not first.get("OK", False):
            s = json.dumps(first, ensure_ascii=False)
            raise RuntimeError(f"Fallo en suscripción. Respuesta: {s}")

        if log:
            log.info("Suscripto correctamente. Esperando notificaciones…")

        # loop de recepción de eventos
        sock.settimeout(1.0)  # permitir Ctrl+C y detectar cortes
        while True:
            try:
                msg = recv_json(sock)
            except socket.timeout:
                # no hay datos por ahora; permite Ctrl+C y sigue
                continue
            except KeyboardInterrupt:
                raise

            if msg is None:
                # socket cerrado por el servidor
                if log:
                    log.warning("Conexión cerrada por el servidor.")
                break

            # formateo consistente de salida
            line = json.dumps(msg, ensure_ascii=False)
            append_line(out_path, line)
            print(line)

    except KeyboardInterrupt:
        if log:
            log.info("Cancelación manual detectada. Cerrando…")
        raise
    except (ConnectionRefusedError, socket.timeout, OSError, RuntimeError) as e:
        # errores de conexión o fallo de acuse → dormir y reintentar
        if log:
            log.error("Error de conexión/suscripción: %s", e)
            log.info("Reintentando en %ss…", retry_s)
        time.sleep(retry_s)
    except Exception as e:
        # cualquier otro error inesperado también reintenta
        if log:
            log.exception("Fallo inesperado:")
            log.info("Reintentando en %ss…", retry_s)
        time.sleep(retry_s)
    finally:
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
            if log:
                log.debug("Socket cerrado.")


def main():
    ap = argparse.ArgumentParser(description="ObserverClient (TCP, reconexión)")
    # Alias -s/--server y -H/--host para comodidad
    ap.add_argument("-s", "--server", "-H", "--host", dest="host", default="127.0.0.1",
                    help="Hostname del servidor TCP (default 127.0.0.1)")
    ap.add_argument("-p", "--port", type=int, default=8080, help="Puerto del servidor TCP (default 8080)")
    ap.add_argument("-o", "--output", help="Archivo de salida (append) para las notificaciones")
    ap.add_argument("-r", "--retry", type=int, default=30, help="Segundos entre reintentos (default 30)")
    ap.add_argument("--uuid", help="(opcional) UUID/node id en hex (12 dígitos) para pruebas")
    ap.add_argument("-v", "--verbose", action="store_true", help="Salida detallada")
    args = ap.parse_args()

    log = setup(args.verbose)

    # UUID: usa el provisto o la MAC local formateada a 12 hex
    uuid_str = (str(args.uuid).strip().lower() if args.uuid else format(uuid.getnode(), "012x"))
    if not UUID_RE.fullmatch(uuid_str):
        print("UUID inválido: debe ser 12 hex (ej: a1b2c3d4e5f6). Valor:", uuid_str, file=sys.stderr)
        sys.exit(2)

    if args.verbose:
        log.debug(f"UUID: {uuid_str}")
        log.debug(f"Servidor: {args.host}:{args.port}")
        if args.output:
            log.debug(f"Output: {args.output}")
        log.debug(f"Retry: {args.retry}s")

    # bucle de reconexión permanente
    try:
        while True:
            run_once(args.host, args.port, args.output, uuid_str, args.retry, log)
            # si salimos del run_once sin excepción: servidor cerró; esperamos y reintentamos
            if args.verbose:
                log.info("Reintentando en %ss…", args.retry)
            time.sleep(args.retry)
    except KeyboardInterrupt:
        if args.verbose:
            log.info("Interrumpido por el usuario. Finalizando ObserverClient…")
    finally:
        if args.verbose:
            log.info("Ejecución terminada.")


if __name__ == "__main__":
    main()
