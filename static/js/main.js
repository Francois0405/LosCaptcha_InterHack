document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initDragAndDrop();
  initChatbot();
});

/* =========================
   THEME TOGGLE
========================= */
function initTheme() {
  const root = document.documentElement;
  const toggleBtn = document.querySelector("[data-theme-toggle]");
  const savedTheme = localStorage.getItem("damm-theme") || "light";

  root.setAttribute("data-bs-theme", savedTheme);
  updateThemeButton(savedTheme);

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const current = root.getAttribute("data-bs-theme");
      const next = current === "light" ? "dark" : "light";
      root.setAttribute("data-bs-theme", next);
      localStorage.setItem("damm-theme", next);
      updateThemeButton(next);
    });
  }
}

function updateThemeButton(theme) {
  const toggleBtn = document.querySelector("[data-theme-toggle]");
  if (!toggleBtn) return;
  toggleBtn.textContent = theme === "light" ? "Dark mode" : "Light mode";
}

/* =========================
   DRAG & DROP (TRUCK VIEW)
========================= */
function initDragAndDrop() {
  const cards = document.querySelectorAll(".package-card");
  const zones = document.querySelectorAll(".pallet-zone");

  let draggedCard = null;

  cards.forEach(card => {
    card.addEventListener("dragstart", () => {
      draggedCard = card;
      card.style.opacity = "0.5";
    });

    card.addEventListener("dragend", () => {
      card.style.opacity = "1";
      draggedCard = null;
    });
  });

  zones.forEach(zone => {
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("drag-over");
    });

    zone.addEventListener("dragleave", () => {
      zone.classList.remove("drag-over");
    });

    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      if (draggedCard) {
        zone.appendChild(draggedCard);
      }
    });
  });
}

/* =========================
   GEMINI CHATBOT
========================= */

const PROJECT_CONTEXT = {
  projectName: "Damm Smart Truck",
  routeId: "DR-042",
  area: "Barcelona Center",
  clients: 22,
  currentStops: 22,
  optimizedStops: 15,
  distanceKm: 24.5,
  routeTime: "3h 30m",
  currentSearchTime: "70 min",
  optimizedSearchTime: "42 min",
  currentWindowCompliance: "82%",
  optimizedWindowCompliance: "94%",
  loadUsage: "82%",
  returnables: "58%",
  truck: {
    type: "6-pallet side-access delivery truck",
    logic: "hybrid loading model",
    palletZones: [
      "P1: earliest deliveries",
      "P2: early deliveries + heavy items",
      "P3: mid-route items",
      "P4: grouped by reference / product family",
      "P5: returnable reserve area",
      "P6: late stops / lower urgency products"
    ]
  },
  routeLogic: [
    "Prioritize strict or early time windows",
    "Group nearby clients into one operational stop where possible",
    "Reduce unnecessary truck repositioning",
    "Align route order with load accessibility"
  ],
  sampleStops: [
    {
      stop: 1,
      location: "Plaça Real",
      time: "08:15",
      type: "grouped stop",
      clients: ["Bar Sol", "Café Centre", "Restaurant Mar"]
    },
    {
      stop: 2,
      location: "Eixample",
      time: "09:05",
      type: "grouped stop",
      clients: ["Hotel Nord", "Bar Provença"]
    },
    {
      stop: 3,
      location: "Gràcia",
      time: "10:10",
      type: "strict time window",
      clients: ["Restaurant Vila"]
    }
  ]
};

