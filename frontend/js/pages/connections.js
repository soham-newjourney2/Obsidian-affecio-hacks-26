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

function render(data) {
  $("#incoming-panel").hidden = data.incoming.length === 0;
  $("#incoming").replaceChildren(
    ...data.incoming.map((r) => {
      const item = el("li", "results-connect__row");
      item.append(el("span", "results-player__name", r.display_name));
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
      item.append(el("span", "results-player__name", c.display_name), el("span", "results-player__role", c.shareable_summary));
      return item;
    }),
  );
  $("#none").hidden = data.connections.length > 0;
  $("#outgoing-panel").hidden = data.outgoing.length === 0;
  $("#outgoing").replaceChildren(...data.outgoing.map((o) => el("li", "results-connect__row", o.display_name)));
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
const user = requireSession();
if (user) {
  mountAppHeader(user, signOut);
  $("#user-initial").textContent = [...user.display_name][0]?.toUpperCase() ?? "";
  load();
}
