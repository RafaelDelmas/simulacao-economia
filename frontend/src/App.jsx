import { useCallback, useEffect, useRef, useState } from "react";

import { brl, clearSession, getJSON, getSession, postJSON } from "./api";
import AdminMarket from "./components/AdminMarket";
import Commodity from "./components/Commodity";
import Login from "./components/Login";
import Market from "./components/Market";
import Portfolio from "./components/Portfolio";
import Users from "./components/Users";

const ABA_PADRAO = "mercado";

/** A API devolve os ticks em lista plana; aqui vira { commodity_id: [{t,p}] }. */
function agruparPontos(flat) {
  const mapa = {};
  for (const p of flat || []) {
    if (!mapa[p.commodity_id]) mapa[p.commodity_id] = [];
    mapa[p.commodity_id].push({
      t: new Date(p.created_at),
      p: Number(p.price),
    });
  }
  return mapa;
}

export default function App() {
  const [usuario, setUsuario] = useState(() => getSession());
  const [aba, setAba] = useState(ABA_PADRAO);
  const [detalhe, setDetalhe] = useState(null);
  const [dados, setDados] = useState({
    me: null,
    commodities: [],
    positions: [],
    points: {},
    ticker: [],
    mine: { open: [], filled: [] },
  });
  const [book, setBook] = useState(null);
  const [aviso, setAviso] = useState("");
  const [toast, setToast] = useState(null);

  const visivel = useRef(true);
  const timerToast = useRef(null);

  const semSessao = () => !getSession();

  /* ---------------------------------------------------------- carga -- */

  /** Carga rápida: carteira, mercado, movimentações e minhas ordens. */
  const carregar = useCallback(async () => {
    if (!visivel.current) return;
    try {
      const [me, commodities, positions, ticker, mine] = await Promise.all([
        getJSON("/auth/me"),
        getJSON("/commodities"),
        getJSON("/positions"),
        getJSON("/orders/filled?limit=30"),
        getJSON("/orders/mine"),
      ]);
      setDados((d) => ({ ...d, me, commodities, positions, ticker, mine }));
      setAviso("");
    } catch (e) {
      if (semSessao()) return;
      setAviso(e.message || "Sem conexão com o backend.");
    }
  }, []);

  /** Carga lenta: série histórica dos gráficos. */
  const carregarHistorico = useCallback(async () => {
    if (!visivel.current) return;
    try {
      const flat = await getJSON("/commodities/history?limit=180");
      setDados((d) => ({ ...d, points: agruparPontos(flat) }));
    } catch {
      // gráfico é opcional: não derruba a tela por causa dele
    }
  }, []);

  useEffect(() => {
    const aoMudar = () => {
      visivel.current = !document.hidden;
    };
    document.addEventListener("visibilitychange", aoMudar);
    return () => document.removeEventListener("visibilitychange", aoMudar);
  }, []);

  useEffect(() => {
    if (!usuario) return;
    carregar();
    carregarHistorico();
    const rapido = setInterval(carregar, 4000);
    const lento = setInterval(carregarHistorico, 12000);
    return () => {
      clearInterval(rapido);
      clearInterval(lento);
    };
  }, [usuario, carregar, carregarHistorico]);

  useEffect(() => {
    const aoExpirar = () => {
      setUsuario(null);
      setAba(ABA_PADRAO);
      setDetalhe(null);
    };
    window.addEventListener("session-expired", aoExpirar);
    return () => window.removeEventListener("session-expired", aoExpirar);
  }, []);

  /* ------------------------------------------------- livro de ofertas -- */

  useEffect(() => {
    if (!detalhe) {
      setBook(null);
      return;
    }
    let vivo = true;
    const ler = async () => {
      try {
        const b = await getJSON(`/orders/book?commodity_id=${detalhe}&depth=10`);
        if (vivo) setBook(b);
      } catch {
        // mantém o último book válido na tela
      }
    };
    ler();
    const id = setInterval(ler, 2500);
    return () => {
      vivo = false;
      clearInterval(id);
    };
  }, [detalhe]);

  /* ---------------------------------------------------------- ações -- */

  const mostrarToast = useCallback((msg, tipo = "ok") => {
    setToast({ msg, tipo });
    clearTimeout(timerToast.current);
    timerToast.current = setTimeout(() => setToast(null), 3200);
  }, []);

  const enviarOrdem = useCallback(
    async (payload) => {
      try {
        const ordem = await postJSON("/orders", payload);
        mostrarToast(
          ordem.filled ? "Executada! ⚡" : "Ordem enviada ao book ✅",
          "ok",
        );
        carregar();
        carregarHistorico();
        return true;
      } catch (e) {
        mostrarToast(e.message || "Não foi possível enviar a ordem.", "err");
        return false;
      }
    },
    [carregar, carregarHistorico, mostrarToast],
  );

  function sair() {
    clearTimeout(timerToast.current);
    clearSession();
    setUsuario(null);
    setDetalhe(null);
    setAba(ABA_PADRAO);
    setToast(null);
  }

  function abrirCommodity(id) {
    setDetalhe(id);
    window.scrollTo(0, 0);
  }

  /* ----------------------------------------------------------- tela -- */

  if (!usuario) {
    return (
      <Login
        onLogin={(u) => {
          setUsuario(u);
          setAba(ABA_PADRAO);
        }}
      />
    );
  }

  const commodity = detalhe
    ? dados.commodities.find((c) => c.id === detalhe)
    : null;
  const posicao = dados.positions.find((p) => p.commodity_id === detalhe);
  const pontos = dados.points[detalhe] || [];

  const abas = [
    { id: "mercado", icone: "🏪", rotulo: "Mercado" },
    { id: "carteira", icone: "💼", rotulo: "Carteira" },
    ...(usuario.is_admin
      ? [{ id: "admin", icone: "🛠️", rotulo: "Admin" }]
      : []),
  ];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">📈</div>
          <div className="brand-text">
            <b>Bolsa de Commodities</b>
            <span>mercado simulado</span>
          </div>
        </div>
        <div className="topbar-user">
          <span
            className="num"
            style={{ color: "var(--gold)", fontWeight: 700 }}
          >
            {brl(dados.me?.balance ?? usuario.balance ?? 0)}
          </span>
          <span className="who">{usuario.username}</span>
          <button className="chip" onClick={sair} aria-label="sair da conta">
            sair
          </button>
        </div>
      </header>

      {aviso && (
        <div className="section" style={{ paddingBottom: 0 }}>
          <div className="error-box">⚠️ {aviso}</div>
        </div>
      )}

      <main>
        {detalhe ? (
          commodity ? (
            <Commodity
              commodity={commodity}
              points={pontos}
              book={book}
              mine={dados.mine}
              position={posicao}
              me={dados.me || usuario}
              onBack={() => setDetalhe(null)}
              onOrder={enviarOrdem}
            />
          ) : (
            <section className="section">
              <div className="empty">
                <span className="big">⏳</span>
                Carregando o mercado…
              </div>
            </section>
          )
        ) : aba === "mercado" ? (
          <Market
            commodities={dados.commodities}
            points={dados.points}
            ticker={dados.ticker}
            me={dados.me || usuario}
            positions={dados.positions}
            onOpen={abrirCommodity}
          />
        ) : aba === "carteira" ? (
          <Portfolio
            me={dados.me || usuario}
            positions={dados.positions}
            commodities={dados.commodities}
            mine={dados.mine}
            onOpen={abrirCommodity}
          />
        ) : (
          <>
            <AdminMarket
              commodities={dados.commodities}
              onToast={mostrarToast}
              onRefresh={carregar}
            />
            <Users onToast={mostrarToast} />
          </>
        )}
      </main>

      {!detalhe && (
        <nav className="tabbar">
          {abas.map((t) => (
            <button
              key={t.id}
              className={aba === t.id ? "on" : ""}
              onClick={() => setAba(t.id)}
            >
              <span className="ico">{t.icone}</span>
              {t.rotulo}
            </button>
          ))}
        </nav>
      )}

      {toast && (
        <div className={`toast ${toast.tipo}`} role="status">
          {toast.tipo === "err" ? "⛔" : "✅"} {toast.msg}
        </div>
      )}
    </div>
  );
}
