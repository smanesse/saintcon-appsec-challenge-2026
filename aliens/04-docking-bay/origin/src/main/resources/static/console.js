// Docking Bay console wiring.
const API = {
  status: "/status",
  notify: "/dock/notify",
  arm:    "/launch/arm",
  fire:   "/launch/fire",
};

// Crew consoles (crew session required). Pilots cannot reach these.
const DIAG = {
  telemetry:   "/crew/telemetry",
  launchPanel: "/crew/" + ["launch", "code"].join("-"),
  keyring:     "/crew/keyring",
  override:    "/crew/override",
  checklist:   "/crew/checklist",
  reviewQueue: "/crew/pending",
};

async function refresh() {
  try {
    const r = await fetch(API.status);
    if (!r.ok) return;
    const el = document.querySelector(".sub");
    if (el) el.textContent = (await r.text()).trim();
  } catch (_) { }
}

document.addEventListener("DOMContentLoaded", refresh);
