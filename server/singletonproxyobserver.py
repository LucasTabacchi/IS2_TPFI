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
    """
    Devuelve el ID desde el nivel superior (ID) o, si no está, desde DATA.id/ID.
    """
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

        # Validaciones base
        uuid_cli = _require_uuid(req)
        action = _require_action(req)
        session = str(uuid.uuid4())
        now = int(time.time() * 1000)

        log.debug(f"ACTION='{action}' UUID='{uuid_cli}' session='{session}'")

        if action == "subscribe":
            # Registrar suscripción
            observers.add(uuid_cli, conn)
            log_db.append({"UUID": uuid_cli, "session": session, "action": "subscribe", "ts": now})
            send_json(conn, {"OK": True, "ACTION": "subscribe"})

            # Mantener viva la conexión (hasta que el cliente cierre)
            try:
                while True:
                    # Un pequeño ping pasivo; si la conexión cae, write fallará en broadcast
                    time.sleep(3600)
            finally:
                # La conexión se cierra en finally externo si no es subscribe;
                # para subscribe dejamos que el cierre lo haga el peer.
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
            # Registrar y listar todo
            log_db.append({"UUID": uuid_cli, "session": session, "action": "list", "ts": now})
            items = data_db.list_all()
            send_json(conn, {"OK": True, "DATA": items})
            return

        elif action == "set":
            # Aceptar formato: ID arriba + DATA{...} (recomendado)
            # Compatibilidad: si ID viene adentro de DATA, también sirve.
            if not isinstance(req.get("DATA"), dict):
                send_json(conn, {"OK": False, "Error": "DATA must be an object with fields to update."})
                return

            id_ = _extract_id(req)
            if not id_:
                send_json(conn, {"OK": False, "Error": "Missing 'ID' for ACTION 'set'."})
                return

            # Armar payload que espera CorporateData.upsert(payload) con 'id' en lowercase
            payload = dict(req["DATA"])  # copia
            payload["id"] = id_          # asegurar presencia de 'id'
            # (si venía 'ID' en DATA, opcionalmente lo removemos para consistencia)
            payload.pop("ID", None)

            log_db.append({"UUID": uuid_cli, "session": session, "action": "set", "id": id_, "ts": now})

            saved = data_db.upsert(payload)
            resp = {"OK": True, "DATA": saved}
            send_json(conn, resp)

            # Notificar a subscriptores
            try:
                observers.broadcast({"ACTION": "change", "DATA": saved}, send_json)
            except Exception as be:
                log.warning(f"Broadcast error: {be}")
            return

        else:
            # (No debería llegar acá por la validación previa)
            send_json(conn, {"OK": False, "Error": f"Unknown ACTION '{req.get('ACTION')}'"})
            return

    except ValueError as ve:
        # Errores de validación “limpios”
        try:
            send_json(conn, {"OK": False, "Error": str(ve)})
        except Exception:
            pass
        return
    except Exception as e:
        # Errores inesperados
        log.error(f"Error handling client {addr}: {e}")
        try:
            send_json(conn, {"OK": False, "Error": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
        return
    finally:
        try:
            # Para 'subscribe' dejamos la conexión viva (return anticipado arriba).
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

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", args.port))
    s.listen(128)
    log.info(f"Server listening on *:{args.port}")

    data_db = CorporateData()
    log_db = CorporateLog()
    observers = ObserverRegistry()

    try:
        while True:
            conn, addr = s.accept()
            t = threading.Thread(
                target=handle_client,
                args=(conn, addr, log, data_db, log_db, observers),
                daemon=True,
            )
            t.start()
    except KeyboardInterrupt:
        log.info("Shutting down by Ctrl+C...")
    finally:
        try:
            s.close()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()

