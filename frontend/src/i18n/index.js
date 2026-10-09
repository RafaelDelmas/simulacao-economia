import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";

/**
 * Idiomas do jogo: `pt` (padrão) e `en`.
 *
 * Estratégia "texto PT é a chave": o código guarda SÓ o português
 * (`t("Patrimônio")`), não existe `pt.json` — quando a chave não existe no
 * idioma ativo, o i18next devolve a própria chave (o texto PT). Ou seja:
 * PT funciona sem nada traduzido, e o `en.json` é um mapa { PT -> EN }.
 *
 * Armadilhas que estas opções evitam:
 * - `keySeparator/nsSeparator: false` — textos PT têm "." e ":" (ex.:
 *   "4️⃣ Manutenção: ocioso também paga"), sem isso o i18next tentaria
 *   navegar "namespace:chave" / objeto aninhado e não achara a string.
 * - `returnEmptyString: false` — chave traduzida com "" (pendência que o
 *   `i18next-parser` deixa ao extrair texto novo) cai no fallback e mostra o
 *   PT em vez de uma tela em branco.
 */
const CHAVE_STORAGE = "simulacao.lang";

function idiomaInicial() {
  try {
    const salvo = localStorage.getItem(CHAVE_STORAGE);
    if (salvo === "pt" || salvo === "en") return salvo;
  } catch {
    /* localStorage indisponível (modo privado): segue a detecção */
  }
  // 1ª visita: navegador em inglês vê inglês; o resto do mundo, português.
  return (navigator.language || "pt").toLowerCase().startsWith("en")
    ? "en"
    : "pt";
}

/** Rótulo do idioma no formato usado na formatação de números/moeda. */
export const localeAtual = () =>
  i18n.language === "en" ? "en-GB" : "pt-BR";

/** Moeda exibida: BRL no PT, £ no EN (1:1 — só o símbolo muda, sem câmbio). */
export const moedaAtual = () => (i18n.language === "en" ? "GBP" : "BRL");

/** Troca o idioma e persiste a escolha (sempre vence a detecção automática). */
export function mudaIdioma(lng) {
  try {
    localStorage.setItem(CHAVE_STORAGE, lng);
  } catch {
    /* sem persistência o idioma volta ao detectado no próximo load */
  }
  document.documentElement.lang = lng;
  // title DEPOIS do changeLanguage — antes, ficaria no idioma antigo
  return i18n.changeLanguage(lng).then(() => {
    document.title = i18n.t("Bolsa de Commodities");
  });
}

i18n.use(initReactI18next).init({
  resources: {
    pt: { translation: {} },
    en: { translation: en },
  },
  lng: idiomaInicial(),
  fallbackLng: "pt",
  keySeparator: false,
  nsSeparator: false,
  returnEmptyString: false,
  interpolation: { escapeValue: false },
  // init síncrono (JSON no bundle): não há o que suspensear.
  react: { useSuspense: false },
});

document.documentElement.lang = i18n.language;
document.title = i18n.t("Bolsa de Commodities");

export default i18n;
