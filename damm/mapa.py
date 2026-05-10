import math
import os
import time
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pymongo import MongoClient

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except Exception:
    ORTOOLS_AVAILABLE = False

try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8"]
except Exception:
    pass


TIEMPO_DESCARGA_PRODUCTO = 1
PENALIZACION_SALTAR_CLIENTE = 999999

CAPACIDAD_CAMION_3 = 60
CAPACIDAD_CAMION_6 = 110
CAPACIDAD_CAMION_8 = 140
CAPACIDAD_CAMION = CAPACIDAD_CAMION_6

MAX_CLIENTES_DEMO = int(os.getenv("ROUTE_DEMO_LIMIT", "5"))

COORDS_ALMACEN_LONLAT = [2.2173, 41.5367]

PEDIDOS_COLLECTIONS = [
    "detalles_entrega_nproductos",
    "detalle_entrega.json",
]

DIRECCIONES_COLLECTIONS = [
    "direcciones.json",
]

HORARIOS_COLLECTIONS = [
    "HorariosEntrega",
    "horarios_entrega.json",
]

BARES_DEMO = [
    "FRANKFURT LEO BOECK GRANOLLERS",
    "BAR LA PETRA II",
    "SUSHI HE GRANOLLERS",
    "IBERICUS CENTRAL",
    "CANTINA IES VIC ST TOMAS",
    "CAN BIN RESTAURANTE",
    "LA ROCA VILLAGE RTE PASARELA (GVC)",
    "KAPHIY BRUNCH",
    "BAR CRISTASOL",
    "PITAPES BERENGUER",
    "MARTU CITY",
    "CAFETERIA ATREZZO",
    "DATOTE AL BAGH",
]


def str_hora_a_minutos(hora_str):
    if not hora_str or not isinstance(hora_str, str):
        return None

    try:
        partes = hora_str.split(":")
        return int(partes[0]) * 60 + int(partes[1])
    except Exception:
        return None


def min_to_hora(minutos):
    minutos = int(minutos or 0)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def format_duration(minutes):
    minutes = int(minutes or 0)

    if minutes < 60:
        return f"{minutes} min"

    hours = minutes // 60
    mins = minutes % 60

    if mins == 0:
        return f"{hours}h"

    return f"{hours}h {mins}m"


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def get_collection(db, candidates):
    existing = set()

    try:
        existing = set(db.list_collection_names())
    except Exception:
        pass

    for name in candidates:
        if name in existing:
            return db[name]

    return db[candidates[0]]


def get_mongo_from_env():
    uri = os.getenv("MONGO_URI")

    if not uri:
        raise RuntimeError("MONGO_URI no configurada. Usa la conexión de Django o exporta MONGO_URI.")

    client = MongoClient(uri)
    return client["BD_DAMM"]


def get_json(url, headers=None, timeout=10):
    request = Request(url, headers=headers or {})

    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode_address_seguro(calle, poblacion):
    headers = {"User-Agent": "HackathonDammApp/1.0"}

    if calle and poblacion:
        query = urlencode({
            "q": f"{calle}, {poblacion}, Spain",
            "format": "json",
            "limit": 1,
        })
        url = f"https://nominatim.openstreetmap.org/search?{query}"

        try:
            res = get_json(url, headers=headers, timeout=8)
            if res:
                return [float(res[0]["lon"]), float(res[0]["lat"])]
        except Exception:
            pass

        time.sleep(0.8)

    if poblacion:
        query = urlencode({
            "q": f"{poblacion}, Catalonia, Spain",
            "format": "json",
            "limit": 1,
        })
        url_pob = f"https://nominatim.openstreetmap.org/search?{query}"

        try:
            res = get_json(url_pob, headers=headers, timeout=8)
            if res:
                return [float(res[0]["lon"]), float(res[0]["lat"])]
        except Exception:
            pass

    return [2.1734, 41.3851]


