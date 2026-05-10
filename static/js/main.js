document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initRouteMap();
  initLoadDistribution();
  initDragAndDrop();
  initChatDrawer();
  initChatbot();
  initSuggestions();
});

/* =========================
   DJANGO JSON DATA
========================= */
function readJsonScript(id) {
  const element = document.getElementById(id);
  if (!element) return null;

  try {
    return JSON.parse(element.textContent);
  } catch (error) {
    console.warn(`No se pudo leer el JSON embebido: ${id}`, error);
    return null;
  }
}

/* =========================
   DARK / LIGHT MODE
========================= */
function initTheme() {
  const html = document.documentElement;
  const buttons = document.querySelectorAll("[data-theme-toggle]");

  const savedTheme = localStorage.getItem("damm-theme") || "light";
  applyTheme(savedTheme);

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const currentTheme = html.getAttribute("data-bs-theme") || "light";
      const nextTheme = currentTheme === "dark" ? "light" : "dark";
      applyTheme(nextTheme);
    });
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-bs-theme", theme);
  document.body.setAttribute("data-bs-theme", theme);
  localStorage.setItem("damm-theme", theme);

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.textContent = theme === "dark" ? "Modo claro" : "Modo oscuro";
  });
}

/* =========================
   LOAD PLAN DATA
========================= */
const backendLoadPlan = readJsonScript("load-plan-data");

const MOCK_OPTIMAL_LOAD_PLAN = [
  {
    zone: "P1",
    label: "Primeras paradas",
    packages: [
      {
        id: "pkg-bar-sol",
        client: "Bar Sol",
        product: "Estrella Damm",
        qty: "8 cajas",
        stop: 1,
        idealZone: "P1",
        type: "early",
        reason: "Primera parada: debe estar en zona lateral accesible."
      },
      {
        id: "pkg-cafe-centre",
        client: "Café Centre",
        product: "Veri",
        qty: "4 cajas",
        stop: 1,
        idealZone: "P1",
        type: "early",
        reason: "Mismo punto operativo que Bar Sol; conviene descargar junto."
      }
    ]
  },
  {
    zone: "P2",
    label: "Primeras paradas + pesado",
    packages: [
      {
        id: "pkg-restaurant-mar",
        client: "Restaurant Mar",
        product: "Barril",
        qty: "2 unidades",
        stop: 1,
        idealZone: "P2",
        type: "heavy",
        reason: "Producto pesado de primera parada: accesible y equilibrado."
      },
      {
        id: "pkg-hotel-nord",
        client: "Hotel Nord",
        product: "Cajas Damm",
        qty: "6 cajas",
        stop: 2,
        idealZone: "P2",
        type: "early",
        reason: "Segunda parada: debe mantenerse cerca del lateral."
      }
    ]
  },
  {
    zone: "P3",
    label: "Ruta media",
    packages: [
      {
        id: "pkg-bar-mercat",
        client: "Bar Mercat",
        product: "Cajas retornables",
        qty: "7 cajas",
        stop: 4,
        idealZone: "P3",
        type: "mid",
        reason: "Ruta media: accesibilidad moderada sin bloquear primeras entregas."
      },
      {
        id: "pkg-restaurant-port",
        client: "Restaurant Port",
        product: "Cajas mixtas",
        qty: "12 cajas",
        stop: 5,
        idealZone: "P3",
        type: "mid",
        reason: "Volumen alto de ruta media: conviene agruparlo en zona central."
      }
    ]
  },
  {
    zone: "P4",
    label: "Referencias agrupadas",
    packages: [
      {
        id: "pkg-high-rotation",
        client: "Stock por referencia",
        product: "Alta rotación Damm",
        qty: "Agrupado",
        stop: 7,
        idealZone: "P4",
        type: "reference",
        reason: "Producto de alta rotación: se mantiene agrupado por referencia."
      },
      {
        id: "pkg-veri-reference",
        client: "Stock por referencia",
        product: "Veri",
        qty: "Agrupado",
        stop: 8,
        idealZone: "P4",
        type: "reference",
        reason: "Referencia común: se prioriza eficiencia de almacén."
      }
    ]
  },
  {
    zone: "P5",
    label: "Reserva retornables",
    packages: [
      {
        id: "pkg-empty-crates",
        client: "Retornables",
        product: "Zona cajas vacías",
        qty: "Reservado",
        stop: 0,
        idealZone: "P5",
        type: "return",
        reason: "Espacio flexible para cajas vacías recogidas durante la ruta."
      },
      {
        id: "pkg-empty-kegs",
        client: "Retornables",
        product: "Barriles vacíos",
        qty: "Reservado",
        stop: 0,
        idealZone: "P5",
        type: "return",
        reason: "Reserva para barriles vacíos y logística inversa."
      }
    ]
  },
  {
    zone: "P6",
    label: "Últimas paradas",
    packages: [
      {
        id: "pkg-late-stops",
        client: "Últimas paradas",
        product: "Referencias secundarias",
        qty: "Mixto",
        stop: 12,
        idealZone: "P6",
        type: "late",
        reason: "Últimas paradas: puede ocupar zonas menos prioritarias."
      }
    ]
  }
];

let optimalLoadPlan = normalizeLoadPlan(backendLoadPlan?.zones || MOCK_OPTIMAL_LOAD_PLAN);
let currentLoadPlan = clonePlan(optimalLoadPlan);
let lastMovedPackage = null;

