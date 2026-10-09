import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  money,
  delJSON,
  erroTraduzido,
  getJSON,
  getSession,
  patchJSON,
  postJSON,
  timeAgo,
  traduzDetalhe,
} from "../api";

/**
 * Painel do admin: criação de jogadores (com saldo de partida), a lista de
 * quem está no mundo simulado com as ações de saldo/apagar, e a entrada da
 * intervenção de mercado (componente irmão AdminMarket).
 */
export default function Users({ onToast }) {
  const { t } = useTranslation();
  const [usuarios, setUsuarios] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [form, setForm] = useState({
    username: "",
    password: "",
    is_admin: false,
    balance: "",
  });
  const [criando, setCriando] = useState(false);

  // ações por linha: editor de saldo aberto e confirmação de exclusão
  const [editando, setEditando] = useState(null);
  const [valorSaldo, setValorSaldo] = useState("");
  const [confirmando, setConfirmando] = useState(null);
  const [ocupado, setOcupado] = useState(null);

  const meuId = getSession()?.id;

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setUsuarios(await getJSON("/users"));
    } catch (e) {
      setErro(erroTraduzido(t, e, "Falha ao listar usuários."));
    } finally {
      setCarregando(false);
    }
  }, [t]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // a confirmação de exclusão expira sozinha: toque perdido não apaga nada
  useEffect(() => {
    if (!confirmando) return;
    const timer = setTimeout(() => setConfirmando(null), 5000);
    return () => clearTimeout(timer);
  }, [confirmando]);

  async function criar(evento) {
    evento.preventDefault();
    const username = form.username.trim();
    if (username.length < 3) {
      setErro(t("Usuário precisa de ao menos 3 caracteres."));
      return;
    }
    if (form.password.length < 4) {
      setErro(t("Senha precisa de ao menos 4 caracteres."));
      return;
    }

    setErro("");
    setCriando(true);
    try {
      const body = {
        username,
        password: form.password,
        is_admin: form.is_admin,
      };
      if (form.balance !== "" && Number(form.balance) >= 0) {
        body.balance = Number(form.balance);
      }
      const novo = await postJSON("/users", body);
      onToast?.(t("{{u}} entrou no mercado 🎉", { u: novo.username }), "ok");
      setForm({ username: "", password: "", is_admin: false, balance: "" });
      await carregar();
    } catch (e) {
      setErro(erroTraduzido(t, e, "Não foi possível criar o usuário."));
    } finally {
      setCriando(false);
    }
  }

  /** Ajusta o saldo: "somar"/"subtrair" mexe por delta, "definir" é absoluto. */
  async function ajustarSaldo(u, modo) {
    const bruto = String(valorSaldo).trim();
    const v = Number(bruto);
    if (bruto === "" || Number.isNaN(v)) {
      onToast?.(t("Digite um valor primeiro."), "err");
      return;
    }
    if (modo === "definir" && v < 0) {
      onToast?.(t("Saldo final não pode ser negativo."), "err");
      return;
    }
    if (modo !== "definir" && v <= 0) {
      onToast?.(t("O valor precisa ser maior que zero."), "err");
      return;
    }

    const chave = `saldo-${u.id}`;
    setOcupado(chave);
    try {
      const body =
        modo === "definir"
          ? { balance: v }
          : { delta: modo === "somar" ? v : -v };
      const atualizado = await patchJSON(`/users/${u.id}`, body);
      onToast?.(
        t("{{u}} agora tem {{v}} 💰", {
          u: u.username,
          v: money(atualizado.balance),
        }),
        "ok",
      );
      setEditando(null);
      await carregar();
    } catch (e) {
      onToast?.(
        erroTraduzido(t, e, "Não foi possível ajustar o saldo."),
        "err",
      );
    } finally {
      setOcupado(null);
    }
  }

  /** Exclusão em dois toques: o primeiro arma, o segundo executa. */
  function toqueApagar(u) {
    if (confirmando !== u.id) {
      setConfirmando(u.id);
      return;
    }
    apagar(u);
  }

  async function apagar(u) {
    const chave = `apaga-${u.id}`;
    setOcupado(chave);
    try {
      const r = await delJSON(`/users/${u.id}`);
      onToast?.(
        t("{{detalhe}} ({{n}} ordens canceladas)", {
          detalhe: traduzDetalhe(t, r),
          n: r.ordens_canceladas,
        }),
        "ok",
      );
      await carregar();
    } catch (e) {
      onToast?.(
        erroTraduzido(t, e, "Não foi possível apagar o usuário."),
        "err",
      );
    } finally {
      setOcupado(null);
      setConfirmando(null);
    }
  }

  function abrirSaldo(u) {
    if (editando === u.id) {
      setEditando(null);
      return;
    }
    setEditando(u.id);
    setValorSaldo("");
    setConfirmando(null);
  }

  return (
    <>
      <section className="section">
        <div className="section-title">
          <h2>{t("Criar jogador")}</h2>
          <span className="hint">admin</span>
        </div>

        <form className="card form-card" onSubmit={criar}>
          {erro && <div className="error-box">{erro}</div>}

          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="novo-usuario">{t("Usuário")}</label>
            <input
              id="novo-usuario"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder={t("ex.: maria")}
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </div>

          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="nova-senha">{t("Senha")}</label>
            <input
              id="nova-senha"
              type="password"
              autoComplete="new-password"
              placeholder={t("mínimo 4 caracteres")}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </div>

          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="saldo-inicial">
              <span>{t("Saldo inicial")}</span>
              <span>{t("vazio = padrão do servidor")}</span>
            </label>
            <input
              id="saldo-inicial"
              type="number"
              inputMode="decimal"
              min="0"
              step="1"
              placeholder={t("ex.: 1500")}
              value={form.balance}
              onChange={(e) => setForm({ ...form, balance: e.target.value })}
            />
          </div>

          <label className="check">
            <input
              type="checkbox"
              checked={form.is_admin}
              onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
            />
            {t("Também é admin")}
          </label>

          <button className="btn btn-gold" type="submit" disabled={criando}>
            {criando ? t("Criando…") : t("Criar jogador")}
          </button>
        </form>
      </section>

      <section className="section">
        <div className="section-title">
          <h2>{t("Quem está no jogo")}</h2>
          <span className="hint">
            {t("{{n}} usuários", { n: usuarios.length })}
          </span>
        </div>

        <div className="card">
          {erro && usuarios.length === 0 && <div className="error-box">{erro}</div>}

          {carregando ? (
            <div className="empty">{t("Carregando…")}</div>
          ) : usuarios.length === 0 ? (
            <div className="empty">
              <span className="big">🫥</span>
              {t("Nenhum usuário ainda.")}
            </div>
          ) : (
            usuarios.map((u) => (
              <div className="user-item" key={u.id}>
                <div className="list-row">
                  <span className="grow">
                    <span className="title">
                      {u.username}
                      {u.is_admin && <span className="badge admin">admin</span>}
                      {!u.is_active && (
                        <span className="badge off">{t("inativo")}</span>
                      )}
                    </span>
                    <span className="sub">
                      {t("entrou {{q}}", { q: timeAgo(u.created_at) })}
                    </span>
                  </span>
                  <span className="right">
                    <span className="big num">{money(u.balance)}</span>
                    <span className="small">{t("saldo")}</span>
                  </span>
                </div>

                <div className="row-actions">
                  <button
                    className={editando === u.id ? "chip on" : "chip"}
                    onClick={() => abrirSaldo(u)}
                    disabled={ocupado !== null}
                  >
                    💰 {t("saldo")}
                  </button>
                  {u.id !== meuId && (
                    <button
                      className={
                        confirmando === u.id ? "chip danger on" : "chip"
                      }
                      onClick={() => toqueApagar(u)}
                      disabled={ocupado !== null}
                    >
                      {confirmando === u.id
                        ? t("apagar mesmo?")
                        : t("🗑️ apagar")}
                    </button>
                  )}
                </div>

                {editando === u.id && (
                  <div className="inline-edit">
                    <input
                      type="number"
                      inputMode="decimal"
                      step="0.01"
                      placeholder={t("ex.: {{v}}", {
                        v: Math.round(u.balance),
                      })}
                      value={valorSaldo}
                      autoFocus
                      onChange={(e) => setValorSaldo(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") ajustarSaldo(u, "definir");
                      }}
                    />
                    <button
                      className="chip"
                      disabled={ocupado !== null}
                      onClick={() => ajustarSaldo(u, "somar")}
                    >
                      + {t("dar")}
                    </button>
                    <button
                      className="chip"
                      disabled={ocupado !== null}
                      onClick={() => ajustarSaldo(u, "subtrair")}
                    >
                      − {t("tirar")}
                    </button>
                    <button
                      className="chip on"
                      disabled={ocupado !== null}
                      onClick={() => ajustarSaldo(u, "definir")}
                    >
                      {t("definir")}
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </section>
    </>
  );
}
