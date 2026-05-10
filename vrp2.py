from pymongo import MongoClient
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import time
import requests
import dns.resolver

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

# --- CONFIGURACIÓN FLOTA Y PESOS ---
TIEMPO_DESCARGA_PRODUCTO = 1
PENALIZACION_SALTAR_CLIENTE = 999999

CAPACIDAD_CAMION_3 = 60  
CAPACIDAD_CAMION_6 = 110 
CAPACIDAD_CAMION_8 = 140 
CAPACIDAD_CAMION = CAPACIDAD_CAMION_6

def str_hora_a_minutos(hora_str):
    if not hora_str or not isinstance(hora_str, str): return None
    try:
        partes = hora_str.split(':')
        return int(partes[0]) * 60 + int(partes[1])
    except: return None

def geocode_address_seguro(calle, poblacion):
    """Intenta buscar la calle exacta. Si falla, busca la ciudad para garantizar distancia de viaje."""
    headers = {'User-Agent': 'HackathonDammApp/1.0'}
    
    # 1. Intentamos con la calle
    url = f"https://nominatim.openstreetmap.org/search?q={calle}, {poblacion}, Spain&format=json&limit=1"
    try:
        res = requests.get(url, headers=headers).json()
        if res: return [float(res[0]['lon']), float(res[0]['lat'])]
    except: pass

    time.sleep(1) # Cuidado con la API

    # 2. Si falla la calle, buscamos solo el pueblo/ciudad
    url_pob = f"https://nominatim.openstreetmap.org/search?q={poblacion}, Catalonia, Spain&format=json&limit=1"
    try:
        res = requests.get(url_pob, headers=headers).json()
        if res: return [float(res[0]['lon']), float(res[0]['lat'])]
    except: pass

    return [2.1734, 41.3851] # Si todo falla, Barcelona centro

def get_osrm_time_matrix(coords_list):
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords_list])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration"
    try:
        response = requests.get(url).json()
        if response.get('code') == 'Ok':
            # Devolvemos enteros (int) siempre
            return [[int(seg / 60) for seg in fila] for fila in response['durations']]
    except: pass
    return []

def get_data_from_mongo():
    uri = "mongodb+srv://Erik:erik123@damm.znsohkl.mongodb.net/?retryWrites=true&w=majority"
    client = MongoClient(uri)
    db = client['BD_DAMM']

    bares_demo = [
        "FRANKFURT LEO BOECK GRANOLLERS", "BAR LA PETRA II", "SUSHI HE GRANOLLERS",
        "IBERICUS CENTRAL", "CANTINA IES VIC ST TOMAS", "CAN BIN RESTAURANTE",
        "LA ROCA VILLAGE RTE PASARELA (GVC)", "KAPHIY BRUNCH", "BAR CRISTASOL",
        "PITAPES BERENGUER", "MARTU CITY", "CAFETERIA ATREZZO", "DATOTE AL BAGH"
    ]

    cursor_pedidos = db['detalles_entrega_nproductos'].find({"nombre_1": {"$in": bares_demo}}).limit(20)
    
    clientes_procesados = []
    nombres_vistos = set() # Evita duplicados como Ibericus

    for pedido_doc in cursor_pedidos:
        if len(clientes_procesados) >= 5: break

        nombre_bar = pedido_doc.get('nombre_1', 'Bar Desconocido')
        if nombre_bar in nombres_vistos: continue

        cliente_id = pedido_doc.get('cliente')
        try: cliente_id = int(cliente_id)
        except: pass

        # Transformamos la demanda anual en un pedido realista diario (ej. de 5 a 20 productos)
        demanda_anual = int(pedido_doc.get('nProductos', 50))
        n_productos = int((demanda_anual % 15) + 5) # Siempre será un INT

        dir_doc = db['direcciones.json'].find_one({"cliente": cliente_id})
        if not dir_doc or not dir_doc.get('calle'): continue

        horario_doc = db['HorariosEntrega'].find_one({"nombre_1": nombre_bar}) or {}
        apertura = str_hora_a_minutos(horario_doc.get('horario_inicia_a'))
        cierre = str_hora_a_minutos(horario_doc.get('horario_termina_a'))

        if apertura == 0 and cierre == 0:
            apertura, cierre = 480, 1080
        else:
            apertura = apertura if apertura is not None else 480
            cierre = cierre if cierre is not None else 1080

        calle = dir_doc.get('calle')
        poblacion = dir_doc.get('poblacion', 'Barcelona')
        coords = geocode_address_seguro(calle, poblacion)
        time.sleep(1)

        nombres_vistos.add(nombre_bar)
        clientes_procesados.append({
            'id': str(cliente_id),
            'nombre': nombre_bar,
            'n_productos': n_productos, # INT garantizado
            'hora_apertura': apertura,
            'hora_cierre': cierre,
            'es_vip': True if horario_doc.get('canal_distribucion') == 10 else False,
            'coords': coords
        })

    return clientes_procesados

