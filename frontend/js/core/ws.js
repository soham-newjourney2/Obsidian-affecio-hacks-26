// Room WebSocket client: auth-first, heartbeat, backoff reconnect, resync on every (re)connect.
// The server answers auth with a fresh room.snapshot, so reconnecting always resyncs state.

const HEARTBEAT_MS = 20_000;
const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];
const NO_RETRY = new Map([
  [4401, "unauthorized"],
  [4403, "forbidden"],
  [1000, "closed"],
]);

function newId() {
  return crypto.randomUUID().replaceAll("-", "");
}

/**
 * connectRoom(roomId, { getToken, onFrame, onStatus })
 * status: "connecting" | "connected" | "reconnecting" | "offline" | "closed" | "unauthorized" | "forbidden"
 */
export function connectRoom(roomId, { getToken, onFrame, onStatus }) {
  let socket = null;
  let attempt = 0;
  let heartbeat = null;
  let retryTimer = null;
  let stopped = false;
  let live = false;

  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/v1/ws/rooms/${encodeURIComponent(roomId)}`;

  function setStatus(status) {
    onStatus?.(status);
  }

  function clearTimers() {
    clearInterval(heartbeat);
    clearTimeout(retryTimer);
    heartbeat = retryTimer = null;
  }

  function scheduleRetry() {
    if (stopped) return;
    if (!navigator.onLine) {
      setStatus("offline"); // the "online" listener reconnects
      return;
    }
    setStatus("reconnecting");
    const base = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)];
    attempt += 1;
    retryTimer = setTimeout(open, base + Math.random() * 400);
  }

  function open() {
    clearTimers();
    const token = getToken();
    if (!token) {
      setStatus("unauthorized");
      return;
    }
    live = false;
    setStatus(attempt === 0 ? "connecting" : "reconnecting");
    socket = new WebSocket(url);
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify({ type: "auth", id: newId(), payload: { token } }));
    });
    socket.addEventListener("message", (event) => {
      let frame;
      try {
        frame = JSON.parse(event.data);
      } catch {
        return;
      }
      if (frame.type === "room.snapshot") {
        live = true;
        attempt = 0;
        setStatus("connected");
        heartbeat = setInterval(() => send("presence.ping", {}), HEARTBEAT_MS);
      }
      onFrame?.(frame);
    });
    socket.addEventListener("close", (event) => {
      clearTimers();
      live = false;
      const final = NO_RETRY.get(event.code);
      if (final || stopped) {
        stopped = true;
        setStatus(final ?? "closed");
        return;
      }
      scheduleRetry();
    });
  }

  function send(type, payload = {}) {
    if (!live || socket?.readyState !== WebSocket.OPEN) return null;
    const id = newId();
    socket.send(JSON.stringify({ type, id, payload }));
    return id;
  }

  function onOnline() {
    if (stopped) return;
    if (live) {
      setStatus("connected"); // the socket survived the blip
      return;
    }
    attempt = 0;
    open();
  }
  function onOffline() {
    if (!stopped) setStatus("offline");
  }
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);

  open();

  return {
    send,
    get live() {
      return live;
    },
    close() {
      stopped = true;
      clearTimers();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      socket?.close(1000);
    },
  };
}

export { newId };
