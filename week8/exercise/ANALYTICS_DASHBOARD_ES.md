# Panel de Análisis — Notas de Implementación

Capa de visualización añadida sobre el framework de agentes existente **"The Price is Right"**.
Introduce una pestaña dedicada `📊 Analytics` con cinco gráficos interactivos de Plotly,
un panel de resumen de KPIs y un gráfico de historial de precios inline dentro de la pestaña
del Rastreador de Productos.

---

## Tabla de Contenidos

1. [Resumen general](#1-resumen-general)
2. [Decisión tecnológica](#2-decisión-tecnológica)
3. [Archivos modificados](#3-archivos-modificados)
   - [Nuevo: `charts.py`](#31-nuevo-chartspy)
   - [Modificado: `price_is_right_final.py`](#32-modificado-price_is_right_finalpy)
4. [Referencia de gráficos](#4-referencia-de-gráficos)
   - [Distribución de precios](#41-distribución-de-precios)
   - [Tendencias de descuento](#42-tendencias-de-descuento)
   - [Radar de calidad de oferta](#43-radar-de-calidad-de-oferta)
   - [Ahorros a lo largo del tiempo](#44-ahorros-a-lo-largo-del-tiempo)
   - [Desglose por categoría](#45-desglose-por-categoría)
   - [Historial de precios (Rastreador de Productos)](#46-historial-de-precios-rastreador-de-productos)
5. [Tarjetas KPI de resumen](#5-tarjetas-kpi-de-resumen)
6. [Tema visual](#6-tema-visual)
7. [Flujo de datos](#7-flujo-de-datos)
8. [Manejo del estado vacío](#8-manejo-del-estado-vacío)
9. [Diseño de la interfaz](#9-diseño-de-la-interfaz)
10. [Limitaciones conocidas y trabajo futuro](#10-limitaciones-conocidas-y-trabajo-futuro)

---

## 1. Resumen general

La capa de análisis lee la misma `List[Opportunity]` en memoria que ya produce el
cazador de ofertas — sin nuevas fuentes de datos, sin cambios en la base de datos,
sin llamadas adicionales a la API. Los cinco gráficos se regeneran bajo demanda cuando
el usuario hace clic en **🔄 Actualizar Panel** o cuando Gradio carga la pestaña por
primera vez.

```
memory.json  ──►  DealAgentFramework.memory  ──►  funciones de charts.py  ──►  gr.Plot
                                                         │
tracked_products.json  ──►  tracked_products[]  ──►  price_history_chart()
```

---

## 2. Decisión tecnológica

| Opción | Veredicto | Razón |
|---|---|---|
| **Plotly** (`plotly.graph_objects`) | ✅ **Elegido** | Ya es una dependencia del proyecto; `gr.Plot` renderiza figuras de Plotly de forma nativa con interactividad completa (zoom, desplazamiento, tooltips al pasar el ratón) |
| **Plotly Dash** | ❌ Rechazado | Requiere un servidor WSGI separado; no puede incrustarse dentro de una app Gradio en ejecución sin hacks complejos con IFrame |
| **Altair** | ❌ Rechazado | Produce especificaciones Vega-Lite que Gradio solo puede renderizar como imágenes SVG estáticas, perdiendo toda la interactividad |
| **Matplotlib / Seaborn** | ❌ Rechazado | Imágenes estáticas, sin hover, pobre compatibilidad con modo oscuro |

**Conclusión:** Plotly ofrece la misma capacidad expresiva que Dash o Altair con cero
infraestructura adicional, que es la compensación adecuada para un prototipo alojado en Gradio.

---

## 3. Archivos modificados

### 3.1 Nuevo: `charts.py`

Un módulo autocontenido que expone una función por gráfico. Todas las funciones comparten
una capa auxiliar de tema oscuro común y manejan el caso de datos vacíos de forma elegante
(sin fallos; en su lugar se muestra un mensaje de marcador de posición amigable).

#### Estructura del módulo

```
charts.py
│
├── Constantes de tema          BG, CARD_BG, GRID, TEXT, PRIMARY, ACCENT, ...
├── Auxiliares de categoría     DEALNEWS_MAP, CATEGORY_PALETTE, infer_category()
├── Auxiliares de diseño        _base(), _xaxis(), _yaxis(), _legend()
├── Auxiliar de estado vacío    _empty(title, message)
├── Auxiliar de normalización   _normalise(values) → [0, 1]
│
├── price_distribution()        Gráfico 1 — Histograma superpuesto
├── discount_trends()           Gráfico 2 — Dispersión + líneas por categoría
├── deal_quality_radar()        Gráfico 3 — Gráfico de radar polar
├── savings_over_time()         Gráfico 4 — Área + barras de doble eje
├── category_breakdown()        Gráfico 5 — Gráfico de rosca
├── price_history_chart()       Gráfico 6 — Gráfico de líneas (Rastreador de Productos)
└── summary_stats_html()        Tarjetas KPI como cadena HTML
```

#### ¿Por qué un módulo separado?

`price_is_right_final.py` ya gestiona el estado de sesión, el threading, el cableado de
eventos y el registro. Mezclar 300 líneas de código de gráficos en él lo haría imposible
de mantener. `charts.py` puede importarse, probarse e iterarse de forma independiente —
llamar a `charts.price_distribution(memory)` en un REPL o notebook produce la misma
figura que renderiza la interfaz.

---

### 3.2 Modificado: `price_is_right_final.py`

Se realizaron tres cambios:

#### a) Nueva importación

```python
import charts as ch
```

#### b) Interfaz reestructurada de 2 a 3 pestañas

```
Antes                       Después
──────────────────          ─────────────────────────────────
🔍 Deal Hunter              🔍 Deal Hunter   (sin cambios)
🎯 Product Tracker          📊 Analytics     (nueva)
                            🎯 Product Tracker + gráfico de historial de precios (mejorado)
```

#### c) Pestaña Analytics — cableado de eventos Gradio

```python
def load_analytics():
    mem = self.get_agent_framework().memory
    return (
        ch.summary_stats_html(mem),     # gr.HTML  — Tarjetas KPI
        ch.price_distribution(mem),     # gr.Plot
        ch.category_breakdown(mem),     # gr.Plot
        ch.discount_trends(mem),        # gr.Plot
        ch.savings_over_time(mem),      # gr.Plot
        ch.deal_quality_radar(mem),     # gr.Plot
    )

ui.load(load_analytics, outputs=analytics_outputs)           # al cargar la página
refresh_analytics_btn.click(load_analytics, outputs=...)     # al hacer clic en el botón
```

#### d) Rastreador de Productos — gráfico de historial de precios al seleccionar fila

```python
def on_row_select(evt: gr.SelectData):
    row = evt.index[0]
    product = fw.tracked_products[row]
    return row, ch.price_history_chart(product)

tracked_table.select(on_row_select, outputs=[selected_tracker_row, chart_price_history])
```

Al hacer clic en cualquier fila de la tabla del rastreador se renderiza ahora el historial
de precios completo de ese producto directamente debajo de la tabla — sin recarga de página.

---

## 4. Referencia de gráficos

### 4.1 Distribución de precios

**Tipo:** Histograma superpuesto (`barmode="overlay"`)  
**Datos:** `deal.price` (rojo) vs `estimate` (verde azulado) para todas las ofertas en memoria  
**Información:** Cuánto por debajo del precio justo estimado por el modelo están las ofertas.
Si el pico de color verde azulado (estimación) se sitúa a la derecha del pico rojo (precio), el
agente encuentra ofertas consistentemente por debajo del mercado.

Elementos adicionales:
- Líneas verticales discontinuas en la mediana de cada distribución
- Anotadas con `"Precio mediano $X"` / `"Est. mediana $X"`

```python
fig.add_vline(x=np.median(prices), line_dash="dash", ...)
fig.add_vline(x=np.median(estimates), line_dash="dash", ...)
```

---

### 4.2 Tendencias de descuento

**Tipo:** Dispersión + líneas conectoras discontinuas  
**Datos:** `discount` por oferta, coloreado por categoría de feed RSS, ordenado por índice de oferta  
**Información:** Si la calidad de la oferta (tamaño del descuento) mejora o se deteriora con
el tiempo, y qué categorías tienen el mejor rendimiento.

La categoría se infiere de la ruta de URL de DealNews:

```python
DEALNEWS_MAP = {
    "c142": "Electrónica",    # /c142/ en la URL
    "c39":  "Informática",
    "c238": "Automoción",
    "f1912":"Hogar inteligente",
    "c196": "Hogar y jardín",
}
```

Una línea de referencia horizontal en `$50` marca el `PlanningAgent.DEAL_THRESHOLD`
existente, para que los usuarios puedan confirmar visualmente qué ofertas habrían
generado una notificación.

---

### 4.3 Radar de calidad de oferta

**Tipo:** `go.Scatterpolar` con `fill="toself"`  
**Datos:** Cuatro dimensiones de calidad normalizadas, dos trazas  
**Información:** Comparación de calidad multidimensional entre el promedio de la cartera
y la mejor oferta encontrada.

#### Dimensiones

| Dimensión | Cálculo | Interpretación |
|---|---|---|
| **Asequibilidad** | `1 − normalise(price)` | Precio más bajo → puntuación más alta |
| **Descuento $** | `normalise(discount)` | Mayor descuento → puntuación más alta |
| **Ratio de valor** | `normalise(estimate / price)` | Más infravalorado → puntuación más alta |
| **Calidad de descripción** | `normalise(len(description))` | Descripción más larga → proxy de información de producto más rica |

Todas las puntuaciones se normalizan min-max a `[0, 1]` a lo largo del conjunto completo de ofertas:

```python
def _normalise(values):
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]
```

Se dibujan dos trazas:
- **Rojo** — Promedio de la cartera (puntuación media de todas las ofertas)
- **Verde azulado** — Mejor oferta (la oferta con mayor descuento)

Requiere al menos **2 ofertas** en memoria; de lo contrario se muestra un marcador de posición
de estado vacío.

---

### 4.4 Ahorros a lo largo del tiempo

**Tipo:** Gráfico de doble eje (`plotly.subplots.make_subplots(secondary_y=True)`)  
**Datos:** Ahorros acumulados (eje Y izquierdo, área verde azulada) + descuento por oferta (eje Y derecho, barras rojas)  
**Información:** Tanto la tasa de acumulación de ahorros como la distribución de los valores
individuales de las ofertas.

```
Eje Y izquierdo  → total acumulado ahorrado ($)   — área rellena verde azulada
Eje Y derecho    → descuento individual por oferta ($) — barras rojas semitransparentes
```

Solo los descuentos no negativos contribuyen al total acumulado (`max(discount, 0)`)
para evitar que la curva baje cuando se encuentra una oferta con descuento negativo
(es decir, el artículo en realidad cuesta más de lo que el modelo estimó).

---

### 4.5 Desglose por categoría

**Tipo:** Gráfico de rosca (`go.Pie` con `hole=0.42`)  
**Datos:** Recuento de ofertas por categoría RSS  
**Información:** En qué categorías de productos se centra más el escáner.

Decisiones de diseño:
- **Estilo de rosca** — la anotación central muestra el recuento total de ofertas
- **Separación** — la categoría superior está ligeramente separada hacia afuera (`pull=0.08`)
  para llamar la atención sobre la categoría dominante
- **Paleta de colores por categoría** — consistente con los colores usados en las
  Tendencias de Descuento y el gráfico de dispersión 3D del almacén vectorial

---

### 4.6 Historial de precios (Rastreador de Productos)

**Tipo:** Gráfico de líneas relleno  
**Datos:** `TrackedProduct.price_history` — lista de dicts `{"timestamp", "price"}`  
**Disparador:** Se renderiza cuando el usuario hace clic en una fila de la tabla del Rastreador de Productos  

Elementos adicionales:
- **Precio objetivo** — línea discontinua amarilla horizontal (solo si se ha establecido `target_price`)
- **Anotaciones de mín. / máx.** — flechas apuntando a los precios más bajos y más altos registrados
  para que el usuario pueda ver el rango completo de un vistazo

```python
if tracked_product.target_price:
    fig.add_hline(y=tracked_product.target_price, line_dash="dash", ...)

# Anotar mínimo y máximo
fig.add_annotation(x=min_x, y=min_y, text=f"Mín. ${min_y:.2f}", ...)
fig.add_annotation(x=max_x, y=max_y, text=f"Máx. ${max_y:.2f}", ...)
```

---

## 5. Tarjetas KPI de resumen

`summary_stats_html()` devuelve una cadena HTML de flex-box con seis tarjetas de métricas:

| Tarjeta | Valor |
|---|---|
| 🏆 Total de ofertas | `len(memory)` |
| 💰 Ahorros totales | `sum(max(discount, 0))` |
| 📊 Descuento promedio | `total_savings / len(memory)` |
| 🚀 Mejor descuento | `max(o.discount for o in memory)` |
| 🏷️ Precio promedio de oferta | `mean(o.deal.price)` |
| 📦 Categoría principal | Moda de las categorías inferidas |

Las tarjetas se renderizan como `gr.HTML` (no `gr.Dataframe`) porque necesitan
estilos personalizados — color, tipografía, emojis, diseño flex responsivo — que
un Dataframe no soporta.

---

## 6. Tema visual

Todos los gráficos comparten un tema oscuro común definido por constantes al inicio
de `charts.py`:

```python
BG      = "#1a1a2e"   # Fondo de página / papel
CARD_BG = "#16213e"   # Fondo interior del gráfico
GRID    = "#2a2a4a"   # Líneas de cuadrícula y bordes
TEXT    = "#eaeaea"   # Todas las etiquetas de ejes y anotaciones
PRIMARY = "#e94560"   # Rojo — ofertas, precios, "malo" (caro)
ACCENT  = "#4ECDC4"   # Verde azulado — estimaciones, ahorros, "bueno" (barato)
FONT    = "Inter, system-ui, sans-serif"
```

El auxiliar `_base()` aplica estos valores a cada gráfico para que sean visualmente
consistentes con el panel de registro existente (`background-color: #222229`) y el
gráfico de dispersión 3D del almacén vectorial que ya está presente en la pestaña
Deal Hunter.

---

## 7. Flujo de datos

```
                         ┌────────────────────────────────────────┐
                         │              charts.py                  │
                         │                                        │
memory (List[Opp])  ───► │  price_distribution()  → go.Figure    │
                         │  discount_trends()      → go.Figure    │
                         │  deal_quality_radar()   → go.Figure    │
                         │  savings_over_time()    → go.Figure    │
                         │  category_breakdown()   → go.Figure    │
                         │  summary_stats_html()   → str (HTML)   │
                         │                                        │
tracked_products    ───► │  price_history_chart()  → go.Figure    │
                         └────────────────────────────────────────┘
                                         │
                                         ▼
                              Componentes gr.Plot / gr.HTML
                              (Gradio renderiza Plotly de forma nativa)
```

No se producen llamadas de red, inferencia de modelos ni E/S de disco durante la
generación de gráficos — es puramente una transformación de datos ya presentes en RAM.

---

## 8. Manejo del estado vacío

Cada función de gráfico comprueba si hay datos suficientes antes de intentar renderizar:

```python
# Ejemplo de price_distribution()
if not memory:
    return _empty("💰 Distribución de precios")

# Ejemplo de deal_quality_radar()
if len(memory) < 2:
    return _empty("🎯 Radar de calidad de oferta", "Se necesitan al menos 2 ofertas para dibujar el radar")
```

`_empty()` devuelve un `go.Figure` en blanco con un mensaje de anotación centrado,
que coincide con el tema oscuro. Esto previene excepciones `ZeroDivisionError`,
`IndexError` y `ValueError` que bloquearían el manejador de eventos de Gradio y
mostrarían un traceback de Python sin formato al usuario.

---

## 9. Diseño de la interfaz

```
📊 Pestaña Analytics
│
├── [ 🔄 Actualizar Panel ]  botón
│
├── Tarjetas KPI (fila HTML flex)
│     🏆 Ofertas | 💰 Ahorros | 📊 Desc. Prom. | 🚀 Mejor | 🏷️ Precio Prom. | 📦 Cat. Principal
│
├── Fila 1  ┌──────────────────────┐  ┌──────────────────────┐
│           │ Distribución precios │  │ Desglose por cat.    │
│           │ (Histograma)         │  │ (Rosca)              │
│           └──────────────────────┘  └──────────────────────┘
│
├── Fila 2  ┌──────────────────────┐  ┌──────────────────────┐
│           │ Tendencias descuento │  │ Ahorros con el tiempo│
│           │ (Dispersión por cat.)│  │ (Área + Barras)      │
│           └──────────────────────┘  └──────────────────────┘
│
└── Fila 3  ┌──────────────────────┐  ┌──────────────────────┐
            │ Radar calidad oferta │  │ Cómo leerlo (guía)   │
            │ (Polar)              │  │ (Markdown)           │
            └──────────────────────┘  └──────────────────────┘

🎯 Pestaña Rastreador de Productos (mejorada)
│
├── [igual que antes — formulario de añadir, tabla, actualizar, eliminar]
│
└── Gráfico de historial de precios  ← aparece al hacer clic en una fila
      (Línea + línea objetivo + anotaciones mín./máx.)
```

---

## 10. Limitaciones conocidas y trabajo futuro

| Limitación | Impacto | Solución sugerida |
|---|---|---|
| Sin marcas de tiempo en los objetos `Opportunity` | El eje X muestra el índice de la oferta, no fecha/hora | Añadir el campo `timestamp: Optional[str]` a `Opportunity`; establecerlo en `DealAgentFramework.run()` |
| Categoría inferida de la URL de DealNews | Se rompe si cambian las URLs del feed; siempre "Otro" para fuentes que no son DealNews | Almacenar la categoría en el modelo `Deal`; rellenarlo en la respuesta de `ScannerAgent` |
| Dimensión "Calidad de descripción" de `deal_quality_radar` | Descripción más larga ≠ necesariamente mejor oferta | Usar una puntuación de calidad de LLM o atributos estructurados del producto |
| Sin actualizaciones de gráficos en tiempo real durante una búsqueda | Los gráficos solo se actualizan tras completar la ejecución | Transmitir resultados parciales en un `gr.State` y actualizar los gráficos de forma incremental |
| Las figuras de Plotly no son responsivas en pantallas pequeñas | El diseño puede desbordarse en ventanas gráficas estrechas | Usar `autosize=True` y márgenes basados en porcentaje |

---

*Documento escrito el 2026-02-25 — The Price is Right · week8/exercise*
