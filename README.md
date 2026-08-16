# NutriMenú · Protein Food — Chatbot RAG con Ollama + Flask

Proyecto completo para ejecutar un chatbot local de recomendación del menú de **Protein Food** usando Python, Ollama, RAG híbrido, Flask y memoria persistente por sala de chat.

> **Identidad fija del asistente:** Clara pertenece a **Protein Food**, un restaurante de comida deliciosa —postres, desayunos, almuerzos, cenas, snacks y bebidas— con opciones orientadas a ayudar a las personas a comer rico con menos calorías.

## Qué incluye

- **RAG local con Ollama**: `gemma3:4b` para respuesta y `embeddinggemma:300m` para embeddings.
- **Base de conocimiento estructurada** con 59 productos.
- **RAG híbrido**: búsqueda densa (embeddings) + BM25 + Reciprocal Rank Fusion.
- **Filtros determinísticos** antes de mostrar productos: kcal, dulce/salado, tipo de consumo, proteína, precio e ingredientes a evitar.
- **Memoria por `room_id`** en SQLite: cada sala conserva mensajes y contexto propio aunque reinicies Flask.
- **Interfaz Flask responsive** inspirada en la imagen de referencia incluida en `static/img/referencia_interfaz.png`.
- **Tarjetas de productos** con precio, rango de kcal estimadas, nivel proteico, alertas e imagen PNG.
- **59 nombres PNG dentro del RAG** (`imagen_png`) y 59 archivos placeholder con esos nombres en `static/products/`.
- **Notebook principal** para preparar y ejecutar el proyecto: `notebooks/00_NutriMenu_RAG_Ollama.ipynb`.
- Los notebooks originales que compartiste quedan en `notebooks/referencia_curso/`.

## Importante sobre las imágenes

No se proporcionaron las fotografías reales de los 59 productos. Para que la aplicación funcione desde el primer momento, el ZIP incluye **placeholders PNG** con exactamente los nombres que aparecen en el RAG.

Cuando tengas las fotos reales, solo reemplaza los archivos de `static/products/` **sin cambiar su nombre**. No tienes que modificar Python, el Excel ni el frontend.

Ejemplo:

```text
static/products/prod_001_proteincookie_vainilla_y_chip.png
```

Ese mismo nombre aparece en:

- `data/catalogo_rag.json`
- `data/rag_chunks.json`
- `data/base_conocimiento_rag_menu.xlsx`

## 1. Requisitos

- Python 3.10+ (recomendado 3.11 o 3.12)
- Ollama instalado y ejecutándose
- Aproximadamente 6 GB o más disponibles para los modelos y entorno

Modelos configurados por defecto:

```bash
ollama pull gemma3:4b
ollama pull embeddinggemma:300m
```

Puedes cambiarlos en `.env`.

## 2. Instalación rápida en Windows

1. Abre la carpeta del proyecto.
2. Verifica que Ollama esté abierto.
3. Ejecuta:

```text
setup_windows.bat
```

Ese script crea `.venv`, instala dependencias, descarga los modelos faltantes y construye el índice RAG.

Después ejecuta:

```text
run_windows.bat
```

Abre:

```text
http://127.0.0.1:5000
```

## 3. Instalación manual

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instala:

```bash
pip install -r requirements.txt
```

Crea configuración:

```bash
# Windows
copy .env.example .env

# Linux/macOS
cp .env.example .env
```

Prepara el índice:

```bash
python scripts/bootstrap.py --pull
```

Inicia Flask:

```bash
python app.py
```

## 4. Ejecutarlo desde el notebook

Abre:

```text
notebooks/00_NutriMenu_RAG_Ollama.ipynb
```

Ejecuta las celdas de arriba hacia abajo. El notebook:

1. instala librerías;
2. verifica Ollama;
3. revisa los 59 productos e imágenes;
4. construye el índice LanceDB;
5. prueba la memoria por sala;
6. realiza una consulta RAG de prueba;
7. inicia Flask.

## 5. Arquitectura

```text
Usuario / navegador
        │
        ▼
     Flask API
        │
        ├──────────────► SQLite
        │                 ├─ chat_rooms
        │                 ├─ messages
        │                 └─ room_state
        │
        ▼
 Parser de requisitos
 kcal · sabor · tipo · proteína · precio · exclusiones
        │
        ├──────────────► Filtro determinístico del catálogo
        │
        ▼
 Recuperación híbrida
        ├─ Ollama Embeddings + LanceDB
        ├─ BM25
        └─ Reciprocal Rank Fusion
        │
        ▼
 Contexto + historial de room_id
        │
        ▼
 Ollama / Gemma 3 4B
        │
        ▼
 Respuesta + hasta 3 productos estructurados
        │
        ▼
 Tarjetas HTML con imagen PNG
```

