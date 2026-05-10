from collections import defaultdict
import json
from math import ceil
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import time

from .mapa import build_route_data_for_frontend

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
LOAD_CAPACITY_UNITS = 110

ROUTE_CACHE = {
    "data": None,
    "timestamp": 0,
}

CACHE_SECONDS = 600


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


def distribucion(request):
    db = get_mongo_db()
    load_plan = build_load_plan(db)

    return render(request, "distribucion.html", {
        "load_plan": load_plan,
    })


def api_dashboard(request):
    db = get_mongo_db()
    return JsonResponse(build_dashboard_json(db), safe=False)


def get_cached_route_data(db):
    now = time.time()

    try:
        if ROUTE_CACHE["data"] is None or now - ROUTE_CACHE["timestamp"] > CACHE_SECONDS:
            calculated_route = build_route_data_for_frontend(db=db)

            if calculated_route:
                ROUTE_CACHE["data"] = calculated_route
                ROUTE_CACHE["timestamp"] = now

        return ROUTE_CACHE["data"] or build_route_data(db)

    except Exception as exc:
        print(f"Error calculando ruta con OR-Tools: {exc}")
        return build_route_data(db)


def mapa(request):
    db = get_mongo_db()
    route_data = get_cached_route_data(db)

    return render(request, "mapa.html", {
        "route_data": route_data,
    })


