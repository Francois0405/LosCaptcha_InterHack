# Damm Smart Truck - InterHack BCN 2026

MVP desarrollado para **INTERHACK BCN 2026**. El proyecto convierte datos operativos de reparto en una experiencia web para planificar rutas, explicar decisiones logísticas y validar la distribución de carga de un camión Damm.

Repositorio: https://github.com/itsCarlosDev/interhack-2026

## Equipo

- Carlos Morales Artés
- Franço¡s Liraud Mathieu
- Ghazal Khitou Khitou 
- Silvia Monfort Moya
- Erik Andres Villca Tunari

## Problema

La operativa de reparto combina datos de pedidos, clientes, horarios, direcciones, productos y capacidad del camión. Si la ruta y la carga se planifican por separado, aparecen fricciones operativas:

- Paradas fuera de secuencia o mal agrupadas.
- Descarga lenta porque los productos no están en la zona adecuada del camión.
- Retornables sin espacio reservado.
- Poca trazabilidad para explicar por qué una ruta o una carga es mejor que otra.

## Solución

La aplicación propone una ruta optimizada y una distribución de carga coordinada con esa ruta.

Incluye:

- Dashboard operativo con KPIs de clientes, paradas, ocupación y retornables.
- Mapa Leaflet con ruta por carretera, paradas numeradas, salida y regreso al almacén.
- Optimización de secuencia con OR-Tools, usando fallback heurístico si no está disponible.
- Cálculo de tiempos/distancias con OSRM y fallback por distancia Haversine.
- Pantalla de carga del camión con zonas P1-P6, validación visual y drag & drop.
- Chat operativo con Gemini para explicar ruta, carga, riesgos y retornables.

## Tecnologías

- Python 3
- Django 5
- django-mongodb-backend
- MongoDB
- PyMongo
- OR-Tools
- Pandas
- Bootstrap
- Leaflet
- OpenStreetMap / OSRM
- Gemini API

## Estructura

```txt
LosCaptcha_InterHack/
├── config/                         # Configuración Django
├── damm/
│   ├── mapa.py                     # Modelo de ruta, OR-Tools, OSRM y formato frontend
│   ├── views.py                    # Vistas, APIs y contexto de pantallas
│   ├── urls.py                     # Rutas de la app
│   └── models.py                   # Modelos base Django
├── mongo_migrations/               # Migraciones para backend MongoDB
├── scripts/
│   └── csv_to_json.py              # Conversión de CSV a JSON
├── static/
│   ├── assets/                     # JSON de datos operativos
│   ├── csv/                        # CSV originales
│   ├── css/styles.css              # Estilos de la aplicación
│   ├── img/                        # Imágenes y logos
│   ├── js/main.js                  # Interacción frontend, mapa, carga y chat
│   └── vendor/bootstrap/           # Bootstrap local
├── templates/
│   ├── dashboard.html              # Panel principal
│   ├── mapa.html                   # Ruta optimizada
│   ├── distribucion.html           # Carga del camión
│   └── index.html
├── manage.py
├── requirements.txt
└── README.md
```

## Configuración

Crear un archivo `.env` en `LosCaptcha_InterHack/`:

```env
SECRET_KEY=dev-secret-key
DEBUG=True
MONGODB_URI=mongodb+srv://usuario:password@cluster/db
MONGODB_NAME=BD_DAMM
GEMINI_API_KEY=tu_api_key_opcional
GEMINI_MODEL=gemini-2.5-flash
ROUTE_DEMO_LIMIT=5
```

Notas:

- `MONGODB_URI` y `MONGODB_NAME` son necesarios para Django.
- `GEMINI_API_KEY` solo es necesario para que el chat responda con Gemini.
- `ROUTE_DEMO_LIMIT` limita el número de clientes usados en la demo de ruta.

## Instalación

Desde la raíz del repositorio:

```bash
cd LosCaptcha_InterHack
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si `pip` no interpreta correctamente `requirements.txt`, conviértelo a UTF-8 o instala las dependencias principales:

```bash
python -m pip install Django django-mongodb-backend pymongo dnspython python-dotenv ortools pandas
```

## Datos

La aplicación espera colecciones MongoDB con los nombres usados por el backend:

- `horarios_entrega.json`
- `cabecera_transporte.json`
- `detalle_entrega.json`
- `direcciones.json`
- `materiales_zubic.json`
- `zm040.json`
- `zonas.json`

Los JSON de referencia están en `static/assets/`. Si partes de los CSV, usa:

```bash
python scripts/csv_to_json.py
```

Después importa los JSON en MongoDB manteniendo el mismo nombre de colección. Ejemplo:

```bash
mongoimport --uri "$MONGODB_URI" --db "$MONGODB_NAME" --collection direcciones.json --file static/assets/direcciones.json --jsonArray
```

## Ejecución

```bash
python manage.py runserver
```

Abrir:

- http://127.0.0.1:8000/dashboard
- http://127.0.0.1:8000/mapa
- http://127.0.0.1:8000/distribucion

## APIs

- `GET /api/dashboard/`: KPIs y resumen operativo.
- `GET /api/route/`: datos de ruta, paradas, almacén y regreso.
- `GET /api/load-plan/`: distribución de carga por zonas del camión.
- `POST /api/gemini-chat/`: preguntas al asistente operativo.

Payload básico para Gemini:

```json
{
  "question": "Explícame por qué esta ruta es mejor",
  "context": {}
}
```

## Funcionamiento de la ruta

El flujo principal está en `damm/mapa.py`:

1. Lee pedidos, direcciones y horarios desde MongoDB.
2. Geocodifica o usa coordenadas disponibles.
3. Construye una matriz de tiempos con OSRM.
4. Resuelve la secuencia con OR-Tools.
5. Si OR-Tools u OSRM fallan, usa fallback heurístico.
6. Devuelve un JSON preparado para `templates/mapa.html` y `static/js/main.js`.

El mapa pinta:

- Almacén de salida.
- Paradas numeradas.
- Línea de ruta por carretera.
- Regreso al almacén para descarga de retornables.

## Distribución de carga

La pantalla `/distribucion` divide el camión en zonas:

- `P1 / P2`: primeras paradas y productos prioritarios.
- `P3`: ruta media.
- `P4`: referencias agrupadas.
- `P5`: reserva de retornables.
- `P6`: últimas paradas.

El usuario puede mover paquetes entre zonas. La interfaz recalcula avisos y score operativo según accesibilidad, equilibrio, ocupación y retornables.

## Limitaciones del MVP

- La geocodificación externa depende de Nominatim.
- OSRM público puede limitar o rechazar peticiones.
- El algoritmo usa un límite de clientes para demo mediante `ROUTE_DEMO_LIMIT`.
- Las métricas de impacto están orientadas a demostración y explicabilidad.
- `DEBUG=True` está pensado solo para desarrollo.
