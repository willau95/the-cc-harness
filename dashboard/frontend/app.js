"use strict";

const $ = (sel) => document.querySelector(sel);
let selectedAgent = null;

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

async function loadStats() {
  const s = await fetchJSON("/api/stats");
  $("#metrics").innerHTML = `
    <div class="metric"><span class="n" style="color:#22c55e">${s.online}</span><span class="l">Online</span></div>
    <div class="metric"><span class="n" style="color:#a855f7">${s.zombies}</span><span class="l">Zombies</span></div>
    <div class="metric"><span class="n" style="color:#14b8a6">${s.pending_proposals}</span><span class="l">Pending proposals</span></div>
    <div class="metric"><span class="n" style="color:#eab308">${s.pending_budgets}</span><span class="l">Budget reqs</span></div>
    <div class="metric"><span class="n" style="color:#ec4899">${s.projects}</span><span class="l">Projects</span></div>
  `;
}

async function loadFleet() {
  const data = await fetchJSON("/api/fleet");
  const html = data.agents.map(ag => {
    const dotCls = ag.stale ? "stale" : "online";
    const sel = ag.agent_id === selectedAgent ? "selected" : "";
    return `
      <div class="row ${sel}" data-agent="${ag.agent_id}">
        <span><span class="dot ${dotCls}"></span>${ag.agent_id}
          <span class="role-tag">${ag.role || ""}</span></span>
        <span class="kv">${ag.last_beat ? ag.last_beat.slice(11,19) : "—"}</span>
      </div>`;
  }).join("") || "<div class='kv'>(no agents)</div>";
  $("#agents").innerHTML = html;
  document.querySelectorAll("#agents [data-agent]").forEach(el => {
    el.addEventListener("click", () => selectAgent(el.dataset.agent));
  });
}

async function selectAgent(aid) {
  selectedAgent = aid;
  await loadFleet();
  try {
    const a = await fetchJSON("/api/agents/" + encodeURIComponent(aid));
    $("#detail-title").textContent = aid;
    const tasks = (a.tasks || []).map(t => `
      <div class="task">
        <span class="state ${t.state}">${t.state}</span>
        <b style="margin-left:6px">${t.task_id}</b>
        <div style="margin-top:4px" class="kv">goal: ${t.original_goal || "?"}</div>
        ${t.next_step ? `<div class="kv">next: ${t.next_step}</div>` : ""}
        ${t.blocked_on ? `<div class="kv" style="color:#ef4444">blocked: ${JSON.stringify(t.blocked_on)}</div>` : ""}
        ${t.task_budget ? `<div class="kv">budget: ${t.task_budget.used}/${t.task_budget.max}</div>` : ""}
      </div>`).join("") || "<div class='kv'>(no active tasks)</div>";
    const events = (a.recent_events || []).slice(-20).reverse().map(e => `
      <div class="evt"><span class="t">${(e.ts || "").slice(11,19)}</span>${e.type || "?"}
        ${Object.entries(e).filter(([k]) => !["ts","type"].includes(k)).slice(0,3)
          .map(([k,v]) => `<span class="kv">${k}=${typeof v==="object"?JSON.stringify(v):v}</span>`).join(" ")}</div>`
    ).join("");
    const inbox = (a.inbox_pending || []).map(m => `
      <div class="evt"><b>${m.subject}</b> ← ${m.from}
        <div class="kv">${m.created_at}</div></div>`).join("") || "<div class='kv'>(inbox empty)</div>";
    $("#agent-detail").innerHTML = `
      <h3 style="font-size:13px;color:#94a3b8">Active tasks</h3>
      ${tasks}
      <h3 style="font-size:13px;color:#94a3b8;margin-top:14px">Inbox (pending)</h3>
      ${inbox}
      <h3 style="font-size:13px;color:#94a3b8;margin-top:14px">Recent events</h3>
      ${events || "<div class='kv'>(none)</div>"}
    `;
  } catch(e) {
    $("#agent-detail").innerHTML = `<div class='kv'>error: ${e.message}</div>`;
  }
}

async function loadEvents() {
  const data = await fetchJSON("/api/events?limit=40");
  $("#events").innerHTML = (data.events || []).map(e => `
    <div class="evt"><span class="t">${(e.ts||"").slice(11,19)}</span>
      <b>${e.agent.split("-").slice(-2,-1)[0] || e.agent}</b>
      ${e.type} ${e.msg_id ? `msg=${e.msg_id.slice(0,6)}` : ""}
      ${e.slug ? `slug=${e.slug}` : ""}</div>`).join("") || "<div class='kv'>(no events today)</div>";
}

async function loadProposals() {
  const data = await fetchJSON("/api/proposals");
  $("#proposals").innerHTML = (data.proposals || []).map(p => {
    const data = p.data || {};
    const critic = p.critic_verdict ? p.critic_verdict.verdict : "pending";
    return `
      <div class="proposal ${p.status === "rejected" ? "rejected" : ""}">
        <div><b>${p.kind}</b> · ${p.id}
          <span class="kv">status=${p.status}</span></div>
        <div class="kv">proposer: ${p.proposer}</div>
        ${data.slug ? `<div class="kv">slug: ${data.slug}</div>` : ""}
        ${data.rationale ? `<div class="kv">reason: ${data.rationale.slice(0,100)}</div>` : ""}
        ${data.lesson ? `<div class="kv">lesson: ${data.lesson.slice(0,100)}</div>` : ""}
        ${data.extra ? `<div class="kv">+${data.extra} iters</div>` : ""}
        <div class="kv">critic: ${critic}</div>
        ${p.status === "critic_approved" ? `
          <button onclick="approveProposal('${p.kind}','${p.id}')">approve</button>
          <button class="reject" onclick="rejectProposal('${p.kind}','${p.id}')">reject</button>` : ""}
      </div>`;
  }).join("") || "<div class='kv'>(no proposals)</div>";
}

window.approveProposal = async (kind, pid) => {
  await fetch(`/api/proposals/${kind}/${pid}/approve`, { method: "POST" });
  loadProposals();
};
window.rejectProposal = async (kind, pid) => {
  await fetch(`/api/proposals/${kind}/${pid}/reject`, { method: "POST" });
  loadProposals();
};

async function loadProjects() {
  const data = await fetchJSON("/api/projects");
  $("#projects").innerHTML = (data.projects || []).map(p => `
    <div class="project">
      <b>${p.project}</b> <span class="kv">(${p.member_count} member${p.member_count===1?"":"s"})</span>
      ${Object.entries(p.state).slice(0,3).map(([k,v]) => `
        <div class="kv">${k}: ${typeof v === "object" ? JSON.stringify(v) : v}</div>`).join("")}
    </div>`).join("") || "<div class='kv'>(no projects)</div>";
}

async function refreshAll() {
  try {
    await Promise.all([loadStats(), loadFleet(), loadEvents(), loadProposals(), loadProjects()]);
    if (selectedAgent) selectAgent(selectedAgent);
  } catch(e) {
    console.error(e);
  }
}

function connectWs() {
  const ws = new WebSocket(`ws://${location.host}/ws/stream`);
  ws.onmessage = () => refreshAll();
  ws.onclose = () => setTimeout(connectWs, 2000);
}

refreshAll();
setInterval(refreshAll, 5000);  // polling fallback
connectWs();