def api_route(request):
    db = get_mongo_db()
    return JsonResponse(get_cached_route_data(db), safe=False)


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
    route_data = get_cached_route_data(db) or build_route_data(db)
    load_plan = build_load_plan(db)
    route_summary = route_data.get("summary") or {}
    load_summary = load_plan.get("summary") or {}
    load_metrics = load_plan.get("metrics") or {}

    clients = route_summary.get("clients") or load_summary.get("clients") or 0
    current_stops = route_summary.get("currentStops") or len(route_data.get("stops") or [])
    optimized_stops = route_summary.get("optimizedStops") or current_stops

    stops_reduction = calculate_reduction_label(current_stops, optimized_stops)

    time_window_compliance = route_summary.get("windowCompliance") or 0
    load_usage = load_metrics.get("occupation", 0)
    returnables_capacity = load_metrics.get("returnables", 0)
    accessibility = load_metrics.get("accessibility", 0)
    balance = load_metrics.get("balance", 0)
    global_score = load_metrics.get("globalScore", 0)
    package_count = load_summary.get("packages") or sum(
        len(zone.get("packages") or [])
        for zone in load_plan.get("zones", [])
    )

    data = {
        "routeId": route_data.get("routeId") or DEFAULT_ROUTE_ID,
        "scenario": route_data.get("scenario") or "Ruta actual",
        "distributionCenter": route_data.get("distributionCenter") or DEFAULT_DDI,
        "date": DEFAULT_DATE,
        "truck": load_plan.get("truck") or {
            "id": "TRUCK-06P",
            "type": "Camión urbano",
            "pallets": 6,
            "access": "lateral",
        },
        "kpis": {
            "clients": clients,
            "currentStops": current_stops,
            "optimizedStops": optimized_stops,
            "loadUsage": load_usage,
            "timeWindowCompliance": time_window_compliance,
            "returnablesCapacity": returnables_capacity,
            "packages": package_count,
        },
        "impactSummary": {
            "stopsReduction": stops_reduction,
            "loadTraceability": f"{package_count} líneas",
            "timeWindowCompliance": f"{time_window_compliance}%",
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
                "metric": "Líneas de carga asignadas",
                "current": package_count,
                "proposal": "P1-P6",
                "impact": "Trazable",
                "impact_class": "status-success",
            },
            {
                "metric": "Cumplimiento de franjas",
                "current": "Calculado en ruta",
                "proposal": f"{time_window_compliance}%",
                "impact": "Visible",
                "impact_class": "status-success",
            },
            {
                "metric": "Accesibilidad primeras entregas",
                "current": "Carga actual",
                "proposal": f"{accessibility}%",
                "impact": "Validado",
                "impact_class": "status-success",
            },
            {
                "metric": "Ocupación del camión",
                "current": "Carga calculada",
                "proposal": f"{load_usage}%",
                "impact": f"Balance {balance}%",
                "impact_class": "status-warning",
            },
        ],
        "loadStatus": {
            "status": load_plan.get("status") or "optimal",
            "globalScore": global_score,
            "accessibility": accessibility,
            "balance": balance,
            "occupation": load_usage,
            "returnables": returnables_capacity,
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

    warehouse = {
        "name": "DDI MOLLET",
        "coords": [41.5402, 2.2135],
    }
    route_points = [warehouse["coords"]] + [stop["coords"] for stop in stops] + [warehouse["coords"]]

    return {
        "routeId": DEFAULT_ROUTE_ID,
        "scenario": "Barcelona Centro",
        "distributionCenter": DEFAULT_DDI,
        "warehouse": warehouse,
        "routePoints": route_points,
        "returnToWarehouse": {
            "name": warehouse["name"],
            "coords": warehouse["coords"],
            "time": "13:45",
            "note": "Regreso al almacén para descargar retornables y cerrar la ruta.",
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
    route_data = get_cached_route_data(db) or {}
    route_stops = route_data.get("stops") or []

    zones = [
        {"zone": "P1", "label": "Primeras paradas", "packages": []},
        {"zone": "P2", "label": "Primeras paradas + pesado", "packages": []},
        {"zone": "P3", "label": "Ruta media", "packages": []},
        {"zone": "P4", "label": "Referencias agrupadas", "packages": []},
        {"zone": "P5", "label": "Reserva retornables", "packages": []},
        {"zone": "P6", "label": "Últimas paradas", "packages": []},
    ]

    route_packages = []

    for stop in route_stops:
        clients = stop.get("clients") or [stop.get("name")]

        for client_name in clients:
            route_packages.append({
                "customerId": stop.get("customerId"),
                "client": client_name or stop.get("name") or "Cliente",
                "delivery": stop.get("delivery"),
                "transport": stop.get("transport"),
                "routeCode": stop.get("routeCode"),
                "date": stop.get("date"),
                "stop": stop.get("number") or len(route_packages) + 1,
                "loadZones": stop.get("loadZones") or [],
                "routeNote": stop.get("note") or "",
            })

    if not route_packages:
        for index, header in enumerate(get_transport_headers(db)[:5], start=1):
            route_packages.append({
                "customerId": header.get("destinatario_mcia"),
                "client": header.get("destinatario_mcia1") or "Cliente",
                "stop": min(ceil(index / 2), 12),
                "loadZones": [],
                "routeNote": "",
            })

    total_products = 0

    for index, route_package in enumerate(route_packages, start=1):
        stop = route_package["stop"]
        product_rows = get_route_product_rows(db, route_package)

        for detail_index, detail in enumerate(product_rows, start=1):
            total_products += 1
            package = build_package_from_detail(route_package, detail, index, detail_index)
            zone_doc = next(z for z in zones if z["zone"] == package["idealZone"])
            zone_doc["packages"].append(package)

        if not product_rows:
            package = build_fallback_package_for_route_client(route_package, index)
            total_products += 1
            zone_doc = next(z for z in zones if z["zone"] == package["idealZone"])
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
        "loadUnits": 0,
        "reason": "Espacio flexible para cajas vacías recogidas durante la ruta.",
    })

    metrics = calculate_load_metrics(zones)
    route_clients = len({
        str(package.get("customerId") or package.get("client"))
        for package in route_packages
    })
    first_stop = next((stop for stop in route_stops if stop.get("number") == 1), None)

    return {
        "routeId": route_data.get("routeId") or DEFAULT_ROUTE_ID,
        "basedOnStops": [
            {
                "number": stop.get("number"),
                "name": stop.get("name"),
                "customerId": stop.get("customerId"),
                "delivery": stop.get("delivery"),
                "transport": stop.get("transport"),
                "routeCode": stop.get("routeCode"),
                "date": stop.get("date"),
                "time": stop.get("time"),
                "clients": stop.get("clients") or [],
                "loadZones": stop.get("loadZones") or [],
            }
            for stop in route_stops
        ],
        "returnToWarehouse": route_data.get("returnToWarehouse"),
        "truck": {
            "id": "TRUCK-06P",
            "type": "Camión urbano de 6 palets",
            "pallets": 6,
            "access": "lateral",
        },
        "status": "optimal",
        "zones": zones,
        "summary": {
            "stops": len(route_stops) or len(route_packages),
            "clients": route_clients,
            "packages": total_products,
            "origin": route_data.get("distributionCenter") or DEFAULT_DDI,
            "firstStopName": first_stop.get("name") if first_stop else (route_packages[0].get("client") if route_packages else "Primera parada"),
            "firstStopTime": first_stop.get("time") if first_stop else "--:--",
            "firstStopClients": len(first_stop.get("clients") or []) if first_stop else 1,
        },
        "metrics": metrics,
    }


def get_route_product_rows(db, route_package, per_client_limit=6):
    query = build_detail_query_for_route_package(route_package)

    if not query:
        return []

    projection = {
        "_id": 0,
        "entrega": 1,
        "material": 1,
        "denominacion": 1,
        "cantidad_entrega": 1,
        "unmedida_venta": 1,
        "destinatario_mcia1": 1,
        "nombre_1": 1,
        "ruta": 1,
        "transporte": 1,
        "fecha": 1,
    }

    total_matches = col(db, "detalle").count_documents(query)
    rows = list(col(db, "detalle").find(query, projection).limit(per_client_limit + 1))

    if not rows:
        fallback_query = build_detail_query_for_route_package(route_package, include_delivery=False)
        if fallback_query and fallback_query != query:
            query = fallback_query
            total_matches = col(db, "detalle").count_documents(query)
            rows = list(col(db, "detalle").find(query, projection).limit(per_client_limit + 1))

    if len(rows) <= per_client_limit:
        return rows

    visible_rows = rows[:per_client_limit]
    visible_rows.append({
        "material": "AGRUPADO",
        "denominacion": f"Otros productos de {route_package.get('client')}",
        "cantidad_entrega": max(total_matches - per_client_limit, 1),
        "unmedida_venta": "refs",
        "nombre_1": route_package.get("client"),
    })
    return visible_rows


def build_detail_query_for_route_package(route_package, include_delivery=True):
    conditions = []
    delivery_conditions = []
    customer_id = route_package.get("customerId")
    client_name = route_package.get("client")
    delivery = route_package.get("delivery")
    transport = route_package.get("transport")

    if customer_id not in [None, ""]:
        conditions.append({"destinatario_mcia1": customer_id})
        conditions.append({"destinatario_mcia1": str(customer_id)})

        try:
            conditions.append({"destinatario_mcia1": int(customer_id)})
        except (TypeError, ValueError):
            pass

    if client_name:
        conditions.append({"nombre_1": client_name})

    if not conditions:
        return {}

    for field, value in [("entrega", delivery), ("transporte", transport)]:
        if value in [None, ""]:
            continue

        delivery_conditions.append({field: value})
        delivery_conditions.append({field: str(value)})

        try:
            delivery_conditions.append({field: int(value)})
        except (TypeError, ValueError):
            pass

    if include_delivery and delivery_conditions:
        return {
            "$and": [
                {"$or": conditions},
                {"$or": delivery_conditions},
            ]
        }

    return {"$or": conditions}


def build_package_from_detail(route_package, detail, route_index, detail_index):
    stop = route_package["stop"]
    package_type = type_for_detail(stop, detail)
    zone = zone_for_route_product(stop, package_type)
    product_name = detail.get("denominacion") or detail.get("material") or "Producto de la ruta"

    return {
        "id": f"pkg-{route_package.get('customerId') or clean_slug(route_package.get('client'))}-{route_index}-{detail_index}",
        "customerId": route_package.get("customerId") or detail.get("destinatario_mcia1"),
        "client": route_package.get("client") or detail.get("nombre_1") or "Cliente",
        "product": product_name,
        "material": detail.get("material"),
        "quantity": format_detail_quantity(detail),
        "qty": format_detail_quantity(detail),
        "stop": stop,
        "idealZone": zone,
        "type": package_type,
        "loadUnits": quantity_to_units(detail),
        "reason": reason_for_product_package(stop, zone, route_package, detail),
    }


def build_fallback_package_for_route_client(route_package, route_index):
    stop = route_package["stop"]
    package_type = type_for_stop(stop)
    zone = zone_for_stop(stop)

    return {
        "id": f"pkg-{route_package.get('customerId') or clean_slug(route_package.get('client'))}-{route_index}",
        "customerId": route_package.get("customerId"),
        "client": route_package.get("client") or "Cliente",
        "product": "Pedido de cliente sin detalle de material",
        "material": None,
        "quantity": "1 entrega",
        "qty": "1 entrega",
        "stop": stop,
        "idealZone": zone,
        "type": package_type,
        "loadUnits": 1,
        "reason": reason_for_route_package(stop, zone, route_package),
    }


def calculate_load_metrics(zones):
    packages = [
        {
            **package,
            "currentZone": zone.get("zone"),
        }
        for zone in zones
        for package in zone.get("packages", [])
    ]

    delivery_packages = [package for package in packages if package.get("type") != "return"]
    early_packages = [
        package for package in delivery_packages
        if package.get("type") in ["early", "heavy"] or safe_int(package.get("stop")) <= 2
    ]
    heavy_packages = [
        package for package in delivery_packages
        if package.get("type") == "heavy"
    ]
    return_packages = [
        package for package in packages
        if package.get("type") == "return"
    ]

    accessibility = percentage(
        len([package for package in early_packages if package.get("currentZone") in ["P1", "P2"]]),
        len(early_packages),
        default=100,
    )
    balance = percentage(
        len([package for package in heavy_packages if package.get("currentZone") in ["P2", "P3"]]),
        len(heavy_packages),
        default=100,
    )
    returnables = percentage(
        len([package for package in return_packages if package.get("currentZone") == "P5"]),
        len(return_packages),
        default=100,
    )
    occupied_units = sum(
        quantity
        for quantity in [package.get("loadUnits", 0) for package in delivery_packages]
        if isinstance(quantity, (int, float))
    )
    occupation = min(100, round((occupied_units / LOAD_CAPACITY_UNITS) * 100)) if occupied_units else 0
    optimality = percentage(
        len([package for package in packages if package.get("currentZone") == package.get("idealZone")]),
        len(packages),
        default=100,
    )
    global_score = round(
        accessibility * 0.38 +
        balance * 0.20 +
        occupation * 0.18 +
        returnables * 0.14 +
        optimality * 0.10
    )

    return {
        "globalScore": global_score,
        "accessibility": accessibility,
        "balance": balance,
        "occupation": occupation,
        "returnables": returnables,
    }


def percentage(part, total, default=0):
    if not total:
        return default

    return round((part / total) * 100)


def quantity_to_units(detail):
    if detail.get("material") == "AGRUPADO":
        return 0

    quantity = detail.get("cantidad_entrega")

    try:
        return max(0, float(quantity))
    except (TypeError, ValueError):
        return 1


def format_detail_quantity(detail):
    quantity = detail.get("cantidad_entrega")
    unit = detail.get("unmedida_venta") or "uds"

    if quantity is None:
        return unit

    try:
        numeric = float(quantity)
        quantity_text = str(int(numeric)) if numeric.is_integer() else str(round(numeric, 2))
    except (TypeError, ValueError):
        quantity_text = str(quantity)

    return f"{quantity_text} {unit}"


def type_for_detail(stop, detail):
    product = clean_text(detail.get("denominacion") or detail.get("material"))
    unit = clean_text(detail.get("unmedida_venta"))

    if "BARRIL" in product or unit == "BRL":
        return "heavy"

    if stop <= 2:
        return "early"

    if stop <= 5:
        return "mid"

    if stop <= 8:
        return "reference"

    return "late"


def zone_for_route_product(stop, package_type):
    if package_type == "heavy":
        return "P2" if stop <= 2 else "P3"

    return zone_for_stop(stop)


def reason_for_product_package(stop, zone, route_package, detail):
    product = detail.get("denominacion") or detail.get("material") or "Producto"
    client = route_package.get("client") or "cliente"

    if detail.get("material") == "AGRUPADO":
        return f"Resto de referencias reales de {client} agrupadas para mantener la pantalla operativa."

    if zone in ["P1", "P2"]:
        return f"{product} pertenece a {client}, parada {stop}. Debe ir accesible para la primera descarga."

    if zone == "P3":
        return f"{product} pertenece a {client}, ruta media. Se coloca en zona equilibrada y accesible."

    if zone == "P4":
        return f"{product} pertenece a {client}, parada avanzada. Se agrupa para no bloquear primeras entregas."

    return f"{product} pertenece a {client}, última parte de la ruta. Puede ocupar una zona menos prioritaria."


def clean_slug(value):
    return clean_text(value).lower().replace(" ", "-") or "cliente"


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


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def reason_for_route_package(stop, zone, route_package):
    client = route_package.get("client") or "cliente"
    route_note = route_package.get("routeNote")

    if zone in ["P1", "P2"]:
        return f"{client} sale en la parada {stop} del mapa. Debe estar en zona accesible para reducir tiempo de descarga."

    if zone == "P3":
        return f"{client} pertenece a una parada media del mapa. Se prioriza equilibrio y accesibilidad moderada."

    if zone == "P4":
        return f"{client} pertenece a una parada avanzada del mapa. Se agrupa para no bloquear las primeras entregas."

    if route_note:
        return route_note

    return f"{client} pertenece a una parada tardía del mapa. Puede ocupar zonas menos prioritarias."


def get_fallback_route_groups():
    return [
        (
            "MOLLET",
            [
                {
                    "customerId": "demo-1",
                    "name": "IBERICUS CENTRAL",
                    "address": "Mollet del Vallès",
                    "delivery": "DEMO-001",
                    "transport": "DR-042",
                },
                {
                    "customerId": "demo-2",
                    "name": "BAR LA PETRA II",
                    "address": "Mollet del Vallès",
                    "delivery": "DEMO-002",
                    "transport": "DR-042",
                },
            ],
        ),
        (
            "GRANOLLERS",
            [
                {
                    "customerId": "demo-3",
                    "name": "FRANKFURT LEO BOECK GRANOLLERS",
                    "address": "Granollers",
                    "delivery": "DEMO-003",
                    "transport": "DR-042",
                },
                {
                    "customerId": "demo-4",
                    "name": "SUSHI HE GRANOLLERS",
                    "address": "Granollers",
                    "delivery": "DEMO-004",
                    "transport": "DR-042",
                },
            ],
        ),
        (
            "VIC",
            [
                {
                    "customerId": "demo-5",
                    "name": "CANTINA IES VIC ST TOMAS",
                    "address": "Vic",
                    "delivery": "DEMO-005",
                    "transport": "DR-042",
                },
            ],
        ),
    ]
