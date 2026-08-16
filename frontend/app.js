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

function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  const isHidden = input.type === "password";
  input.type = isHidden ? "text" : "password";
  btn.textContent = isHidden ? "Hide" : "Show";
}

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
    const [groups, me] = await Promise.all([apiFetch("/users/me/groups"), apiFetch("/users/me")]);
    if (groups.length === 0) {
      el.innerHTML = `<p class="empty-state">You're not in a group yet — create one or join with an invite code below.</p>`;
      return;
    }

    // Render group shells first, then fill in members async per group.
    el.innerHTML = groups
      .map((g) => {
        const isCreator = g.creator_id === me.id;
        const actionBtn = isCreator
          ? `<button type="button" class="danger-btn" onclick="handleDeleteGroup('${g.id}', '${g.name}')">Delete group</button>`
          : `<button type="button" class="danger-btn" onclick="handleLeaveGroup('${g.id}', '${g.name}')">Leave group</button>`;
        return `
      <div class="group-item">
        <div class="group-name">${g.name}</div>
        <div class="group-code">Invite code: <code onclick="copyInvite('${g.invite_code}')" title="Click to copy">${g.invite_code}</code></div>
        <div class="group-code">${g.telegram_chat_id ? "✓ Group Telegram chat linked" : "⚠ No group chat linked"}</div>
        <div class="members-list" id="members-${g.id}">Loading members...</div>
        <div style="margin-top:10px;">${actionBtn}</div>
      </div>`;
      })
      .join("");

    for (const g of groups) {
      loadGroupMembers(g.id);
    }
  } catch (err) {
    el.innerHTML = `<p class="error">${err.message}</p>`;
  }
}

async function handleDeleteGroup(groupId, groupName) {
  if (!confirm(`Delete "${groupName}"? This removes it for every member and can't be undone.`)) return;
  try {
    await apiFetch(`/groups/${groupId}`, { method: "DELETE" });
    await loadGroups();
  } catch (err) {
    alert(err.message);
  }
}

async function handleLeaveGroup(groupId, groupName) {
  if (!confirm(`Leave "${groupName}"?`)) return;
  try {
    await apiFetch(`/groups/${groupId}/leave`, { method: "POST" });
    await loadGroups();
  } catch (err) {
    alert(err.message);
  }
}

async function loadGroupMembers(groupId) {
  const el = document.getElementById(`members-${groupId}`);
  try {
    const members = await apiFetch(`/groups/${groupId}/members`);
    el.innerHTML = members
      .map(
        (m) => `
        <div class="member-row">
          <span>${m.username} <span class="member-lc">(${m.leetcode_username})</span></span>
          <span class="${m.telegram_linked ? "member-linked" : "member-unlinked"}">
            ${m.telegram_linked ? "✓ Telegram" : "✗ Telegram"} · streak ${m.current_streak}
          </span>
        </div>`
      )
      .join("");
  } catch (err) {
    el.innerHTML = `<p class="error">Couldn't load members</p>`;
  }
}

function copyInvite(code) {
  navigator.clipboard.writeText(code);
}

async function detectGroupChats() {
  const el = document.getElementById("detected-chats-list");
  el.innerHTML = `<p class="empty-state">Checking recent bot activity...</p>`;
  try {
    const data = await apiFetch("/telegram/detected-group-chats");
    if (data.chats.length === 0) {
      el.innerHTML = `<p class="empty-state">No group chats found yet — add the bot to your Telegram group and send a message there, then try again.</p>`;
      return;
    }
    el.innerHTML = data.chats
      .map(
        (c) => `
        <div class="detected-chat" onclick="selectDetectedChat('${c.chat_id}')">
          ${c.title} <span class="member-lc">(${c.chat_id})</span>
        </div>`
      )
      .join("");
  } catch (err) {
    el.innerHTML = `<p class="error">${err.message}</p>`;
  }
}

function selectDetectedChat(chatId) {
  document.getElementById("create-group-chat-id").value = chatId;
}

// ---------- Telegram linking ----------

async function loadTelegramLinkStatus() {
  const el = document.getElementById("telegram-link-section");
  try {
    const me = await apiFetch("/users/me");
    const linked = !!me.telegram_chat_id;

    document.getElementById("group-actions-locked").classList.toggle("hidden", linked);
    document.getElementById("create-group-details").classList.toggle("hidden", !linked);
    document.getElementById("join-group-details").classList.toggle("hidden", !linked);

    if (linked) {
      el.innerHTML = `<p class="empty-state">✓ Telegram linked — you'll get a personal daily check-in and weekly summary DM. Group digests also need the group's own chat linked (set at group creation).</p>`;
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
    telegram_chat_id: document.getElementById("create-group-chat-id").value,
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