## 6. Por qué no es un RAG “solo vectorial”

Para una recomendación con límites numéricos, dejar toda la decisión al LLM es riesgoso. Este proyecto separa responsabilidades:

- El **RAG** encuentra contexto semántico y reglas relevantes.
- El **código Python** aplica restricciones verificables como `kcal_max_est <= presupuesto` en modo estricto.
- El **LLM** redacta y explica, pero las tarjetas solo pueden usar productos ya seleccionados por código.

Así se reduce el riesgo de que el modelo invente un precio, un rango de kcal o una imagen.

## 7. Memoria por sala de chat

Cada conversación recibe un UUID, por ejemplo:

```text
7a644bf8-88f7-4a25-b6c7-1d67dfad13e7
```

SQLite guarda por ese `room_id`:

- historial usuario/asistente;
- presupuesto de kcal para la comida;
- meta diaria si fue indicada;
- modo estricto o “alrededor de”;
- dulce/salado;
- comida/postre/bebida;
- prioridad de proteína;
- precio máximo;
- ingredientes a evitar.

Por eso en una sala puede ocurrir:

```text
Usuario: Tengo 500 kcal para almorzar y quiero proteína.
Usuario: ¿Y algo más barato?
```

La segunda pregunta conserva el contexto de las 500 kcal, el almuerzo y la prioridad de proteína de **esa misma sala**. Otra sala tiene un estado independiente.

La base se crea en:

```text
storage/chats.db
```

## 8. Reglas de calorías y seguridad implementadas

- Los valores de kcal son **estimados**, no oficiales.
- En límite estricto se intenta cumplir usando `kcal_max_est`.
- “Alrededor de X kcal” permite comparar por `kcal_ref_est`, advirtiendo que el rango puede cruzar X.
- Si el usuario solo dice “consumo 1800 kcal al día”, NutriMenú pregunta cuánto quiere reservar para esa comida.
- No se garantiza ausencia de alérgenos ni contaminación cruzada.
- Una condición médica o dieta clínica no se trata como prescripción nutricional.

## 9. Archivos principales

```text
app.py                         Flask + API
config.py                      configuración y prompt del sistema
rag/engine.py                  RAG híbrido + Ollama
rag/filters.py                 extracción de requisitos y filtros
rag/ingest.py                  creación del índice LanceDB
rag/memory.py                  SQLite por room_id

data/base_conocimiento_rag_menu.xlsx
data/catalogo_rag.json
data/rag_chunks.json
data/reglas_chatbot.json

static/products/*.png          imágenes por nombre RAG
templates/index.html           interfaz
static/css/style.css
static/js/app.js
```

## 10. Endpoints Flask

| Método | Ruta | Función |
|---|---|---|
| GET | `/` | interfaz web |
| GET | `/api/health` | estado de Ollama/modelos |
| GET | `/api/rooms` | listar salas |
| POST | `/api/rooms` | crear sala |
| DELETE | `/api/rooms/<id>` | eliminar sala |
| POST | `/api/rooms/<id>/reset` | borrar contexto de esa sala |
| GET | `/api/rooms/<id>/messages` | recuperar historial |
| POST | `/api/chat` | enviar mensaje al RAG |

Ejemplo:

```json
{
  "room_id": "uuid-de-la-sala",
  "message": "Tengo 500 kcal para almorzar y quiero algo salado y proteico"
}
```

## 11. Pruebas

Prueba de integridad del catálogo e imágenes:

```bash
python tests/smoke_data.py
```

Pruebas de filtros:

```bash
pytest -q
```

Estas pruebas no necesitan llamar al LLM.

## 12. Cambiar el modelo de Ollama

Edita `.env`:

```env
OLLAMA_LLM_MODEL=gemma3:4b
OLLAMA_EMBED_MODEL=embeddinggemma:300m
```

Si cambias embeddings, reconstruye el índice:

```bash
python scripts/bootstrap.py
```

## 13. Limitación de la base actual

La base no contiene macronutrientes oficiales ni gramajes completos para todos los productos. Por eso el sistema **no debe convertir estas estimaciones en una dieta clínica** ni afirmar valores exactos. Si Protein Food entrega fichas técnicas reales, la estructura está preparada para reemplazar las estimaciones.