function normalizeLoadPlan(zones) {
  const validZones = ["P1", "P2", "P3", "P4", "P5", "P6"];

  const normalized = validZones.map((zone) => {
    const existingZone = zones.find((item) => item.zone === zone) || {
      zone,
      label: getZonePrintLabel(zone),
      packages: []
    };

    return {
      zone,
      label: existingZone.label || getZonePrintLabel(zone),
      packages: (existingZone.packages || []).map((pkg, index) => {
        const type = pkg.type || inferTypeFromZone(zone);
        const stop = Number(pkg.stop || 0);

        return {
          id: String(pkg.id || `pkg-${zone}-${index + 1}`),
          customerId: pkg.customerId || pkg.deudor || pkg.clientId || null,
          client: pkg.client || pkg.name || pkg.nombre_1 || "Cliente",
          product: pkg.product || pkg.numero_de_material || pkg.material || "Producto",
          qty: pkg.qty || pkg.quantity || pkg.cantidad || "1 caja",
          quantity: pkg.quantity || pkg.qty || pkg.cantidad || "1 caja",
          stop,
          idealZone: pkg.idealZone || zone,
          type,
          reason: pkg.reason || reasonForZone(zone, type)
        };
      })
    };
  });

  return normalized;
}

function inferTypeFromZone(zone) {
  if (zone === "P1" || zone === "P2") return "early";
  if (zone === "P3") return "mid";
  if (zone === "P4") return "reference";
  if (zone === "P5") return "return";
  return "late";
}

function reasonForZone(zone, type) {
  if (type === "return" || zone === "P5") {
    return "Zona reservada para retornables y logística inversa.";
  }

  if (zone === "P1" || zone === "P2") {
    return "Producto asignado a una zona accesible para las primeras paradas.";
  }

  if (zone === "P3") {
    return "Producto de ruta media con accesibilidad moderada.";
  }

  if (zone === "P4") {
    return "Producto agrupado por referencia para facilitar preparación de almacén.";
  }

  return "Producto de últimas paradas en zona menos prioritaria.";
}

/* =========================
   LOAD DISTRIBUTION
========================= */
function initLoadDistribution() {
  const truckGrid = document.getElementById("truckGrid");
  if (!truckGrid) return;

  renderLoadPlan(currentLoadPlan);
  renderDriverTable();
  updateEvaluation();

  const calculateButton = document.getElementById("calculateLoadBtn");
  if (calculateButton) {
    calculateButton.addEventListener("click", () => {
      currentLoadPlan = clonePlan(optimalLoadPlan);
      lastMovedPackage = null;
      renderLoadPlan(currentLoadPlan);
      renderDriverTable();
      updateEvaluation();
      appendMessage("assistant", "Se ha recalculado el plan óptimo. Las primeras paradas vuelven a P1/P2, la zona P5 queda reservada para retornables y las referencias de alta rotación permanecen agrupadas en P4.");
      openChatDrawer();
    });
  }

  const resetButton = document.getElementById("resetOptimalBtn");
  if (resetButton) {
    resetButton.addEventListener("click", () => {
      currentLoadPlan = clonePlan(optimalLoadPlan);
      lastMovedPackage = null;
      renderLoadPlan(currentLoadPlan);
      renderDriverTable();
      updateEvaluation();
    });
  }

  const validateButton = document.getElementById("validateChangesBtn");
  if (validateButton) {
    validateButton.addEventListener("click", () => {
      const evaluation = evaluateCurrentPlan();

      if (evaluation.isOptimal) {
        appendMessage("assistant", "La distribución actual coincide con el plan óptimo calculado. Puede validarse sin penalizaciones operativas.");
      } else {
        appendMessage("assistant", `La distribución actual ha sido modificada. Score global: ${evaluation.globalScore}%. Revisa las alertas porque algunos productos ya no están en su zona recomendada.`);
      }

      openChatDrawer();
    });
  }

  const printButton = document.getElementById("printLoadBtn");
  if (printButton) {
    printButton.addEventListener("click", () => {
      printCurrentLoadSheet();
    });
  }
}

function clonePlan(plan) {
  return JSON.parse(JSON.stringify(plan));
}

function renderLoadPlan(plan) {
  document.querySelectorAll(".pallet-zone").forEach((zone) => {
    zone.querySelectorAll(".package-card").forEach((card) => card.remove());
  });

  plan.forEach((zoneData) => {
    const zone = document.querySelector(`.pallet-zone[data-zone="${zoneData.zone}"]`);
    if (!zone) return;

    zoneData.packages.forEach((pkg) => {
      zone.appendChild(createPackageCard(pkg, zoneData.zone));
    });
  });
}

function createPackageCard(pkg, currentZone) {
  const card = document.createElement("div");
  card.className = "package-card";
  card.draggable = true;
  card.dataset.packageId = pkg.id;
  card.dataset.idealZone = pkg.idealZone;
  card.dataset.currentZone = currentZone;
  card.dataset.type = pkg.type;
  card.dataset.stop = pkg.stop;

  if (currentZone !== pkg.idealZone) {
    card.classList.add("not-optimal");
  }

  const status = currentZone === pkg.idealZone ? "Óptimo" : "Modificado";

  card.innerHTML = `
    <strong>${escapeHTML(pkg.client)}</strong><br>
    <small>${escapeHTML(pkg.product)} · ${escapeHTML(pkg.qty || pkg.quantity)}</small>
    <div class="package-meta">
      <span class="package-tag">Parada ${pkg.stop || "retorno"}</span>
      <span class="package-tag">Ideal: ${pkg.idealZone}</span>
      <span class="package-tag">${status}</span>
    </div>
  `;

  return card;
}

