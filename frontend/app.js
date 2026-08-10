// Same-origin by default since FastAPI serves this file directly. If you ever open this
// file standalone (e.g. file:// or a different dev server), set API_BASE to your backend URL.
const API_BASE = "";

function getToken() {
  return localStorage.getItem("streakpact_token");
}
function setToken(token) {
  localStorage.setItem("streakpact_token", token);
}
function clearToken() {
  localStorage.removeItem("streakpact_token");
}

async function apiFetch(path, options = {}) {
  const headers = options.headers || {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body.detail) detail = body.detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return resp.json();
}

// ---------- Tabs ----------

function showTab(which) {
  document.getElementById("tab-login").classList.toggle("active", which === "login");
  document.getElementById("tab-signup").classList.toggle("active", which === "signup");
  document.getElementById("login-form").classList.toggle("hidden", which !== "login");
  document.getElementById("signup-form").classList.toggle("hidden", which !== "signup");
}

// ---------- Auth ----------

async function handleLogin(event) {
  event.preventDefault();
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "";

  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;

  try {
    const form = new URLSearchParams();
    form.set("username", username);
    form.set("password", password);

    const resp = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || "Login failed");
    }
    const data = await resp.json();
    setToken(data.access_token);
    await enterDashboard();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

async function handleSignup(event) {
  event.preventDefault();
  const errorEl = document.getElementById("signup-error");
  errorEl.textContent = "";

  const payload = {
    username: document.getElementById("signup-username").value,
    password: document.getElementById("signup-password").value,
    leetcode_username: document.getElementById("signup-leetcode").value,
    codeforces_handle: document.getElementById("signup-codeforces").value || null,
  };

  try {
    await apiFetch("/users", { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
    // Auto-login after successful signup.
    const form = new URLSearchParams();
    form.set("username", payload.username);
    form.set("password", payload.password);
    const resp = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    const data = await resp.json();
    setToken(data.access_token);
    await enterDashboard();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

function logout() {
  clearToken();
  document.getElementById("dashboard-view").classList.add("hidden");
  document.getElementById("logout-btn").classList.add("hidden");
  document.getElementById("auth-view").classList.remove("hidden");
}

// ---------- Dashboard ----------

async function enterDashboard() {
  document.getElementById("auth-view").classList.add("hidden");
  document.getElementById("dashboard-view").classList.remove("hidden");
  document.getElementById("logout-btn").classList.remove("hidden");
  await Promise.all([loadProfile(), loadGroups(), loadTelegramLinkStatus()]);
}

async function loadProfile() {
  const el = document.getElementById("profile-summary");
  try {
    const data = await apiFetch("/users/me/history?days=14");
    const streak = data.streak || { current_streak: 0, longest_streak: 0 };
    el.innerHTML = `
      <div class="stat-row">
        <div class="stat"><div class="stat-value">${streak.current_streak}</div><div class="stat-label">Current streak</div></div>
        <div class="stat"><div class="stat-value">${streak.longest_streak}</div><div class="stat-label">Longest streak</div></div>
      </div>
      <p class="empty-state">Signed in as <strong>${data.user.username}</strong> (LeetCode: ${data.user.leetcode_username})</p>
    `;
    renderHistory(data.history);
  } catch (err) {
    el.innerHTML = `<p class="error">${err.message}</p>`;
  }
}

function renderHistory(history) {
  const el = document.getElementById("history-list");
  if (!history || history.length === 0) {
    el.innerHTML = `<p class="empty-state">No activity yet — your first daily pull will show up here.</p>`;
    return;
  }
  el.innerHTML = history
    .map(
      (row) => `
      <div class="history-row">
        <span class="history-date">${row.activity_date}</span>
        <span>${row.problems_solved} solved (E:${row.easy_count} M:${row.medium_count} H:${row.hard_count})</span>
      </div>`
    )
    .join("");
}

async function loadGroups() {
  const el = document.getElementById("groups-list");
  try {
    const groups = await apiFetch("/users/me/groups");
    if (groups.length === 0) {
      el.innerHTML = `<p class="empty-state">You're not in a group yet — create one or join with an invite code below.</p>`;
      return;
    }
    el.innerHTML = groups
      .map((g) => {
        const chatStatus = g.telegram_chat_id
          ? `<div class="group-code">✓ Group Telegram chat linked</div>`
          : `
            <div class="group-code">No group chat linked yet</div>
            <form onsubmit="handleSetGroupChatId(event, '${g.id}')" style="margin-top:8px;">
              <input type="text" id="group-chat-input-${g.id}" placeholder="Telegram group chat ID" style="margin-bottom:6px;" />
              <button type="submit">Link this group's chat</button>
            </form>
            <p class="error" id="group-chat-error-${g.id}"></p>
          `;
        return `
      <div class="group-item">
        <div class="group-name">${g.name}</div>
        <div class="group-code">Invite code: <code onclick="copyInvite('${g.invite_code}')" title="Click to copy">${g.invite_code}</code></div>
        ${chatStatus}
      </div>`;
      })
      .join("");
  } catch (err) {
    el.innerHTML = `<p class="error">${err.message}</p>`;
  }
}

async function handleSetGroupChatId(event, groupId) {
  event.preventDefault();
  const input = document.getElementById(`group-chat-input-${groupId}`);
  const errorEl = document.getElementById(`group-chat-error-${groupId}`);
  errorEl.textContent = "";
  try {
    await apiFetch(`/groups/${groupId}/telegram-chat-id`, {
      method: "PATCH",
      body: JSON.stringify({ telegram_chat_id: input.value }),
      headers: { "Content-Type": "application/json" },
    });
    await loadGroups();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

function copyInvite(code) {
  navigator.clipboard.writeText(code);
}

// ---------- Telegram linking ----------

async function loadTelegramLinkStatus() {
  const el = document.getElementById("telegram-link-section");
  try {
    const me = await apiFetch("/users/me");
    if (me.telegram_chat_id) {
      el.innerHTML = `<p class="empty-state">✓ Telegram linked — you'll get a personal daily check-in and weekly summary DM. Group digests also need the group's own chat linked (see "Your groups" below).</p>`;
      return;
    }
    renderLinkTelegramButton(el);
  } catch (err) {
    el.innerHTML = "";
  }
}

async function renderLinkTelegramButton(el) {
  try {
    const data = await apiFetch("/users/me/telegram-link");
    el.innerHTML = `
      <p class="empty-state">Telegram not linked yet.</p>
      <a href="${data.link}" target="_blank" rel="noopener">
        <button type="button">Open Telegram &amp; tap Start</button>
      </a>
      <button type="button" onclick="checkTelegramLink()" style="margin-top:8px;background:none;border:1px solid var(--border);color:var(--text-muted)">
        I've done that — check now
      </button>
      <p class="error" id="telegram-link-error"></p>
    `;
  } catch (err) {
    el.innerHTML = `<p class="empty-state">Telegram linking isn't configured on this server yet.</p>`;
  }
}

async function checkTelegramLink() {
  const errorEl = document.getElementById("telegram-link-error");
  errorEl.textContent = "Checking...";
  try {
    await apiFetch("/users/me/link-telegram", { method: "POST" });
    await loadTelegramLinkStatus();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

async function handleCreateGroup(event) {
  event.preventDefault();
  const errorEl = document.getElementById("create-group-error");
  errorEl.textContent = "";

  const payload = {
    name: document.getElementById("create-group-name").value,
    telegram_chat_id: document.getElementById("create-group-chat-id").value || null,
  };

  try {
    await apiFetch("/groups", { method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" } });
    document.getElementById("create-group-name").value = "";
    document.getElementById("create-group-chat-id").value = "";
    await loadGroups();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

async function handleJoinGroup(event) {
  event.preventDefault();
  const errorEl = document.getElementById("join-group-error");
  errorEl.textContent = "";

  const invite_code = document.getElementById("join-invite-code").value;

  try {
    await apiFetch("/groups/join", { method: "POST", body: JSON.stringify({ invite_code }), headers: { "Content-Type": "application/json" } });
    document.getElementById("join-invite-code").value = "";
    await loadGroups();
  } catch (err) {
    errorEl.textContent = err.message;
  }
}

// ---------- Init ----------

if (getToken()) {
  enterDashboard().catch(() => logout()); // token might be expired/invalid
}