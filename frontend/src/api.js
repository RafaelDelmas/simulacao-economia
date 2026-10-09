// Instância global do i18n: este módulo não é um componente React, então fora
// do `useTranslation()` a tradução é `i18n.t(...)` direto (timeAgo, regime).
import i18n, { localeAtual, moedaAtual } from "./i18n/index.js";

const API = "/api";

/**
 * Espelha `jogador_ordens_abertas_max` do backend (config.py) — só pra UI
 * bloquear o balcão antes do envio. A fonte de verdade continua sendo a API:
 * se o admin mudar o limite no .env, o 409 com a mensagem certa chega mesmo
 * que este número esteja defasado.
 */
export const MAX_ORDENS_ABERTAS = 10;

/**
 * Humor do mercado (backend: `app/core/market/regimes.py`). O backend manda o
 * id cru no `regime` da commodity; este rótulo é pro chip no card.
 * Função (não objeto) pra reagir à troca de idioma.
 */
export function regimeLabel(regime) {
  const mapa = {
    calmo: "😐 calmo",
    alta: "📈 alta",
    euforia: "🔥 euforia",
    correcao: "📉 correção",
  };
  return mapa[regime] ? i18n.t(mapa[regime]) : regime;
}

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

/** Parse de erro da API ({"detail": "...", "code", "params"}) com fallback. */
export class ApiError extends Error {
  constructor(message, code = null, params = null) {
    super(message);
    this.code = code; // chave estável de tradução (mensagens dinâmicas)
    this.params = params; // valores interpolados da mensagem
  }
}

export async function errorOf(res, fallback) {
  try {
    const data = await res.json();
    // Só string: validação do FastAPI devolve `detail` como lista (422).
    if (typeof data.detail === "string") {
      return new ApiError(data.detail, data.code, data.params);
    }
    return new ApiError(fallback);
  } catch {
    return new ApiError(fallback);
  }
}

/**
 * Mensagem de erro traduzida, na ordem:
 * 1. `code` + `params` do backend (mensagens dinâmicas — a tradução monta
 *    o texto com os valores, o `detail` PT fica como `defaultValue`);
 * 2. o `detail` PT como chave (textos estáticos não têm code — e como a chave
 *    É o texto, sem tradução ele volta em PT sozinho);
 * 3. o fallback do call site.
 * Parâmetros string (nomes de commodity) passam por `t()` também — assim
 * "Carvão" vira "Coal" dentro da própria mensagem de erro.
 */
export function erroTraduzido(t, e, padrao) {
  if (e instanceof ApiError && e.code) {
    return t(e.code, { ...traduzParams(t, e.params), defaultValue: e.message });
  }
  if (e && typeof e.message === "string" && e.message) return t(e.message);
  return t(padrao);
}

/** Params do backend → valores prontos: strings e listas de strings (nomes)
 * passam por `t()`; o resto (números) vai cru. */
function traduzParams(t, params) {
  const out = {};
  for (const [k, v] of Object.entries(params || {})) {
    if (typeof v === "string") out[k] = t(v);
    else if (Array.isArray(v))
      out[k] = v.map((x) => (typeof x === "string" ? t(x) : x)).join(", ");
    else out[k] = v;
  }
  return out;
}

/**
 * `detail` de sucesso da API traduzido (toasts do admin): usa `code`/`params`
 * quando o backend mandou (detalhe dinâmico), senão o `detail` PT como chave.
 */
export function traduzDetalhe(t, r) {
  if (!r) return "";
  if (r.code) {
    return t(r.code, { ...traduzParams(t, r.params), defaultValue: r.detail });
  }
  return r.detail ? t(r.detail) : "";
}

/** GET JSON: lança Error(message) quando a API responde com erro. */
export async function getJSON(path) {
  const res = await api(path);
  if (!res.ok) throw await errorOf(res, "Falha na API");
  return res.json();
}

/** POST JSON com o mesmo contrato do getJSON. */
export async function postJSON(path, body) {
  const res = await api(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw await errorOf(res, "Falha na API");
  return res.json();
}

/** PATCH JSON com o mesmo contrato do getJSON. */
export async function patchJSON(path, body) {
  const res = await api(path, {
    method: "PATCH",
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw await errorOf(res, "Falha na API");
  return res.json();
}

/** DELETE com o mesmo contrato do getJSON (204 vira null). */
export async function delJSON(path) {
  const res = await api(path, { method: "DELETE" });
  if (!res.ok) throw await errorOf(res, "Falha na API");
  return res.status === 204 ? null : res.json();
}

/* ------------------------------------------------------------------ formatação */

/**
 * Dinheiro: mesmo valor sempre (a simulação não tem câmbio — 1:1, só o
 * símbolo muda: R$ 45,08 → £45.08 no idioma EN).
 */
export const money = (v) =>
  Number(v || 0).toLocaleString(localeAtual(), {
    style: "currency",
    currency: moedaAtual(),
  });

/** Número com casas decimais mínimas/máximas no locale ativo (sem símbolo). */
export const num = (v, min = 2, max = min) =>
  Number(v || 0).toLocaleString(localeAtual(), {
    minimumFractionDigits: min,
    maximumFractionDigits: max,
  });

/** Quantidade de unidades: some casas decimais inúteis (5 vira 5, 2.35 vira 2,35). */
export const qty = (v) => num(v, 0, 3);

export const pct = (v) => `${Number(v || 0) >= 0 ? "+" : ""}${num(v, 2)}%`;

export function timeAgo(iso) {
  if (!iso) return "";
  const seg = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seg < 60) return i18n.t("agora");
  if (seg < 3600) return i18n.t("há {{n}}min", { n: Math.floor(seg / 60) });
  if (seg < 86400) return i18n.t("há {{n}}h", { n: Math.floor(seg / 3600) });
  return i18n.t("há {{n}}d", { n: Math.floor(seg / 86400) });
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
