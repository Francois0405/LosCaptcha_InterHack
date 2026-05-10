from collections import defaultdict
import json
from math import ceil
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db import connections
from django.views.decorators.csrf import csrf_exempt


COLLECTIONS = {
    "horarios": "horarios_entrega.json",
    "cabecera": "cabecera_transporte.json",
    "detalle": "detalle_entrega.json",
    "direcciones": "direcciones.json",
    "materiales": "materiales_zubic.json",
    "zm040": "zm040.json",
    "zonas": "zonas.json",
}

DEFAULT_ROUTE_ID = "DR-042"
DEFAULT_DATE = "30/01/2026"
DEFAULT_DDI = "DDI MOLLET"


CITY_COORDS = {
    "BARCELONA": [41.3874, 2.1686],
    "MOLLET": [41.5402, 2.2135],
    "MOLLET DEL VALLES": [41.5402, 2.2135],
    "GRANOLLERS": [41.6086, 2.2877],
    "VIC": [41.9301, 2.2549],
    "SABADELL": [41.5463, 2.1086],
    "TERRASSA": [41.5632, 2.0089],
    "BADALONA": [41.4500, 2.2474],
    "MATARO": [41.5381, 2.4445],
}


def get_mongo_db():
    conn = connections["default"]
    conn.ensure_connection()
    return conn.connection[conn.settings_dict["NAME"]]


def col(db, key):
    return db[COLLECTIONS[key]]


def index(request):
    return redirect("/dashboard")


def dashboard(request):
    db = get_mongo_db()
    context = build_dashboard_context(db)
    return render(request, "dashboard.html", context)


def mapa(request):
    db = get_mongo_db()
    route_data = build_route_data(db)

    return render(request, "mapa.html", {
        "route_data": route_data,
    })


def distribucion(request):
    db = get_mongo_db()
    load_plan = build_load_plan(db)

    return render(request, "distribucion.html", {
        "load_plan": load_plan,
    })


def api_dashboard(request):
    db = get_mongo_db()
    return JsonResponse(build_dashboard_json(db), safe=False)


def api_route(request):
    db = get_mongo_db()
    return JsonResponse(build_route_data(db), safe=False)


def api_load_plan(request):
    db = get_mongo_db()
    return JsonResponse(build_load_plan(db), safe=False)


