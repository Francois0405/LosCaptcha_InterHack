from django.shortcuts import render

def dashboard(request):
    return render(request, "dashboard.html")

def distribucion(request):
    return render(request, "distribucion.html")

def mapa(request):
    return render(request, "mapa.html")