/**
 * Extração automática de chaves de tradução (usada só em dev).
 *
 * `npm run i18n:extract` varre `src/**` e reescreve `src/i18n/en.json`
 * mantendo as traduções já existentes e criando as chaves NOVAS com valor
 * "" (pendência). Valor "" cai no fallback (`returnEmptyString: false` no
 * init), então uma chave nova SEM tradução mostra o texto PT na tela —
 * nunca uma tela em branco.
 *
 * O locale `pt` não existe de propósito: a chave É o texto PT (PT-as-key).
 *
 * Cuidado: `keySeparator/nsSeparator` precisam bater com o init — os textos
 * PT contêm "." e ":" e o parser, sem isso, quebraria cada chave em pedaços.
 */
export default {
  locales: ["en"],
  output: "src/i18n/en.json",
  input: ["src/**/*.{js,jsx}"],
  keySeparator: false,
  nsSeparator: false,
  namespaceSeparator: false,
  namespace: "translation",
  defaultNamespace: "translation",
  // mantém as traduções já escritas e não reordena o arquivo
  keepRemoved: true,
  useKeysAsDefaultValue: false,
  // chaves de Trans (i18nKey) e interpolations
  lexers: {
    javascript: ["JavascriptLexer"],
    jsx: ["JsxLexer"],
  },
};
