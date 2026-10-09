import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { Sparkline } from "./Chart";
import { iconFor, money, num, pct, regimeLabel, timeAgo } from "../api";

/**
 * Tela principal: quanto você tem, o mercado inteiro e o que está acontecendo
 * agora nas trocas dos bots e dos outros jogadores.
 */
export default function Market({
  commodities,
  points,
  ticker,
  destaques,
  manchete,
  inflacao,
  me,
  positions,
  onOpen,
}) {
  const { t } = useTranslation();
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
          <div className="label">{t("Saldo")}</div>
          <div className="value num">{money(saldo)}</div>
          <div className="sub">{t("dinheiro em caixa")}</div>
        </div>
        <div className="balance-card">
          <div className="label">{t("Patrimônio")}</div>
          <div className="value num">{money(patrimonio)}</div>
          <div className="sub num">
            {t("estoque {{v}}", { v: money(estoque) })}
            {resultado !== 0 && (
              <>
                {" · "}
                <span className={resultado >= 0 ? "up" : "down"}>
                  {resultado >= 0 ? "+" : ""}
                  {money(resultado)}
                </span>
              </>
            )}
            {inflacao > 1.0005 && (
              <>
                {" · "}
                <span
                  className="down"
                  title={t("poder de compra desde o início da rodada")}
                >
                  💸 {pct((inflacao - 1) * 100)}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section-title">
          <h2>{t("Mercado")}</h2>
          <span className="hint">
            <span className="live-dot" />
            {t("ao vivo · toque para negociar")}
          </span>
        </div>

        {!commodities?.length ? (
          <div className="empty">
            <span className="big">⏳</span>
            {t("Carregando as commodities…")}
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
                    <span className="name">{t(c.name)}</span>
                    {c.regime && c.regime !== "calmo" && (
                      <span className={`badge regime ${c.regime}`}>
                        {regimeLabel(c.regime)}
                      </span>
                    )}
                    {c.is_frozen && (
                      <span className="badge off">{t("suspenso")}</span>
                    )}
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
                      {money(c.current_price)}
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
          <h2>{t("Movimentações")}</h2>
          <span className="hint">{t("últimas trocas")}</span>
        </div>

        <div className="card">
          {!ticker?.length && !destaques?.length && !manchete ? (
            <div className="empty">
              <span className="big">🫧</span>
              {t("Nenhuma negociação nos últimos segundos…")}
            </div>
          ) : (
            <div className="ticker">
              {/* 📰 manchete no topo: a notícia é a cena, não o número */}
              {manchete && (
                <div className="tick-row news" key={`news-${manchete.emitido_em}`}>
                  <span className="emoji">{manchete.emoji}</span>
                  <span className="what">
                    <span className="news-chip">{t("📰 manchete")}</span>{" "}
                    {manchete.titulo}
                  </span>
                  <span className={`val num ${manchete.impacto >= 0 ? "up" : "down"}`}>
                    {pct(manchete.impacto)}
                  </span>
                  <span className="when">{t("agora")}</span>
                </div>
              )}

              {/* 🐋 baleias primeiro: o grande prêmio não pode se perder */}
              {(destaques || []).map((d) => (
                <div className="tick-row whale" key={d.chave}>
                  <span className="emoji">🐋</span>
                  <span className="what">
                    {t(nomeDe(d, commodities))}{" "}
                    <span className="qty">
                      {t("baleia {{acao}} {{qtd}} un", {
                        acao: d.side === "bid" ? t("comprou") : t("vendeu"),
                        qtd: num(d.quantity, 0, 2),
                      })}
                    </span>
                  </span>
                  <span
                    className={`val num ${d.side === "bid" ? "up" : "down"}`}
                  >
                    {money(d.price)}
                  </span>
                  <span className="when">{t("agora")}</span>
                </div>
              ))}

              {ticker.slice(0, 18).map((o) => (
                <div className="tick-row" key={o.id}>
                  <span className="emoji">{iconFor(nomeDe(o, commodities))}</span>
                  <span className="what">
                    {t(nomeDe(o, commodities))}{" "}
                    <span className="qty">
                      {o.side === "bid" ? t("comprou") : t("vendeu")}
                      {Number(o.executed_quantity) > 0
                        ? t(" {{qtd}} un", { qtd: num(o.executed_quantity, 0, 2) })
                        : ""}
                    </span>
                  </span>
                  <span className={`val num ${o.side === "bid" ? "up" : "down"}`}>
                    {money(o.price)}
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