function initChatbot() {
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatMessages = document.getElementById("chatMessages");
  const suggestionButtons = document.querySelectorAll(".suggestion-chip");

  if (!chatForm || !chatInput || !chatMessages) return;

  suggestionButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const prompt = btn.dataset.prompt;
      chatInput.value = prompt;
      chatInput.focus();
    });
  });

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const question = chatInput.value.trim();
    if (!question) return;

    appendMessage("user", question);
    chatInput.value = "";

    const loadingId = appendTypingMessage();

    try {
      const answer = await getAssistantReply(question);
      removeTypingMessage(loadingId);
      appendMessage("assistant", answer);
    } catch (error) {
      removeTypingMessage(loadingId);
      appendMessage("assistant", "I couldn't generate a live Gemini answer right now, but the demo assistant is still available.");
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
  const id = `typing-${Date.now()}`;

  const wrapper = document.createElement("div");
  wrapper.className = "chat-message assistant";
  wrapper.id = id;

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = "Thinking...";

  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  return id;
}

function removeTypingMessage(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

async function getAssistantReply(question) {
  try {
    const response = await fetch("/api/gemini-chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question,
        context: PROJECT_CONTEXT
      })
    });

    if (!response.ok) {
      throw new Error("No Gemini backend available");
    }

    const data = await response.json();
    if (data.reply) return data.reply;

    throw new Error("Invalid Gemini response");
  } catch (error) {
    return getDemoReply(question);
  }
}

/* =========================
   DEMO REPLIES (fallback)
========================= */
function getDemoReply(question) {
  const q = question.toLowerCase();

  if (q.includes("route") || q.includes("ruta") || q.includes("summary")) {
    return `The optimized route for ${PROJECT_CONTEXT.routeId} serves ${PROJECT_CONTEXT.clients} clients using ${PROJECT_CONTEXT.optimizedStops} operational stops instead of ${PROJECT_CONTEXT.currentStops}. The proposal improves urban efficiency by grouping nearby clients, prioritizing strict time windows and coordinating the route with the truck loading sequence.`;
  }

  if (q.includes("pallet") || q.includes("load") || q.includes("carga")) {
    return `The loading logic is hybrid. P1 and P2 are reserved for earliest deliveries, P3 supports mid-route unloading, P4 groups products by reference, P5 keeps reserve space for returnables, and P6 contains later-stop items. This reduces product search time and makes first deliveries easier for the driver.`;
  }

  if (q.includes("time window") || q.includes("horario") || q.includes("strict")) {
    return `The most critical stop in the demo is Stop 3 in Gràcia at 10:10, marked as a strict time-window delivery. In the heuristic, customers with early or strict windows are prioritized before lower urgency stops.`;
  }

  if (q.includes("impact") || q.includes("improvement") || q.includes("mejora")) {
    return `Main estimated improvements: stops reduced from ${PROJECT_CONTEXT.currentStops} to ${PROJECT_CONTEXT.optimizedStops}, search time reduced from ${PROJECT_CONTEXT.currentSearchTime} to ${PROJECT_CONTEXT.optimizedSearchTime}, and time-window compliance improved from ${PROJECT_CONTEXT.currentWindowCompliance} to ${PROJECT_CONTEXT.optimizedWindowCompliance}.`;
  }

  if (q.includes("return") || q.includes("retornable")) {
    return `Returnables are explicitly considered in the load plan. Pallet zone P5 is reserved as a flexible returnable area so empty crates and kegs can be collected without disrupting accessibility for the next deliveries.`;
  }

  if (q.includes("why") || q.includes("logic") || q.includes("group")) {
    return `The stop-grouping logic is useful because one truck stop does not necessarily equal one customer. If several nearby clients can be served from one parking position and have compatible time windows, the system groups them into a single operational stop to reduce maneuvering and parking inefficiency.`;
  }

  return `This MVP is designed to help Damm plan routes and truck loading together. You can ask me about optimized stops, grouped customers, time windows, load accessibility, returnables, or estimated operational impact.`;
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initLoadDistribution();
  initDragAndDrop();
  initChatDrawer();
  initChatbot();
});