def haversine_km_lonlat(a, b):
    lon1, lat1 = a
    lon2, lat2 = b

    radius = 6371

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * radius * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def build_fallback_time_matrix(coords_list):
    matrix = []

    for origin in coords_list:
        row = []

        for destination in coords_list:
            km = haversine_km_lonlat(origin, destination)
            minutes = max(1, round((km / 35) * 60))
            row.append(minutes)

        matrix.append(row)

    return matrix


def get_osrm_time_matrix(coords_list):
    if not coords_list or len(coords_list) < 2:
        return []

    coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords_list])
    url = f"https://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration"

    try:
        response = get_json(url, timeout=12)

        if response.get("code") == "Ok" and response.get("durations"):
            matrix = [[int(seg / 60) if seg is not None else 9999 for seg in fila] for fila in response["durations"]]

            if len(matrix) == len(coords_list) and all(len(row) == len(coords_list) for row in matrix):
                return matrix

    except Exception as exc:
        print(f"OSRM table fallback: {exc}")

    return []


def find_direction_by_client(direcciones_col, cliente_id):
    candidate_ids = []

    candidate_ids.append(cliente_id)
    candidate_ids.append(str(cliente_id))

    try:
        candidate_ids.append(int(cliente_id))
    except Exception:
        pass

    for candidate in candidate_ids:
        doc = direcciones_col.find_one({"cliente": candidate})
        if doc:
            return doc

    return None


def normalize_delivery_window(horario_doc):
    apertura = str_hora_a_minutos(horario_doc.get("horario_inicia_a"))
    cierre = str_hora_a_minutos(horario_doc.get("horario_termina_a"))

    if apertura == 0 and cierre == 0:
        return 480, 1080

    apertura = apertura if apertura is not None else 480
    cierre = cierre if cierre is not None else 1080

    if cierre <= apertura:
        cierre = 1080

    return apertura, cierre


def get_data_from_mongo(db=None):
    if db is None:
        db = get_mongo_from_env()

    pedidos_col = get_collection(db, PEDIDOS_COLLECTIONS)
    direcciones_col = get_collection(db, DIRECCIONES_COLLECTIONS)
    horarios_col = get_collection(db, HORARIOS_COLLECTIONS)

    cursor_pedidos = list(
        pedidos_col.find({"nombre_1": {"$in": BARES_DEMO}}).limit(30)
    )

    if not cursor_pedidos:
        cursor_pedidos = list(pedidos_col.find({}).limit(30))

    clientes_procesados = []
    nombres_vistos = set()

    for pedido_doc in cursor_pedidos:
        if len(clientes_procesados) >= MAX_CLIENTES_DEMO:
            break

        nombre_bar = pedido_doc.get("nombre_1") or pedido_doc.get("destinatario_mcia1") or "Bar Desconocido"

        if nombre_bar in nombres_vistos:
            continue

        cliente_id = pedido_doc.get("cliente") or pedido_doc.get("destinatario_mcia")

        if cliente_id is None:
            continue

        demanda_anual = safe_int(pedido_doc.get("nProductos"), 50)
        n_productos = int((demanda_anual % 15) + 5)

        dir_doc = find_direction_by_client(direcciones_col, cliente_id)

        if not dir_doc or not dir_doc.get("calle"):
            continue

        horario_doc = horarios_col.find_one({"nombre_1": nombre_bar}) or {}
        apertura, cierre = normalize_delivery_window(horario_doc)

        calle = dir_doc.get("calle")
        poblacion = dir_doc.get("poblacion", "Barcelona")
        coords = geocode_address_seguro(calle, poblacion)

        time.sleep(0.6)

        nombres_vistos.add(nombre_bar)

        clientes_procesados.append({
            "id": str(cliente_id),
            "nombre": nombre_bar,
            "n_productos": n_productos,
            "hora_apertura": apertura,
            "hora_cierre": cierre,
            "es_vip": True if horario_doc.get("canal_distribucion") == 10 else False,
            "coords": coords,
        })

    if not clientes_procesados:
        return get_fallback_clients()

    return clientes_procesados