function syncPlanFromDom() {
  const zones = ["P1", "P2", "P3", "P4", "P5", "P6"];

  const newPlan = zones.map((zone) => ({
    zone,
    label: getZonePrintLabel(zone),
    packages: []
  }));

  document.querySelectorAll(".package-card").forEach((card) => {
    const zoneElement = card.closest(".pallet-zone");
    if (!zoneElement) return;

    const currentZone = zoneElement.dataset.zone;
    const pkg = findPackageById(card.dataset.packageId);

    if (!pkg) return;

    const target = newPlan.find((item) => item.zone === currentZone);
    target.packages.push(pkg);
  });

  currentLoadPlan = newPlan;
}

function findPackageById(id) {
  return optimalLoadPlan
    .flatMap((zone) => zone.packages)
    .find((pkg) => pkg.id === id);
}

/* =========================
   EVALUATION
========================= */
function evaluateCurrentPlan() {
  const packages = [];

  currentLoadPlan.forEach((zone) => {
    zone.packages.forEach((pkg) => {
      packages.push({
        ...pkg,
        currentZone: zone.zone,
        isOptimal: zone.zone === pkg.idealZone
      });
    });
  });

  const total = packages.length || 1;
  const optimalCount = packages.filter((pkg) => pkg.isOptimal).length;

  const earlyPackages = packages.filter((pkg) => pkg.type === "early" || pkg.type === "heavy");
  const accessibleEarly = earlyPackages.filter((pkg) => ["P1", "P2"].includes(pkg.currentZone)).length;

  const returnPackages = packages.filter((pkg) => pkg.type === "return");
  const returnsInP5 = returnPackages.filter((pkg) => pkg.currentZone === "P5").length;

  const heavyPackages = packages.filter((pkg) => pkg.type === "heavy");
  const heavyBalanced = heavyPackages.filter((pkg) => ["P2", "P3"].includes(pkg.currentZone)).length;

  const accessibility = earlyPackages.length
    ? Math.round((accessibleEarly / earlyPackages.length) * 100)
    : 100;

  const returnCapacity = returnPackages.length
    ? Math.round((returnsInP5 / returnPackages.length) * 100)
    : 76;

  const balance = heavyPackages.length
    ? Math.round((heavyBalanced / heavyPackages.length) * 100)
    : 84;

  const occupation = backendLoadPlan?.metrics?.occupation || 82;
  const optimality = Math.round((optimalCount / total) * 100);

  const globalScore = Math.round(
    accessibility * 0.38 +
    balance * 0.20 +
    occupation * 0.18 +
    returnCapacity * 0.14 +
    optimality * 0.10
  );

  const warnings = buildWarnings(packages, {
    accessibility,
    returnCapacity,
    balance,
    optimality,
    globalScore
  });

  return {
    accessibility,
    returnCapacity,
    balance,
    occupation,
    optimality,
    globalScore,
    warnings,
    isOptimal: optimalCount === packages.length
  };
}

function buildWarnings(packages, scores) {
  const warnings = [];

  const moved = packages.filter((pkg) => !pkg.isOptimal);

  moved.forEach((pkg) => {
    if ((pkg.type === "early" || pkg.type === "heavy") && !["P1", "P2"].includes(pkg.currentZone)) {
      warnings.push({
        level: "danger",
        title: `${pkg.client} se ha movido fuera de zona accesible`,
        text: `Este producto pertenece a una parada temprana. Moverlo a ${pkg.currentZone} puede aumentar el tiempo de búsqueda y descarga. Zona recomendada: ${pkg.idealZone}.`
      });
    } else if (pkg.type === "return" && pkg.currentZone !== "P5") {
      warnings.push({
        level: "warning",
        title: "La zona de retornables ha sido modificada",
        text: `${pkg.product} debería mantenerse en P5. Si se mueve, puede bloquear productos pendientes o reducir espacio flexible para cajas vacías.`
      });
    } else if (pkg.type === "reference" && pkg.currentZone !== "P4") {
      warnings.push({
        level: "warning",
        title: "Referencia de alta rotación fuera de su grupo",
        text: `${pkg.product} se ha movido de P4. Esto puede complicar la preparación en almacén aunque no afecte tanto a la primera descarga.`
      });
    } else {
      warnings.push({
        level: "warning",
        title: `${pkg.client} se ha movido de su zona ideal`,
        text: `Ahora está en ${pkg.currentZone}, pero el plan óptimo lo recomienda en ${pkg.idealZone}. El plan sigue siendo posible, pero ya no es la distribución más eficiente.`
      });
    }
  });

  if (scores.globalScore < 75) {
    warnings.push({
      level: "danger",
      title: "La distribución pierde eficiencia operativa",
      text: "El score global ha bajado de forma relevante. Conviene recalcular o restaurar el plan óptimo."
    });
  }

  if (!warnings.length) {
    warnings.push({
      level: "success",
      title: "Sin alertas",
      text: "La distribución actual coincide con el plan óptimo calculado automáticamente."
    });
  }

  return warnings;
}

