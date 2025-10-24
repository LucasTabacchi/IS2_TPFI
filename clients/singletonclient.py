import argparse, json, socket, re, sys
from common.logging_setup import setup
from common.net import send_json, recv_json

UUID_RE = re.compile(r"^[0-9a-f]{12}$")
ACTIONS = {"get", "set", "list"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True, help="input JSON file")
    ap.add_argument("-o", "--output", help="output JSON file")
    ap.add_argument("-s", "--server", default="127.0.0.1")
    ap.add_argument("-p", "--port", type=int, default=8080)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    log = setup(args.verbose)

    # cargar request base
    with open(args.input, "r", encoding="utf-8") as f:
        req = json.load(f)

    # --- Validar UUID (12 hex) tomado del JSON ---
    uuid_val = req.get("UUID")
    if not uuid_val:
        log.error("El JSON de entrada debe incluir 'UUID' (node id en hex).")
        sys.exit(2)
    uuid_str = str(uuid_val).strip().lower()
    if not UUID_RE.fullmatch(uuid_str):
        log.error("UUID inválido: debe ser 12 hex (ej: 'a1b2c3d4e5f6').")
        sys.exit(2)
    req["UUID"] = uuid_str  # normalizado

    # --- Validar ACTION ---
    action = str(req.get("ACTION", "")).strip().lower()
    if action not in ACTIONS:
        log.error("ACTION debe ser 'get', 'set' o 'list'.")
        sys.exit(2)
    req["ACTION"] = action  # normalizado

    # --- Reglas por acción ---
    if action in {"get", "set"}:
        if not req.get("ID"):
            log.error("Para ACTION '%s' el JSON debe incluir 'ID'.", action)
            sys.exit(2)
    elif action == "list":
        if "ID" in req:
            log.warning("ACTION 'list' no usa 'ID'; se eliminará del request.")
            req.pop("ID", None)

    # (Opcional) Podés validar que DATA sea dict cuando action == "set"
    if action == "set":
        data = req.get("DATA")
        if data is not None and not isinstance(data, dict):
            log.error("Para ACTION 'set', 'DATA' (si se incluye) debe ser un objeto JSON.")
            sys.exit(2)

    # --- Enviar ---
    with socket.create_connection((args.server, args.port)) as sock:
        send_json(sock, req)
        resp = recv_json(sock)

    out = json.dumps(resp, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    print(out)

if __name__ == "__main__":
    main()
