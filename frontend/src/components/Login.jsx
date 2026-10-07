import { useState } from "react";

import { postJSON, saveSession } from "../api";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);

  async function entrar(evento) {
    evento.preventDefault();
    if (!username.trim() || !password) {
      setErro("Preencha usuário e senha.");
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
      setErro(e.message || "Não foi possível conectar ao backend.");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={entrar}>
        <div className="login-logo">
          <div className="mark">📈</div>
          <h1>Bolsa de Commodities</h1>
          <p>mercado simulado</p>
        </div>

        {erro && <div className="error-box">{erro}</div>}

        <div className="field">
          <label htmlFor="usuario">Usuário</label>
          <input
            id="usuario"
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            placeholder="como o admin te chamou"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="senha">Senha</label>
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
          {carregando ? "Entrando…" : "Entrar no mercado"}
        </button>

        <p className="login-hint">
          Os usuários são criados pelo admin.
          <br />
          Cada jogador começa com saldo para negociar.
        </p>
      </form>
    </div>
  );
}
