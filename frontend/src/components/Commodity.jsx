import { useEffect, useMemo, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { PriceChart } from "./Chart";
import { iconFor, MAX_ORDENS_ABERTAS, money, num, pct, regimeLabel, timeAgo } from "../api";

/** Distância máxima (sobre o preço alvo) pra uma ordem contar como "quase". */
const QUASE_LIMITE = 0.02;

/**
 * Tela do commodity: gráfico, livro de ofertas ao vivo, o balcão de compra/venda
 * e o histórico de ordens do próprio jogador nesta commodity.
 */
export default function Commodity({
  commodity,
  points,
  book,
  mine,
  position,
  me,
  onBack,
  onOrder,
}) {
  const { t } = useTranslation();
  const [lado, setLado] = useState("bid");
  const [qtd, setQtd] = useState("1");
  const [manual, setManual] = useState("");
  const [auto, setAuto] = useState(true);
  const [enviando, setEnviando] = useState(false);

  const melhorAsk = book?.asks?.[0]?.price;
  const melhorBid = book?.bids?.[0]?.price;
  const atual = Number(commodity?.current_price || 0);
  const ideal = lado === "bid" ? (melhorAsk ?? atual) : (melhorBid ?? atual);

  // trocou de lado, volta pro melhor preço do book
  useEffect(() => {
    setAuto(true);
  }, [lado]);

  const preco = auto ? ideal : Number(manual || 0);
  const quantidade = Number(qtd || 0);
  const saldo = Number(me?.balance || 0);
  const estoque = Number(position?.quantity || 0);

  const custo = quantidade * preco;
  const ehCompra = lado === "bid";

  // Saldo/estoque LIVRE: desconta o já comprometido em ordens abertas —
  // espelha o `_check_trade` do backend. Sem isso duas ordens de 1 un
  // passariam cada uma checando contra o mesmo saldo/estoque de 1.
  const abertasMinhas = mine?.open || [];
  const saldoComprometido = abertasMinhas
    .filter((o) => o.side === "bid")
    .reduce((soma, o) => soma + o.quantity * o.price, 0);
  const estoqueComprometido = abertasMinhas
    .filter((o) => o.side === "ask" && o.commodity_id === commodity.id)
    .reduce((soma, o) => soma + o.quantity, 0);
  const saldoLivre = saldo - saldoComprometido;
  const estoqueLivre = estoque - estoqueComprometido;

  const semSaldo = ehCompra && custo > saldoLivre + 1e-9;
  const semEstoque = !ehCompra && quantidade > estoqueLivre + 1e-9;
  // Limite é GLOBAL (todas as commodities), por isso conta mine.open inteiro.
  const noLimite = abertasMinhas.length >= MAX_ORDENS_ABERTAS;

  const abertas = (mine?.open || []).filter(
    (o) => o.commodity_id === commodity.id,
  );
  const executadas = (mine?.filled || [])
    .filter((o) => o.commodity_id === commodity.id)
    .slice(0, 8);

  // Efeito "quase executou": ordem do jogador grudada no outro lado do book
  // mas ainda sem cruzar. O book já está na tela — é só a conta de distância.
  const quases = abertas.flatMap((o) => {
    if (o.side === "ask") {
      if (melhorBid == null || o.price <= melhorBid) return [];
      const falta = o.price - melhorBid;
      return falta / Math.max(o.price, 0.01) <= QUASE_LIMITE
        ? [{ o, falta, alvo: melhorBid, lado: t("melhor compra") }]
        : [];
    }
    if (melhorAsk == null || o.price >= melhorAsk) return [];
    const falta = melhorAsk - o.price;
    return falta / Math.max(melhorAsk, 0.01) <= QUASE_LIMITE
      ? [{ o, falta, alvo: melhorAsk, lado: t("melhor venda") }]
      : [];
  });

  const maximo = useMemo(() => {
    if (ehCompra) {
      return preco > 0 ? Math.max(0, Math.floor(saldoLivre / preco)) : 0;
    }
    return Math.max(0, Math.floor(estoqueLivre));
  }, [ehCompra, preco, saldoLivre, estoqueLivre]);

  function ajustar(delta) {
    setQtd(String(Math.max(0, Math.round((quantidade + delta) * 100) / 100)));
  }

  async function enviar() {
    if (commodity.is_frozen) return; // balcão fechado pelo admin
    if (noLimite) return; // já tem o máximo de ordens abertas no book
    if (quantidade <= 0 || preco <= 0 || semSaldo || semEstoque) return;
    setEnviando(true);
    try {
      const ok = await onOrder({
        commodity_id: commodity.id,
        side: lado,
        quantity: quantidade,
        price: preco,
      });
      if (ok) setAuto(true);
    } finally {
      setEnviando(false);
    }
  }

  const asks = [...(book?.asks || [])].reverse();
  const bids = book?.bids || [];
  const maiorVolume = Math.max(
    1,
    ...asks.map((n) => n.quantity),
    ...bids.map((n) => n.quantity),
  );
  const varia = Number(commodity.variation_24h || 0);

  return (
    <>
      <section className="section" style={{ paddingTop: 16 }}>
        <button className="back-btn" onClick={onBack}>
          ‹ {t("voltar ao mercado")}
        </button>

        <div className="detail-head">
          <span className="icon">{iconFor(commodity.name)}</span>
          <div style={{ minWidth: 0 }}>
            <h1>{t(commodity.name)}</h1>
            {commodity.description && (
              <div className="desc">{t(commodity.description)}</div>
            )}
          </div>
        </div>

        <div className="detail-price">
          <span className="now num">{money(commodity.current_price)}</span>
          <span className={`pill ${varia >= 0 ? "up" : "down"}`}>
            {pct(varia)}
          </span>
          {commodity.regime && commodity.regime !== "calmo" && (
            <span className={`badge regime ${commodity.regime}`}>
              {regimeLabel(commodity.regime)}
            </span>
          )}
          {commodity.is_frozen && (
            <span className="badge off">{t("suspenso")}</span>
          )}
        </div>

        <div className="card">
          <PriceChart points={points || []} cor="#f2c14e" />
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Livro de ofertas")}</h2>
          <span className="hint">
            <span className="live-dot" />
            {t("ao vivo")}
          </span>
        </div>

        <div className="card">
          <div className="book">
            <div className="book-head">
              <span>{t("preço")}</span>
              <span>{t("quantidade")}</span>
              <span style={{ textAlign: "right" }}>{t("ordens")}</span>
            </div>

            {asks.length === 0 && bids.length === 0 ? (
              <div className="book-empty">{t("Book vazio neste instante…")}</div>
            ) : (
              <>
                {asks.map((n) => (
                  <div className="book-row ask" key={`a${n.price}`}>
                    <span
                      className="bar"
                      style={{
                        width: `${(n.quantity / maiorVolume) * 100}%`,
                      }}
                    />
                    <span className="price num">{money(n.price)}</span>
                    <span className="qty num">{num(n.quantity, 0, 3)}</span>
                    <span className="orders num">{n.orders}</span>
                  </div>
                ))}

                <div className="book-spread">
                  <span>
                    {t("melhor venda")}{" "}
                    <b className="num">{melhorAsk ? money(melhorAsk) : "—"}</b>
                  </span>
                  <span>
                    spread{" "}
                    <b className="num">
                      {book?.spread != null && book.spread >= 0
                        ? money(book.spread)
                        : "—"}
                    </b>
                  </span>
                  <span>
                    {t("melhor compra")}{" "}
                    <b className="num">{melhorBid ? money(melhorBid) : "—"}</b>
                  </span>
                </div>

                {bids.map((n) => (
                  <div className="book-row bid" key={`b${n.price}`}>
                    <span
                      className="bar"
                      style={{
                        width: `${(n.quantity / maiorVolume) * 100}%`,
                      }}
                    />
                    <span className="price num">{money(n.price)}</span>
                    <span className="qty num">{num(n.quantity, 0, 3)}</span>
                    <span className="orders num">{n.orders}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Negociar")}</h2>
          <span className="hint">{t("balcão do jogador")}</span>
        </div>

        <div className="card">
          {commodity.is_frozen && (
            <div className="warn">
              {t("🧊 Mercado suspenso pelo admin — sem ordem nova até reabrir.")}
            </div>
          )}
          <div className="seg">
            <button
              className={lado === "bid" ? "on-buy" : ""}
              onClick={() => setLado("bid")}
            >
              {t("Comprar")}
            </button>
            <button
              className={lado === "ask" ? "on-sell" : ""}
              onClick={() => setLado("ask")}
            >
              {t("Vender")}
            </button>
          </div>

          <div className="you-own">
            <span>
              {t("seu estoque:")}{" "}
              <b className="num">
                {num(estoque, 0, 3)} {t("un")}
              </b>
            </span>
            {position && position.quantity > 0 && (
              <span>
                {t("média")}{" "}
                <b className="num">{money(position.avg_price)}</b>
              </span>
            )}
            <span>
              {t("saldo")} <b className="num">{money(saldo)}</b>
            </span>
          </div>

          <div className="field">
            <label>
              <span>{t("Quantidade")}</span>
              <span className="num">
                {maximo > 0 ? t("máx {{n}}", { n: num(maximo, 0, 0) }) : ""}
              </span>
            </label>
            <div className="stepper">
              <button type="button" onClick={() => ajustar(-1)} aria-label={t("menos")}>
                −
              </button>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="1"
                value={qtd}
                onChange={(e) => setQtd(e.target.value)}
              />
              <button type="button" onClick={() => ajustar(1)} aria-label={t("mais")}>
                +
              </button>
            </div>
            <div className="chips">
              {[1, 5, 10].map((n) => (
                <button
                  key={n}
                  className={`chip ${quantidade === n ? "on" : ""}`}
                  onClick={() => setQtd(String(n))}
                >
                  {n}
                </button>
              ))}
              {maximo > 0 && (
                <button
                  className={`chip ${quantidade === maximo ? "on" : ""}`}
                  onClick={() => setQtd(String(maximo))}
                >
                  {t("tudo ({{n}})", { n: num(maximo, 0, 0) })}
                </button>
              )}
            </div>
          </div>

          <div className="field">
            <label>
              <span>{t("Preço por unidade")}</span>
              <span className="num">
                {auto ? t("seguindo o book") : t("manual")}
              </span>
            </label>
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={auto ? ideal : manual}
              onChange={(e) => {
                setManual(e.target.value);
                setAuto(false);
              }}
            />
            <div className="chips">
              <button
                className={`chip ${auto ? "on" : ""}`}
                onClick={() => setAuto(true)}
              >
                {t("melhor preço")}
              </button>
              {melhorAsk && (
                <button
                  className="chip"
                  onClick={() => {
                    setManual(String(melhorAsk));
                    setAuto(false);
                  }}
                >
                  {t("venda {{v}}", { v: money(melhorAsk) })}
                </button>
              )}
              {melhorBid && (
                <button
                  className="chip"
                  onClick={() => {
                    setManual(String(melhorBid));
                    setAuto(false);
                  }}
                >
                  {t("compra {{v}}", { v: money(melhorBid) })}
                </button>
              )}
            </div>
          </div>

          <div className="estimate">
            <span>
              {ehCompra ? t("Você vai pagar") : t("Você vai receber")}
            </span>
            <b className="num">{money(custo)}</b>
          </div>

          {semSaldo && (
            <div className="warn">
              {t("Saldo insuficiente — livre {{livre}}, faltam {{falta}}.", {
                livre: money(saldoLivre),
                falta: money(custo - saldoLivre),
              })}
              {saldoComprometido > 1e-9 && (
                <>
                  {" "}
                  {t("({{v}} já em compras abertas)", {
                    v: money(saldoComprometido),
                  })}
                </>
              )}
            </div>
          )}
          {semEstoque && (
            <div className="warn">
              {t("Só tem {{qtd}} un livre de {{nome}}.", {
                qtd: num(estoqueLivre, 0, 3),
                nome: t(commodity.name),
              })}
              {estoqueComprometido > 1e-9 && (
                <>
                  {" "}
                  {t("({{qtd}} un em vendas abertas)", {
                    qtd: num(estoqueComprometido, 0, 3),
                  })}
                </>
              )}
            </div>
          )}
          {noLimite && (
            <div className="warn">
              {t("🔒 Você já tem {{n}} ordens abertas — cancele uma na carteira antes de enviar outra.", {
                n: MAX_ORDENS_ABERTAS,
              })}
            </div>
          )}

          <button
            className={`btn ${ehCompra ? "btn-buy" : "btn-sell"}`}
            disabled={
              enviando ||
              commodity.is_frozen ||
              noLimite ||
              quantidade <= 0 ||
              preco <= 0 ||
              semSaldo ||
              semEstoque
            }
            onClick={enviar}
          >
            {enviando
              ? t("Enviando…")
              : commodity.is_frozen
                ? t("Mercado suspenso")
                : noLimite
                  ? t("Limite de {{n}} ordens atingido", { n: MAX_ORDENS_ABERTAS })
                  : ehCompra
                    ? t("Comprar {{qtd}} de {{nome}}", {
                        qtd: num(quantidade, 0, 3),
                        nome: t(commodity.name),
                      })
                    : t("Vender {{qtd}} de {{nome}}", {
                        qtd: num(quantidade, 0, 3),
                        nome: t(commodity.name),
                      })}
          </button>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Suas ordens")}</h2>
          <span className="hint">{t("neste commodity")}</span>
        </div>

        <div className="card">
          {abertas.length === 0 && executadas.length === 0 ? (
            <div className="empty">
              <span className="big">🗒️</span>
              {t("Você ainda não negociou {{nome}}.", { nome: t(commodity.name) })}
              <br />
              {t("Coloque a primeira ordem acima.")}
            </div>
          ) : (
            <>
              {quases.map(({ o, falta, alvo, lado: ladoQuase }) => (
                <div className="quase" key={`q${o.id}`}>
                  <Trans
                    i18nKey="⏳ <b>Quase!</b> sua {{tipo}} a <num>{{preco}}</num> faltou <b>{{falta}}</b> para {{alvo}} (<num>{{meta}}</num>)."
                    values={{
                      tipo: o.side === "ask" ? t("venda") : t("compra"),
                      preco: money(o.price),
                      falta: money(falta),
                      alvo: ladoQuase,
                      meta: money(alvo),
                    }}
                    components={{
                      b: <b />,
                      num: <span className="num" />,
                    }}
                  />
                </div>
              ))}

              {abertas.map((o) => (
                <div className="list-row" key={o.id}>
                  <span className="grow">
                    <span className="title">
                      {o.side === "bid" ? t("🟢 Compra") : t("🔴 Venda")}{" "}
                      <span className="badge open">{t("no book")}</span>
                    </span>
                    <span className="sub num">
                      {t("restam {{qtd}} un a {{preco}}", {
                        qtd: num(o.quantity, 0, 3),
                        preco: money(o.price),
                      })}{" "}
                      · {timeAgo(o.created_at)}
                    </span>
                  </span>
                </div>
              ))}

              {executadas.map((o) => (
                <div className="list-row" key={`f${o.id}`}>
                  <span className="grow">
                    <span className="title">
                      {o.side === "bid" ? t("Compra") : t("Venda")}{" "}
                      <span className="badge done">{t("executada")}</span>
                    </span>
                    <span className="sub num">
                      {t("a {{preco}}", { preco: money(o.price) })} ·{" "}
                      {timeAgo(o.created_at)}
                    </span>
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      </section>
    </>
  );
}
