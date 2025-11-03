import argparse
import socket
import threading
import json
import uuid
import time
import sys
import re
from typing import Optional

from common.logging_setup import setup
from common.net import send_json, recv_json
from storage.adapter import CorporateData, CorporateLog
from server.observer import ObserverRegistry

# ======= Validaciones =======
UUID_HEX_RE = re.compile(r"^[0-9a-f]{12}$")
ALLOWED = {"subscribe", "get", "list", "set"}


def _require_uuid(req: dict) -> str:
    val = str(req.get("UUID", "")).strip().lower()
    if not UUID_HEX_RE.fullmatch(val):
        raise ValueError("Falta 'UUID' o no es válido (12 hex, ej: 'a1b2c3d4e5f6').")
    return val


def _require_action(req: dict) -> str:
    action = str(req.get("ACTION", "")).strip().lower()
    if action not in ALLOWED:
        raise ValueError("ACTION debe ser 'subscribe', 'get', 'list' o 'set'.")
    return action


def _extract_id(req: dict) -> Optional[str]:
    """Devuelve el ID desde el nivel superior o desde DATA.id / DATA.ID."""
    if "ID" in req and str(req["ID"]).strip():
        return str(req["ID"]).strip()
    data = req.get("DATA")
    if isinstance(data, dict):
        if data.get("id"):
            return str(data["id"]).strip()
        if data.get("ID"):
            return str(data["ID"]).strip()
    return None


# ======= Servicio (Proxy a la capa de datos + auditoría + observer) =======

class Service:
    def __init__(self, data_db: CorporateData, log_db: CorporateLog, observers: ObserverRegistry, log):
        self.data_db = data_db
        self.log_db = log_db
        self.observers = observers
        self.log = log

    def _audit(self, uuid_cli: str, action: str, item_id: Optional[str] = None) -> int:
        """Registra en CorporateLog (modo general) y devuelve timestamp en ms."""
        now = int(time.time() * 1000)
        entry = {"UUID": uuid_cli, "session": str(uuid.uuid4()), "action": action, "ts": now}
        if item_id is not None:
            entry["id"] = item_id  # GET debe registrar "ID solicitado"
        self.log_db.append(entry)
        return now

    def do_get(self, uuid_cli: str, item_id: str) -> dict:
        self._audit(uuid_cli, "get", item_id)
        item = self.data_db.get(item_id)
        if item:
            return {"OK": True, "DATA": item}
        return {"OK": False, "Error": "NotFound"}

    def do_list(self, uuid_cli: str) -> dict:
        self._audit(uuid_cli, "list")  # sin id
        items = self.data_db.list_all()
        return {"OK": True, "DATA": items}

    def do_set(self, uuid_cli: str, item_id: str, value_obj: dict) -> dict:
        if not isinstance(value_obj, dict):
            return {"OK": False, "Error": "DATA must be an object with fields to update."}

        # Normalizar payload (si llega 'ID' dentro de DATA, lo homogenizamos a 'id')
        payload = dict(value_obj)
        payload["id"] = item_id          # ← asegurar clave correcta para upsert
        payload.pop("ID", None)

        ts = self._audit(uuid_cli, "set")  # ← sin id en la auditoría
        saved = self.data_db.upsert(payload)

        # Respuesta al solicitante
        resp = {"OK": True, "DATA": saved}

        # Notificación a todos los suscriptores
        event = {"ACTION": "change", "DATA": saved, "ts": ts}
        try:
            self.observers.broadcast(event, send_json)
            self.log.debug(f"[BROADCAST] id='{item_id}' notificado a suscriptores")
        except Exception as be:
            self.log.warning(f"Broadcast error: {be}")

        return resp

    def do_subscribe_ack(self, uuid_cli: str) -> dict:
        """Audita 'subscribe' con append_exact para que el adapter pueda formar la PK técnica UUID#subscribe#session."""
        now = int(time.time() * 1000)
        entry = {"UUID": uuid_cli, "session": str(uuid.uuid4()), "action": "subscribe", "ts": now}
        self.log_db.append_exact(entry)  # ← clave: no usamos append()
        return {"OK": True, "ACTION": "subscribe"}


# ======= Handler por conexión TCP =======

