from pymongo import MongoClient
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import datetime
import time
import requests
import dns.resolver

dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']
# Carrer del Molí de Can Bassa, 1, 08100 Mollet del Vallès, Barcelona

TIEMPO_DESCARGA_PRODUCTO = 5
PENALIZACION_SALTAR_CLIENTE = 999999

def str_hora_a_minutos(hora_str):
    if not hora_str or not isinstance(hora_str, str): return None
    try:
        partes = hora_str.split(':')
        return int(partes[0]) * 60 + int(partes[1])
    except:
        return None

def geocode_address(direccion):
    """Convierte una dirección de texto a coordenadas [Longitud, Latitud] usando Nominatim"""
    url = f"https://nominatim.openstreetmap.org/search?q={direccion}&format=json&limit=1"
    headers = {'User-Agent': 'HackathonDammApp/1.0'} # Nominatim exige que te identifiques
    
    try:
        response = requests.get(url, headers=headers).json()
        if response:
            # OSRM necesita el formato: [Longitud, Latitud]
            return [float(response[0]['lon']), float(response[0]['lat'])]
    except Exception as e:
        print(f"Error geocodificando {direccion}: {e}")
    
    # Si falla, devolvemos el centro de Barcelona por defecto
    return [2.1734, 41.3851]

def get_osrm_time_matrix(coords_list):
    """Llama a OSRM para obtener la matriz de tiempos entre todas las coordenadas"""
    # Formato que pide OSRM: lon1,lat1;lon2,lat2;...
    coords_str = ";".join([f"{lon},{lat}" for lon, lat in coords_list])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration"
    
    try:
        response = requests.get(url).json()
        if response.get('code') == 'Ok':
            # OSRM devuelve duraciones en segundos. Las pasamos a minutos enteros.
            matriz_segundos = response['durations']
            matriz_minutos = [[int(seg / 60) for seg in fila] for fila in matriz_segundos]
            return matriz_minutos
    except Exception as e:
        print(f"Error obteniendo matriz OSRM: {e}")
        
    # Si falla la API, devolvemos una matriz vacía para que no pete el código
    return []

def get_data_from_mongo():
    uri = "mongodb+srv://Erik:erik123@damm.znsohkl.mongodb.net/?retryWrites=true&w=majority"
    client = MongoClient(uri)
    db = client['BD_DAMM']

    # PASO 1: Empezamos por la tabla maestra de pedidos agrupados
    # Cogemos unos 20 de muestra por si algunos fallan en la dirección
    cursor_pedidos = db['detalles_entrega_nproductos'].find({}).limit(20)
    
    clientes_procesados = []
    ids_vistos = set() # 🛡️ Escudo antiduplicados

    for pedido_doc in cursor_pedidos:
        if len(clientes_procesados) >= 5: 
            break # Ya tenemos nuestros 5 distintos
            
        raw_cliente = pedido_doc.get('cliente')
        try:
            cliente_id = int(raw_cliente)
        except:
            cliente_id = raw_cliente

        # Si ya hemos procesado a este cliente, lo saltamos
        if cliente_id in ids_vistos:
            continue

        n_productos = pedido_doc.get('nProductos', 3)

        # PASO 2: Buscamos su dirección
        dir_doc = db['direcciones.json'].find_one({"cliente": cliente_id})
        if not dir_doc or not dir_doc.get('calle'):
            continue # Sin dirección no podemos ir

        # PASO 3: Buscamos su horario (Si no tiene, ponemos por defecto)
        horario_doc = db['HorariosEntrega'].find_one({"deudor": cliente_id}) or {}
        apertura = str_hora_a_minutos(horario_doc.get('horario_inicia_a'))
        cierre = str_hora_a_minutos(horario_doc.get('horario_termina_a'))
        
        if apertura == 0 and cierre == 0:
            apertura, cierre = 480, 1080
        else:
            apertura = apertura if apertura is not None else 480
            cierre = cierre if cierre is not None else 1080

        # PASO 4: Geocodificamos
        dir_texto = f"{dir_doc.get('calle')}, {dir_doc.get('poblacion')}, Spain"
        coords = geocode_address(dir_texto)
        time.sleep(1)

        # Lo marcamos como visto y lo guardamos
        ids_vistos.add(cliente_id)
        clientes_procesados.append({
            'id': str(cliente_id),
            'nombre': dir_doc.get('nombre_1', 'Bar Damm'),
            'n_productos': n_productos,
            'hora_apertura': apertura,
            'hora_cierre': cierre,
            'es_vip': True if horario_doc.get('canal_distribucion') == 10 else False,
            'coords': coords
        })
    
    return clientes_procesados