function updateEvaluation() {
  const evaluation = evaluateCurrentPlan();

  setText("accessibilityMetric", `${evaluation.accessibility}%`);
  setText("globalScoreMetric", `${evaluation.globalScore}%`);
  setText("accessibilityScoreText", `${evaluation.accessibility}%`);
  setText("balanceScoreText", `${evaluation.balance}%`);
  setText("occupationScoreText", `${evaluation.occupation}%`);
  setText("returnsScoreText", `${evaluation.returnCapacity}%`);

  setBar("accessibilityBar", evaluation.accessibility);
  setBar("balanceBar", evaluation.balance);
  setBar("occupationBar", evaluation.occupation);
  setBar("returnsBar", evaluation.returnCapacity);

  const scoreBadge = document.getElementById("scoreBadge");
  const layoutStatus = document.getElementById("layoutStatus");
  const globalPlanStatus = document.getElementById("globalPlanStatus");
  const impactAlert = document.getElementById("moveImpactAlert");
  const accessibilityBadge = document.getElementById("accessibilityBadge");

  if (evaluation.isOptimal) {
    setBadge(scoreBadge, "Óptimo", "status-pill status-success");
    setBadge(layoutStatus, "Distribución calculada automáticamente", "status-pill status-success");
    setBadge(globalPlanStatus, "Plan óptimo inicial", "status-pill status-success");
    setBadge(accessibilityBadge, "Primeras paradas", "status-pill status-success");

    if (impactAlert) {
      impactAlert.className = "impact-alert mt-4";
      impactAlert.innerHTML = `
        <div>
          <strong>Distribución inicial óptima.</strong>
          <span class="text-muted">
            Los productos de las primeras paradas están en zonas accesibles, los pesados están equilibrados y hay espacio reservado para retornables.
          </span>
        </div>
      `;
    }
  } else if (evaluation.globalScore >= 80) {
    setBadge(scoreBadge, "Modificado", "status-pill status-warning");
    setBadge(layoutStatus, "Plan modificado por el trabajador", "status-pill status-warning");
    setBadge(globalPlanStatus, "Ya no es el óptimo inicial", "status-pill status-warning");
    setBadge(accessibilityBadge, "Revisar cambios", "status-pill status-warning");

    if (impactAlert) {
      impactAlert.className = "impact-alert warning mt-4";
      impactAlert.innerHTML = `
        <div>
          <strong>Distribución modificada.</strong>
          <span class="text-muted">
            El trabajador ha cambiado la carga. El plan sigue siendo viable, pero ya no coincide con la distribución óptima calculada.
          </span>
        </div>
      `;
    }
  } else {
    setBadge(scoreBadge, "Riesgo", "status-pill status-danger");
    setBadge(layoutStatus, "Distribución con riesgo operativo", "status-pill status-danger");
    setBadge(globalPlanStatus, "Requiere revisión", "status-pill status-danger");
    setBadge(accessibilityBadge, "Penalizado", "status-pill status-danger");

    if (impactAlert) {
      impactAlert.className = "impact-alert danger mt-4";
      impactAlert.innerHTML = `
        <div>
          <strong>Atención: la modificación penaliza la operativa.</strong>
          <span class="text-muted">
            Puede aumentar el tiempo de búsqueda, dificultar la primera descarga o bloquear la zona de retornables.
          </span>
        </div>
      `;
    }
  }

  renderWarnings(evaluation.warnings);
  renderDriverTable();

  const nextUnloadZone = document.getElementById("nextUnloadZone");
  const firstStopZone = findFirstPackageZoneByStop(1);

  if (nextUnloadZone && firstStopZone) {
    nextUnloadZone.textContent = firstStopZone;
  }
}

function setText(id, text) {
  const element = document.getElementById(id);
  if (element) element.textContent = text;
}

function setBar(id, value) {
  const bar = document.getElementById(id);
  if (bar) {
    bar.style.width = `${value}%`;
    bar.setAttribute("aria-valuenow", value);
  }
}

function setBadge(element, text, className) {
  if (!element) return;
  element.textContent = text;
  element.className = className;
}

function renderWarnings(warnings) {
  const container = document.getElementById("warningsList");
  if (!container) return;

  container.innerHTML = warnings.map((warning) => `
    <div class="warning-item ${warning.level}">
      <strong>${escapeHTML(warning.title)}</strong>
      <p class="text-muted mb-0">${escapeHTML(warning.text)}</p>
    </div>
  `).join("");
}

function findFirstPackageZoneByStop(stopNumber) {
  for (const zone of currentLoadPlan) {
    if (zone.packages.some((pkg) => Number(pkg.stop) === stopNumber)) {
      return zone.zone;
    }
  }

  return null;
}

function renderDriverTable() {
  const tbody = document.getElementById("driverTableBody");
  if (!tbody) return;

  const rows = currentLoadPlan
    .flatMap((zone) => zone.packages.map((pkg) => ({ ...pkg, currentZone: zone.zone })))
    .sort((a, b) => {
      const stopA = Number(a.stop) || 99;
      const stopB = Number(b.stop) || 99;
      return stopA - stopB;
    })
    .slice(0, 7);

  tbody.innerHTML = rows.map((item) => {
    const isOptimal = item.currentZone === item.idealZone;
    const statusClass = isOptimal ? "status-success" : "status-warning";
    const statusText = isOptimal ? "Correcto" : `Movido desde ${item.idealZone}`;

    return `
      <tr>
        <td>${escapeHTML(item.client)}</td>
        <td>${escapeHTML(item.product)}</td>
        <td>${escapeHTML(item.qty || item.quantity || "-")}</td>
        <td>${escapeHTML(item.currentZone)}</td>
        <td><span class="status-pill ${statusClass}">${statusText}</span></td>
      </tr>
    `;
  }).join("");
}

