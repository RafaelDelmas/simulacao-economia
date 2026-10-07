import { useEffect, useRef } from "react";

import { Sparkline } from "./Chart";
import { brl, iconFor, num, pct, timeAgo } from "../api";

/**
 * Tela principal: quanto você tem, o mercado inteiro e o que está acontecendo
 * agora nas trocas dos bots e dos outros jogadores.
 */
export default function Market({
  commodities,
  points,
  ticker,
  me,
  positions,
  onOpen,
}) {
  const anterior = useRef({});
  const dirs = {};

  for (const c of commodities || []) {
    const antes = anterior.current[c.id];
    if (antes === undefined) continue;
    if (c.current_price > antes) dirs[c.id] = "up";
    else if (c.current_price < antes) dirs[c.id] = "down";
  }

  useEffect(() => {
    anterior.current = Object.fromEntries(
      (commodities || []).map((c) => [c.id, c.current_price]),
    );
  }, [commodities]);

  const saldo = Number(me?.balance || 0);
  const estoque = (positions || []).reduce((s, p) => s + (p.valor || 0), 0);
  const resultado = (positions || []).reduce((s, p) => s + (p.lucro || 0), 0);
  const patrimonio = saldo + estoque;

  return (
    <>
      <div className="balance-hero">
        <div className="balance-card accent">
          <div className="label">Saldo</div>
          <div className="value num">{brl(saldo)}</div>
          <div className="sub">dinheiro em caixa</div>
        </div>
        <div className="balance-card">
          <div className="label">Patrimônio</div>
          <div className="value num">{brl(patrimonio)}</div>
          <div className="sub num">
            estoque {brl(estoque)}
            {resultado !== 0 && (
              <>
                {" · "}
                <span className={resultado >= 0 ? "up" : "down"}>
                  {resultado >= 0 ? "+" : ""}
                  {brl(resultado)}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section-title">
          <h2>Mercado</h2>
          <span className="hint">
            <span className="live-dot" />
            ao vivo · toque para negociar
          </span>
        </div>

        {!commodities?.length ? (
          <div className="empty">
            <span className="big">⏳</span>
            Carregando as commodities…
          </div>
        ) : (
          <div className="commodity-grid">
            {commodities.map((c) => {
              const serie = points?.[c.id] || [];
              const dir = dirs[c.id];
              const varia = Number(c.variation_24h || 0);
              const classe =
                varia > 0 ? "up" : varia < 0 ? "down" : "flat";

              return (
                <button
                  key={c.id}
                  className="commodity-card"
                  onClick={() => onOpen(c.id)}
                >
                  <div className="head">
                    <span className="icon">{iconFor(c.name)}</span>
                    <span className="name">{c.name}</span>
                    {c.is_frozen && <span className="badge off">suspenso</span>}
                  </div>

                  <div className="price num">
                    <span
                      key={c.current_price}
                      className={
                        dir === "up"
                          ? "flash-up"
                          : dir === "down"
                            ? "flash-down"
                            : ""
                      }
                    >
                      {brl(c.current_price)}
                    </span>
                    <span className={`pill ${classe}`}>{pct(varia)}</span>
                  </div>

                  <Sparkline
                    points={serie.slice(-40)}
                    up={serie.length > 1 ? serie[serie.length - 1].p - serie[0].p : 0}
                  />
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="section">
        <div className="section-title">
          <h2>Movimentações</h2>
          <span className="hint">últimas trocas</span>
        </div>

        <div className="card">
          {!ticker?.length ? (
            <div className="empty">
              <span className="big">🫧</span>
              Nenhuma negociação nos últimos segundos…
            </div>
          ) : (
            <div className="ticker">
              {ticker.slice(0, 18).map((o) => (
                <div className="tick-row" key={o.id}>
                  <span className="emoji">{iconFor(nomeDe(o, commodities))}</span>
                  <span className="what">
                    {nomeDe(o, commodities)}{" "}
                    <span className="qty">
                      {o.side === "bid" ? "comprou" : "vendeu"}
                      {Number(o.executed_quantity) > 0
                        ? ` ${num(o.executed_quantity, 0, 2)} un`
                        : ""}
                    </span>
                  </span>
                  <span className={`val num ${o.side === "bid" ? "up" : "down"}`}>
                    {brl(o.price)}
                  </span>
                  <span className="when">{timeAgo(o.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}

function nomeDe(ordem, commodities) {
  const c = (commodities || []).find((x) => x.id === ordem.commodity_id);
  return c ? c.name : `#${ordem.commodity_id}`;
}
