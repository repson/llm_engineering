# Rastreador de Productos — Notas de Implementación

Añadido sobre el framework existente de búsqueda de ofertas **"The Price is Right"**.  
Esta funcionalidad permite a los usuarios añadir manualmente URLs de productos de Amazon
y recibir alertas cuando el precio baja o alcanza un valor objetivo.

---

## Tabla de Contenidos

1. [Resumen general](#1-resumen-general)
2. [Arquitectura](#2-arquitectura)
3. [Archivos modificados](#3-archivos-modificados)
   - [Nuevo: `agents/product_tracker_agent.py`](#31-nuevo-agentsproduct_tracker_agentpy)
   - [Modificado: `agents/deals.py`](#32-modificado-agentsdealpyy)
   - [Modificado: `deal_agent_framework.py`](#33-modificado-deal_agent_frameworkpy)
   - [Modificado: `price_is_right_final.py`](#34-modificado-price_is_right_finalpy)
4. [Modelo de datos](#4-modelo-de-datos)
5. [Condiciones de alerta](#5-condiciones-de-alerta)
6. [Estrategia de scraping en Amazon](#6-estrategia-de-scraping-en-amazon)
7. [Persistencia](#7-persistencia)
8. [Uso](#8-uso)
9. [Limitaciones conocidas](#9-limitaciones-conocidas)

---

## 1. Resumen general

El **Rastreador de Productos** es una nueva funcionalidad que coexiste con el cazador
de ofertas autónomo. Mientras que el cazador de ofertas *descubre* ofertas aleatorias
de feeds RSS, el rastreador permite al usuario *elegir* productos específicos y
seguir sus precios a lo largo del tiempo.

**Flujo de trabajo:**

```
El usuario introduce una URL de Amazon
        │
        ▼
ProductTrackerAgent extrae datos de la página (título, precio, disponibilidad, imagen)
        │
        ▼
TrackedProduct guardado en tracked_products.json
        │
        ▼
Cada vez que se ejecuta "Comprobar precios ahora" (o en ejecución programada futura)
        │
        ├─▶ ¿Precio ≤ precio objetivo?            → 🎯 Alerta
        ├─▶ ¿Precio bajó ≥ X% desde el inicio?    → 📉 Alerta
        └─▶ ¿Palabras clave de bajo stock?         → ⚠️  Alerta
                │
                ▼
        Alertas mostradas en la UI + notificación push de Pushover
```

---

## 2. Arquitectura

La nueva funcionalidad sigue el mismo **patrón de agentes** ya utilizado en el proyecto:
una subclase `Agent` dedicada gestiona toda la E/S externa (scraping HTTP), mientras que
`DealAgentFramework` gestiona el ciclo de vida de los datos (persistencia, CRUD, programación).

```
DealAgentFramework
    ├── PlanningAgent          (existente — cazador de ofertas RSS)
    └── ProductTrackerAgent    (nuevo — monitor de precios de Amazon)
            └── requests + BeautifulSoup  (scraping HTML)
```

La interfaz de Gradio se divide en dos pestañas para que ambas funcionalidades sean
accesibles de forma independiente sin interferencias.

---

## 3. Archivos modificados

### 3.1 Nuevo: `agents/product_tracker_agent.py`

Una nueva subclase `Agent` responsable de todo el scraping de Amazon y la lógica de alertas.

#### Decisiones clave de diseño

| Decisión | Justificación |
|---|---|
| Múltiples selectores CSS de precio con cadena de respaldo | Amazon realiza pruebas A/B de su diseño de página con frecuencia; un único selector falla de forma silenciosa |
| Reutilización de `requests.Session` | Mantiene las conexiones TCP activas entre múltiples comprobaciones de productos, reduciendo la latencia |
| Retraso cortés de 1,5 s entre solicitudes | Evita activar los límites de velocidad de detección de bots de Amazon |
| Lógica de alertas separada en `_check_alerts()` | Facilita las pruebas unitarias sin necesidad de una llamada HTTP real |

#### Cadena de selectores de precio

```python
PRICE_SELECTORS = [
    ("span", {"id": "priceblock_ourprice"}),    # diseño clásico
    ("span", {"id": "priceblock_dealprice"}),   # precio de oferta
    ("span", {"id": "priceblock_saleprice"}),   # precio de venta
    ("span", {"class": "a-price-whole"}),       # diseño moderno (parte entera)
    ("span", {"class": "a-offscreen"}),         # precio accesible para lector de pantalla
]
```

Si ninguno de estos coincide, un respaldo final lee el par `a-price-whole` +
`a-price-fraction`.

#### API pública

```python
# Comprobar un único producto, devuelve (producto_actualizado, alertas)
agent.check_product(product: TrackedProduct) -> Tuple[TrackedProduct, List[str]]

# Comprobar todos los productos de una lista
agent.check_all(products: List[TrackedProduct]) -> Tuple[List[TrackedProduct], List[str]]
```

---

### 3.2 Modificado: `agents/deals.py`

Se añadió el modelo Pydantic `TrackedProduct` y se actualizó la importación de `Optional`.

#### Nuevo modelo

```python
class TrackedProduct(BaseModel):
    url: str
    title: str = "Pendiente..."
    image_url: Optional[str] = None
    current_price: Optional[float] = None
    target_price: Optional[float] = None
    alert_threshold_pct: float = 10.0   # % de bajada desde el precio inicial para activar una alerta
    price_history: List[Dict] = []      # [{"timestamp": "ISO-str", "price": float}, ...]
    last_checked: Optional[str] = None
    added_at: str = ""
    scrape_error: Optional[str] = None  # Último error de ProductTrackerAgent, si existe
```

`price_history` es una lista ordenada (la más antigua primero). El precio inicial
registrado en el momento de `add_tracked_product()` es siempre `price_history[0]`,
que es la línea base para las alertas de caída porcentual.

---

### 3.3 Modificado: `deal_agent_framework.py`

Tres grupos de cambios:

#### a) Nuevas importaciones y variables de instancia

```python
from datetime import datetime
from agents.deals import Opportunity, TrackedProduct   # TrackedProduct añadido

# En __init__:
self.tracker = None                                    # inicialización perezosa
self.tracked_products = self.read_tracked_products()  # cargado al inicio
```

#### b) Inicialización del rastreador (perezosa)

`ProductTrackerAgent` solo se instancia en el primer uso — patrón idéntico al de
`PlanningAgent` — de modo que la biblioteca de scraping no se carga a menos que
se use la pestaña.

```python
def init_tracker_as_needed(self):
    if not self.tracker:
        from agents.product_tracker_agent import ProductTrackerAgent
        self.tracker = ProductTrackerAgent()
```

#### c) Nuevos métodos públicos

| Método | Propósito |
|---|---|
| `read_tracked_products()` | Deserializar `tracked_products.json` en `List[TrackedProduct]` |
| `write_tracked_products()` | Serializar la lista actual de nuevo a JSON |
| `add_tracked_product(url, target_price, alert_threshold_pct)` | Crear un `TrackedProduct`, realizar un scraping inicial, persistir |
| `remove_tracked_product(url)` | Filtrar el producto por URL y persistir |
| `check_tracked_products()` | Refrescar todos los productos, persistir, disparar alertas de Pushover |
| `get_tracker_table()` | Devolver una lista de listas lista para el `Dataframe` de Gradio |

##### Disposición de columnas de `get_tracker_table()`

```
[Título del producto (60 caracteres), Precio actual, Precio objetivo, Alerta %, Resumen de historial de precios, Última comprobación, Estado de scraping, URL]
```

La celda **Historial de precios** muestra `↓$MÍN ↑$MÁX (N lecturas)` para que el
usuario pueda ver el rango de precios de un vistazo sin expandir la fila.

---

### 3.4 Modificado: `price_is_right_final.py`

El diseño de página única de Gradio se reorganizó en una **interfaz con pestañas**:

```
gr.Tabs()
  ├── 🔍 Deal Hunter    (todo el contenido original, comportamiento sin cambios)
  └── 🎯 Product Tracker  (nuevo)
```

#### Diseño de la pestaña Rastreador de Productos

```
┌─────────────────────────────────────────────────────────────┐
│ Campo URL de Amazon │ Precio objetivo ($) │ Deslizad. Alerta % │ ➕ Rastrear│
├─────────────────────────────────────────────────────────────┤
│ Mensaje de estado (✅ Añadido / ⚠️ Advertencia / ❌ Error)  │
├─────────────────────────────────────────────────────────────┤
│ Tabla de productos rastreados (8 columnas)                  │
│  • Producto | $ Actual | $ Objetivo | Alerta % |            │
│    Historial | Última comprob. | Estado | URL               │
├─────────────────────────────────────────────────────────────┤
│ [ 🔄 Comprobar precios ahora ]  [ 🗑️ Eliminar seleccionado ]│
├─────────────────────────────────────────────────────────────┤
│ Panel de alertas (cuadros resaltados en rojo, uno por alerta)│
└─────────────────────────────────────────────────────────────┘
```

#### Cableado de eventos de Gradio

| Evento | Manejador | Salidas |
|---|---|---|
| `add_btn.click` | `add_product()` | tabla, markdown de estado |
| `refresh_btn.click` | `check_prices()` | tabla, HTML de alertas |
| `tracked_table.select` | `on_row_select()` | índice de fila seleccionada (State) |
| `remove_btn.click` | `remove_product()` | tabla, limpiar State de selección |
| `ui.load` | `load_tracker_table()` | tabla (rellenar en el primer renderizado) |

---

## 4. Modelo de datos

### Referencia de campos de `TrackedProduct`

| Campo | Tipo | Descripción |
|---|---|---|
| `url` | `str` | URL del producto de Amazon (clave primaria para la eliminación) |
| `title` | `str` | Título del producto (extraído de `#productTitle`) |
| `image_url` | `Optional[str]` | URL de la imagen del producto |
| `current_price` | `Optional[float]` | Precio extraído más recientemente |
| `target_price` | `Optional[float]` | Precio objetivo definido por el usuario; activa la alerta 🎯 |
| `alert_threshold_pct` | `float` | % de bajada desde el precio inicial para activar la alerta 📉 |
| `price_history` | `List[Dict]` | `[{"timestamp": str, "price": float}]` lista ordenada |
| `last_checked` | `Optional[str]` | Marca de tiempo ISO de la última comprobación exitosa |
| `added_at` | `str` | Marca de tiempo ISO cuando el usuario añadió el producto |
| `scrape_error` | `Optional[str]` | Último mensaje de error de scraping, `None` si está bien |

### Ejemplo de `tracked_products.json`

```json
[
  {
    "url": "https://www.amazon.com/dp/B09XY123AB",
    "title": "Sony WH-1000XM5 Auriculares inalámbricos con cancelación de ruido",
    "image_url": "https://m.media-amazon.com/images/I/...",
    "current_price": 279.99,
    "target_price": 250.00,
    "alert_threshold_pct": 10.0,
    "price_history": [
      {"timestamp": "2026-02-25T21:55:00", "price": 299.99},
      {"timestamp": "2026-02-26T21:55:00", "price": 279.99}
    ],
    "last_checked": "2026-02-26T21:55:00",
    "added_at": "2026-02-25T21:55:00",
    "scrape_error": null
  }
]
```

---

## 5. Condiciones de alerta

Se evalúan tres condiciones independientes en cada comprobación:

### 🎯 Precio objetivo alcanzado

```python
if product.target_price and current_price <= product.target_price:
    # Disparar alerta
```

Se activa cuando el precio extraído es igual o inferior al precio objetivo del usuario.

### 📉 Caída porcentual

```python
initial_price = product.price_history[0]["price"]
drop_pct = (initial_price - current_price) / initial_price * 100
if drop_pct >= product.alert_threshold_pct:
    # Disparar alerta
```

La línea base es siempre el **primer precio registrado** (cuando se añadió el producto),
no la comprobación anterior. Esto previene la "fatiga de alertas" por pequeñas oscilaciones.

### ⚠️ Stock limitado

```python
LOW_STOCK_KEYWORDS = [
    "only", "left in stock", "few left", "order soon",
    "limited availability", "1 left", "2 left", "3 left",
]
if any(kw in availability.lower() for kw in LOW_STOCK_KEYWORDS):
    # Disparar alerta
```

Extraído del div `#availability` en la página del producto de Amazon.

---

## 6. Estrategia de scraping en Amazon

Amazon bloquea activamente el tráfico automatizado. La implementación utiliza varias
mitigaciones:

| Mitigación | Implementación |
|---|---|
| Cabecera `User-Agent` realista | Cadena UA de Chrome en macOS |
| Cabeceras `Accept`, `Accept-Language`, `DNT` | Coinciden con el perfil de un navegador real |
| `requests.Session` | Grupo de conexiones persistente, parece más un navegador |
| Retraso de 1,5 s entre productos | `time.sleep(1.5)` en `check_all()` |
| Múltiples respaldos de selectores de precio | Manejo elegante de las pruebas A/B del diseño de Amazon |
| Protección frente a precio cero | `if price and price > 0` antes de registrar |

> **Nota:** Para scraping de alto volumen o fiable, debería usarse un servicio
> dedicado como la [API de Keepa](https://keepa.com/#!api) o
> [RainforestAPI](https://www.rainforestapi.com/).

---

## 7. Persistencia

| Archivo | Contenido | Cuándo se escribe |
|---|---|---|
| `memory.json` | Resultados del cazador de ofertas (existente) | Después de cada ejecución del cazador de ofertas |
| `tracked_products.json` | Todos los productos rastreados con historial de precios completo | Después de añadir, eliminar o comprobar |

Ambos archivos son JSON plano, legibles por humanos, y pueden editarse manualmente
o guardarse en control de versiones (excluyendo datos sensibles).

---

## 8. Uso

### Añadir un producto

1. Abre la pestaña **🎯 Rastreador de Productos**.
2. Pega una URL de producto de Amazon (p. ej. `https://www.amazon.com/dp/B09XY123AB`).
3. Opcionalmente, establece un **Precio objetivo** (el precio que estás dispuesto a pagar).
4. Ajusta el deslizador de **Alerta %** (predeterminado: 10 — alerta si el precio baja un 10% respecto a hoy).
5. Haz clic en **➕ Rastrear**.

El sistema realiza un scraping inmediato y muestra el título del producto y el precio
actual en la línea de estado.

### Comprobar precios manualmente

Haz clic en **🔄 Comprobar precios ahora**. Todos los productos rastreados se vuelven
a extraer de forma secuencial. Las alertas aparecen en el panel rojo debajo de la tabla
y también se envían como notificaciones push de Pushover (si está configurado).

### Eliminar un producto

Haz clic en cualquier fila de la tabla para seleccionarla (la fila se resalta) y,
a continuación, haz clic en **🗑️ Eliminar seleccionado**.

### Comprobaciones diarias automatizadas

El `gr.Timer` existente en la pestaña Deal Hunter se ejecuta cada 5 minutos. Para añadir
comprobaciones automáticas del rastreador, el evento `timer.tick` puede extenderse:

```python
# Ejemplo: comprobar tanto el cazador de ofertas como el rastreador cada 5 minutos
timer.tick(
    lambda ld: (*run_with_logging(ld), check_prices()),
    ...
)
```

---

## 9. Limitaciones conocidas

| Limitación | Impacto | Posible solución |
|---|---|---|
| Detección de bots de Amazon | El scraping puede fallar en algunas páginas | Usar Keepa / RainforestAPI |
| Sin renderizado de JavaScript | Los precios cargados por JS no serán visibles | Usar Playwright o Selenium |
| Moneda única (USD) | El análisis de precios asume el formato `$` | Extender `_parse_price()` |
| Sin comprobación de duplicados al añadir | La misma URL puede añadirse dos veces | Comprobar `url in [p.url for p in tracked_products]` antes de insertar |
| Alertas solo en "Comprobar ahora" manual | Sin programación real en segundo plano | Añadir APScheduler o extender WorkManager |

---

*Documento escrito el 2026-02-25 — The Price is Right · week8/exercise*