def get_fallback_clients():
    return [
        {
            "id": "demo-1",
            "nombre": "IBERICUS CENTRAL",
            "n_productos": 12,
            "hora_apertura": 480,
            "hora_cierre": 1080,
            "es_vip": False,
            "coords": [2.2877, 41.6086],
        },
        {
            "id": "demo-2",
            "nombre": "FRANKFURT LEO BOECK GRANOLLERS",
            "n_productos": 8,
            "hora_apertura": 540,
            "hora_cierre": 900,
            "es_vip": False,
            "coords": [2.2864, 41.6079],
        },
        {
            "id": "demo-3",
            "nombre": "BAR LA PETRA II",
            "n_productos": 10,
            "hora_apertura": 600,
            "hora_cierre": 1080,
            "es_vip": False,
            "coords": [2.2135, 41.5402],
        },
        {
            "id": "demo-4",
            "nombre": "SUSHI HE GRANOLLERS",
            "n_productos": 7,
            "hora_apertura": 570,
            "hora_cierre": 960,
            "es_vip": False,
            "coords": [2.2901, 41.6112],
        },
        {
            "id": "demo-5",
            "nombre": "LA ROCA VILLAGE RTE PASARELA",
            "n_productos": 15,
            "hora_apertura": 660,
            "hora_cierre": 1200,
            "es_vip": True,
            "coords": [2.3442, 41.6103],
        },
    ]


def create_data_model_from_mongo(db=None):
    print("Extrayendo datos y geocodificando...")
    clientes = get_data_from_mongo(db=db)

    data = {}
    data["coords"] = [COORDS_ALMACEN_LONLAT] + [c["coords"] for c in clientes]

    print("Calculando matriz de tiempos...")
    osrm_matrix = get_osrm_time_matrix(data["coords"])
    data["time_matrix"] = osrm_matrix or build_fallback_time_matrix(data["coords"])

    data["service_time"] = [0] + [
        int(c["n_productos"] * TIEMPO_DESCARGA_PRODUCTO) for c in clientes
    ]

    data["time_windows"] = [(480, 1200)] + [
        (c["hora_apertura"], c["hora_cierre"]) for c in clientes
    ]

    data["vips"] = [False] + [c["es_vip"] for c in clientes]
    data["nombres"] = ["ALMACÉN"] + [c["nombre"] for c in clientes]
    data["demands"] = [0] + [c["n_productos"] for c in clientes]
    data["vehicle_capacities"] = [CAPACIDAD_CAMION]
    data["num_vehicles"] = 1
    data["depot"] = 0
    data["clientes"] = clientes

    return data


def solve_greedy_fallback(data):
    pending = list(range(1, len(data["nombres"])))
    current = 0
    current_time = 480
    load = 0
    route = []

    route.append({
        "orden": 0,
        "nombre": "ALMACÉN",
        "llegada_minutos": current_time,
        "llegada_formato": min_to_hora(current_time),
        "carga_descargada": 0,
        "retornos_recogidos": 0,
        "coordenadas_gps": data["coords"][0],
    })

    while pending:
        pending.sort(key=lambda node: (
            data["time_windows"][node][1],
            data["time_matrix"][current][node],
        ))

        next_node = pending.pop(0)
        travel_time = data["time_matrix"][current][next_node]
        arrival = current_time + travel_time

        opening, closing = data["time_windows"][next_node]

        if arrival < opening:
            arrival = opening

        service = data["service_time"][next_node]
        demand = data["demands"][next_node]
        load += demand

        route.append({
            "orden": len(route),
            "nombre": data["nombres"][next_node],
            "llegada_minutos": arrival,
            "llegada_formato": min_to_hora(arrival),
            "carga_descargada": demand,
            "retornos_recogidos": int(demand * 0.6),
            "coordenadas_gps": data["coords"][next_node],
        })

        current_time = arrival + service
        current = next_node

    current_time += data["time_matrix"][current][0]

    route.append({
        "orden": len(route),
        "nombre": "ALMACÉN (FIN)",
        "llegada_minutos": current_time,
        "llegada_formato": min_to_hora(current_time),
        "carga_descargada": 0,
        "retornos_recogidos": "Descarga total en planta",
        "coordenadas_gps": data["coords"][0],
    })

    return route


