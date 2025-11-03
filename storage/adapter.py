import os, json, threading, time
from typing import Any, Dict, List, Optional
try:
    import boto3  # type: ignore
except Exception:  # boto3 opcional
    boto3 = None

# Normalizar Decimals de DynamoDB -> tipos nativos
try:
    from decimal import Decimal
except Exception:
    Decimal = None  # fallback

_MOCK = os.getenv("MOCK_DB") == "1"


def _to_native(obj):
    """
    Convierte recursivamente:
      - Decimal -> int si es entero, sino float
      - list/dict -> procesa elementos
      - otros tipos -> igual
    """
    if Decimal is not None and isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, list):
        return [_to_native(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    return obj


class _Singleton(type):
    _instances = {}
    _lock = threading.Lock()
    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


# ========================= CorporateData =========================

class CorporateData(metaclass=_Singleton):
    def __init__(self):
        if _MOCK or boto3 is None:
            self.path = os.path.join(os.path.dirname(__file__), "..", "mock_db", "corporate_data.json")
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if not os.path.exists(self.path):
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump([], f)
            self.backend = "mock"
        else:
            self.dynamodb = boto3.resource("dynamodb")
            self.table = self.dynamodb.Table("CorporateData")
            self.backend = "aws"

    def get(self, id_: str) -> Optional[Dict[str, Any]]:
        if self.backend == "mock":
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                if item.get("id") == id_:
                    return item
            return None
        resp = self.table.get_item(Key={"id": id_})
        item = resp.get("Item")
        return _to_native(item) if item is not None else None

    def list_all(self) -> List[Dict[str, Any]]:
        if self.backend == "mock":
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        items: List[Dict[str, Any]] = []
        scan_kwargs: Dict[str, Any] = {}
        while True:
            resp = self.table.scan(**scan_kwargs)
            items.extend(resp.get("Items", []))
            if "LastEvaluatedKey" in resp:
                scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
            else:
                break
        return _to_native(items)

    def upsert(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if self.backend == "mock":
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = None
            for i, it in enumerate(data):
                if it.get("id") == item.get("id"):
                    existing = i
                    break
            if existing is None:
                data.append(item)
            else:
                data[existing].update(item)
                item = data[existing]
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return item

        # AWS: merge parcial
        existing = self.get(item["id"])
        if existing:
            merged = dict(existing)
            merged.update(item)
            self.table.put_item(Item=merged)
            return merged
        else:
            self.table.put_item(Item=item)
            return item


# ========================= CorporateLog =========================

class CorporateLog(metaclass=_Singleton):
    def __init__(self):
        if _MOCK or boto3 is None:
            self.path = os.path.join(os.path.dirname(__file__), "..", "mock_db", "corporate_log.json")
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if not os.path.exists(self.path):
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump([], f)
            self.backend = "mock"
            self._hash_key_cache: Optional[str] = None
        else:
            self.dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("CORPORATELOG_TABLE", "CorporateLog")
            self.table = self.dynamodb.Table(table_name)
            self.backend = "aws"
            # cachear el nombre de la hash key (o permitir forzarlo por env)
            self._hash_key_cache: Optional[str] = os.getenv("CORPORATELOG_HASH_KEY")
            if not self._hash_key_cache:
                try:
                    self.table.load()  # un DescribeTable al arranque
                    for k in self.table.key_schema:
                        if k.get("KeyType") == "HASH":
                            self._hash_key_cache = k.get("AttributeName")
                            break
                except Exception:
                    self._hash_key_cache = None

    def _aws_hash_key_name(self) -> Optional[str]:
        return self._hash_key_cache

    # ---------- subscribe usa append_exact ----------
    def append_exact(self, record: Dict[str, Any]) -> None:
        item = dict(record)
        # Consigna mínima
        for k in ("UUID", "session", "action", "ts"):
            if k not in item:
                raise ValueError(f"CorporateLog.append_exact: falta '{k}'")

        if self.backend == "mock":
            # En mock: no guardamos 'id' para subscribe
            item.pop("id", None)
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.append(item)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return

        # AWS: si la tabla exige PK, poner una PK técnica estable para subscribe
        hash_key = (self._aws_hash_key_name() or "id")
        item[hash_key] = f"{item['UUID']}#subscribe#{item['session']}"
        if hash_key != "id":
            item.pop("id", None)
        self.table.put_item(Item=item)

    # ---------- get/list/set usan append ----------
    def append(self, record: Dict[str, Any]) -> None:
        """
        - GET  : conserva 'id' (ID solicitado).
        - SET/LIST/SUBSCRIBE: no registran 'id' de negocio.
            * mock: no hay 'id'
            * aws : si la tabla exige PK, se completa con PK técnica (UUID#accion#ts)
        """
        item = dict(record)
        item["ts"] = item.get("ts") or int(time.time() * 1000)

        # limpiar bandera interna
        item.pop("_no_id", None)

        action = (item.get("action") or "").lower()
        is_get = (action == "get")
        is_set = (action == "set")
        is_list = (action == "list")
        is_subscribe = (action == "subscribe")

        if self.backend == "mock":
            # MOCK:
            # - GET: si vino 'id', se deja; no generamos uno si no vino.
            # - SET/LIST/SUBSCRIBE: no guardamos 'id'.
            if not is_get:
                item.pop("id", None)
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.append(item)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return

        # AWS:
        hash_key = (self._aws_hash_key_name() or "id")
        if is_get:
            # GET: PK puede ser el id solicitado; si faltara, usa ts
            item.setdefault(hash_key, str(item.get("id", item["ts"])))
        elif is_set or is_list or is_subscribe:
            # SET/LIST/SUBSCRIBE: PK técnica (no es id de negocio)
            item.pop(hash_key, None)
            item[hash_key] = f"{item.get('UUID','unknown')}#{action}#{item['ts']}"
            if hash_key != "id":
                item.pop("id", None)
        else:
            # Fallback
            item.setdefault(hash_key, str(item.get("id", item["ts"])))

        self.table.put_item(Item=item)
