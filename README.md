# IS2 TPFI – Proxy / Singleton / Observer (Python)

Este proyecto implementa los tres ejecutables requeridos:

- `clients/singletonclient.py`
- `clients/observerclient.py`
- `server/singletonproxyobserver.py`

cumpliendo con **Proxy**, **Singleton** (acceso a tablas `CorporateData` y `CorporateLog`) y **Observer** (subscripciones con notificaciones).

## Requisitos

- Python 3.10+
- `pytest` (incluido en `requirements.txt`) para ejecutar tests
- (Opcional) `boto3` si utilizarás AWS DynamoDB real
- Variables de entorno AWS estándar (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`) solo si usas DynamoDB

## Modo de Almacenamiento

El proyecto soporta dos modos de almacenamiento:

### Modo Mock (por defecto para desarrollo y tests)

- **Archivos JSON locales** en `mock_db/`
- No requiere AWS ni credenciales
- Configurar: `MOCK_DB=1` (o dejar sin configurar si `boto3` no está instalado)
- Usado automáticamente en tests

### Modo DynamoDB (producción)

- **Tablas AWS DynamoDB** (`CorporateData` y `CorporateLog`)
- Requiere credenciales AWS configuradas
- No configurar `MOCK_DB` (o configurarlo como `null`/`0`)
- Requiere que `boto3` esté instalado

> Para ejecutar sin AWS, puedes usar el modo **mock** exportando `MOCK_DB=1`. En ese modo se persiste en `mock_db/*.json`.

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

### Servidor

**Con Mock DB (sin AWS):**
```bash
# Linux/Mac
export MOCK_DB=1
python server/singletonproxyobserver.py -p 8080 -v

# Windows PowerShell
$env:MOCK_DB="1"
python server/singletonproxyobserver.py -p 8080 -v

# Windows CMD
set MOCK_DB=1
python server/singletonproxyobserver.py -p 8080 -v
```

**Con DynamoDB (producción):**
```bash
# Configurar credenciales AWS primero
export AWS_ACCESS_KEY_ID="tu-access-key"
export AWS_SECRET_ACCESS_KEY="tu-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Asegurar que MOCK_DB NO esté configurado
unset MOCK_DB  # Linux/Mac
# $env:MOCK_DB=$null  # Windows PowerShell

python server/singletonproxyobserver.py -p 8080 -v
```

### Cliente (get/set/list)
```bash
python clients/singletonclient.py -i input.json -o output.json -s 127.0.0.1 -p 8080 -v
```

Ejemplos de `input.json`:
```json
{ "UUID":"<uuid4>", "ACTION":"get", "ID":"UADER-FCyT-IS2" }
```
```json
{ "UUID":"<uuid4>", "ACTION":"list" }
```
```json
{
  "UUID":"<uuid4>",
  "ACTION":"set",
  "DATA": {
    "id": "UADER-FCyT-IS2",
    "cp": "3260",
    "CUIT": "30-70925411-8",
    "domicilio": "25 de Mayo 385-1P",
    "idreq": "473",
    "idSeq": "1146",
    "localidad": "Concepción del Uruguay",
    "provincia": "Entre Rios",
    "sede": "FCyT",
    "seqID": "23",
    "telefono": "03442 43-1442",
    "web": "http://www.uader.edu.ar"
  }
}
```

### Observer
```bash
python clients/observerclient.py -s 127.0.0.1 -p 8080 -o observer_out.json -v
```

## Framing del protocolo
Mensajes **JSON** con *prefijo de longitud* de 4 bytes **big‑endian** para evitar pegado/fragmentación de tramas.

## Tests

El proyecto incluye tests automatizados que verifican que las acciones impacten correctamente en las tablas `CorporateData` y `CorporateLog`.

### Ejecutar todos los tests

```bash
pytest tests/ -v
```

### Ejecutar un archivo de tests específico

```bash
pytest tests/test_happy_path.py -v
pytest tests/test_malformed_arguments.py -v
```

### Ejecutar un test específico

```bash
pytest tests/test_happy_path.py::TestHappyPath::test_set_action_happy_path -v
```

### Tests disponibles

- **`test_happy_path.py`**: Tests de camino feliz (SET, GET, LIST, SUBSCRIBE)
- **`test_malformed_arguments.py`**: Tests de argumentos malformados
- **`test_missing_data.py`**: Tests de datos faltantes
- **`test_server_down.py`**: Tests de manejo cuando el servidor está caído
- **`test_server_double_start.py`**: Test de inicio múltiple del servidor

> Los tests usan automáticamente `MOCK_DB=1` y limpian las tablas antes y después de cada test.

Para más detalles, ver `tests/README.md`.

## Visualización de Logs

### Ver logs en Mock DB (archivos JSON)

```bash
python view_logs.py
```

Muestra los logs almacenados en `mock_db/corporate_log.json`.

### Ver logs en DynamoDB

```bash
# Ver los últimos 20 logs
python view_logs_dynamodb.py

# Ver los últimos N logs
python view_logs_dynamodb.py 10
```

Requiere credenciales AWS configuradas.

### Ver datos generados por los tests

Los tests limpian los archivos JSON después de ejecutarse. Para ver los datos generados durante los tests:

```bash
# Ver datos actuales
python tests/view_test_data.py

# Modo watch (actualiza automáticamente cada segundo)
python tests/view_test_data.py --watch
```

Ejecuta el script en otra terminal mientras los tests se ejecutan, o usa el modo watch para ver los datos en tiempo real.

> **Nota:** Los tests limpian los archivos antes y después de cada ejecución, por lo que normalmente están vacíos. Para más opciones, ver `tests/README.md`.

## CI/CD

El proyecto incluye CI/CD con GitHub Actions que ejecuta los tests automáticamente en cada push y pull request.

- **Workflow**: `.github/workflows/ci.yml`
- **Versiones de Python**: 3.10, 3.11, 3.12, 3.13
- **Ejecuta**: Todos los tests con `MOCK_DB=1`

El estado de los tests se muestra en la pestaña **Actions** del repositorio en GitHub.

## Estructura del Proyecto

```
is2_tpfi_python/
├── clients/                    # Clientes del sistema
│   ├── singletonclient.py     # CLI para get/set/list
│   └── observerclient.py      # CLI para subscribe
├── server/                     # Servidor
│   ├── singletonproxyobserver.py  # Servidor TCP (proxy) + Singletons + Observer
│   └── observer.py            # Registro de subscriptores (Observer pattern)
├── storage/                    # Capa de almacenamiento
│   └── adapter.py             # Singleton para CorporateData y CorporateLog
├── common/                     # Utilidades compartidas
│   ├── net.py                 # send/recv con longitud 4 bytes big endian
│   └── logging_setup.py       # Configuración de logging
├── tests/                      # Tests automatizados
│   ├── test_happy_path.py     # Tests de camino feliz
│   ├── test_malformed_arguments.py  # Tests de argumentos inválidos
│   ├── test_missing_data.py   # Tests de datos faltantes
│   ├── test_server_down.py    # Tests de servidor caído
│   ├── test_server_double_start.py  # Tests de inicio múltiple
│   ├── conftest.py            # Configuración de tests (fixtures)
│   └── README.md              # Documentación de tests
├── mock_db/                    # Base de datos mock (archivos JSON)
│   ├── corporate_data.json    # Datos corporativos (modo mock)
│   └── corporate_log.json     # Logs de acciones (modo mock)
├── samples/                    # Ejemplos de requests
│   ├── set.json               # Ejemplo de SET
│   ├── get.json               # Ejemplo de GET
│   └── list.json              # Ejemplo de LIST
├── .github/workflows/          # CI/CD
│   └── ci.yml                 # Workflow de GitHub Actions
├── view_logs.py               # Script para ver logs (mock)
├── view_logs_dynamodb.py      # Script para ver logs (DynamoDB)
├── requirements.txt            # Dependencias del proyecto
└── README.md                   # Este archivo
```

## Componentes Principales

- **`common/net.py`**: Envío/recepción de mensajes JSON con prefijo de longitud 4 bytes big endian.
- **`common/logging_setup.py`**: Configuración de logging con flag `-v`.
- **`storage/adapter.py`**: Singleton para `CorporateData` y `CorporateLog` con backend AWS DynamoDB o mock JSON.
- **`server/observer.py`**: Registro de subscriptores (patrón Observer).
- **`server/singletonproxyobserver.py`**: Servidor TCP (proxy) + uso de Singletons + Observer.
- **`clients/singletonclient.py`**: CLI para acciones get/set/list.
- **`clients/observerclient.py`**: CLI para suscribirse a notificaciones.
- **`samples/*.json`**: Ejemplos de requests JSON para cada acción.

## Verificación de Impacto en Tablas

Todos los tests verifican que las acciones impacten correctamente en las tablas:

- **CorporateData**: Se verifica que los datos se crean, actualizan y leen correctamente
- **CorporateLog**: Se verifica que todas las acciones se registran con:
  - UUID del cliente
  - Session ID
  - Action (get/set/list/subscribe)
  - Timestamp (ts)
  - ID (para GET, cuando corresponde)

## Notas Adicionales

- Los tests usan `MOCK_DB=1` automáticamente para no requerir AWS
- Cada test limpia las tablas antes y después de ejecutarse
- El servidor usa Singletons que se inicializan una vez al arrancar
- Para cambiar entre mock y DynamoDB, reinicia el servidor con la configuración correcta
