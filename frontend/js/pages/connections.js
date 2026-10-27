// Connections: people who both chose to stay in touch, plus requests waiting on you.
import { ApiError, api, signOut } from "../core/api.js";
import { requireSession } from "../core/auth.js";
import { initAtmosphere } from "../core/fx.js";
import { applyTempStrings, tt } from "../core/strings-temp.js";
import { mountAppHeader, setPageState } from "../core/ui.js";

const $ = (s) => document.querySelector(s);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

async function respond(requestId, action) {
  await api(`/connections/${encodeURIComponent(requestId)}/${action}`, { method: "POST" });
  await load();
}

let activeFilter = "all";

function avatar(name) {
  const node = el("span", "storybook-avatar", [...(name || "?")][0]?.toUpperCase() ?? "?");
  node.setAttribute("aria-hidden", "true");
  return node;
}

function applyFilter() {
  const query = $("#connection-search").value.trim().toLocaleLowerCase();
  let visibleInScope = 0;
  for (const section of document.querySelectorAll("[data-connection-kind]")) {
    const kind = section.dataset.connectionKind;
    const inScope = activeFilter === "all" || activeFilter === kind;
    const list = section.querySelector("ul");
    let visibleRows = 0;
    for (const row of list.children) {
      const matches = row.textContent.toLocaleLowerCase().includes(query);
      row.hidden = !matches;
      if (matches) visibleRows += 1;
    }
    if (inScope) visibleInScope += visibleRows;
    const noConnections = kind === "connections" && !query && list.children.length === 0 && inScope;
    section.hidden = !inScope || (visibleRows === 0 && !noConnections);
  }
  const noConnections = $("#connections").children.length === 0 && !query && (activeFilter === "all" || activeFilter === "connections");
  $("#none").hidden = !noConnections;
  $("#filter-empty").hidden = !query || visibleInScope > 0;
  for (const button of document.querySelectorAll("[data-filter]")) {
    const selected = button.dataset.filter === activeFilter;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function render(data) {
  $("#incoming").replaceChildren(
    ...data.incoming.map((r) => {
      const item = el("li", "results-connect__row");
      item.append(avatar(r.display_name), el("span", "results-player__name", r.display_name));
      for (const [action, key, kind] of [["accept", "accept", "btn--primary"], ["decline", "decline", "btn--ghost"]]) {
        const button = el("button", `btn ${kind} btn--sm`, tt(`connections.${key}`));
        button.type = "button";
        button.addEventListener("click", () => respond(r.request_id, action));
        item.append(button);
      }
      return item;
    }),
  );
  $("#connections").replaceChildren(
    ...data.connections.map((c) => {
      const item = el("li", "results-connect__row");
      item.append(avatar(c.display_name), el("span", "results-player__name", c.display_name), el("span", "results-player__role", c.shareable_summary));
      return item;
    }),
  );
  $("#none").hidden = data.connections.length > 0;
  $("#outgoing").replaceChildren(...data.outgoing.map((o) => {
    const item = el("li", "results-connect__row");
    item.append(avatar(o.display_name), el("span", "results-player__name", o.display_name));
    return item;
  }));
  applyFilter();
}

async function load() {
  setPageState($("#page-state"), "loading");
  try {
    render(await api("/users/me/connections"));
    setPageState($("#page-state"), null);
    $("#content").hidden = false;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return;
    setPageState($("#page-state"), "error", { message: tt("connections.loadError"), onRetry: load });
  }
}

applyTempStrings();
initAtmosphere();
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
  activeFilter = button.dataset.filter;
  applyFilter();
}));
$("#connection-search").addEventListener("input", applyFilter);
const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  $("#user-initial").textContent = [...user.display_name][0]?.toUpperCase() ?? "";
  load();
}
