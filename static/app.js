// IBVAP CYPHER - Command Center Frontend Application Controller
document.addEventListener("DOMContentLoaded", () => {
    initClock();
    initTabs();
    fetchAnalytics();
    fetchEvents();
    fetchVehicles();
    fetchSuspiciousLogs();
    fetchBlockchainLedger();

    // Poll data every 4 seconds
    setInterval(() => {
        fetchAnalytics();
        fetchEvents();
        fetchSuspiciousLogs();
    }, 4000);
});

// Live Clock
function initClock() {
    const clockEl = document.getElementById("live-clock");
    function update() {
        const now = new Date();
        clockEl.textContent = now.toUTCString().replace("GMT", "UTC");
    }
    update();
    setInterval(update, 1000);
}

// Tab Switching
function initTabs() {
    const buttons = document.querySelectorAll(".nav-btn");
    const contents = document.querySelectorAll(".tab-content");

    buttons.forEach(btn => {
        btn.addEventListener("click", () => {
            buttons.forEach(b => b.classList.remove("active"));
            contents.forEach(c => c.classList.remove("active"));

            btn.classList.add("active");
            const target = btn.getAttribute("data-tab");
            document.getElementById(target).classList.add("active");
        });
    });
}

// Fetch System Analytics & Risk Metrics
async function fetchAnalytics() {
    try {
        const res = await fetch("/api/analytics");
        const data = await res.json();

        document.getElementById("metric-breaches").textContent = data.unauthorized_intrusions;
        document.getElementById("metric-verified").textContent = data.verified_entries;

        const threatBadge = document.getElementById("threat-badge");
        const threatText = document.getElementById("threat-text");

        threatText.textContent = `THREAT: ${data.threat_level}`;
        if (data.threat_level === "CRITICAL" || data.threat_level === "HIGH") {
            threatBadge.className = "threat-pill threat-critical";
        } else {
            threatBadge.className = "threat-pill threat-normal";
        }
    } catch (err) {
        console.error("Analytics fetch error:", err);
    }
}