def handle_client(conn: socket.socket, addr, service: Service):
    """
    Maneja una única solicitud por conexión:
      - get / list / set → responde una vez y cierra
      - subscribe        → acuse, registra el socket y mantiene la conexión abierta
    """
    log = service.log
    req = None
    try:
        req = recv_json(conn)
        if not req:
            return

        log.debug(f"REQ {addr}: {req}")

        uuid_cli = _require_uuid(req)
        action = _require_action(req)

        # ---- SUBSCRIBE ----
        if action == "subscribe":
            # 1) Auditoría con append_exact
            ack = service.do_subscribe_ack(uuid_cli)
            # 2) Registrar el socket en ObserverRegistry
            service.observers.add(uuid_cli, conn)
            # 3) Enviar acuse
            send_json(conn, ack)
            log.info(f"[SUBSCRIBE] {uuid_cli} @{addr} suscripto; conexión queda abierta.")

            # 4) Mantener la conexión viva (las notificaciones las envía observers.broadcast)
            try:
                while True:
                    time.sleep(3600)
            except Exception:
                # cierre remoto o interrupción
                pass
            finally:
                # remover del registry si existe API; sino, close_all() en shutdown
                try:
                    service.observers.remove(uuid_cli, conn)
                except Exception:
                    pass
            return

        # ---- GET ----
        if action == "get":
            item_id = _extract_id(req)
            if not item_id:
                send_json(conn, {"OK": False, "Error": "Missing 'ID' for ACTION 'get'."})
                return
            resp = service.do_get(uuid_cli, item_id)
            send_json(conn, resp)
            return

        # ---- LIST ----
        if action == "list":
            # Si vino ID por error, lo ignoramos (la consigna indica que list no requiere ID)
            resp = service.do_list(uuid_cli)
            send_json(conn, resp)
            return

        # ---- SET ----
        if action == "set":
            item_id = _extract_id(req)
            if not item_id:
                send_json(conn, {"OK": False, "Error": "Missing 'ID' for ACTION 'set'."})
                return
            resp = service.do_set(uuid_cli, item_id, req.get("DATA"))
            send_json(conn, resp)
            return

        # ---- Desconocido (por si las dudas) ----
        send_json(conn, {"OK": False, "Error": f"Unknown ACTION '{req.get('ACTION')}'"})
        return

    except ValueError as ve:
        try:
            send_json(conn, {"OK": False, "Error": str(ve)})
        except Exception:
            pass
    except Exception as e:
        log.error(f"Error con {addr}: {e}")
        try:
            send_json(conn, {"OK": False, "Error": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    finally:
        # Para subscribe dejamos abierto; para el resto, cerramos acá
        try:
            if not (req and str(req.get("ACTION", "")).strip().lower() == "subscribe"):
                conn.close()
        except Exception:
            pass


# ======= Main (servidor TCP) =======

def main():
    ap = argparse.ArgumentParser(description="SingletonProxyObserverTPFI (TCP puro)")
    ap.add_argument("-p", "--port", type=int, default=8080, help="Puerto TCP (default 8080)")
    ap.add_argument("-v", "--verbose", action="store_true", help="Log detallado")
    args = ap.parse_args()

    log = setup(args.verbose)

    # Singletons de datos y log (requisito)
    data_db = CorporateData()
    log_db = CorporateLog()

    # Observer para manejar suscripciones (requisito)
    observers = ObserverRegistry()

    # Servicio (Proxy): valida, audita, accede a datos y notifica (requisito)
    service = Service(data_db, log_db, observers, log)

    # Servidor TCP
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", args.port))
    srv.listen(128)
    srv.settimeout(1.0)

    log.info(f"Servidor escuchando en *:{args.port}")
    log.info("Acciones soportadas: subscribe / get / list / set")
    log.info("Ctrl+C para detenerlo.")

    try:
        while True:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            t = threading.Thread(
                target=handle_client,
                name=f"client@{addr[0]}:{addr[1]}",
                args=(conn, addr, service),
                daemon=True,
            )
            t.start()

    except KeyboardInterrupt:
        log.info("Cancelación manual detectada (Ctrl+C). Cerrando servidor…")

    finally:
        try:
            srv.close()
        except Exception:
            pass
        try:
            observers.close_all()  # asegurar cierre de sockets suscriptos
        except Exception as e:
            log.warning(f"Error al cerrar suscriptores: {e}")
        log.info("Servidor detenido correctamente.")
        sys.exit(0)


if __name__ == "__main__":
    main()
