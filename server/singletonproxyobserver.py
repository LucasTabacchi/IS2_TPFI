import argparse, socket, threading, json, uuid, time, sys, re
from common.logging_setup import setup
from common.net import send_json, recv_json
from storage.adapter import CorporateData, CorporateLog
from server.observer import ObserverRegistry

UUID_HEX_RE = re.compile(r"^[0-9a-f]{12}$")


def _require_uuid(req):
    val = str(req.get("UUID", "")).strip().lower()
    if not UUID_HEX_RE.fullmatch(val):
        raise ValueError("Falta 'UUID' o no es válido (debe ser 12 hex, ej: 'a1b2c3d4e5f6').")
    return val


def _require_action(req):
    action = str(req.get("ACTION", "")).strip().lower()
    if action not in {"subscribe", "get", "list", "set"}:
        raise ValueError("ACTION debe ser 'subscribe', 'get', 'list' o 'set'.")
    return action


def _extract_id(req):
    """ Devuelve el ID desde el nivel superior (ID) o, si no está, desde DATA.id/ID. """
    if "ID" in req and str(req["ID"]).strip():
        return str(req["ID"]).strip()
    data = req.get("DATA")
    if isinstance(data, dict):
        if data.get("id"):
            return str(data["id"]).strip()
        if data.get("ID"):
            return str(data["ID"]).strip()
    return None


def handle_client(conn, addr, log, data_db, log_db, observers):
    req = None
    try:
        req = recv_json(conn)
        if not req:
            return

        log.debug(f"RAW request from {addr}: {req}")

        uuid_cli = _require_uuid(req)
        action = _require_action(req)
        session = str(uuid.uuid4())
        now = int(time.time() * 1000)

        log.debug(f"ACTION='{action}' UUID='{uuid_cli}' session='{session}'")

        if action == "subscribe":
            observers.add(uuid_cli, conn)
            log_db.append({"UUID": uuid_cli, "session": session, "action": "subscribe", "ts": now})
            send_json(conn, {"OK": True, "ACTION": "subscribe"})
            log.info(f"Cliente {uuid_cli} suscripto desde {addr}")

            # Mantener viva la conexión hasta cierre remoto
            try:
                while True:
                    time.sleep(3600)
            except Exception:
                pass
            return

        elif action == "get":
            id_ = _extract_id(req)
            if not id_:
                send_json(conn, {"OK": False, "Error": "Missing 'ID' for ACTION 'get'."})
                return
            log_db.append({"UUID": uuid_cli, "session": session, "action": "get", "id": id_, "ts": now})
            item = data_db.get(id_)
            if item:
                send_json(conn, {"OK": True, "DATA": item})
            else:
                send_json(conn, {"OK": False, "Error": "NotFound"})
            return

        elif action == "list":
            log_db.append({"UUID": uuid_cli, "session": session, "action": "list", "ts": now})
            items = data_db.list_all()
            send_json(conn, {"OK": True, "DATA": items})
            return

        elif action == "set":
            if not isinstance(req.get("DATA"), dict):
                send_json(conn, {"OK": False, "Error": "DATA must be an object with fields to update."})
                return

            id_ = _extract_id(req)
            if not id_:
                send_json(conn, {"OK": False, "Error": "Missing 'ID' for ACTION 'set'."})
                return

            payload = dict(req["DATA"])
            payload["id"] = id_
            payload.pop("ID", None)

            log_db.append({"UUID": uuid_cli, "session": session, "action": "set", "id": id_, "ts": now})
            saved = data_db.upsert(payload)
            send_json(conn, {"OK": True, "DATA": saved})

            try:
                observers.broadcast({"ACTION": "change", "DATA": saved}, send_json)
            except Exception as be:
                log.warning(f"Broadcast error: {be}")
            return

        else:
            send_json(conn, {"OK": False, "Error": f"Unknown ACTION '{req.get('ACTION')}'"})
            return

    except ValueError as ve:
        try:
            send_json(conn, {"OK": False, "Error": str(ve)})
        except Exception:
            pass
    except Exception as e:
        log.error(f"Error handling client {addr}: {e}")
        try:
            send_json(conn, {"OK": False, "Error": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    finally:
        try:
            if not (req and str(req.get("ACTION", "")).strip().lower() == "subscribe"):
                conn.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--port", type=int, default=8080)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    log = setup(args.verbose)

    data_db = CorporateData()
    log_db = CorporateLog()
    observers = ObserverRegistry()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", args.port))
    server.listen(128)
    server.settimeout(1.0)  # ⏱ evita bloqueo indefinido en accept()
    # log.info(f"Servidor escuchando en *:{args.port}")
    # log.info("Presione Ctrl+C para detenerlo de forma segura.")

    try:
        while True:
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue  # permite chequear KeyboardInterrupt
            except OSError:
                break

            t = threading.Thread(
                target=handle_client,
                args=(conn, addr, log, data_db, log_db, observers),
                daemon=True,
            )
            t.start()

    except KeyboardInterrupt:
        log.info("Cancelación manual detectada (Ctrl+C). Cerrando servidor...")

    finally:
        try:
            server.close()
            observers.close_all()  # 🔒 asegúrate de tener método para cerrar subscriptores
        except Exception as e:
            log.warning(f"Error al cerrar servidor: {e}")
        log.info("Servidor detenido correctamente.")
        sys.exit(0)


if __name__ == "__main__":
    main()