// Fetch Perimeter Breach Events
async function fetchEvents() {
    try {
        const res = await fetch("/api/events");
        const events = await res.json();
        const tbody = document.getElementById("events-table-body");

        if (!events || events.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No breach events recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = events.map(e => `
            <tr>
                <td><code class="mono-id">${e.event_id}</code></td>
                <td><i class="fa-solid fa-layer-group text-muted"></i> ${e.object_type}</td>
                <td><code class="mono-track">#${e.track_id}</code></td>
                <td><span class="mono-time">${e.timestamp}</span></td>
                <td>
                    <span class="status-badge ${e.status === 'VERIFIED_VEHICLE' ? 'status-verified' : 'status-alert'}">
                        ${e.status === 'VERIFIED_VEHICLE' ? 'VERIFIED' : 'UNAUTHORIZED'}
                    </span>
                </td>
                <td>
                    <a href="${e.evidence_url}" target="_blank" class="btn-evidence">
                        <i class="fa-solid fa-image"></i> View Evidence
                    </a>
                </td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("Events fetch error:", err);
    }
}

// Fetch Vehicle Registry
async function fetchVehicles() {
    try {
        const res = await fetch("/api/vehicles");
        const vehicles = await res.json();
        const tbody = document.getElementById("vehicles-table-body");

        if (!vehicles || vehicles.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No registered vehicles found.</td></tr>`;
            return;
        }

        tbody.innerHTML = vehicles.map(v => `
            <tr>
                <td><code class="mono-plate">${v.plate_number}</code></td>
                <td>${v.vehicle_type}</td>
                <td>${v.owner}</td>
                <td><span class="status-badge status-verified"><i class="fa-solid fa-circle-check"></i> ${v.status}</span></td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("Vehicles fetch error:", err);
    }
}

// Fetch Suspicious Logs
async function fetchSuspiciousLogs() {
    try {
        const res = await fetch("/api/suspicious");
        const logs = await res.json();
        const tbody = document.getElementById("suspicious-table-body");

        if (!logs || logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No suspicious activity detected.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => `
            <tr>
                <td><code class="mono-id">${l.activity_id}</code></td>
                <td><code class="mono-track">#${l.track_id}</code></td>
                <td><span class="status-badge status-alert">${l.activity_type}</span></td>
                <td><strong class="text-alert">${l.severity}</strong></td>
                <td>${l.description}</td>
                <td><span class="mono-time">${l.timestamp}</span></td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("Suspicious logs fetch error:", err);
    }
}

// Fetch Blockchain Audit Ledger
async function fetchBlockchainLedger() {
    try {
        const res = await fetch("/api/blockchain/ledger");
        const blocks = await res.json();
        const tbody = document.getElementById("blockchain-table-body");
        document.getElementById("metric-ledger").textContent = `${blocks.length} Blocks`;

        if (!blocks || blocks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Blockchain ledger is empty.</td></tr>`;
            return;
        }

        tbody.innerHTML = blocks.map(b => `
            <tr>
                <td><code class="mono-id">Block #${b.block_index}</code></td>
                <td><code class="mono-id">${b.event_id}</code></td>
                <td><code class="mono-hash-teal">${b.block_hash.substring(0, 16)}...</code></td>
                <td><code class="mono-hash-green">${b.evidence_hash.substring(0, 16)}...</code></td>
                <td><code class="mono-track">${b.nonce}</code></td>
                <td><span class="mono-time">${b.timestamp}</span></td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("Blockchain ledger fetch error:", err);
    }
}

// Audit Integrity Check
async function verifyBlockchainAudit() {
    try {
        const res = await fetch("/api/blockchain/verify");
        const result = await res.json();

        const banner = document.getElementById("audit-status-banner");
        const title = document.getElementById("audit-status-title");
        const msg = document.getElementById("audit-status-msg");

        if (result.valid) {
            banner.style.borderLeftColor = "var(--color-state-green)";
            title.textContent = "Ledger Integrity 100% Authentic";
            title.className = "text-success";
            msg.textContent = result.message;
        } else {
            banner.style.borderLeftColor = "var(--color-alert-red)";
            title.textContent = "CORRUPTION DETECTED";
            title.className = "text-alert";
            msg.textContent = result.message;
        }
        alert(result.message);
    } catch (err) {
        alert("Error conducting blockchain audit: " + err);
    }
}

// Verify Plate Search Test
async function verifyPlateSearch() {
    const input = document.getElementById("search-plate-input").value.trim();
    const resultBox = document.getElementById("search-result-box");

    if (!input) {
        alert("Please enter a license plate number.");
        return;
    }

    try {
        const res = await fetch("/api/vehicles");
        const vehicles = await res.json();

        const normInput = input.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
        const found = vehicles.find(v => v.plate_number.replace(/[^A-Za-z0-9]/g, "").toUpperCase() === normInput);

        if (found) {
            resultBox.innerHTML = `
                <h4 class="text-success" style="margin-bottom: 8px;"><i class="fa-solid fa-circle-check"></i> VERIFIED IN REGISTRY</h4>
                <p><strong>Plate:</strong> <code class="mono-plate">${found.plate_number}</code></p>
                <p><strong>Vehicle Type:</strong> ${found.vehicle_type}</p>
                <p><strong>Registered Owner:</strong> ${found.owner}</p>
                <p><strong>Status:</strong> <span class="status-badge status-verified">${found.status}</span></p>
            `;
        } else {
            resultBox.innerHTML = `
                <h4 class="text-alert" style="margin-bottom: 8px;"><i class="fa-solid fa-circle-xmark"></i> UNKNOWN / UNREGISTERED</h4>
                <p>Entered plate '<strong>${input}</strong>' was not found in the border whitelist database.</p>
                <p><strong>Action:</strong> Flagged for security check.</p>
            `;
        }
    } catch (err) {
        console.error("Plate search error:", err);
    }
}

// Generate SITREP Report
async function generateSitrep() {
    const output = document.getElementById("sitrep-output");
    output.textContent = "Generating AI Military Intelligence Situation Report...";

    try {
        const res = await fetch("/api/llm/sitrep", { method: "POST" });
        const data = await res.json();
        output.textContent = data.sitrep;
    } catch (err) {
        output.textContent = "Failed to generate SITREP report: " + err;
    }
}

// Modal Controllers
function openVehicleModal() {
    document.getElementById("modal-vehicle").classList.add("active");
}

function closeVehicleModal() {
    document.getElementById("modal-vehicle").classList.remove("active");
}

async function submitAddVehicle(e) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    try {
        const res = await fetch("/api/vehicles", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        alert(data.message);
        closeVehicleModal();
        form.reset();
        fetchVehicles();
    } catch (err) {
        alert("Error registering vehicle: " + err);
    }
}
