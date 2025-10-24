import argparse, json, socket, time, uuid, sys, re
from common.logging_setup import setup
from common.net import send_json, recv_json

UUID_RE = re.compile(r"^[0-9a-f]{12}$")

def run_once(server, port, out_path, uuid_str, log):
    with socket.create_connection((server, port)) as sock:
        req = {"UUID": uuid_str, "ACTION": "subscribe"}
        send_json(sock, req)

        # primer acuse
        first = recv_json(sock)
        if not first or not isinstance(first, dict) or not first.get("OK", False):
            s = json.dumps(first, ensure_ascii=False)
            log.error("Fallo en suscripción. Respuesta: %s", s)
            return

        s = json.dumps(first, ensure_ascii=False)
        log.info("Suscripto: %s", s)

        # escuchar notificaciones hasta que el socket se cierre
        while True:
            msg = recv_json(sock)
            if msg is None:
                # socket cerrado por el servidor
                return
            line = json.dumps(msg, ensure_ascii=False)
            if out_path:
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            print(line)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--server", default="127.0.0.1", help="hostname del servidor")
    ap.add_argument("-p", "--port", type=int, default=8080, help="puerto del servidor")
    ap.add_argument("-o", "--output", help="archivo de salida (append)")
    ap.add_argument("-r", "--retry", type=int, default=30, help="segundos entre reintentos")
    ap.add_argument("--uuid", help="(opcional) UUID/node id en hex (12 dígitos) para pruebas")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    log = setup(args.verbose)

    # Determinar y validar UUID
    if args.uuid:
        uuid_str = str(args.uuid).strip().lower()
    else:
        uuid_str = format(uuid.getnode(), "012x")

    if not UUID_RE.fullmatch(uuid_str):
        log.error("UUID inválido: debe ser 12 hex (ej: 'a1b2c3d4e5f6'). Valor: %r", uuid_str)
        sys.exit(2)

    # Loop de reconexión
    try:
        while True:
            try:
                run_once(args.server, args.port, args.output, uuid_str, log)
                # si run_once retorna, fue cierre remoto → reintentar
                log.warning("Conexión cerrada. Reintentando en %ss...", args.retry)
                time.sleep(args.retry)
            except (ConnectionRefusedError, OSError) as e:
                log.warning("No conecta (%s). Reintentando en %ss...", e, args.retry)
                time.sleep(args.retry)
    except KeyboardInterrupt:
        log.info("Interrumpido por el usuario.")

if __name__ == "__main__":
    main()
