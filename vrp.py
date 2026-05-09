from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

def create_data_model():
    """Almacena los datos para el problema. 
       ¡AQUÍ CONECTARÉIS VUESTRA BASE DE DATOS MONGODB!"""
    data = {}
    
    # Matriz de distancias (o tiempos) entre los clientes.
    # El índice 0 suele ser el almacén (Depot).
    # Esto lo podéis generar con una API de mapas (OSRM, Google Maps) o simularlo.
    data['distance_matrix'] = [
        [0, 548, 776, 696, 582, 274],
        [548, 0, 684, 308, 194, 502],
        [776, 684, 0, 992, 878, 502],
        [696, 308, 992, 0, 114, 650],
        [582, 194, 878, 114, 0, 536],
        [274, 502, 502, 650, 536, 0],
    ]
    
    # Demanda de cada cliente (volumen o número de palets). 
    # El índice 0 es el almacén (demanda 0).
    data['demands'] = [0, 1, 1, 2, 4, 2]
    
    # Capacidad máxima del camión (ej. 8 palets/unidades logísticas)
    data['vehicle_capacities'] = [8] 
    
    data['num_vehicles'] = 1 # Empezamos optimizando 1 camión
    data['depot'] = 0 # El índice del almacén en la matriz
    
    return data

def solve_vrp():
    """Resuelve el VRP y devuelve la ruta óptima."""
    data = create_data_model()

    # Crea el Routing Index Manager
    manager = pywrapcp.RoutingIndexManager(
        len(data['distance_matrix']), data['num_vehicles'], data['depot']
    )

    # Crea el modelo de ruteo
    routing = pywrapcp.RoutingModel(manager)

    # Crea y registra la función (callback) que devuelve las distancias
    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # Define el coste de cada arco de la ruta
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Añade la restricción de Capacidad
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # null capacity slack
        data['vehicle_capacities'],  # capacidad máxima del vehículo
        True,  # empieza la ruta con la capacidad acumulada a cero
        'Capacity'
    )

    # Configura los parámetros de búsqueda (heurísticas)
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    # ¡Resuelve el problema!
    solution = routing.SolveWithParameters(search_parameters)

    # Formatea la salida para enviarla al Frontend
    if solution:
        return format_solution(data, manager, routing, solution)
    else:
        return {"error": "No se ha encontrado solución"}

def format_solution(data, manager, routing, solution):
    """Convierte la solución de OR-Tools en un JSON amigable para vuestro Frontend."""
    route = []
    index = routing.Start(0)
    route_load = 0
    
    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)
        route_load += data['demands'][node_index]
        route.append({
            "cliente_id": node_index,
            "carga_acumulada": route_load
        })
        index = solution.Value(routing.NextVar(index))
    
    # Añadir el retorno al almacén
    node_index = manager.IndexToNode(index)
    route.append({
        "cliente_id": node_index,
        "carga_final": route_load
    })
    
    return {"ruta": route}