/* =========================
   DRAG & DROP
========================= */
function initDragAndDrop() {
  let draggedCard = null;

  document.addEventListener("dragstart", (event) => {
    if (!event.target.classList.contains("package-card")) return;

    draggedCard = event.target;
    event.target.style.opacity = "0.5";
  });

  document.addEventListener("dragend", (event) => {
    if (!event.target.classList.contains("package-card")) return;

    event.target.style.opacity = "1";
    draggedCard = null;
  });

  document.querySelectorAll(".pallet-zone").forEach((zone) => {
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });

    zone.addEventListener("dragleave", () => {
      zone.classList.remove("drag-over");
    });

    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");

      if (!draggedCard) return;

      const originZone = draggedCard.closest(".pallet-zone")?.dataset.zone;
      const targetZone = zone.dataset.zone;
      const packageId = draggedCard.dataset.packageId;
      const pkg = findPackageById(packageId);

      zone.appendChild(draggedCard);

      if (pkg) {
        lastMovedPackage = {
          ...pkg,
          originZone,
          targetZone
        };
      }

      syncPlanFromDom();
      renderLoadPlan(currentLoadPlan);
      updateEvaluation();
      explainLastMove();
    });
  });
}

function explainLastMove() {
  if (!lastMovedPackage) return;

  const { client, product, idealZone, targetZone, type } = lastMovedPackage;
  let message = "";

  if (targetZone === idealZone) {
    message = `${client} vuelve a su zona ideal (${idealZone}). La distribución recupera eficiencia para esa entrega.`;
  } else if ((type === "early" || type === "heavy") && !["P1", "P2"].includes(targetZone)) {
    message = `${client} se ha movido a ${targetZone}, fuera de la zona recomendada ${idealZone}. Esto puede retrasar la primera descarga porque el producto será menos accesible.`;
  } else if (type === "return" && targetZone !== "P5") {
    message = `${product} se ha movido fuera de P5. Esto reduce la zona flexible para retornables y puede bloquear productos pendientes de entrega.`;
  } else if (type === "reference" && targetZone !== "P4") {
    message = `${product} ya no está agrupado por referencia en P4. Esto puede complicar la preparación en almacén.`;
  } else {
    message = `${client} se ha movido a ${targetZone}. El cambio es viable, pero ya no coincide con la distribución óptima calculada inicialmente.`;
  }

  appendMessage("assistant", message);
}

/* =========================
   CHAT
========================= */
function initChatDrawer() {
  document.querySelectorAll("[data-chat-open]").forEach((button) => {
    button.addEventListener("click", openChatDrawer);
  });

  document.querySelectorAll("[data-chat-close]").forEach((button) => {
    button.addEventListener("click", closeChatDrawer);
  });
}

function openChatDrawer() {
  const drawer = document.getElementById("chatDrawer");
  if (drawer) drawer.classList.add("open");
}

function closeChatDrawer() {
  const drawer = document.getElementById("chatDrawer");
  if (drawer) drawer.classList.remove("open");
}

function initSuggestions() {
  document.querySelectorAll(".suggestion-chip").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById("chatInput");
      if (!input) return;

      input.value = button.dataset.prompt || "";
      input.focus();
      openChatDrawer();
    });
  });
}

function getProjectContext() {
  const routeData = readJsonScript("route-data");
  const loadPlanData = readJsonScript("load-plan-data");
  const evaluation = typeof evaluateCurrentPlan === "function" ? evaluateCurrentPlan() : null;

  return {
    projectName: "Damm Smart Truck",
    routeId: routeData?.routeId || loadPlanData?.routeId || "DR-042",
    area: routeData?.scenario || "Barcelona Centro",
    distributionCenter: routeData?.distributionCenter || "DDI MOLLET",
    clients: routeData?.summary?.clients || 22,
    currentStops: routeData?.summary?.currentStops || 22,
    optimizedStops: routeData?.summary?.optimizedStops || 15,
    distanceKm: routeData?.summary?.distanceKm || 24.5,
    routeTime: routeData?.summary?.estimatedTime || "3h 30m",
    currentSearchTime: "70 min",
    optimizedSearchTime: "42 min",
    currentWindowCompliance: "82%",
    optimizedWindowCompliance: `${routeData?.summary?.windowCompliance || 94}%`,
    currentEvaluation: evaluation,
    currentLoadPlan,
    truck: {
      type: loadPlanData?.truck?.type || "Camión de reparto de 6 palets con acceso lateral",
      loadingModel: "Modelo híbrido de carga",
      palletZones: [
        "P1: primeras entregas",
        "P2: primeras entregas y productos pesados",
        "P3: ruta media",
        "P4: productos agrupados por referencia",
        "P5: zona reservada para retornables",
        "P6: últimas paradas"
      ]
    }
  };
}

function initChatbot() {
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");

  if (!chatForm || !chatInput) return;

  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const question = chatInput.value.trim();
    if (!question) return;

    appendMessage("user", question);
    chatInput.value = "";

    const loadingId = appendTypingMessage();

    try {
      const answer = await getAssistantReply(question);
      removeTypingMessage(loadingId);
      appendMessage("assistant", answer);
    } catch {
      removeTypingMessage(loadingId);
      appendMessage("assistant", "No he podido conectar con Gemini ahora mismo, pero puedo responder con el contexto local de la demo.");
    }
  });
}

