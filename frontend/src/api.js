const API = "/api";

/**
 * Espelha `jogador_ordens_abertas_max` do backend (config.py) — só pra UI
 * bloquear o balcão antes do envio. A fonte de verdade continua sendo a API:
 * se o admin mudar o limite no .env, o 409 com a mensagem certa chega mesmo
 * que este número esteja defasado.
 */
export const MAX_ORDENS_ABERTAS = 10;

export function getToken() {
  return localStorage.getItem("token");
}

export function getSession() {
  try {
    const raw = localStorage.getItem("session");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveSession(token, user) {
  localStorage.setItem("token", token);
  localStorage.setItem("session", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("token");
  localStorage.removeItem("session");
}

/**
 * Fetch com token Bearer. Em 401 limpa a sessão (login expirado).
 */
export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";

  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearSession();
    window.dispatchEvent(new Event("session-expired"));
  }

  return res;
}

/** Parse de erro da API ({"detail": "..."}) com fallback. */
export async function errorOf(res, fallback) {
  try {
    const data = await res.json();
    return data.detail || fallback;
  } catch {
    return fallback;
  }
}

/** GET JSON: lança Error(message) quando a API responde com erro. */
export async function getJSON(path) {
  const res = await api(path);
  if (!res.ok) throw new Error(await errorOf(res, "Falha na API"));
  return res.json();
}

/** POST JSON com o mesmo contrato do getJSON. */
export async function postJSON(path, body) {
  const res = await api(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(await errorOf(res, "Falha na API"));
  return res.json();
}

/** PATCH JSON com o mesmo contrato do getJSON. */
export async function patchJSON(path, body) {
  const res = await api(path, {
    method: "PATCH",
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(await errorOf(res, "Falha na API"));
  return res.json();
}

/** DELETE com o mesmo contrato do getJSON (204 vira null). */
export async function delJSON(path) {
  const res = await api(path, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorOf(res, "Falha na API"));
  return res.status === 204 ? null : res.json();
}

/* ------------------------------------------------------------------ formatação */

export const brl = (v) =>
  Number(v || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });

/** Número com casas decimais mínimas/máximas em pt-BR (sem símbolo). */
export const num = (v, min = 2, max = min) =>
  Number(v || 0).toLocaleString("pt-BR", {
    minimumFractionDigits: min,
    maximumFractionDigits: max,
  });

/** Quantidade de unidades: some casas decimais inúteis (5 vira 5, 2.35 vira 2,35). */
export const qty = (v) => num(v, 0, 3);

export const pct = (v) => `${Number(v || 0) >= 0 ? "+" : ""}${num(v, 2)}%`;

export function timeAgo(iso) {
  if (!iso) return "";
  const seg = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seg < 60) return "agora";
  if (seg < 3600) return `há ${Math.floor(seg / 60)}min`;
  if (seg < 86400) return `há ${Math.floor(seg / 3600)}h`;
  return `há ${Math.floor(seg / 86400)}d`;
}

/** Emoji do commodity (o mundo simulado fica com cara de mundo mesmo). */
export function iconFor(name = "") {
  const n = name.toLowerCase();
  const mapa = [
    ["café", "☕"],
    ["trigo", "🌾"],
    ["algod", "🧶"],
    ["aço", "⚙️"],
    ["aco", "⚙️"],
    ["carv", "⛏️"],
    ["borracha", "🛞"],
    ["petr", "🛢️"],
    ["ouro", "🪙"],
    ["prata", "🥈"],
    ["milho", "🌽"],
    ["arroz", "🍚"],
    ["soja", "🌱"],
    ["coco", "🥥"],
    ["sal", "🧂"],
    ["made", "🪵"],
    ["couro", "🥾"],
    ["lã", "🐑"],
    ["fumo", "🍂"],
    ["vinho", "🍇"],
    ["ferro", "🔩"],
    ["cobre", "🥉"],
    ["zinc", "🥫"],
    ["tabaco", "🚬"],
    ["linha", "🧵"],
  ];
  for (const [chave, emoji] of mapa) {
    if (n.includes(chave)) return emoji;
  }
  return "📦";
}
