import { useEffect, useState } from "react";

import { brl, getJSON, iconFor, patchJSON, pct, postJSON } from "../api";

const CHOQUES = [-10, -5, 5, 10];

/**
 * Intervenções de mercado do admin (combo de emergência do mundo simulado):
 *
 * - choque: empurra todas as ordens abertas de uma commodity em ±% (o book
 *   inteiro anda, recortado na faixa nominal, e o preço exibido acompanha);
 * - preço base: troca a âncora nominal e recorta o book na nova faixa;
 * - limpar book: cancela tudo que está aberto e volta o preço ao nominal;
 * - congelar/reabrir: congelada não aceita ordem nova (nem de bot);
 * - zerada geral: as três anteriores de uma vez, no mercado inteiro;
 * - manchetes (cartas de evento): dispara uma notícia com choque na hora —
 *   o professor vira mestre de cena.
 */
export default function AdminMarket({ commodities, onToast, onRefresh }) {
  const [aberto, setAberto] = useState(null); // id da commodity expandida
  const [bases, setBases] = useState({}); // edições de preço base por id
  const [ocupado, setOcupado] = useState(null); // chave da ação em andamento
  const [conf, setConf] = useState(null); // ação destrutiva armada (2º toque)
  const [cartas, setCartas] = useState([]); // baralho de cartas de evento
  const [cartaSel, setCartaSel] = useState(""); // carta escolhida ("" = sorteio)

  // confirmação armada expira sozinha: toque perdido não destrói nada
  useEffect(() => {
    if (!conf) return;
    const t = setTimeout(() => setConf(null), 5000);
    return () => clearTimeout(t);
  }, [conf]);

  // Baralho de cartas de evento (público) — só pra popular o seletor
  useEffect(() => {
    let vivo = true;
    getJSON("/news")
      .then((n) => vivo && setCartas(n.cartas || []))
      .catch(() => {}); // sem /news o resto da tela funciona igual
    return () => {
      vivo = false;
    };
  }, []);

  async function agir(chave, fn) {
    if (ocupado) return;
    setOcupado(chave);
    try {
      const r = await fn();
      onToast?.(r?.detail || "Intervenção aplicada", "ok");
      await onRefresh?.();
    } catch (e) {
      onToast?.(e.message || "Falha na intervenção.", "err");
    } finally {
      setOcupado(null);
      setConf(null);
    }
  }

  const choque = (c, percent) =>
    agir(`choque-${c.id}-${percent}`, () =>
      postJSON(`/commodities/${c.id}/shock`, { percent }),
    );

  const congelar = (c) =>
    agir(`freeze-${c.id}`, () =>
      postJSON(`/commodities/${c.id}/freeze`, { frozen: !c.is_frozen }),
    );

  const limparBook = (c) => {
    const chave = `limpa-${c.id}`;
    if (conf !== chave) {
      setConf(chave);
      return;
    }
    agir(chave, () =>
      postJSON(`/commodities/${c.id}/clear-book`, { reset_price: true }),
    );
  };

  const zerarTudo = () => {
    if (conf !== "reset-geral") {
      setConf("reset-geral");
      return;
    }
    agir("reset-geral", () => postJSON("/commodities/reset"));
  };

  const dispararManchete = () =>
    agir("manchete", () =>
      postJSON("/news/disparar", cartaSel ? { id: cartaSel } : {}),
    );

  const salvarBase = (c) => {
    const bruto = bases[c.id] ?? c.base_price;
    const v = Number(bruto);
    if (!Number.isFinite(v) || v <= 0) {
      onToast?.("Preço base precisa ser maior que zero.", "err");
      return;
    }
    agir(`base-${c.id}`, async () => {
      const r = await patchJSON(`/commodities/${c.id}`, { base_price: v });
      setBases((b) => {
        const n = { ...b };
        delete n[c.id];
        return n;
      });
      return { detail: `${r.name}: nominal em ${brl(r.base_price)}` };
    });
  };

  const lista = commodities || [];

  return (
    <>
      <section className="section">
        <div className="section-title">
          <h2>Intervenções no mercado</h2>
          <span className="hint">admin</span>
        </div>

        <div className="card">
          {lista.length === 0 ? (
            <div className="empty">Carregando o mercado…</div>
          ) : (
            lista.map((c) => (
              <div className="adm-item" key={c.id}>
                <button
                  className="list-row list-row-btn"
                  onClick={() => setAberto(aberto === c.id ? null : c.id)}
                >
                  <span className="grow">
                    <span className="title">
                      {iconFor(c.name)} {c.name}
                      {c.is_frozen && <span className="badge off">suspenso</span>}
                    </span>
                    <span className="sub">
                      nominal {brl(c.base_price)} · toque pra intervir
                    </span>
                  </span>
                  <span className="right">
                    <span className="big num">{brl(c.current_price)}</span>
                    <span className="small">{pct(c.variation_24h)}</span>
                  </span>
                </button>

                {aberto === c.id && (
                  <div className="adm-panel">
                    <span className="hint">
                      Choque de preço (empurra o book inteiro)
                    </span>
                    <div className="chips">
                      {CHOQUES.map((p) => (
                        <button
                          key={p}
                          className="chip"
                          disabled={ocupado !== null}
                          onClick={() => choque(c, p)}
                        >
                          {p > 0 ? `▲ +${p}%` : `▼ ${p}%`}
                        </button>
                      ))}
                    </div>

                    <div className="field">
                      <label htmlFor={`base-${c.id}`}>
                        <span>Preço base (âncora nominal)</span>
                        <span>o book é recortado na nova faixa</span>
                      </label>
                      <input
                        id={`base-${c.id}`}
                        type="number"
                        inputMode="decimal"
                        step="0.01"
                        min="0.01"
                        value={bases[c.id] ?? c.base_price}
                        onChange={(e) =>
                          setBases({ ...bases, [c.id]: e.target.value })
                        }
                      />
                    </div>

                    <div className="chips">
                      <button
                        className="chip"
                        disabled={ocupado !== null}
                        onClick={() => salvarBase(c)}
                      >
                        salvar nominal
                      </button>
                      <button
                        className={
                          conf === `limpa-${c.id}` ? "chip danger on" : "chip"
                        }
                        disabled={ocupado !== null}
                        onClick={() => limparBook(c)}
                      >
                        {conf === `limpa-${c.id}`
                          ? "cancelar tudo?"
                          : "🧹 limpar book"}
                      </button>
                      <button
                        className={c.is_frozen ? "chip on" : "chip"}
                        disabled={ocupado !== null}
                        onClick={() => congelar(c)}
                      >
                        {c.is_frozen ? "▶ reabrir" : "🧊 congelar"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>📰 Manchetes (cartas de evento)</h2>
          <span className="hint">mestre de cena</span>
        </div>

        <div className="card form-card">
          <p className="hint" style={{ margin: 0 }}>
            Dispara uma notícia com choque de preço na hora — o banner
            “ÚLTIMA HORA” aparece pra todo mundo. Sem carta escolhida, o
            sorteio é o mesmo do automático (45–75 min).
          </p>
          <div className="field">
            <label htmlFor="carta-sel">
              <span>Carta</span>
              <span>baralho em cartas_evento.json</span>
            </label>
            <select
              id="carta-sel"
              value={cartaSel}
              onChange={(e) => setCartaSel(e.target.value)}
            >
              <option value="">🎲 sorteio aleatório</option>
              {cartas.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.emoji} {c.titulo} ({c.impacto > 0 ? "+" : ""}
                  {c.impacto}%)
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn btn-ghost"
            disabled={ocupado !== null}
            onClick={dispararManchete}
          >
            📰 Disparar manchete agora
          </button>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>Zona de perigo</h2>
          <span className="hint">admin</span>
        </div>

        <div className="card form-card">
          <p className="hint" style={{ margin: 0 }}>
            Cancela <b>todas</b> as ordens abertas e devolve os preços ao
            nominal. O histórico de negociações fica — o gráfico mostra a queda.
          </p>
          <button
            className={conf === "reset-geral" ? "btn btn-danger" : "btn btn-ghost"}
            disabled={ocupado !== null}
            onClick={zerarTudo}
          >
            {conf === "reset-geral"
              ? "⚠️ confirmar zerada geral"
              : "Zerar todo o mercado"}
          </button>
        </div>
      </section>
    </>
  );
}
