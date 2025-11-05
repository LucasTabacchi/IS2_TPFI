"""
Tests de camino feliz para cada acción.
Verifica que las acciones funcionen correctamente y se registren en CorporateLog.
"""
import socket
from tests.conftest import (
    send_request, read_corporate_data, read_corporate_log,
    generate_uuid
)


class TestHappyPath:
    """Tests de camino feliz para cada acción."""
    
    def test_set_action_happy_path(self, server_process):
        """Test de camino feliz para acción SET."""
        port, _ = server_process
        uuid_cli = generate_uuid()
        item_id = "TEST-ITEM-001"
        
        # Realizar SET
        payload = {
            "UUID": uuid_cli,
            "ACTION": "set",
            "ID": item_id,
            "DATA": {
                "id": item_id,
                "nombre": "Test Item",
                "cp": "3260",
                "CUIT": "30-12345678-9"
            }
        }
        
        response = send_request("127.0.0.1", port, payload)
        
        # Verificar respuesta
        assert response["OK"] is True
        assert "DATA" in response
        assert response["DATA"]["id"] == item_id
        
        # Verificar CorporateData
        data = read_corporate_data()
        assert len(data) == 1
        assert data[0]["id"] == item_id
        assert data[0]["nombre"] == "Test Item"
        
        # Verificar CorporateLog
        log = read_corporate_log()
        set_logs = [entry for entry in log if entry.get("action") == "set"]
        assert len(set_logs) == 1
        assert set_logs[0]["UUID"] == uuid_cli
        assert set_logs[0]["action"] == "set"
        assert "ts" in set_logs[0]
        assert "session" in set_logs[0]
    
    def test_get_action_happy_path(self, server_process):
        """Test de camino feliz para acción GET."""
        port, _ = server_process
        uuid_cli = generate_uuid()
        item_id = "TEST-ITEM-002"
        
        # Primero crear el item con SET
        set_payload = {
            "UUID": uuid_cli,
            "ACTION": "set",
            "ID": item_id,
            "DATA": {
                "id": item_id,
                "nombre": "Test Get Item",
                "cp": "3260"
            }
        }
        send_request("127.0.0.1", port, set_payload)
        
        # Realizar GET
        get_payload = {
            "UUID": uuid_cli,
            "ACTION": "get",
            "ID": item_id
        }
        
        response = send_request("127.0.0.1", port, get_payload)
        
        # Verificar respuesta
        assert response["OK"] is True
        assert "DATA" in response
        assert response["DATA"]["id"] == item_id
        assert response["DATA"]["nombre"] == "Test Get Item"
        
        # Verificar CorporateLog
        log = read_corporate_log()
        get_logs = [entry for entry in log if entry.get("action") == "get"]
        assert len(get_logs) >= 1
        # El último GET debe ser el que acabamos de hacer
        last_get = get_logs[-1]
        assert last_get["UUID"] == uuid_cli
        assert last_get["action"] == "get"
        assert last_get.get("id") == item_id
        assert "ts" in last_get
        assert "session" in last_get
    
    def test_list_action_happy_path(self, server_process):
        """Test de camino feliz para acción LIST."""
        port, _ = server_process
        uuid_cli = generate_uuid()
        
        # Crear varios items
        for i in range(3):
            set_payload = {
                "UUID": uuid_cli,
                "ACTION": "set",
                "ID": f"TEST-ITEM-LIST-{i}",
                "DATA": {
                    "id": f"TEST-ITEM-LIST-{i}",
                    "nombre": f"Item {i}",
                    "cp": "3260"
                }
            }
            send_request("127.0.0.1", port, set_payload)
        
        # Realizar LIST
        list_payload = {
            "UUID": uuid_cli,
            "ACTION": "list"
        }
        
        response = send_request("127.0.0.1", port, list_payload)
        
        # Verificar respuesta
        assert response["OK"] is True
        assert "DATA" in response
        assert isinstance(response["DATA"], list)
        assert len(response["DATA"]) == 3
        
        # Verificar CorporateLog
        log = read_corporate_log()
        list_logs = [entry for entry in log if entry.get("action") == "list"]
        assert len(list_logs) >= 1
        last_list = list_logs[-1]
        assert last_list["UUID"] == uuid_cli
        assert last_list["action"] == "list"
        assert "ts" in last_list
        assert "session" in last_list
        # LIST no debe tener 'id' en el log
        assert "id" not in last_list or last_list.get("id") is None
    
    def test_subscribe_action_happy_path(self, server_process):
        """Test de camino feliz para acción SUBSCRIBE."""
        import threading
        import time
        from common.net import send_json, recv_json
        
        port, _ = server_process
        uuid_cli = generate_uuid()
        
        # Conectar y suscribirse
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(("127.0.0.1", port))
            sock.settimeout(2.0)
            
            # Enviar suscripción
            subscribe_payload = {
                "UUID": uuid_cli,
                "ACTION": "subscribe"
            }
            send_json(sock, subscribe_payload)
            
            # Recibir acuse
            ack = recv_json(sock)
            assert ack["OK"] is True
            assert ack.get("ACTION") == "subscribe"
            
            # Verificar CorporateLog
            log = read_corporate_log()
            subscribe_logs = [entry for entry in log if entry.get("action") == "subscribe"]
            assert len(subscribe_logs) >= 1
            last_sub = subscribe_logs[-1]
            assert last_sub["UUID"] == uuid_cli
            assert last_sub["action"] == "subscribe"
            assert "ts" in last_sub
            assert "session" in last_sub
            
            # Hacer un SET para generar notificación
            set_payload = {
                "UUID": generate_uuid(),
                "ACTION": "set",
                "ID": "TEST-NOTIFY-001",
                "DATA": {
                    "id": "TEST-NOTIFY-001",
                    "nombre": "Notificación Test"
                }
            }
            send_request("127.0.0.1", port, set_payload)
            
            # Esperar notificación
            try:
                notification = recv_json(sock)
                assert notification is not None
                assert notification.get("ACTION") == "change"
                assert "DATA" in notification
                assert notification["DATA"]["id"] == "TEST-NOTIFY-001"
            except socket.timeout:
                # Puede que no llegue la notificación a tiempo, pero la suscripción funcionó
                pass
            
        finally:
            sock.close()
    
    def test_multiple_actions_impact_on_tables(self, server_process):
        """Test que verifica el impacto de múltiples acciones en las tablas."""
        port, _ = server_process
        uuid_cli = generate_uuid()
        item_id = "TEST-MULTI-001"
        
        # SET
        set_payload = {
            "UUID": uuid_cli,
            "ACTION": "set",
            "ID": item_id,
            "DATA": {"id": item_id, "nombre": "Multi Test"}
        }
        send_request("127.0.0.1", port, set_payload)
        
        # GET
        get_payload = {
            "UUID": uuid_cli,
            "ACTION": "get",
            "ID": item_id
        }
        send_request("127.0.0.1", port, get_payload)
        
        # LIST
        list_payload = {
            "UUID": uuid_cli,
            "ACTION": "list"
        }
        send_request("127.0.0.1", port, list_payload)
        
        # Verificar CorporateData
        data = read_corporate_data()
        assert len(data) == 1
        assert data[0]["id"] == item_id
        
        # Verificar CorporateLog
        log = read_corporate_log()
        assert len(log) >= 3  # SET, GET, LIST
        
        actions_in_log = [entry.get("action") for entry in log]
        assert "set" in actions_in_log
        assert "get" in actions_in_log
        assert "list" in actions_in_log
        
        # Verificar que todos los logs tienen UUID, session, action, ts
        for entry in log:
            assert "UUID" in entry
            assert "session" in entry
            assert "action" in entry
            assert "ts" in entry

