# Tests de Aceptación

Este directorio contiene los tests de aceptación automatizados para el sistema IS2 TPFI.

## Estructura de Tests

Los tests están organizados en los siguientes archivos:

- **`test_happy_path.py`**: Tests de camino feliz para cada acción (get, set, list, subscribe)
  - Verifica que las acciones funcionen correctamente
  - Valida el impacto en `CorporateData` y `CorporateLog`
  
- **`test_malformed_arguments.py`**: Tests de argumentos malformados
  - Servidor con puerto malformado
  - Cliente singleton con archivo/argumentos inválidos
  - Cliente observer con argumentos inválidos
  
- **`test_missing_data.py`**: Tests de requerimientos sin datos mínimos
  - GET sin ID
  - SET sin ID o sin DATA
  - Acciones sin UUID
  - UUID inválido
  - Acción inválida
  
- **`test_server_down.py`**: Tests de manejo cuando el servidor está caído
  - Cliente singleton con servidor caído
  - Cliente observer con servidor caído
  - Manejo de timeouts
  
- **`test_server_double_start.py`**: Test de intento de levantar el servidor dos veces
  - Mismo puerto (debe fallar o manejar conflicto)
  - Puertos diferentes (debe funcionar)

## Requisitos

- Python 3.10+
- pytest (incluido en `requirements.txt`)
- Variable de entorno `MOCK_DB=1` (configurada automáticamente en los tests)

## Ejecución

### Ejecutar todos los tests

```bash
pytest tests/ -v
```

### Ejecutar un archivo de tests específico

```bash
pytest tests/test_happy_path.py -v
```

### Ejecutar un test específico

```bash
pytest tests/test_happy_path.py::TestHappyPath::test_set_action_happy_path -v
```

### Ejecutar con más detalle

```bash
pytest tests/ -v -s
```

### Ejecutar con cobertura (opcional)

```bash
pytest tests/ --cov=. --cov-report=html
```

## Casos de Prueba Cubiertos

### 1. Camino Feliz
- ✅ SET: Crea/actualiza datos en `CorporateData` y registra en `CorporateLog`
- ✅ GET: Lee datos de `CorporateData` y registra en `CorporateLog` con el ID solicitado
- ✅ LIST: Lista todos los datos y registra en `CorporateLog`
- ✅ SUBSCRIBE: Registra suscripción en `CorporateLog` y recibe notificaciones

### 2. Argumentos Malformados
- ✅ Servidor con puerto inválido/negativo
- ✅ Cliente singleton con archivo inexistente
- ✅ Cliente singleton con JSON inválido
- ✅ Cliente singleton sin argumentos requeridos
- ✅ Cliente singleton con puerto/host inválidos
- ✅ Cliente observer con argumentos inválidos

### 3. Datos Mínimos Faltantes
- ✅ GET sin ID
- ✅ SET sin ID
- ✅ SET sin DATA
- ✅ Acciones sin UUID
- ✅ UUID en formato inválido
- ✅ Acción inválida

### 4. Servidor Caído
- ✅ Cliente singleton maneja conexión rechazada
- ✅ Cliente singleton maneja timeout
- ✅ Cliente observer reintenta automáticamente

### 5. Servidor Dos Veces
- ✅ Intentar iniciar servidor dos veces en el mismo puerto
- ✅ Iniciar servidores en puertos diferentes (debe funcionar)

## Verificación de Tablas

Todos los tests verifican el impacto correcto en las tablas:

- **CorporateData**: Se verifica que los datos se crean, actualizan y leen correctamente
- **CorporateLog**: Se verifica que todas las acciones se registran con:
  - UUID del cliente
  - Session ID
  - Action (get/set/list/subscribe)
  - Timestamp (ts)
  - ID (para GET, cuando corresponde)

## Ver Datos Generados por los Tests

Los tests limpian los archivos JSON antes y después de cada ejecución, por lo que normalmente están vacíos. Para ver los datos generados:

### Opción 1: Script de Visualización (Recomendado)

Ejecuta el script en otra terminal mientras los tests se ejecutan:

```bash
# Ver datos actuales
python tests/view_test_data.py

# Modo watch (actualiza automáticamente cada segundo)
python tests/view_test_data.py --watch
```

### Opción 2: Desactivar Limpieza Temporalmente

Si quieres que los datos persistan después de los tests, puedes comentar temporalmente la limpieza en `conftest.py`:

```python
@pytest.fixture(scope="function")
def clean_mock_db():
    """Fixture que limpia la BD antes y después de cada test."""
    cleanup_mock_db()
    yield
    # cleanup_mock_db()  # Comentar esta línea para no limpiar después
```

**Nota:** Recuerda descomentar la línea después de ver los datos para que los tests funcionen correctamente.

### Opción 3: Ver Durante la Ejecución

Los archivos se llenan durante la ejecución de cada test. Puedes:

1. Ejecutar un test específico y rápido
2. Mientras se ejecuta, en otra terminal ejecutar: `python tests/view_test_data.py`
3. O usar el modo watch: `python tests/view_test_data.py --watch`

### Opción 4: Agregar Print en los Tests

Puedes agregar temporalmente un print al final de un test para ver los datos:

```python
def test_set_action_happy_path(self, server_process):
    # ... código del test ...
    
    # Al final, ver los datos
    data = read_corporate_data()
    log = read_corporate_log()
    print(f"\nCorporateData: {json.dumps(data, indent=2)}")
    print(f"\nCorporateLog: {json.dumps(log, indent=2)}")
```

## Notas

- Los tests usan `MOCK_DB=1` para usar archivos JSON locales en lugar de AWS DynamoDB
- Cada test limpia la BD antes y después de ejecutarse (por defecto)
- Los tests usan puertos dinámicos para evitar conflictos
- El servidor se inicia y detiene automáticamente para cada test


