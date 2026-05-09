from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import copy

TIEMPO_DESCARGA_PRODUCTO = 5  # Minutos por producto
PENALIZACION_CIERRE = 999999 

class Path:
    def init(self, route, hora_inicial):
        if type(route) is list:
            self.route = route
        else:
            self.route = [route]

        self.head = self.route[0]
        self.last = self.route[-1]
        if len(self.route) >= 2:
            self.penultimate = self.route[-2]
        # Real cost
        self.g = 0
        self.hora = hora_inicial

    def update_g_and_time(self, g, nuevo_reloj):
        self.g += g
        self.reloj = nuevo_reloj

    def add_route(self, children):
        self.route.append(children)
        self.penultimate = self.route[-2]
        self.last = self.route[-1]

def calcular_coste_tramo(hora_actual, t_trayecto, n_productos, hora_apertura, hora_cierre, es_vip):    
    t_descarga = n_productos * TIEMPO_DESCARGA_PRODUCTO
    hora_llegada = hora_actual + t_trayecto
    t_espera = max(0, hora_apertura - hora_llegada)
    
    g_cierre = PENALIZACION_CIERRE if hora_llegada > hora_cierre else 0
    t_total = t_trayecto + t_espera + t_descarga
    g_camino = t_total + g_cierre
    
    if es_vip and g_cierre == 0:
        g_camino = g_camino * 0.8  
        
    hora_salida = hora_llegada + t_espera + t_descarga
    return g_camino, hora_salida
 

def print_hora(minutos):
    horas = minutos // 60
    mins = minutos % 60
    return f"{horas:02d}:{mins:02d}"

def expand(path, map):
    llista=[]
    if path.last in map.stations:
        for connexio, cost in map.connections[path.last].items():
            pathexp=copy.deepcopy(path)
            pathexp.add_route(connexio)
            llista.append(pathexp)
    return llista


if __name__ == "__main__":
    # Vamos al Bar 1 (Tarda 30 min, descarga en 15 min, abre a las 09:00(540), cierra 14:00(840), No VIP)
    coste_bar1, nueva_hora = calcular_coste_tramo(
        hora_actual=reloj_camion, 
        t_trayecto=30, 
        n_productos=3,
        hora_apertura=540, 
        hora_cierre=840, 
        es_vip=False
    )

    print(f"Coste Bar 1: {coste_bar1} | Hora de salida hacia el siguiente: {print_hora(nueva_hora)}")
    # El output será: Coste 75 (30 viaje + 30 espera + 15 descarga). Sale a las 555 min (09:15)