@csrf_exempt
def api_gemini_chat(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return JsonResponse({"error": "GEMINI_API_KEY is not configured"}, status=503)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    question = str(payload.get("question", "")).strip()
    if not question:
        return JsonResponse({"error": "Question is required"}, status=400)

    context = payload.get("context") or {}
    prompt = build_gemini_prompt(question, context)
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    gemini_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 500,
        },
    }

    request_data = json.dumps(gemini_payload).encode("utf-8")
    gemini_request = Request(
        url,
        data=request_data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urlopen(gemini_request, timeout=20) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        return JsonResponse({"error": f"Gemini request failed: {exc}"}, status=502)

    reply = extract_gemini_text(response_data)
    if not reply:
        return JsonResponse({"error": "Gemini response did not include text"}, status=502)

    return JsonResponse({"reply": reply})


def build_gemini_prompt(question, context):
    compact_context = json.dumps(context, ensure_ascii=False, indent=2)[:8000]

    return (
        "Eres el asistente operativo de Damm Smart Truck, un MVP para explicar "
        "rutas de reparto, carga de camión, palets, retornables, métricas e impacto. "
        "Responde en español, de forma breve y accionable. Usa solo el contexto "
        "del proyecto cuando sea relevante y no inventes datos operativos.\n\n"
        f"Contexto disponible:\n{compact_context}\n\n"
        f"Pregunta del usuario:\n{question}"
    )


def extract_gemini_text(response_data):
    candidates = response_data.get("candidates") or []
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts") or []
    text_parts = [part.get("text", "") for part in parts if part.get("text")]
    return "\n".join(text_parts).strip()


def build_dashboard_context(db):
    data = build_dashboard_json(db)

    dashboard_metrics = [
        {
            "label": "Clientes",
            "value": data["kpis"]["clients"],
            "pill": data["routeId"],
            "pill_class": "",
        },
        {
            "label": "Paradas optimizadas",
            "value": data["kpis"]["optimizedStops"],
            "pill": data["impactSummary"]["stopsReduction"],
            "pill_class": "status-success",
        },
        {
            "label": "Ocupación",
            "value": f'{data["kpis"]["loadUsage"]}%',
            "pill": f'{data["truck"]["pallets"]} palets',
            "pill_class": "",
        },
        {
            "label": "Retornables",
            "value": f'{data["kpis"]["returnablesCapacity"]}%',
            "pill": "zona reservada",
            "pill_class": "status-warning",
        },
    ]

    impact_rows = data["impact"]

    return {
        "dashboard_data": data,
        "dashboard_metrics": dashboard_metrics,
        "impact_rows": impact_rows,
    }


def build_dashboard_json(db):
    headers = get_transport_headers(db)

    client_ids = {
        h.get("destinatario_mcia")
        for h in headers
        if h.get("destinatario_mcia") is not None
    }

    clients = len(client_ids)

    if clients == 0:
        clients = col(db, "direcciones").count_documents({})

    current_stops = clients
    optimized_stops = max(1, round(current_stops * 0.68)) if current_stops else 0

    stops_reduction = calculate_reduction_label(current_stops, optimized_stops)

    strict_windows = count_strict_delivery_windows(db)
    time_window_compliance = 94 if strict_windows else 82

    data = {
        "routeId": DEFAULT_ROUTE_ID,
        "scenario": "Barcelona Centro",
        "distributionCenter": DEFAULT_DDI,
        "date": DEFAULT_DATE,
        "truck": {
            "id": "TRUCK-06P",
            "type": "Camión urbano",
            "pallets": 6,
            "access": "lateral",
        },
        "kpis": {
            "clients": clients,
            "currentStops": current_stops,
            "optimizedStops": optimized_stops,
            "loadUsage": 82,
            "timeWindowCompliance": time_window_compliance,
            "returnablesCapacity": 76,
            "estimatedSearchTimeBefore": 70,
            "estimatedSearchTimeAfter": 42,
        },
        "impactSummary": {
            "stopsReduction": stops_reduction,
            "searchTimeReduction": "-40%",
            "timeWindowImprovement": "+12 pp",
        },
        "impact": [
            {
                "metric": "Paradas del camión",
                "current": current_stops,
                "proposal": optimized_stops,
                "impact": stops_reduction,
                "impact_class": "status-success",
            },
            {
                "metric": "Tiempo buscando producto",
                "current": "70 min",
                "proposal": "42 min",
                "impact": "-40%",
                "impact_class": "status-success",
            },
            {
                "metric": "Cumplimiento de franjas",
                "current": "82%",
                "proposal": f"{time_window_compliance}%",
                "impact": "+12 pp",
                "impact_class": "status-success",
            },
            {
                "metric": "Accesibilidad primeras entregas",
                "current": "Media",
                "proposal": "Alta",
                "impact": "Mejora",
                "impact_class": "status-success",
            },
            {
                "metric": "Ocupación del camión",
                "current": "84%",
                "proposal": "82%",
                "impact": "Trade-off aceptable",
                "impact_class": "status-warning",
            },
        ],
        "loadStatus": {
            "status": "optimal",
            "globalScore": 89,
            "accessibility": 91,
            "balance": 84,
            "occupation": 82,
            "returnables": 76,
            "manualChanges": 0,
            "warnings": 0,
        },
        "alerts": [
            {
                "level": "success",
                "title": "Plan de carga óptimo",
                "message": "La distribución actual coincide con el plan recomendado.",
            },
            {
                "level": "warning",
                "title": "Datos de coordenadas",
                "message": "Si no hay latitud/longitud real, el mapa usa coordenadas aproximadas por población.",
            },
        ],
    }

    return data


def get_transport_headers(db):
    projection = {
        "_id": 0,
        "entrega": 1,
        "no_transporte": 1,
        "creado_el": 1,
        "repartidor": 1,
        "unnamed_4": 1,
        "destinatario_mcia": 1,
        "destinatario_mcia1": 1,
    }

    docs = list(
        col(db, "cabecera").find(
            {"creado_el": DEFAULT_DATE},
            projection,
        ).limit(200)
    )

    if not docs:
        docs = list(col(db, "cabecera").find({}, projection).limit(200))

    return docs


def count_strict_delivery_windows(db):
    return col(db, "horarios").count_documents({
        "descripcion": DEFAULT_DDI,
        "$or": [
            {"cierre_si_no": None},
            {"cierre_si_no": ""},
            {"cierre_si_no": "N"},
            {"cierre_si_no": False},
        ],
        "horario_inicia_a": {
            "$nin": [None, "", "0:00:00", "00:00:00"]
        },
        "horario_termina_a": {
            "$nin": [None, "", "0:00:00", "00:00:00"]
        },
    })


def build_route_data(db):
    headers = get_transport_headers(db)
    directions = get_directions_by_client(db, headers)

    grouped = defaultdict(list)

    for header in headers:
        client_id = header.get("destinatario_mcia")
        direction = directions.get(client_id) or {}

        city = clean_text(direction.get("poblacion")) or "BARCELONA"
        grouped[city].append({
            "customerId": client_id,
            "name": header.get("destinatario_mcia1")
                    or direction.get("nombre_1")
                    or "Cliente sin nombre",
            "address": build_address(direction),
            "delivery": header.get("entrega"),
            "transport": header.get("no_transporte"),
        })

    stops = []
    selected_groups = list(grouped.items())[:5]

    if not selected_groups:
        selected_groups = get_fallback_route_groups()

    for index, (city, clients) in enumerate(selected_groups, start=1):
        coords = coords_for_city(city, index)

        stops.append({
            "number": index,
            "name": format_city_name(city),
            "coords": coords,
            "time": get_demo_time(index),
            "clients": [c["name"] for c in clients[:4]],
            "clientDetails": clients[:4],
            "loadZones": get_load_zones_for_stop(index),
            "note": get_route_note(index),
        })

    return {
        "routeId": DEFAULT_ROUTE_ID,
        "scenario": "Barcelona Centro",
        "distributionCenter": DEFAULT_DDI,
        "warehouse": {
            "name": "DDI MOLLET",
            "coords": [41.5402, 2.2135],
        },
        "summary": {
            "clients": sum(len(clients) for _, clients in selected_groups),
            "currentStops": sum(len(clients) for _, clients in selected_groups),
            "optimizedStops": len(stops),
            "distanceKm": 24.5,
            "estimatedTime": "3h 30m",
            "windowCompliance": 94,
        },
        "stops": stops,
    }


def get_directions_by_client(db, headers):
    client_ids = list({
        h.get("destinatario_mcia")
        for h in headers
        if h.get("destinatario_mcia") is not None
    })

    query_ids = client_ids + [str(c) for c in client_ids]

    docs = col(db, "direcciones").find(
        {"cliente": {"$in": query_ids}},
        {
            "_id": 0,
            "cliente": 1,
            "nombre_1": 1,
            "nombre_2": 1,
            "calle": 1,
            "cp": 1,
            "poblacion": 1,
            "latitud": 1,
            "longitud": 1,
            "lat": 1,
            "lng": 1,
        }
    )

    result = {}

    for doc in docs:
        key = doc.get("cliente")
        result[key] = doc

        try:
            result[int(key)] = doc
        except (TypeError, ValueError):
            pass

    return result


def build_load_plan(db):
    headers = get_transport_headers(db)[:12]
    materials = get_materials(db)

    zones = [
        {"zone": "P1", "label": "Primeras paradas", "packages": []},
        {"zone": "P2", "label": "Primeras paradas + pesado", "packages": []},
        {"zone": "P3", "label": "Ruta media", "packages": []},
        {"zone": "P4", "label": "Referencias agrupadas", "packages": []},
        {"zone": "P5", "label": "Reserva retornables", "packages": []},
        {"zone": "P6", "label": "Últimas paradas", "packages": []},
    ]

    for index, header in enumerate(headers, start=1):
        stop = min(ceil(index / 2), 12)
        zone = zone_for_stop(stop)
        package_type = type_for_stop(stop)

        material = materials[(index - 1) % len(materials)] if materials else {}

        package = {
            "id": f"pkg-{header.get('destinatario_mcia')}-{index}",
            "customerId": header.get("destinatario_mcia"),
            "client": header.get("destinatario_mcia1") or "Cliente",
            "product": material.get("numero_de_material") or "Pedido cliente",
            "material": material.get("material"),
            "quantity": "1 CAJ",
            "qty": "1 caja",
            "stop": stop,
            "idealZone": zone,
            "type": package_type,
            "reason": reason_for_package(stop, zone, header),
        }

        zone_doc = next(z for z in zones if z["zone"] == zone)
        zone_doc["packages"].append(package)

    p5 = next(z for z in zones if z["zone"] == "P5")
    p5["packages"].append({
        "id": "pkg-returnables-crates",
        "customerId": None,
        "client": "Retornables",
        "product": "Zona cajas vacías",
        "quantity": "Reservado",
        "qty": "Reservado",
        "stop": 0,
        "idealZone": "P5",
        "type": "return",
        "reason": "Espacio flexible para cajas vacías recogidas durante la ruta.",
    })

    return {
        "routeId": DEFAULT_ROUTE_ID,
        "truck": {
            "id": "TRUCK-06P",
            "type": "Camión urbano de 6 palets",
            "access": "lateral",
        },
        "status": "optimal",
        "zones": zones,
        "metrics": {
            "globalScore": 89,
            "accessibility": 91,
            "balance": 84,
            "occupation": 82,
            "returnables": 76,
        },
    }


def get_materials(db):
    docs = list(
        col(db, "materiales").find(
            {},
            {
                "_id": 0,
                "material": 1,
                "numero_de_material": 1,
                "ubic": 1,
                "umb": 1,
            }
        ).limit(30)
    )

    if not docs:
        docs = list(
            col(db, "detalle").find(
                {},
                {
                    "_id": 0,
                    "material": 1,
                    "numero_de_material": 1,
                    "ubic": 1,
                    "umb": 1,
                }
            ).limit(30)
        )

    return docs


def calculate_reduction_label(current, proposal):
    if not current:
        return "0%"

    reduction = round(((current - proposal) / current) * 100)
    return f"-{reduction}%"


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip().upper()


def format_city_name(city):
    city = clean_text(city)

    if not city:
        return "Zona reparto"

    return city.title()


def build_address(direction):
    if not direction:
        return ""

    parts = [
        direction.get("calle"),
        direction.get("cp"),
        direction.get("poblacion"),
    ]

    return ", ".join(str(p) for p in parts if p not in [None, ""])


def coords_for_city(city, index):
    city_clean = clean_text(city)

    base = CITY_COORDS.get(city_clean)

    if not base:
        for key, coords in CITY_COORDS.items():
            if key in city_clean or city_clean in key:
                base = coords
                break

    if not base:
        base = CITY_COORDS["BARCELONA"]

    offset_lat = ((index % 3) - 1) * 0.012
    offset_lng = ((index % 2) - 0.5) * 0.018

    return [
        round(base[0] + offset_lat, 6),
        round(base[1] + offset_lng, 6),
    ]


def get_demo_time(index):
    times = ["08:15", "09:05", "10:10", "11:00", "12:20", "13:10"]
    return times[(index - 1) % len(times)]


def get_load_zones_for_stop(index):
    if index == 1:
        return ["P1", "P2"]
    if index == 2:
        return ["P2"]
    if index == 3:
        return ["P2", "P3"]
    if index == 4:
        return ["P3"]
    return ["P3", "P4"]


def get_route_note(index):
    notes = {
        1: "Primera parada agrupada. Productos muy accesibles.",
        2: "Clientes cercanos con franja compatible.",
        3: "Franja estricta. Parada prioritaria.",
        4: "Recogida prevista de retornables.",
    }

    return notes.get(index, "Parada de ruta media con carga agrupada.")


def zone_for_stop(stop):
    if stop <= 1:
        return "P1"
    if stop <= 2:
        return "P2"
    if stop <= 5:
        return "P3"
    if stop <= 8:
        return "P4"
    return "P6"


def type_for_stop(stop):
    if stop <= 2:
        return "early"
    if stop <= 5:
        return "mid"
    if stop <= 8:
        return "reference"
    return "late"


def reason_for_package(stop, zone, header):
    client = header.get("destinatario_mcia1") or "cliente"

    if zone in ["P1", "P2"]:
        return f"{client} pertenece a una parada temprana. Debe estar en zona accesible para reducir tiempo de descarga."

    if zone == "P3":
        return f"{client} pertenece a una parada de ruta media. Se prioriza equilibrio y accesibilidad moderada."

    if zone == "P4":
        return f"{client} se agrupa con referencias de alta rotación para facilitar preparación de almacén."

    return f"{client} pertenece a una parada tardía. Puede ocupar zonas menos prioritarias."