def solve_vrptw(data):
    if not ORTOOLS_AVAILABLE:
        print("OR-Tools no disponible. Usando heurística fallback.")
        return solve_greedy_fallback(data)

    if not data.get("time_matrix") or len(data["time_matrix"]) != len(data["coords"]):
        print("Matriz de tiempo inválida. Usando heurística fallback.")
        return solve_greedy_fallback(data)

    manager = pywrapcp.RoutingIndexManager(
        len(data["time_matrix"]),
        data["num_vehicles"],
        data["depot"],
    )

    routing = pywrapcp.RoutingModel(manager)

    def demand_cost_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        tiempo_total = data["time_matrix"][from_node][to_node] + data["service_time"][from_node]

        if data["vips"][to_node]:
            return int(tiempo_total * 0.8)

        return int(tiempo_total)

    cost_callback_index = routing.RegisterTransitCallback(demand_cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_callback_index)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        return int(data["time_matrix"][from_node][to_node] + data["service_time"][from_node])

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(time_callback_index, 60, 1440, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")

    for location_idx, time_window in enumerate(data["time_windows"]):
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])

        if location_idx != 0:
            routing.AddDisjunction([index], PENALIZACION_SALTAR_CLIENTE)

    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return int(data["demands"][from_node])

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        data["vehicle_capacities"],
        True,
        "Capacity",
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 3

    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        print("OR-Tools no encontró solución. Usando heurística fallback.")
        return solve_greedy_fallback(data)

    ruta_final = []
    index = routing.Start(0)
    carga_actual = 0

    while not routing.IsEnd(index):
        node_idx = manager.IndexToNode(index)
        minutos = solution.Min(time_dimension.CumulVar(index))
        demanda = int(data["demands"][node_idx])
        carga_actual += demanda

        retornos_texto = 0 if node_idx == 0 else int(demanda * 0.6)

        ruta_final.append({
            "orden": len(ruta_final),
            "nombre": data["nombres"][node_idx],
            "llegada_minutos": minutos,
            "llegada_formato": min_to_hora(minutos),
            "carga_descargada": demanda,
            "retornos_recogidos": retornos_texto,
            "coordenadas_gps": data["coords"][node_idx],
            "carga_acumulada": carga_actual,
            "capacidad_camion": CAPACIDAD_CAMION,
        })

        index = solution.Value(routing.NextVar(index))

    minutos_fin = solution.Min(time_dimension.CumulVar(index))

    ruta_final.append({
        "orden": len(ruta_final),
        "nombre": "ALMACÉN (FIN)",
        "llegada_minutos": minutos_fin,
        "llegada_formato": min_to_hora(minutos_fin),
        "carga_descargada": 0,
        "retornos_recogidos": "Descarga total en planta",
        "coordenadas_gps": data["coords"][0],
    })

    return ruta_final


def lonlat_to_latlon(coords):
    if not coords or len(coords) != 2:
        return [41.5367, 2.2173]

    lon, lat = coords
    return [lat, lon]


def get_load_zone_by_order(order):
    if order <= 2:
        return "P1 / P2"

    if order <= 5:
        return "P3"

    if order <= 8:
        return "P4"

    return "P6"


def get_load_zones_by_order(order):
    zone = get_load_zone_by_order(order)
    return [part.strip() for part in zone.split("/")]


