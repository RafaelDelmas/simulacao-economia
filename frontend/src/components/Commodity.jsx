import { useEffect, useMemo, useState } from "react";

import { PriceChart } from "./Chart";
import { brl, iconFor, MAX_ORDENS_ABERTAS, num, pct, REGIME_LABEL, timeAgo } from "../api";

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
        ? [{ o, falta, alvo: melhorBid, lado: "melhor compra" }]
        : [];
    }
    if (melhorAsk == null || o.price >= melhorAsk) return [];
    const falta = melhorAsk - o.price;
    return falta / Math.max(melhorAsk, 0.01) <= QUASE_LIMITE
      ? [{ o, falta, alvo: melhorAsk, lado: "melhor venda" }]
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
          ‹ voltar ao mercado
        </button>

        <div className="detail-head">
          <span className="icon">{iconFor(commodity.name)}</span>
          <div style={{ minWidth: 0 }}>
            <h1>{commodity.name}</h1>
            {commodity.description && (
              <div className="desc">{commodity.description}</div>
            )}
          </div>
        </div>

        <div className="detail-price">
          <span className="now num">{brl(commodity.current_price)}</span>
          <span className={`pill ${varia >= 0 ? "up" : "down"}`}>
            {pct(varia)}
          </span>
          {commodity.regime && commodity.regime !== "calmo" && (
            <span className={`badge regime ${commodity.regime}`}>
              {REGIME_LABEL[commodity.regime] || commodity.regime}
            </span>
          )}
          {commodity.is_frozen && <span className="badge off">suspenso</span>}
        </div>

        <div className="card">
          <PriceChart points={points || []} cor="#f2c14e" />
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>Livro de ofertas</h2>
          <span className="hint">
            <span className="live-dot" />
            ao vivo
          </span>
        </div>

        <div className="card">
          <div className="book">
            <div className="book-head">
              <span>preço</span>
              <span>quantidade</span>
              <span style={{ textAlign: "right" }}>ordens</span>
            </div>

            {asks.length === 0 && bids.length === 0 ? (
              <div className="book-empty">Book vazio neste instante…</div>
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
                    <span className="price num">{brl(n.price)}</span>
                    <span className="qty num">{num(n.quantity, 0, 3)}</span>
                    <span className="orders num">{n.orders}</span>
                  </div>
                ))}

                <div className="book-spread">
                  <span>
                    melhor venda <b className="num">{melhorAsk ? brl(melhorAsk) : "—"}</b>
                  </span>
                  <span>
                    spread{" "}
                    <b className="num">
                      {book?.spread != null && book.spread >= 0
                        ? brl(book.spread)
                        : "—"}
                    </b>
                  </span>
                  <span>
                    melhor compra{" "}
                    <b className="num">{melhorBid ? brl(melhorBid) : "—"}</b>
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
                    <span className="price num">{brl(n.price)}</span>
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
          <h2>Negociar</h2>
          <span className="hint">balcão do jogador</span>
        </div>

        <div className="card">
          {commodity.is_frozen && (
            <div className="warn">
              🧊 Mercado suspenso pelo admin — sem ordem nova até reabrir.
            </div>
          )}
          <div className="seg">
            <button
              className={lado === "bid" ? "on-buy" : ""}
              onClick={() => setLado("bid")}
            >
              Comprar
            </button>
            <button
              className={lado === "ask" ? "on-sell" : ""}
              onClick={() => setLado("ask")}
            >
              Vender
            </button>
          </div>

          <div className="you-own">
            <span>
              seu estoque: <b className="num">{num(estoque, 0, 3)} un</b>
            </span>
            {position && position.quantity > 0 && (
              <span>
                média <b className="num">{brl(position.avg_price)}</b>
              </span>
            )}
            <span>
              saldo <b className="num">{brl(saldo)}</b>
            </span>
          </div>

          <div className="field">
            <label>
              <span>Quantidade</span>
              <span className="num">
                {maximo > 0 ? `máx ${num(maximo, 0, 0)}` : ""}
              </span>
            </label>
            <div className="stepper">
              <button type="button" onClick={() => ajustar(-1)} aria-label="menos">
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
              <button type="button" onClick={() => ajustar(1)} aria-label="mais">
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
                  tudo ({num(maximo, 0, 0)})
                </button>
              )}
            </div>
          </div>

          <div className="field">
            <label>
              <span>Preço por unidade</span>
              <span className="num">
                {auto ? "seguindo o book" : "manual"}
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
                melhor preço
              </button>
              {melhorAsk && (
                <button
                  className="chip"
                  onClick={() => {
                    setManual(String(melhorAsk));
                    setAuto(false);
                  }}
                >
                  venda {brl(melhorAsk)}
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
                  compra {brl(melhorBid)}
                </button>
              )}
            </div>
          </div>

          <div className="estimate">
            <span>{ehCompra ? "Você vai pagar" : "Você vai receber"}</span>
            <b className="num">{brl(custo)}</b>
          </div>

          {semSaldo && (
            <div className="warn">
              Saldo insuficiente — livre {brl(saldoLivre)}, faltam{" "}
              {brl(custo - saldoLivre)}.
              {saldoComprometido > 1e-9 && (
                <> ({brl(saldoComprometido)} já em compras abertas)</>
              )}
            </div>
          )}
          {semEstoque && (
            <div className="warn">
              Só tem {num(estoqueLivre, 0, 3)} un livre de {commodity.name}.
              {estoqueComprometido > 1e-9 && (
                <> ({num(estoqueComprometido, 0, 3)} un em vendas abertas)</>
              )}
            </div>
          )}
          {noLimite && (
            <div className="warn">
              🔒 Você já tem {MAX_ORDENS_ABERTAS} ordens abertas — cancele uma
              na carteira antes de enviar outra.
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
              ? "Enviando…"
              : commodity.is_frozen
                ? "Mercado suspenso"
                : noLimite
                  ? `Limite de ${MAX_ORDENS_ABERTAS} ordens atingido`
                  : ehCompra
                    ? `Comprar ${num(quantidade, 0, 3)} de ${commodity.name}`
                    : `Vender ${num(quantidade, 0, 3)} de ${commodity.name}`}
          </button>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>Suas ordens</h2>
          <span className="hint">neste commodity</span>
        </div>

        <div className="card">
          {abertas.length === 0 && executadas.length === 0 ? (
            <div className="empty">
              <span className="big">🗒️</span>
              Você ainda não negociou {commodity.name}.
              <br />
              Coloque a primeira ordem acima.
            </div>
          ) : (
            <>
              {quases.map(({ o, falta, alvo, lado }) => (
                <div className="quase" key={`q${o.id}`}>
                  ⏳ <b>Quase!</b> sua {o.side === "ask" ? "venda" : "compra"} a{" "}
                  <span className="num">{brl(o.price)}</span> faltou{" "}
                  <b className="num">{brl(falta)}</b> para {lado} (
                  <span className="num">{brl(alvo)}</span>).
                </div>
              ))}

              {abertas.map((o) => (
                <div className="list-row" key={o.id}>
                  <span className="grow">
                    <span className="title">
                      {o.side === "bid" ? "🟢 Compra" : "🔴 Venda"}{" "}
                      <span className="badge open">no book</span>
                    </span>
                    <span className="sub num">
                      restam {num(o.quantity, 0, 3)} un a {brl(o.price)} ·{" "}
                      {timeAgo(o.created_at)}
                    </span>
                  </span>
                </div>
              ))}

              {executadas.map((o) => (
                <div className="list-row" key={`f${o.id}`}>
                  <span className="grow">
                    <span className="title">
                      {o.side === "bid" ? "Compra" : "Venda"}{" "}
                      <span className="badge done">executada</span>
                    </span>
                    <span className="sub num">
                      a {brl(o.price)} · {timeAgo(o.created_at)}
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