def create_data_model_from_mongo():
    print("Extrayendo datos y geocodificando... (esto tardará unos 5-10 segundos)")
    clientes = get_data_from_mongo()
    data = {}

    coords_almacen = [2.2173, 41.5367] # Mollet del Vallès
    data['coords'] = [coords_almacen] + [c['coords'] for c in clientes]

    print("Calculando distancias de tráfico reales con OSRM...")
    data['time_matrix'] = get_osrm_time_matrix(data['coords'])

    # Obligamos a que el tiempo de descarga sea un entero (int) para que OR-Tools no pete
    data['service_time'] = [0] + [int(c['n_productos'] * TIEMPO_DESCARGA_PRODUCTO) for c in clientes]
    
    data['time_windows'] = [(480, 1200)] + [(c['hora_apertura'], c['hora_cierre']) for c in clientes]
    data['vips'] = [False] + [c['es_vip'] for c in clientes]
    data['nombres'] = ["ALMACÉN"] + [c['nombre'] for c in clientes]
    
    data['demands'] = [0] + [c['n_productos'] for c in clientes]
    data['vehicle_capacities'] = [CAPACIDAD_CAMION]

    data['num_vehicles'] = 1
    data['depot'] = 0
    return data

def solve_vrptw(data):
    manager = pywrapcp.RoutingIndexManager(len(data['time_matrix']), data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # 1. EVALUADOR DE COSTES (Estrategia VIP)
    def demand_cost_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        tiempo_total = data['time_matrix'][from_node][to_node] + data['service_time'][from_node]
        if data['vips'][to_node]: return int(tiempo_total * 0.8)
        return tiempo_total

    cost_callback_index = routing.RegisterTransitCallback(demand_cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_callback_index)

    # 2. EVALUADOR FÍSICO DE TIEMPO (El Reloj)
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['time_matrix'][from_node][to_node] + data['service_time'][from_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(time_callback_index, 60, 1440, False, 'Time')
    time_dimension = routing.GetDimensionOrDie('Time')

    for location_idx, time_window in enumerate(data['time_windows']):
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])
        if location_idx != 0:
            routing.AddDisjunction([index], PENALIZACION_SALTAR_CLIENTE)

    # 3. EVALUADOR DE CAPACIDAD FÍSICA DEL CAMIÓN
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  
        data['vehicle_capacities'],
        True,
        'Capacity'
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 3 

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        print("\n🍺 RUTA ÓPTIMA CALCULADA:")
        ruta_final = []
        carga_actual = 0
        index = routing.Start(0)
        
        while not routing.IsEnd(index):
            node_idx = manager.IndexToNode(index)
            minutos = solution.Min(time_dimension.CumulVar(index))
            nombre = data['nombres'][node_idx]
            vip = "[VIP]" if data['vips'][node_idx] else ""
            carga_actual += data['demands'][node_idx]
            demanda = data['demands'][node_idx]
            retornos = int(demanda * 0.6)

            if node_idx == 0:
                print(f" -> {nombre} (Salida: {minutos//60:02d}:{minutos%60:02d}) | Camión Vacío")
                retornos_texto = 0
            else:
                print(f" -> {nombre} {vip} (Llegada: {minutos//60:02d}:{minutos%60:02d}) | Huecos Ocupados: {carga_actual}/{CAPACIDAD_CAMION}")
                retornos_texto = retornos

            ruta_final.append({
                "orden": len(ruta_final),
                "nombre": nombre,
                "llegada_formato": f"{minutos//60:02d}:{minutos%60:02d}",
                "carga_descargada": demanda,
                "retornos_recogidos": retornos,
                "retornos_recogidos": retornos_texto,
                "coordenadas_gps": data['coords'][node_idx]
            })
            index = solution.Value(routing.NextVar(index))
            
        minutos_fin = solution.Min(time_dimension.CumulVar(index))
        print(f" -> Vuelta al ALMACÉN (Llegada: {minutos_fin//60:02d}:{minutos_fin%60:02d})")
        ruta_final.append({
            "orden": len(ruta_final),
            "nombre": "ALMACÉN (FIN)",
            "llegada_formato": f"{minutos_fin//60:02d}:{minutos_fin%60:02d}",
            "carga_descargada": 0,
            "retornos_recogidos": "Descarga total en planta",
            "coordenadas_gps": data['coords'][0]
        })
        return ruta_final
    else:
        print("Error: No se pudo encontrar una ruta viable.")
        return None

def min_to_hora(minutos):
    return f"{minutos//60:02d}:{minutos%60:02d}"

def imprimir_dashboard_inicial(data):
    print("\n" + "📦 "*25)
    print(f"📋 DATOS EXTRAÍDOS DE MONGODB | CAMIÓN ASIGNADO: {CAPACIDAD_CAMION} uds")
    print("📦 "*25)
    
    total_productos = 0
    total_tiempo_descarga = 0

    for i in range(len(data['nombres'])):
        nombre = data['nombres'][i]
        
        if i == 0:
            print(f"\n🏠 {nombre} (Origen/Destino)")
        else:
            prod = data['demands'][i]
            tiempo_descarga = data['service_time'][i]
            apertura = min_to_hora(data['time_windows'][i][0])
            cierre = min_to_hora(data['time_windows'][i][1])
            vip = "⭐ VIP" if data['vips'][i] else "Normal"
            
            total_productos += prod
            total_tiempo_descarga += tiempo_descarga
            
            print(f"🍺 {i}. {nombre}")
            print(f"   ├─ Pide:     {prod} productos ({tiempo_descarga} min descarga)")
            print(f"   ├─ Horario:  {apertura} - {cierre}")
            print(f"   └─ Estado:   {vip}")
            
    print("\n" + "="*50)
    print(f"📊 A REPARTIR: {total_productos} productos | {total_tiempo_descarga} mins de descarga estimada")
    print("="*50 + "\n")

if __name__ == "__main__":
    modelo = create_data_model_from_mongo()
    imprimir_dashboard_inicial(modelo)
    print("⏳ Ejecutando motor de Inteligencia Artificial (OR-Tools)...")
    solve_vrptw(modelo)