function appendMessage(role, text) {
  const chatMessages = document.getElementById("chatMessages");
  if (!chatMessages) return;

  const wrapper = document.createElement("div");
  wrapper.className = `chat-message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = text;

  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendTypingMessage() {
  const chatMessages = document.getElementById("chatMessages");
  if (!chatMessages) return null;

  const id = `typing-${Date.now()}`;

  const wrapper = document.createElement("div");
  wrapper.className = "chat-message assistant";
  wrapper.id = id;

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = "Analizando distribución, ruta y restricciones...";

  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  return id;
}

function removeTypingMessage(id) {
  if (!id) return;

  const element = document.getElementById(id);
  if (element) element.remove();
}

async function getAssistantReply(question) {
  const context = getProjectContext();

  try {
    const response = await fetch("/api/gemini-chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question,
        context
      })
    });

    if (!response.ok) throw new Error("Gemini backend not available");

    const data = await response.json();
    if (data.reply) return data.reply;

    throw new Error("Invalid Gemini response");
  } catch {
    return getDemoReply(question, context);
  }
}

function getDemoReply(question, context = getProjectContext()) {
  const q = question.toLowerCase();
  const evaluation = context.currentEvaluation;

  if (q.includes("ruta") || q.includes("parada")) {
    return `La ruta ${context.routeId} pasa de ${context.currentStops} paradas a ${context.optimizedStops}. La carga se coordina con esa ruta para que los productos de las primeras paradas estén en P1/P2.`;
  }

  if (q.includes("palet") || q.includes("carga") || q.includes("camión") || q.includes("camion")) {
    if (evaluation) {
      return `La distribución actual tiene un score global de ${evaluation.globalScore}%. P1/P2 son zonas accesibles para primeras entregas, P4 mantiene referencias agrupadas y P5 reserva espacio para retornables.`;
    }

    return "El modelo de carga prioriza P1/P2 para primeras entregas, P4 para referencias agrupadas y P5 para retornables.";
  }

  if (q.includes("movido") || q.includes("mover") || q.includes("cambio")) {
    if (!lastMovedPackage) {
      return "Todavía no se ha movido ningún paquete. La distribución actual coincide con el plan óptimo calculado.";
    }

    return `Último cambio: ${lastMovedPackage.client} se movió de ${lastMovedPackage.originZone} a ${lastMovedPackage.targetZone}. Zona ideal: ${lastMovedPackage.idealZone}. Si no coincide con la zona ideal, el plan deja de ser óptimo aunque pueda seguir siendo viable.`;
  }

  if (q.includes("retornable") || q.includes("retorno")) {
    return "Los retornables se gestionan reservando P5 como zona flexible para cajas y barriles vacíos. Si se ocupa P5 con otros productos, puede reducirse la capacidad de logística inversa durante la ruta.";
  }

  if (q.includes("impacto") || q.includes("mejora") || q.includes("score")) {
    if (evaluation) {
      return `Score actual: ${evaluation.globalScore}%. Accesibilidad: ${evaluation.accessibility}%. Equilibrio: ${evaluation.balance}%. Retornables: ${evaluation.returnCapacity}%. Si el trabajador mueve productos fuera de su zona ideal, estos valores bajan.`;
    }

    return "El impacto estimado se basa en reducción de paradas, menor tiempo buscando producto y mejor accesibilidad de carga.";
  }

  return "Este asistente ayuda a explicar la distribución de carga, los cambios manuales del trabajador, la ruta, los palets, los retornables y el impacto operativo de cada decisión.";
}

/* =========================
   REAL ROUTE MAP - LEAFLET + OSRM
========================= */
function initRouteMap() {
  const mapElement = document.getElementById("routeMap");
  if (!mapElement || typeof L === "undefined") return;

  const backendRoute = readJsonScript("route-data");

  const warehouse = normalizeWarehouse(
    backendRoute?.warehouse || {
      name: "Almacén / centro de salida",
      coords: [41.4322, 2.1899],
      type: "warehouse"
    }
  );

  const stops = normalizeRouteStops(backendRoute?.stops || getFallbackStops());
  const routePoints = [warehouse.coords, ...stops.map((stop) => stop.coords)].filter(isValidCoordinate);

  const map = L.map("routeMap", {
    zoomControl: true,
    scrollWheelZoom: true
  });

  map.setView(warehouse.coords || [41.3925, 2.1769], 11);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);

  const warehouseIcon = L.divIcon({
    className: "",
    html: `<div class="custom-warehouse-marker">Almacén</div>`,
    iconSize: [84, 38],
    iconAnchor: [42, 19]
  });

  if (isValidCoordinate(warehouse.coords)) {
    L.marker(warehouse.coords, { icon: warehouseIcon })
      .addTo(map)
      .bindPopup(`
        <div class="route-popup-title">${escapeHTML(warehouse.name || "Almacén")}</div>
        <div class="route-popup-meta">Inicio de ruta ${escapeHTML(backendRoute?.routeId || "DR-042")}</div>
        <p class="mb-0">Salida del camión con plan de carga calculado automáticamente.</p>
      `);
  }

  stops.forEach((stop) => {
    if (!isValidCoordinate(stop.coords)) return;

    const markerIcon = L.divIcon({
      className: "",
      html: `<div class="custom-route-marker">${stop.number}</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17]
    });

    L.marker(stop.coords, { icon: markerIcon })
      .addTo(map)
      .bindPopup(`
        <div class="route-popup-title">Parada ${stop.number} · ${escapeHTML(stop.name)}</div>
        <div class="route-popup-meta">${escapeHTML(stop.time)} · Carga: ${escapeHTML(stop.load)}</div>
        <ul class="route-popup-list">
          ${stop.clients.map((client) => `<li>${escapeHTML(client)}</li>`).join("")}
        </ul>
        <p class="mt-2 mb-0">${escapeHTML(stop.note)}</p>
      `);
  });

  if (routePoints.length > 1) {
    drawRoadRoute(map, routePoints).catch(() => {
      drawStraightFallbackRoute(map, routePoints);
    });
  }
}

