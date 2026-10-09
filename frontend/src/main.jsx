import React from "react";
import { createRoot } from "react-dom/client";
import "./i18n/index.js"; // precisa antes do App: t() só existe depois do init
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Registra o service worker (PWA) apenas no navegador.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => {
      console.warn("Falha ao registrar o service worker:", err);
    });
  });
}
