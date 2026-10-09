import { useEffect, useMemo, useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { money, num } from "../api";

/**
 * Indústria: as produtoras (clicker de estoque).
 *
 * Um card por produtora que você já tem (botão gigante com anel de
 * cooldown, barra de energia, progresso do cap do dia e manutenção) e um
 * card de compra por commodity que você ainda não tem.
 *
 * O servidor manda tudo em epoch (próxima energia, fim do cooldown, fim do
 * dia) — aqui só interpolamos contra o relógio local, sem acumular estado
 * de tempo (o polling de 4s re-sincroniza sozinho).
 */
export default function Producers({ estado, me, onComprar, onProduzir, onMelhorar }) {
  const { t } = useTranslation();
  const [agora, setAgora] = useState(() => Date.now() / 1000);
  const [floater, setFloater] = useState(null); // "+3 ☃️" do último clique
  const [enviando, setEnviando] = useState(null); // id em voo (anti double-tap)

  // Relógio fino (150ms): anel do cooldown e barra de energia andam sozinhos
  // entre um poll e outro.
  useEffect(() => {
    const id = setInterval(() => setAgora(Date.now() / 1000), 150);
    return () => clearInterval(id);
  }, []);

  // O floater some sozinho.
  useEffect(() => {
    if (!floater) return;
    const timer = setTimeout(() => setFloater(null), 1100);
    return () => clearTimeout(timer);
  }, [floater]);

  const minhas = estado?.minhas || [];
  const catalogo = estado?.catalogo || [];
  const config = estado?.config || {};

  const porCommodity = useMemo(
    () => Object.fromEntries(minhas.map((p) => [p.commodity_id, p])),
    [minhas],
  );

  if (!estado) {
    return (
      <section className="section">
        <div className="empty">
          <span className="big">🏭</span>
          {t("Carregando as indústrias…")}
        </div>
      </section>
    );
  }

  /** Energia corrente: derivada de `proxima_energia_em` (epoch do cheio). */
  function energiaAgora(p) {
    if (p.proxima_energia_em == null) return p.energia_max;
    const faltam = p.proxima_energia_em - agora;
    const e = p.energia_max - faltam * (p.energia_regen_por_segundo || 1);
    return Math.min(p.energia_max, Math.max(p.energia, e));
  }

  /** Cooldown: 0 = liberado; senão 0..cooldown_segundos. */
  function cooldownRestante(p) {
    if (!p.proximo_clique_em) return 0;
    return Math.max(0, p.proximo_clique_em - agora);
  }

  /** Progresso do anel do botão (0 = só começou, 100 = liberado). */
  function anelPct(p) {
    const cd = p.cooldown_segundos || 0;
    if (cd <= 0) return 100;
    const restante = cooldownRestante(p);
    return Math.min(100, Math.max(0, ((cd - restante) / cd) * 100));
  }

  async function produzir(p) {
    if (enviando) return;
    setEnviando(p.id);
    try {
      const r = await onProduzir(p.id);
      if (r) {
        setFloater({
          chave: Date.now(),
          un: r.unidades,
          emoji: r.produzida.emoji,
          jp: r.jackpot,
          custo: r.custo_insumo,
        });
      }
    } finally {
      setEnviando(null);
    }
  }

  /** Compra e melhoria também travam o botão durante o voo. */
  async function emVoo(chave, fn) {
    if (enviando) return;
    setEnviando(chave);
    try {
      await fn();
    } finally {
      setEnviando(null);
    }
  }

  const fmtMMSS = (seg) => {
    const s = Math.max(0, Math.ceil(seg));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  };

  /** Card de quem já tem a produtora. */
  function cardProdutora(p) {
    const com = catalogo.find((c) => c.commodity_id === p.commodity_id) || {};
    const energia = energiaAgora(p);
    const cd = cooldownRestante(p);
    const pctEnergia = (energia / (p.energia_max || 1)) * 100;
    const pctCap = Math.min(100, (p.producao_dia / (p.cap_diario || 1)) * 100);
    const capAlcancado = p.producao_dia >= (p.cap_diario || 0) - 1e-9;
    const semEnergia = energia < (config.energia_por_clique || 20) - 1e-9;
    const congelada = !!com.congelada;
    const parada = !p.ativa;
    const bloqueado = cd > 0 || capAlcancado || semEnergia || congelada || parada;
    const podeMelhorar = p.custo_melhoria != null && !parada;

    let motivo = t("lote {{a}}–{{b}} un · insumo ≈ {{c}}/un", {
      a: p.lote_min,
      b: p.lote_max,
      c: money(p.custo_insumo_unidade),
    });
    if (parada) motivo = t("💸 inadimplente — dívida {{v}}", { v: money(p.divida) });
    else if (congelada) motivo = t("🧊 commodity congelada pelo admin");
    else if (capAlcancado)
      motivo = t("📦 cap do dia ({{v}} un) — dia vira em {{t}}", {
        v: num(p.cap_diario, 0),
        t: fmtMMSS(p.dia_vence_em - agora),
      });
    else if (semEnergia)
      motivo = t("⚡ sem energia — recarrega em {{t}}", {
        t: fmtMMSS((p.proxima_energia_em || agora) - agora),
      });
    else if (cd > 0) motivo = t("⏳ descansando {{v}}s", { v: cd.toFixed(1) });

    return (
      <div className="prod-card" key={p.id}>
        <div className="prod-head">
          <span className="prod-ico">{p.emoji}</span>
          <span className="grow">
            <span className="prod-nome">
              {t(p.nome)} <span className="badge open">{t("nv {{n}}", { n: p.nivel })}</span>
            </span>
            <span className="prod-sub num">
              {t("{{nome}} · manutenção {{man}}/dia · dia vira em {{t}}", {
                nome: t(p.name),
                man: money(p.manutencao_dia),
                t: fmtMMSS(p.dia_vence_em - agora),
              })}
            </span>
          </span>
        </div>

        {parada && (
          <div className="warn">
            <Trans
              i18nKey="💸 Parada por falta de saldo: dívida de <b>{{divida}}</b> (não compõe). Assim que o saldo cobrir, a próxima varredura quita e reativa sozinha."
              values={{ divida: money(p.divida) }}
              components={{ b: <b /> }}
            />
          </div>
        )}

        <div className="prod-bars">
          <div className="prod-bar-line">
            <span>⚡ {num(energia, 0, 0)}/{num(p.energia_max, 0, 0)}</span>
            <div className="prod-bar">
              <i
                className={pctEnergia < 30 ? "low" : ""}
                style={{ width: `${pctEnergia}%` }}
              />
            </div>
          </div>
          <div className="prod-bar-line">
            <span>
              📦 {num(p.producao_dia, 0, 1)}/{num(p.cap_diario, 0, 0)}{" "}
              {t("hoje")}
            </span>
            <div className="prod-bar">
              <i className="cap" style={{ width: `${pctCap}%` }} />
            </div>
          </div>
        </div>

        <div className="prod-click-wrap">
          {/* anel de cooldown: conic-gradient em volta do botão */}
          <div
            className="prod-ring"
            style={{
              background: `conic-gradient(var(--gold) ${anelPct(p)}%, var(--line) 0)`,
            }}
          >
            <button
              className="prod-btn"
              disabled={!!bloqueado || enviando === p.id}
              onClick={() => produzir(p)}
            >
              <span className="ico">{p.emoji}</span>
              <span>{t("PRODUZIR")}</span>
            </button>
          </div>

          {floater && (
            <div className="prod-floater" key={floater.chave}>
              <b className={floater.jp ? "jp" : ""}>
                +{num(floater.un, 0, 0)} {floater.emoji}
              </b>
              <span>{t("−{{v}} de insumo", { v: money(floater.custo) })}</span>
            </div>
          )}
        </div>

        <div className="prod-motivo num">{motivo}</div>

        <div className="prod-actions">
          <span className="hint">
            {p.nivel >= p.nivel_max
              ? t("nível máximo")
              : t("próx. nível: lote até {{lote}} un · cap {{cap}}", {
                  lote: num(p.lote_max * (config.lote_nivel_fator || 1.5), 0, 1),
                  cap: num(p.cap_diario * (config.cap_nivel_fator || 1.5), 0, 0),
                })}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            disabled={!podeMelhorar || enviando === p.id}
            onClick={() => emVoo(p.id, () => onMelhorar(p.id))}
          >
            {p.custo_melhoria == null
              ? t("máx ✨")
              : t("⬆ melhorar {{v}}", { v: money(p.custo_melhoria) })}
          </button>
        </div>
      </div>
    );
  }

  /** Card de compra (commodity sem produtora ainda). */
  function cardCompra(c) {
    const pode = !c.congelada && Number(me?.balance || 0) >= c.custo_compra;
    return (
      <div className="prod-card buy" key={c.commodity_id}>
        <div className="prod-head">
          <span className="prod-ico">{c.emoji}</span>
          <span className="grow">
            <span className="prod-nome">{t(c.nome)}</span>
            <span className="prod-sub num">
              {t("{{nome}} · nominal {{nom}} · custo diário ~{{dia}}/dia", {
                nome: t(c.name),
                nom: money(c.base_price),
                dia: money(
                  c.custo_compra * (config.manutencao_fracao || 0.05),
                ),
              })}
            </span>
          </span>
        </div>
        <button
          className="btn btn-gold"
          disabled={!pode || enviando === c.commodity_id}
          onClick={() => emVoo(c.commodity_id, () => onComprar(c.commodity_id))}
        >
          {c.congelada
            ? t("congelada 🧊")
            : pode
              ? t("comprar por {{v}}", { v: money(c.custo_compra) })
              : t("faltam {{v}}", {
                  v: money(c.custo_compra - Number(me?.balance || 0)),
                })}
        </button>
      </div>
    );
  }

  const compraveis = catalogo.filter((c) => !porCommodity[c.commodity_id]);

  return (
    <>
      <section className="section">
        <div className="section-title">
          <h2>{t("🏭 Minhas produtoras")}</h2>
          <span className="hint">
            {t("clique = lote · cobra insumo · cap por dia")}
          </span>
        </div>
        <div className="prod-grid">
          {minhas.length ? (
            minhas.map(cardProdutora)
          ) : (
            <div className="card">
              <div className="empty">
                <span className="big">🧰</span>
                {t("Você ainda não tem nenhuma produtora.")}
                <br />
                {t("Compre uma abaixo e clique pra produzir estoque.")}
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Compra")}</h2>
          <span className="hint">{t("uma por commodity · progressão 1..5")}</span>
        </div>
        <div className="prod-grid">
          {compraveis.length ? (
            compraveis.map(cardCompra)
          ) : (
            <div className="card">
              <div className="empty">
                <span className="big">✅</span>
                {t("Você já tem produtora de todas as commodities.")}
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Como funciona")}</h2>
          <span className="hint">{t("4 travas de propósito")}</span>
        </div>
        <div className="card">
          <div className="prod-regras num">
            <div>
              <Trans
                i18nKey="1️⃣ <b>Insumo:</b> cada clique custa ~{{custo}}% do preço nominal por unidade — margem bruta ~{{margem}}%. Se o mercado saturar e o preço cair, produzir vira prejuízo."
                values={{
                  custo: num((config.insumo_fracao || 0.8) * 100, 0, 0),
                  margem: num(100 - (config.insumo_fracao || 0.8) * 100, 0, 0),
                }}
                components={{ b: <b /> }}
              />
            </div>
            <div>
              <Trans
                i18nKey="2️⃣ <b>Energia:</b> rajada de {{n}} cliques, depois o ritmo é a regeneração."
                values={{
                  n: num(
                    (config.energia_max || 100) /
                      (config.energia_por_clique || 20),
                    0,
                    0,
                  ),
                }}
                components={{ b: <b /> }}
              />
            </div>
            <div>
              <Trans
                i18nKey="3️⃣ <b>Cap diário:</b> o teto chega antes da paciência — o dia de jogo vira e zera."
                components={{ b: <b /> }}
              />
            </div>
            <div>
              <Trans
                i18nKey="4️⃣ <b>Manutenção:</b> ocioso também paga; sem saldo a produtora PARA até a dívida ser quitada."
                components={{ b: <b /> }}
              />
            </div>
            <div>
              <Trans
                i18nKey="🍀 <b>Boa safra:</b> {{chance}}% de chance o lote sair ×{{fator}}."
                values={{
                  chance: num((config.jackpot_chance || 0.05) * 100, 0, 0),
                  fator: num(config.jackpot_fator || 3, 0, 0),
                }}
                components={{ b: <b /> }}
              />
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
