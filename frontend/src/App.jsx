import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  clearSession,
  delJSON,
  erroTraduzido,
  getJSON,
  getSession,
  money,
  pct,
  postJSON,
} from "./api";
import { mudaIdioma } from "./i18n/index.js";
import AdminMarket from "./components/AdminMarket";
import Commodity from "./components/Commodity";
import Login from "./components/Login";
import Market from "./components/Market";
import Portfolio from "./components/Portfolio";
import Producers from "./components/Producers";
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
  const { t, i18n } = useTranslation();
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
    produtoras: null,
  });
  const [book, setBook] = useState(null);
  const [aviso, setAviso] = useState("");
  const [toast, setToast] = useState(null);
  // --- feed ao vivo do WebSocket (market.tick / regime / fomo / 🐋 / 📰) ---
  const [fomo, setFomo] = useState(null); // {commodity_id, titulo, fim}
  const [manchete, setManchete] = useState(null); // carta de evento {…, fim}
  const [destaques, setDestaques] = useState([]); // fills de baleia recentes
  const [inflacao, setInflacao] = useState(1); // índice Σbase desde o boot
  const [agora, setAgora] = useState(() => Date.now()); // pulso do contador

  const visivel = useRef(true);
  const timerToast = useRef(null);
  const streakAnterior = useRef(undefined);
  const mancheteVista = useRef(null); // dedup: WS + polling não repetem a mesma

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
      setAviso(erroTraduzido(t, e, "Sem conexão com o backend."));
    }
    // Indústria: separado de propósito — se /produtoras falhar (backend
    // antigo, por exemplo), o mercado e a carteira não caem junto.
    try {
      const produtoras = await getJSON("/produtoras");
      setDados((d) => ({ ...d, produtoras }));
    } catch {
      // aba de indústria fica no "carregando" e o resto segue
    }
    // Rede de segurança da manchete: se o WS caiu, o polling pega a última
    // carta emitida (mesmo dedup por emitido_em do WS).
    try {
      const n = await getJSON("/news");
      const ultima = (n.ultimas || [])[0];
      if (
        ultima &&
        ultima.emitido_em > (mancheteVista.current || 0) &&
        ultima.emitido_em * 1000 + (ultima.segundos || 18) * 1000 > Date.now()
      ) {
        mancheteVista.current = ultima.emitido_em;
        setManchete({
          ...ultima,
          fim: Date.now() + (ultima.segundos || 18) * 1000,
        });
      }
    } catch {
      // /news é opcional: não derruba a carga principal por causa dele
    }
  }, [t]); // `t` nas deps: os avisos mudam de idioma junto

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

  /* --------------------------------------------- websocket ao vivo -- */

  useEffect(() => {
    if (!usuario) return;
    let vivo = true;
    let ws = null;
    let retry = null;

    const tratar = (data) => {
      if (!vivo || !data) return;
      if (data.type === "init") return;

      if (data.timestamp && data.prices) {
        // market.tick: preços ao vivo (3s) + índice de inflação + FOMO
        setDados((d) => ({
          ...d,
          commodities: d.commodities.map((c) => {
            const p = data.prices[c.id];
            return p
              ? { ...c, current_price: p.price, variation_24h: p.variation }
              : c;
          }),
        }));
        if (typeof data.inflacao_indice === "number") {
          setInflacao(data.inflacao_indice);
        }
        setFomo(
          data.fomo
            ? {
                commodity_id: data.fomo.commodity_id,
                titulo: data.fomo.titulo,
                fim: Date.now() + data.fomo.segundos_restantes * 1000,
              }
            : null,
        );
        return;
      }

      if (data.commodity_id !== undefined && data.regime) {
        // market.regime: o chip do card muda na hora, sem esperar o polling
        setDados((d) => ({
          ...d,
          commodities: d.commodities.map((c) =>
            c.id === data.commodity_id ? { ...c, regime: data.regime } : c,
          ),
        }));
        return;
      }

      if (data.tipo === "manchete") {
        // market.news: carta de evento (manchete) — a cena do dia
        if (data.emitido_em > (mancheteVista.current || 0)) {
          mancheteVista.current = data.emitido_em;
          setManchete({
            ...data,
            fim: Date.now() + (data.segundos || 18) * 1000,
          });
        }
        return;
      }

      if (data.titulo && data.tipo === "fomo") {
        // market.event (janela FOMO) — guard apertado: "manchete" também
        // tem titulo+tipo e chegaria aqui por engano
        setFomo({
          commodity_id: data.commodity_id,
          titulo: data.titulo,
          fim: Date.now() + data.segundos * 1000,
        });
        return;
      }

      if (data.rate_percent !== undefined) {
        // tax.applied: a hora de agir (dinheiro parado derretendo)
        mostrarToast(
          t("💸 Inflação de {{r}}% aplicada — dinheiro parado perde valor", {
            r: data.rate_percent,
          }),
          "err",
        );
        return;
      }

      if (data.bots_active !== undefined && data.destaques?.length) {
        // bot.activity: fills de baleia (🐋) — entram no topo do feed
        const novos = data.destaques.map((b) => ({
          ...b,
          recebidoEm: Date.now(),
          chave: `${Date.now()}-${Math.random()}`,
        }));
        setDestaques((lista) => [...novos.reverse(), ...lista].slice(0, 8));
      }
    };

    const conectar = () => {
      if (!vivo) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      try {
        ws = new WebSocket(`${proto}://${window.location.host}/ws/market`);
      } catch {
        retry = setTimeout(conectar, 4000);
        return;
      }
      ws.onmessage = (ev) => {
        try {
          tratar(JSON.parse(ev.data));
        } catch {
          // frame corrompido: ignora, o próximo tick corrige
        }
      };
      // Caiu? Reconecta em 3s — o polling continua como rede de segurança.
      ws.onclose = () => {
        if (vivo) retry = setTimeout(conectar, 3000);
      };
    };
    conectar();

    return () => {
      vivo = false;
      clearTimeout(retry);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [usuario, mostrarToast, t]);

  /* ------------------------------------------------- combo 🔥 do streak -- */

  useEffect(() => {
    const s = dados.me?.streak;
    if (s == null) return;
    const antes = streakAnterior.current;
    streakAnterior.current = s;
    if (antes === undefined || antes === s) return;
    if (s > antes) mostrarToast(t("🔥 Combo de vendas lucrativas: x{{n}}", { n: s }), "ok");
    else if (s === 0) mostrarToast(t("💔 Combo perdido!"), "err");
  }, [dados.me?.streak, mostrarToast, t]);

  /* --------------------------------------- contagem do banner FOMO -- */

  useEffect(() => {
    if (!fomo) return;
    const id = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(id);
  }, [fomo]);

  const enviarOrdem = useCallback(
    async (payload) => {
      try {
        const ordem = await postJSON("/orders", payload);
        mostrarToast(
          ordem.filled ? t("Executada! ⚡") : t("Ordem enviada ao book ✅"),
          "ok",
        );
        carregar();
        carregarHistorico();
        return true;
      } catch (e) {
        mostrarToast(erroTraduzido(t, e, "Não foi possível enviar a ordem."), "err");
        return false;
      }
    },
    [carregar, carregarHistorico, mostrarToast, t],
  );

  /** Cancela uma ordem aberta (o backend some do book e do banco junto). */
  const cancelarOrdem = useCallback(
    async (id) => {
      try {
        await delJSON(`/orders/${id}`);
        mostrarToast(t("Ordem cancelada ✖️"), "ok");
        await carregar();
        return true;
      } catch (e) {
        mostrarToast(erroTraduzido(t, e, "Não foi possível cancelar a ordem."), "err");
        return false;
      }
    },
    [carregar, mostrarToast, t],
  );

  /* -------------------------------------------- ações das produtoras -- */

  const comprarProdutora = useCallback(
    async (commodityId) => {
      try {
        const p = await postJSON("/produtoras/comprar", { commodity_id: commodityId });
        mostrarToast(`${p.emoji} ${t(p.nome)} ${t("comprada!")}`, "ok");
        carregar();
        return true;
      } catch (e) {
        mostrarToast(erroTraduzido(t, e, "Não foi possível comprar."), "err");
        return false;
      }
    },
    [carregar, mostrarToast, t],
  );

  /** Um clique: devolve o resultado pra UI animar (floater) sem esperar o poll. */
  const produzirProdutora = useCallback(
    async (producerId) => {
      try {
        const r = await postJSON(`/produtoras/${producerId}/produzir`);
        // Saldo e carteira mudam junto — aplica na hora (o poll de 4s
        // re-sincroniza o resto: posição com preço médio, etc).
        setDados((d) => ({
          ...d,
          me: d.me ? { ...d.me, balance: r.saldo } : d.me,
          produtoras: d.produtoras
            ? {
                ...d.produtoras,
                minhas: d.produtoras.minhas.map((p) =>
                  p.id === r.produzida.id ? r.produzida : p,
                ),
              }
            : d.produtoras,
        }));
        return r;
      } catch (e) {
        mostrarToast(erroTraduzido(t, e, "Não foi possível produzir."), "err");
        return null;
      }
    },
    [mostrarToast, t],
  );

  const melhorarProdutora = useCallback(
    async (producerId) => {
      try {
        const p = await postJSON(`/produtoras/${producerId}/melhorar`);
        mostrarToast(
          `${p.emoji} ${t(p.nome)} ${t("subiu pro nível {{n}}! 🚀", { n: p.nivel })}`,
          "ok",
        );
        carregar();
        return true;
      } catch (e) {
        mostrarToast(erroTraduzido(t, e, "Não foi possível melhorar."), "err");
        return false;
      }
    },
    [carregar, mostrarToast, t],
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

  // Janela FOMO viva (o `agora` de 1s faz a contagem descer)
  const fomoAtiva = fomo && fomo.fim > agora ? fomo : null;
  const nomeFomo = fomoAtiva
    ? t(
        dados.commodities.find((c) => c.id === fomoAtiva.commodity_id)?.name ||
          "#?",
      )
    : "";
  const segundosFomo = fomoAtiva
    ? Math.max(0, Math.ceil((fomoAtiva.fim - agora) / 1000))
    : 0;
  // Manchete viva (carta de evento) — o relógio de 1s expira o banner sozinho
  const mancheteAtiva = manchete && manchete.fim > agora ? manchete : null;
  // 🐋: só as fills dos últimos 20s (o polling re-renderiza e limpa as velhas)
  const destaquesFrescos = destaques.filter(
    (d) => Date.now() - d.recebidoEm < 20000,
  );

  const abas = [
    { id: "mercado", icone: "🏪", rotulo: t("Mercado") },
    { id: "industria", icone: "🏭", rotulo: t("Indústria") },
    { id: "carteira", icone: "💼", rotulo: t("Carteira") },
    ...(usuario.is_admin
      ? [{ id: "admin", icone: "🛠️", rotulo: "Admin" }]
      : []),
  ];

  const outroIdioma = i18n.language === "en" ? "pt" : "en";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">📈</div>
          <div className="brand-text">
            <b>{t("Bolsa de Commodities")}</b>
            <span>{t("mercado simulado")}</span>
          </div>
        </div>
        <div className="topbar-user">
          <span
            className="num"
            style={{ color: "var(--gold)", fontWeight: 700 }}
          >
            {money(dados.me?.balance ?? usuario.balance ?? 0)}
          </span>
          <span className="who">{usuario.username}</span>
          <button
            className="chip"
            onClick={() => mudaIdioma(outroIdioma)}
            aria-label={t("mudar idioma")}
            title={t("mudar idioma")}
          >
            {i18n.language === "en" ? "🇬🇧 EN" : "🇧🇷 PT"}
          </button>
          <button className="chip" onClick={sair} aria-label={t("sair da conta")}>
            {t("sair")}
          </button>
        </div>
      </header>

      {aviso && (
        <div className="section" style={{ paddingBottom: 0 }}>
          <div className="error-box">⚠️ {aviso}</div>
        </div>
      )}

      {mancheteAtiva && (
        <div className="section" style={{ paddingBottom: 0 }}>
          <button
            className="news-banner"
            onClick={() =>
              mancheteAtiva.commodity_id && abrirCommodity(mancheteAtiva.commodity_id)
            }
          >
            <span className="news-ico">{mancheteAtiva.emoji}</span>
            <span className="news-txt">
              <span className="news-tag">{t("📰 ÚLTIMA HORA")}</span>
              <b>{mancheteAtiva.titulo}</b>
              <span className="news-sub">
                {mancheteAtiva.alvos
                  .map(
                    (a) =>
                      `${t(a.name)} ${a.impacto >= 0 ? "▲" : "▼"} ${pct(a.impacto)}`,
                  )
                  .join(" · ")}
              </span>
            </span>
          </button>
        </div>
      )}

      {fomoAtiva && (
        <div className="section" style={{ paddingBottom: 0 }}>
          <button
            className="fomo-banner"
            onClick={() => abrirCommodity(fomoAtiva.commodity_id)}
          >
            <span className="fomo-ico">⚡</span>
            <span className="fomo-txt">
              <b>{fomoAtiva.titulo}</b>{" "}
              {t("em {{nome}} — pressão de compra forte!", { nome: nomeFomo })}
            </span>
            <span className="fomo-timer num">{segundosFomo}s</span>
          </button>
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
                {t("Carregando o mercado…")}
              </div>
            </section>
          )
        ) : aba === "mercado" ? (
          <Market
            commodities={dados.commodities}
            points={dados.points}
            ticker={dados.ticker}
            destaques={destaquesFrescos}
            manchete={mancheteAtiva || null}
            inflacao={inflacao}
            me={dados.me || usuario}
            positions={dados.positions}
            onOpen={abrirCommodity}
          />
        ) : aba === "industria" ? (
          <Producers
            estado={dados.produtoras}
            me={dados.me || usuario}
            onComprar={comprarProdutora}
            onProduzir={produzirProdutora}
            onMelhorar={melhorarProdutora}
          />
        ) : aba === "carteira" ? (
          <Portfolio
            me={dados.me || usuario}
            positions={dados.positions}
            commodities={dados.commodities}
            mine={dados.mine}
            inflacao={inflacao}
            onOpen={abrirCommodity}
            onCancel={cancelarOrdem}
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
          {abas.map((abaItem) => (
            <button
              key={abaItem.id}
              className={aba === abaItem.id ? "on" : ""}
              onClick={() => setAba(abaItem.id)}
            >
              <span className="ico">{abaItem.icone}</span>
              {abaItem.rotulo}
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