function initLoadDistribution() {
  const truckGrid = document.getElementById("truckGrid");
  if (!truckGrid) return;

  const loadPlan = [
    {
      zone: "P1",
      packages: [
        { client: "Bar Sol", product: "Estrella Damm", qty: "8 crates", status: "Accessible" },
        { client: "Café Centre", product: "Veri", qty: "4 crates", status: "Accessible" }
      ]
    },
    {
      zone: "P2",
      packages: [
        { client: "Restaurant Mar", product: "Keg", qty: "2 units", status: "Heavy" },
        { client: "Hotel Nord", product: "Damm crates", qty: "6 crates", status: "Accessible" }
      ]
    },
    {
      zone: "P3",
      packages: [
        { client: "Bar Mercat", product: "Returnable crates", qty: "7 crates", status: "Mid route" },
        { client: "Restaurant Port", product: "Mixed crates", qty: "12 crates", status: "Mid route" }
      ]
    },
    {
      zone: "P4",
      packages: [
        { client: "Reference stock", product: "High rotation Damm", qty: "Grouped", status: "Reference" },
        { client: "Reference stock", product: "Veri", qty: "Grouped", status: "Reference" }
      ]
    },
    {
      zone: "P5",
      packages: [
        { client: "Returnables", product: "Empty crates area", qty: "Reserved", status: "Return" },
        { client: "Returnables", product: "Empty kegs", qty: "Reserved", status: "Return" }
      ]
    },
    {
      zone: "P6",
      packages: [
        { client: "Late stops", product: "Secondary references", qty: "Mixed", status: "Late" }
      ]
    }
  ];

  renderLoadPlan(loadPlan);
  renderDriverTable(loadPlan);
}

function renderLoadPlan(loadPlan) {
  loadPlan.forEach(zoneData => {
    const zone = document.querySelector(`.pallet-zone[data-zone="${zoneData.zone}"]`);
    if (!zone) return;

    zoneData.packages.forEach(pkg => {
      const card = document.createElement("div");
      card.className = "package-card";
      card.draggable = true;
      card.innerHTML = `
        <strong>${pkg.client}</strong><br>
        <small>${pkg.product} · ${pkg.qty}</small>
      `;
      zone.appendChild(card);
    });
  });
}

function renderDriverTable(loadPlan) {
  const tbody = document.getElementById("driverTableBody");
  if (!tbody) return;

  const firstStops = loadPlan
    .flatMap(zone => zone.packages.map(pkg => ({ ...pkg, zone: zone.zone })))
    .slice(0, 5);

  tbody.innerHTML = firstStops.map(item => `
    <tr>
      <td>${item.client}</td>
      <td>${item.product}</td>
      <td>${item.qty}</td>
      <td>${item.zone}</td>
      <td><span class="status-pill">${item.status}</span></td>
    </tr>
  `).join("");
}

function initChatDrawer() {
  const drawer = document.getElementById("chatDrawer");
  const openButtons = document.querySelectorAll("[data-chat-open]");
  const closeButton = document.querySelector("[data-chat-close]");

  if (!drawer) return;

  openButtons.forEach(button => {
    button.addEventListener("click", () => {
      drawer.classList.add("open");
    });
  });

  if (closeButton) {
    closeButton.addEventListener("click", () => {
      drawer.classList.remove("open");
    });
  }
}

function initDragAndDrop() {
  let draggedCard = null;

  document.addEventListener("dragstart", event => {
    if (!event.target.classList.contains("package-card")) return;
    draggedCard = event.target;
    event.target.style.opacity = "0.5";
  });

  document.addEventListener("dragend", event => {
    if (!event.target.classList.contains("package-card")) return;
    event.target.style.opacity = "1";
    draggedCard = null;
  });

  document.querySelectorAll(".pallet-zone").forEach(zone => {
    zone.addEventListener("dragover", event => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });

    zone.addEventListener("dragleave", () => {
      zone.classList.remove("drag-over");
    });

    zone.addEventListener("drop", event => {
      event.preventDefault();
      zone.classList.remove("drag-over");

      if (draggedCard) {
        zone.appendChild(draggedCard);
      }
    });
  });
}