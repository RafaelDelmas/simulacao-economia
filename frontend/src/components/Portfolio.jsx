import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { money, iconFor, MAX_ORDENS_ABERTAS, num, pct, timeAgo } from "../api";

/**
 * Carteira: quanto dinheiro você tem, quanto está em estoque e o que está
 * parado no book esperando executar.
 */
export default function Portfolio({
  me,
  positions,
  commodities,
  mine,
  inflacao,
  onOpen,
  onCancel,
}) {
  const { t } = useTranslation();
  const [confirmando, setConfirmando] = useState(null);

  const saldo = Number(me?.balance || 0);
  const estoque = (positions || []).reduce((s, p) => s + (p.valor || 0), 0);
  const custo = (positions || []).reduce((s, p) => s + (p.custo || 0), 0);
  const resultado = estoque - custo;
  const patrimonio = saldo + estoque;
  const streak = Number(me?.streak || 0);
  // Índice de preços da rodada (1 = sem inflação): o patrimônio "real" é o
  // nominal deflacionado — quanto o dinheiro ainda compra de verdade.
  const indice = Number(inflacao || 1);
  const patrimonioReal = patrimonio / indice;

  const abertas = mine?.open || [];
  const executadas = (mine?.filled || []).slice(0, 12);
  const nomeDe = (id) =>
    t(commodities?.find((c) => c.id === id)?.name || `#${id}`);

  // a confirmação expira sozinha: toque perdido não cancela nada
  // (mesmo padrão do painel de usuários)
  useEffect(() => {
    if (!confirmando) return;
    const timer = setTimeout(() => setConfirmando(null), 5000);
    return () => clearTimeout(timer);
  }, [confirmando]);

  /** Cancelamento em dois toques: o primeiro arma, o segundo executa. */
  async function toqueCancelar(o) {
    if (confirmando !== o.id) {
      setConfirmando(o.id);
      return;
    }
    const ok = await onCancel?.(o.id);
    if (!ok) setConfirmando(null); // erro (ex.: já executou): volta ao normal
  }

  return (
    <>
      <div className="balance-hero">
        <div className="balance-card accent">
          <div className="label">{t("Saldo")}</div>
          <div className="value num">{money(saldo)}</div>
          <div className="sub">{t("livre para usar")}</div>
        </div>
        <div className="balance-card">
          <div className="label">{t("Patrimônio")}</div>
          <div className="value num">{money(patrimonio)}</div>
          <div className="sub num">
            {t("estoque {{v}}", { v: money(estoque) })}
            {indice > 1.0005 && (
              <>
                {" · "}
                <span
                  className="down"
                  title={t("poder de compra desde o início da rodada")}
                >
                  💸 {t("inflação {{v}}", { v: pct((indice - 1) * 100) })} ·{" "}
                  {t("real {{v}}", { v: money(patrimonioReal) })}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section-title">
          <h2>{t("Resultado")}</h2>
          <span className="hint">{t("marcação a mercado")}</span>
        </div>
        <div className="card">
          {streak > 0 && (
            <div className="list-row">
              <span className="grow">
                <span className="title">{t("🔥 Combo de vendas lucrativas")}</span>
                <span className="sub">
                  {t("venda no lucro aumenta · no prejuízo zera")}
                </span>
              </span>
              <span className="right">
                <span className="big num">x{streak}</span>
              </span>
            </div>
          )}
          <div className="list-row">
            <span className="grow">
              <span className="title">{t("Lucro / prejuízo")}</span>
              <span className="sub num">
                {t("pago {{a}} · agora vale {{b}}", {
                  a: money(custo),
                  b: money(estoque),
                })}
              </span>
            </span>
            <span className="right">
              <span className={`big num ${resultado >= 0 ? "up" : "down"}`}>
                {resultado >= 0 ? "+" : ""}
                {money(resultado)}
              </span>
              <span className="small num">
                {custo > 0
                  ? `${resultado >= 0 ? "+" : ""}${num((resultado / custo) * 100, 2)}%`
                  : "—"}
              </span>
            </span>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Seu estoque")}</h2>
          <span className="hint">{t("toque para negociar")}</span>
        </div>

        <div className="card">
          {!positions?.length ? (
            <div className="empty">
              <span className="big">🧺</span>
              {t("Sua carteira está vazia.")}
              <br />
              {t("Compre sua primeira commodity no mercado.")}
            </div>
          ) : (
            positions.map((p) => (
              <button
                key={p.commodity_id}
                className="list-row list-row-btn"
                onClick={() => onOpen(p.commodity_id)}
              >
                <span style={{ fontSize: 20 }}>{iconFor(p.name)}</span>
                <span className="grow">
                  <span className="title">{t(p.name)}</span>
                  <span className="sub num">
                    {t("{{qtd}} un · média {{a}} · atual {{b}}", {
                      qtd: num(p.quantity, 0, 3),
                      a: money(p.avg_price),
                      b: money(p.current_price),
                    })}
                  </span>
                </span>
                <span className="right">
                  <span className="big num">{money(p.valor)}</span>
                  <span className={`small num ${p.lucro >= 0 ? "up" : "down"}`}>
                    {p.lucro >= 0 ? "+" : ""}
                    {money(p.lucro)}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Ordens abertas")}</h2>
          <span className="hint">
            {t("{{n}}/{{max}} ordens · expiram em 10h · toque ✖ para cancelar", {
              n: abertas.length,
              max: MAX_ORDENS_ABERTAS,
            })}
          </span>
        </div>
        <div className="card">
          {!abertas.length ? (
            <div className="empty">
              <span className="big">🕊️</span>
              {t("Nenhuma ordem esperando no book.")}
            </div>
          ) : (
            abertas.map((o) => (
              <div className="list-row" key={o.id}>
                <button
                  className="row-open"
                  onClick={() => onOpen(o.commodity_id)}
                >
                  <span className="title">
                    {nomeDe(o.commodity_id)}{" "}
                    <span className="badge open">
                      {o.side === "bid" ? t("compra") : t("venda")}
                    </span>
                  </span>
                  <span className="sub num">
                    {t("restam {{qtd}} un a {{preco}}", {
                      qtd: num(o.quantity, 0, 3),
                      preco: money(o.price),
                    })}{" "}
                    · {timeAgo(o.created_at)}
                  </span>
                </button>
                <button
                  className={confirmando === o.id ? "chip danger on" : "chip"}
                  onClick={() => toqueCancelar(o)}
                >
                  {confirmando === o.id
                    ? t("cancelar mesmo?")
                    : t("✖ cancelar")}
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Histórico")}</h2>
          <span className="hint">{t("suas execuções")}</span>
        </div>
        <div className="card">
          {!executadas.length ? (
            <div className="empty">
              <span className="big">📜</span>
              {t("Suas ordens executadas aparecem aqui.")}
            </div>
          ) : (
            executadas.map((o) => (
              <div className="list-row" key={o.id}>
                <span className="grow">
                  <span className="title">
                    {nomeDe(o.commodity_id)}{" "}
                    <span className="badge done">
                      {o.side === "bid" ? t("comprou") : t("vendeu")}
                    </span>
                  </span>
                  <span className="sub num">
                    {t("a {{preco}}", { preco: money(o.price) })} ·{" "}
                    {timeAgo(o.created_at)}
                  </span>
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </>
  );
}