def calculate_route_distance_km_from_lonlat(points):
    if len(points) < 2:
        return 0

    total = 0

    for index in range(len(points) - 1):
        total += haversine_km_lonlat(points[index], points[index + 1])

    return round(total, 1)


def build_route_data_for_frontend(db=None):
    modelo = create_data_model_from_mongo(db=db)
    ruta = solve_vrptw(modelo)

    if not ruta:
        return None

    warehouse_coords = lonlat_to_latlon(modelo["coords"][0])
    stops = []

    for item in ruta:
        nombre = item.get("nombre", "")

        if "ALMACÉN" in nombre:
            continue

        order = len(stops) + 1
        load = get_load_zone_by_order(order)

        stops.append({
            "number": order,
            "name": nombre,
            "coords": lonlat_to_latlon(item.get("coordenadas_gps")),
            "time": item.get("llegada_formato", "--:--"),
            "clients": [nombre],
            "load": load,
            "loadZones": get_load_zones_by_order(order),
            "note": (
                f"Entrega de {item.get('carga_descargada', 0)} productos. "
                f"Retornos previstos: {item.get('retornos_recogidos', 0)}."
            ),
        })

    route_points_lonlat = [
        item["coordenadas_gps"]
        for item in ruta
        if item.get("coordenadas_gps")
    ]

    distance_km = calculate_route_distance_km_from_lonlat(route_points_lonlat)

    start_time = ruta[0].get("llegada_minutos", 480)
    end_time = ruta[-1].get("llegada_minutos", start_time)

    estimated_minutes = max(0, end_time - start_time)

    return {
        "routeId": "DR-042",
        "scenario": "Reparto Damm - Mollet / Vallès",
        "distributionCenter": "DDI Mollet",
        "warehouse": {
            "name": "DDI Mollet",
            "coords": warehouse_coords,
        },
        "routePoints": [
            lonlat_to_latlon(coords)
            for coords in route_points_lonlat
        ],
        "returnToWarehouse": {
            "name": "DDI Mollet",
            "coords": warehouse_coords,
            "time": ruta[-1].get("llegada_formato", "--:--"),
            "note": "Regreso al almacén para descargar retornables y cerrar la ruta.",
        },
        "summary": {
            "clients": len(stops),
            "currentStops": len(stops),
            "optimizedStops": len(stops),
            "distanceKm": distance_km,
            "estimatedTime": format_duration(estimated_minutes),
            "windowCompliance": 94,
        },
        "stops": stops,
    }


def imprimir_dashboard_inicial(data):
    print("\n" + "📦 " * 25)
    print(f"📋 DATOS EXTRAÍDOS DE MONGODB | CAMIÓN ASIGNADO: {CAPACIDAD_CAMION} uds")
    print("📦 " * 25)

    total_productos = 0
    total_tiempo_descarga = 0

    for i in range(len(data["nombres"])):
        nombre = data["nombres"][i]

        if i == 0:
            print(f"\n🏠 {nombre} (Origen/Destino)")
        else:
            prod = data["demands"][i]
            tiempo_descarga = data["service_time"][i]
            apertura = min_to_hora(data["time_windows"][i][0])
            cierre = min_to_hora(data["time_windows"][i][1])
            vip = "⭐ VIP" if data["vips"][i] else "Normal"

            total_productos += prod
            total_tiempo_descarga += tiempo_descarga

            print(f"🍺 {i}. {nombre}")
            print(f"   ├─ Pide:     {prod} productos ({tiempo_descarga} min descarga)")
            print(f"   ├─ Horario:  {apertura} - {cierre}")
            print(f"   └─ Estado:   {vip}")

    print("\n" + "=" * 50)
    print(f"📊 A REPARTIR: {total_productos} productos | {total_tiempo_descarga} mins de descarga estimada")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    modelo = create_data_model_from_mongo()
    imprimir_dashboard_inicial(modelo)
    print("Ejecutando motor de optimización...")
    result = build_route_data_for_frontend()
    print(result)
