import { useState } from "react";
import { useTranslation } from "react-i18next";

import { erroTraduzido, postJSON, saveSession } from "../api";
import { mudaIdioma } from "../i18n/index.js";

export default function Login({ onLogin }) {
  const { t, i18n } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function entrar(evento) {
    evento.preventDefault();
    if (!username.trim() || !password) {
      setErro(t("Preencha usuário e senha."));
      return;
    }
    setErro("");
    setCarregando(true);
    try {
      const data = await postJSON("/auth/login", {
        username: username.trim(),
        password,
      });
      saveSession(data.access_token, data.user);
      onLogin(data.user);
    } catch (e) {
      setErro(erroTraduzido(t, e, "Não foi possível conectar ao backend."));
    } finally {
      setCarregando(false);
    }
  }

  const outroIdioma = i18n.language === "en" ? "pt" : "en";

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={entrar}>
        <div className="login-logo">
          <div className="mark">📈</div>
          <h1>{t("Bolsa de Commodities")}</h1>
          <p>{t("mercado simulado")}</p>
        </div>

        {erro && <div className="error-box">{erro}</div>}

        <div className="field">
          <label htmlFor="usuario">{t("Usuário")}</label>
          <input
            id="usuario"
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            placeholder={t("como o admin te chamou")}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="senha">{t("Senha")}</label>
          <input
            id="senha"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button className="btn btn-gold" type="submit" disabled={carregando}>
          {carregando ? t("Entrando…") : t("Entrar no mercado")}
        </button>

        <p className="login-hint">
          {t("Os usuários são criados pelo admin.")}
          <br />
          {t("Cada jogador começa com saldo para negociar.")}
        </p>

        <button
          type="button"
          className="chip"
          style={{ margin: "12px auto 0" }}
          onClick={() => mudaIdioma(outroIdioma)}
          aria-label={t("mudar idioma")}
        >
          {i18n.language === "en" ? "🇬🇧 English" : "🇧🇷 Português"}
        </button>
      </form>
    </div>
  );
}