function normalizeWarehouse(warehouse) {
  return {
    name: warehouse.name || "Almacén",
    coords: normalizeCoords(warehouse.coords) || [41.4322, 2.1899],
    type: warehouse.type || "warehouse"
  };
}

function normalizeRouteStops(stops) {
  return stops.map((stop, index) => {
    const clients = (stop.clients || []).map((client) => {
      if (typeof client === "string") return client;
      return client.name || client.client || client.customerId || "Cliente";
    });

    const load = stop.load || (stop.loadZones || []).join(" / ") || "P1";

    return {
      number: stop.number || index + 1,
      name: stop.name || `Parada ${index + 1}`,
      coords: normalizeCoords(stop.coords) || [41.3925, 2.1769],
      time: stop.time || "--:--",
      clients,
      load,
      note: stop.note || "Parada generada desde datos de MongoDB."
    };
  });
}

function normalizeCoords(coords) {
  if (!Array.isArray(coords) || coords.length < 2) return null;

  const lat = Number(coords[0]);
  const lng = Number(coords[1]);

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;

  return [lat, lng];
}

function isValidCoordinate(coords) {
  if (!Array.isArray(coords) || coords.length < 2) return false;

  const lat = Number(coords[0]);
  const lng = Number(coords[1]);

  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}

async function drawRoadRoute(map, routePoints) {
  const limitedRoutePoints = routePoints.slice(0, 25);

  const osrmCoordinates = limitedRoutePoints
    .map(([lat, lng]) => `${lng},${lat}`)
    .join(";");

  const url = `https://router.project-osrm.org/route/v1/driving/${osrmCoordinates}?overview=full&geometries=geojson&steps=false`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("OSRM route request failed");
  }

  const data = await response.json();

  if (!data.routes || !data.routes.length || !data.routes[0].geometry) {
    throw new Error("OSRM did not return a valid route");
  }

  const route = data.routes[0];

  const roadCoordinates = route.geometry.coordinates.map(([lng, lat]) => [lat, lng]);

  L.polyline(roadCoordinates, {
    color: "#ffffff",
    weight: 10,
    opacity: 0.45,
    lineJoin: "round"
  }).addTo(map);

  const routeLine = L.polyline(roadCoordinates, {
    color: "#d8141c",
    weight: 5,
    opacity: 0.9,
    lineJoin: "round"
  }).addTo(map);

  routeLine.bringToFront();

  map.fitBounds(routeLine.getBounds(), {
    padding: [40, 40]
  });

  updateRouteMetricsFromOSRM(route);
  setRouteSourceBadge("Ruta real por carretera");
}

function drawStraightFallbackRoute(map, routePoints) {
  L.polyline(routePoints, {
    color: "#ffffff",
    weight: 9,
    opacity: 0.35,
    lineJoin: "round"
  }).addTo(map);

  const routeLine = L.polyline(routePoints, {
    color: "#d8141c",
    weight: 5,
    opacity: 0.85,
    lineJoin: "round",
    dashArray: "10, 8"
  }).addTo(map);

  routeLine.bringToFront();

  map.fitBounds(routeLine.getBounds(), {
    padding: [40, 40]
  });

  setRouteSourceBadge("Ruta aproximada");
  console.warn("OSRM no ha respondido. Mostrando ruta visual aproximada.");
}

function updateRouteMetricsFromOSRM(route) {
  const distanceKm = route.distance ? (route.distance / 1000).toFixed(1) : null;
  const durationMinutes = route.duration ? Math.round(route.duration / 60) : null;

  const distanceElement = document.querySelector("[data-route-distance]");
  const durationElement = document.querySelector("[data-route-duration]");
  const durationPill = document.querySelector("[data-route-duration-pill]");

  if (distanceElement && distanceKm) {
    distanceElement.textContent = distanceKm;
  }

  if (durationElement && durationMinutes !== null) {
    const hours = Math.floor(durationMinutes / 60);
    const minutes = durationMinutes % 60;

    if (hours > 0) {
      durationElement.textContent = `${hours}h`;
      if (durationPill) durationPill.textContent = `${minutes}m`;
    } else {
      durationElement.textContent = `${durationMinutes}`;
      if (durationPill) durationPill.textContent = "min";
    }
  }
}

function setRouteSourceBadge(text) {
  const badge = document.querySelector("[data-route-source]");
  if (badge) {
    badge.textContent = text;
  }
}

function getFallbackStops() {
  return [
    {
      number: 1,
      name: "Plaça Real",
      coords: [41.3801, 2.1753],
      time: "08:15",
      clients: ["Bar Sol", "Café Centre", "Restaurant Mar"],
      load: "P1 / P2",
      note: "Primera parada agrupada. Productos muy accesibles."
    },
    {
      number: 2,
      name: "Eixample",
      coords: [41.3917, 2.1649],
      time: "09:05",
      clients: ["Hotel Nord", "Bar Provença"],
      load: "P2",
      note: "Clientes cercanos con franja compatible."
    },
    {
      number: 3,
      name: "Gràcia",
      coords: [41.4036, 2.1569],
      time: "10:10",
      clients: ["Restaurant Vila"],
      load: "P2 / P3",
      note: "Franja estricta. Parada prioritaria."
    },
    {
      number: 4,
      name: "Sant Antoni",
      coords: [41.3786, 2.1604],
      time: "11:00",
      clients: ["Bar Mercat", "Cafeteria Ronda"],
      load: "P3",
      note: "Recogida prevista de retornables."
    },
    {
      number: 5,
      name: "Poblenou",
      coords: [41.4017, 2.2038],
      time: "12:20",
      clients: ["Restaurant Port", "Bar Llacuna"],
      load: "P3 / P4",
      note: "Volumen alto de ruta media."
    }
  ];
}