def create_data_model_from_mongo():
    print("Extrayendo datos y geocodificando... (esto tardará unos 5 segundos)")
    clientes = get_data_from_mongo()
    data = {}
    
    # 1. COORDENADAS DEL ALMACÉN DE DAMM (Mollet del Vallès)
    # Longitud, Latitud
    coords_almacen = [2.2173, 41.5367] # Coordenadas aproximadas de Can Bassa
    
    # Juntamos las coordenadas del almacén (índice 0) con la de los 5 bares
    todas_las_coords = [coords_almacen] + [c['coords'] for c in clientes]
    
    # 2. TIEMPOS DE TRAYECTO (Matriz Real con OSRM)
    print("Calculando distancias de tráfico con OSRM...")
    data['time_matrix'] = get_osrm_time_matrix(todas_las_coords)
    
    # 3. SERVICE TIME (Tu variable t_descarga)
    data['service_time'] = [0] + [c['n_productos'] * 5 for c in clientes]
    
    # 4. TIME WINDOWS (Tus horas de apertura y cierre)
    data['time_windows'] = [(480, 1200)] + [(c['hora_apertura'], c['hora_cierre']) for c in clientes]
    
    # 5. PRIORIDADES
    data['vips'] = [False] + [c['es_vip'] for c in clientes]
    data['nombres'] = ["ALMACÉN"] + [c['nombre'] for c in clientes]
    
    data['num_vehicles'] = 1
    data['depot'] = 0
    
    return data

def solve_vrptw(data):
    manager = pywrapcp.RoutingIndexManager(len(data['time_matrix']), data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    # REGLA A: EL COSTE (Lo que el algoritmo quiere minimizar)
    def demand_cost_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        
        tiempo_total = data['time_matrix'][from_node][to_node] + data['service_time'][from_node]
        
        # Si el destino es VIP, le decimos al algoritmo que cuesta un 20% menos.
        if data['vips'][to_node]:
            return int(tiempo_total * 0.8)
        return tiempo_total

    cost_callback_index = routing.RegisterTransitCallback(demand_cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_callback_index)

    # REGLA B: EL RELOJ FÍSICO (El tiempo real que pasa)
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['time_matrix'][from_node][to_node] + data['service_time'][from_node]

    time_callback_index = routing.RegisterTransitCallback(time_callback)
    
    # Creamos la dimensión de tiempo (abre/cierra)
    routing.AddDimension(time_callback_index, 60, 1440, False, 'Time')
    time_dimension = routing.GetDimensionOrDie('Time')

    # Aplicamos los horarios a cada bar
    for location_idx, time_window in enumerate(data['time_windows']):
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(time_window[0], time_window[1])
        
        # Permitimos que se salte un bar si paga la multa (excepto el almacén)
        if location_idx != 0:
            routing.AddDisjunction([index], PENALIZACION_SALTAR_CLIENTE)

    # ¡A RESOLVER!
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 3 
    
    solution = routing.SolveWithParameters(search_parameters)

    # Imprimimos el resultado de forma legible
    if solution:
        print("\n🍺 RUTA ÓPTIMA CALCULADA:")
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node_idx = manager.IndexToNode(index)
            minutos = solution.Min(time_dimension.CumulVar(index))
            nombre = data['nombres'][node_idx]
            vip = "[VIP]" if data['vips'][node_idx] else ""
            print(f" -> {nombre} {vip} (Llegada: {minutos//60:02d}:{minutos%60:02d})")
            index = solution.Value(routing.NextVar(index))
        print(" -> Vuelta al ALMACÉN")
    else:
        print("Error: No se pudo resolver la ruta.")
    
def min_to_hora(minutos):
    """Convierte 540 a '09:00' para que los humanos lo entendamos"""
    return f"{minutos//60:02d}:{minutos%60:02d}"

def imprimir_dashboard_inicial(data):
    print("\n" + "📦 "*25)
    print("📋 DATOS EXTRAÍDOS DE MONGODB (SAP) - SIN ORDENAR")
    print("📦 "*25)
    
    total_productos = 0
    total_tiempo_descarga = 0

    for i in range(len(data['nombres'])):
        nombre = data['nombres'][i]
        
        if i == 0:
            print(f"\n🏠 {nombre} (Origen/Destino)")
            print(f"   ├─ Apertura del Centro: {min_to_hora(data['time_windows'][i][0])}")
            print(f"   └─ Cierre del Centro:   {min_to_hora(data['time_windows'][i][1])}")
        else:
            prod = data['service_time'][i] // 5 # Recuperamos el número de productos
            tiempo_descarga = data['service_time'][i]
            apertura = min_to_hora(data['time_windows'][i][0])
            cierre = min_to_hora(data['time_windows'][i][1])
            vip = "⭐ SÍ (-20% Coste)" if data['vips'][i] else "❌ NO"
            
            total_productos += prod
            total_tiempo_descarga += tiempo_descarga
            
            print(f"\n🍺 {i}. {nombre}")
            print(f"   ├─ Demanda:  {prod} productos ({tiempo_descarga} min de descarga)")
            print(f"   ├─ Horario:  {apertura} - {cierre}")
            print(f"   └─ Estado:   {vip}")
            
    print("\n" + "="*50)
    print(f"📊 RESUMEN TOTAL: {total_productos} productos | {total_tiempo_descarga} mins de descarga estimados")
    print("="*50 + "\n")

if __name__ == "__main__":
    modelo = create_data_model_from_mongo()
    
    # 1. Imprime todos los datos crudos y pesos
    imprimir_dashboard_inicial(modelo)
    
    print("⏳ Ejecutando motor de Inteligencia Artificial (OR-Tools)...")
    # 2. Resuelve y devuelve la ruta óptima
    solve_vrptw(modelo)