/* =========================
   PRINT LOAD SHEET
========================= */
function printCurrentLoadSheet() {
  const existingSheet = document.getElementById("printSheet");
  if (existingSheet) {
    existingSheet.remove();
  }

  const sheet = document.createElement("section");
  sheet.id = "printSheet";
  sheet.className = "print-sheet";
  sheet.innerHTML = buildPrintSheetHTML();

  document.body.appendChild(sheet);

  setTimeout(() => {
    window.print();
  }, 150);
}

function buildPrintSheetHTML() {
  const evaluation = typeof evaluateCurrentPlan === "function"
    ? evaluateCurrentPlan()
    : {
        globalScore: 89,
        accessibility: 91,
        balance: 84,
        returnCapacity: 76,
        isOptimal: true
      };

  const context = getProjectContext();

  const currentDate = new Date().toLocaleString("es-ES", {
    dateStyle: "short",
    timeStyle: "short"
  });

  const zones = currentLoadPlan && currentLoadPlan.length
    ? currentLoadPlan
    : optimalLoadPlan;

  const totalPackages = zones.reduce((acc, zone) => acc + zone.packages.length, 0);
  const logoSrc = document.querySelector(".brand-logo-full")?.src || "/static/img/damm-logo.png";

  return `
    <div class="print-header">
      <div>
        <img src="${logoSrc}" alt="Damm" class="print-logo">
        <h1>Hoja de carga del camión</h1>
        <p>
          Ruta ${escapeHTML(context.routeId)} · Camión urbano de 6 palets · Acceso lateral
        </p>
      </div>

      <div class="print-meta">
        <strong>Generado:</strong> ${currentDate}<br>
        <strong>Estado:</strong> ${evaluation.isOptimal ? "Plan óptimo inicial" : "Plan modificado por trabajador"}<br>
        <strong>Uso:</strong> Documento operativo para almacén y repartidor
      </div>
    </div>

    <div class="print-summary">
      <div class="print-summary-item">
        <span class="print-summary-label">Paquetes / grupos</span>
        <span class="print-summary-value">${totalPackages}</span>
      </div>

      <div class="print-summary-item">
        <span class="print-summary-label">Score global</span>
        <span class="print-summary-value">${evaluation.globalScore}%</span>
      </div>

      <div class="print-summary-item">
        <span class="print-summary-label">Accesibilidad</span>
        <span class="print-summary-value">${evaluation.accessibility}%</span>
      </div>

      <div class="print-summary-item">
        <span class="print-summary-label">Retornables</span>
        <span class="print-summary-value">${evaluation.returnCapacity}%</span>
      </div>
    </div>

    ${zones.map(zone => buildPrintZoneHTML(zone)).join("")}

    <div class="print-warning">
      <strong>Nota operativa:</strong>
      esta hoja refleja la distribución actual en pantalla. Si el trabajador ha movido productos manualmente,
      el plan puede seguir siendo viable, pero puede dejar de ser la distribución óptima calculada inicialmente.
    </div>
  `;
}

function buildPrintZoneHTML(zone) {
  const zoneLabel = getZonePrintLabel(zone.zone);

  return `
    <div class="print-zone">
      <div class="print-zone-title">${zone.zone} · ${zoneLabel}</div>

      <table class="print-table">
        <thead>
          <tr>
            <th>Cliente / grupo</th>
            <th>Producto</th>
            <th>Cantidad</th>
            <th>Parada</th>
            <th>Zona ideal</th>
            <th>Estado</th>
            <th>Motivo</th>
          </tr>
        </thead>
        <tbody>
          ${
            zone.packages.length
              ? zone.packages.map(pkg => buildPrintPackageRow(pkg, zone.zone)).join("")
              : `
                <tr>
                  <td colspan="7">Sin productos asignados.</td>
                </tr>
              `
          }
        </tbody>
      </table>
    </div>
  `;
}

function buildPrintPackageRow(pkg, currentZone) {
  const isOptimal = currentZone === pkg.idealZone;
  const status = isOptimal ? "Correcto" : `Modificado desde ${pkg.idealZone}`;
  const stop = Number(pkg.stop) === 0 ? "Retorno" : pkg.stop;

  return `
    <tr>
      <td>${escapeHTML(pkg.client || "-")}</td>
      <td>${escapeHTML(pkg.product || "-")}</td>
      <td>${escapeHTML(pkg.qty || pkg.quantity || "-")}</td>
      <td>${escapeHTML(stop || "-")}</td>
      <td>${escapeHTML(pkg.idealZone || "-")}</td>
      <td>${escapeHTML(status)}</td>
      <td>${escapeHTML(pkg.reason || "-")}</td>
    </tr>
  `;
}

function getZonePrintLabel(zone) {
  const labels = {
    P1: "Primeras paradas",
    P2: "Primeras paradas y producto pesado",
    P3: "Ruta media",
    P4: "Referencias agrupadas",
    P5: "Reserva para retornables",
    P6: "Últimas paradas"
  };

  return labels[zone] || "Zona de carga";
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}