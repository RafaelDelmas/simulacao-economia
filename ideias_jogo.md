# 💡 Ideias de jogo

Coleção de ideias pra deixar a simulação mais divertida (e com mais economia embutida).
Cada uma tem o **gancho** — o pedaço do sistema que já existe pra se pendurar — e o
**porquê** de divertir.

Marcadores: ⭐ = diversão alta com pouco código · 🔥 = impacto grande · 🧠 = aprendizado
de economia em destaque · ⚠️ = arriscada (vale como "modo difícil" / experimento de aula).

---

## 1. Mecânicas de mercado

**1. ⭐ Ordem stop (stop-loss / take-profit)** — "se o café cair a R$ 4,00, vende".
Ordem dormente (gatilho + lado) que só entra no book quando `preco_vivo()` toca o preço
— o `MarketEngine` já roda por tick, é checar a condição lá. *Diverte:* o jogador monta
estratégia de proteção igual corretora de verdade. *Ensina:* gestão de risco.

**2. ⭐ Alertas de preço** — "avise quando o aço passar de R$ 7". O WS já existe: grava o
alerta e publica `price.alert` no `events.py`; sendo PWA, dá pra notificar no celular.
*Diverte:* ninguém fica refrescando a tela.

**3. ⭐ Compra por orçamento** — "quero gastar R$ 500 em café" em vez de escolher
quantidade + preço; o engine preenche contra o book até estourar o orçamento.
*Diverte:* entrada muito mais simples pra quem só quer entrar rápido.

**4. 🧠 Opção de compra (call)** — pagar um prêmio hoje pelo direito de comprar a preço
fixo até data X; a contraparte é a tesouraria do sistema (`user_id = None` já é sistema).
*Ensina:* hedge de verdade. *Diverte:* aposta alavancada com risco limitado (perde só
o prêmio).

**5. ⭐ Lotes por commodity** — trigo em "sacas de 5", aço em "bobinas de 10"
(validar múltiplo de N no `OrderCreate`). *Diverte:* o book fica legível, acaba o
"1.37 un" esquisito.

**6. ⚠️ Venda a descoberto (short) com garantia** — só se o jogador "congelar" saldo
como margem cobrindo a venda. *Ensina:* por que a bolsa exige margem. *Arriscada:*
mexeria na regra que acabamos de proteger — só como opcional configurável por partida.

## 2. Eventos & narrativa

**7. 🔥 Cartas de evento (manchetes)** — botão no painel do admin: "Greve nos portos",
"Safra recorde de trigo", "Embargo ao carvão", "Chuva atrasa a colheita do café".
Cada carta = texto da manchete + `shock`/`freeze` na commodity + banner colorido no topo
(via WS, evento `news`). *Diverte:* vira cena, não só número. *Gancho:* a chamada de
choque já existe e faz o trabalho pesado.

**8. 🧠 Rumores (informação incerta)** — o feed publica um boato ("dizem que haverá
embargo no carvão") que acerta ~50% das vezes. Quando o evento verdadeiro rola, quem
comprou antes lucra e quem não acreditou perde. *Ensina:* informação assimétrica e
risco. *Diverte:* fase de "apostar no boato" antes de saber a verdade.

**9. 🔥 Leilão relâmpago** — a cada X minutos uma commodity entra em leilão de 60s:
lote único, melhor lance vence (a tesouraria entrega). *Diverte:* correria contra o
relógio; *gancho:* book + uma ordem especial `auction=true`.

**10. 🧠 Embargo com contagem regressiva** — o `freeze` já existe; falta mostrar o
cronômetro ("Mercado fechado 04:32") e reabrir automático. *Ensina:* escassez — todo
mundo empilha ordem esperando reabrir e o preço explode na reabertura.

**11. ⚠️ Empréstimo da banca (crédito)** — o admin oferta crédito com juros que
compõe por tick; quem atrasa (fica sem saldo) toma calote. *Ensina:* risco de crédito.
*Arriscada:* precisa da mesma disciplina do `_check_trade` pra nunca deixar saldo
negativo sem log.

## 3. Progressão & gamificação

**12. 🔥 Ranking com patrimônio e patentes** — hoje não existe ranking público (só a
lista de usuários do admin). Ordenar por `saldo + Σ(posição × preço atual)`, com
patentes Bronze → Prata → Ouro → Diamante por faixa. *Diverte:* a corrida é o coração
do multiplayer; *gancho:* `positions` já tem `avg_price` e o preço atual vem de
`/api/commodities`.

**13. ⭐ Medalhas / conquistas** — "Primeira venda", "10 ordens abertas", "Comprou
antes de uma alta de 10%", "Sobreviveu a um embargo". Tabela `achievements` + ícone
na carteira. *Gancho:* `executed_quantity` já conta o volume negociado.

**14. Missões da rodada** — desafio que muda a cada partida: "negocie 100 de trigo",
"feche com lucro em 3 commodities". Recompensa: badge ou XP.

**15. XP por volume negociado** — `Σ executed_quantity × preço` vira XP; o nível dá
cor/badge no nome. *Diverte:* mesmo quem perde dinheiro "subiu de nível" — retém quem
tá começando apanhando.

**16. ⭐ Avatar: sigla + cor do jogador** — 4 letras e uma cor no ranking e no ticker.
*Diverte:* humano tem que se reconhecer; hoje todo mundo é linha igual linha de bot.

## 4. Social & turmas

**17. 🔥 Turmas (times)** — campo `team` no usuário; ranking de turma = soma do
patrimônio dos membros. *Diverte:* competição coletiva (perfeito pra sala de aula);
*gancho:* uma query e uma tela.

**18. ⭐ Ticker "movimentações"** — fita de notícias no topo: "Fulano comprou 50 café a
R$ 5,10". *Gancho:* `events.py` já publica `bot.activity`; é juntar os fills de
jogadores (todos passam pelo `_apply_fill`). *Diverte:* mercado vivo, dá pra ver a
"baleia" chegando.

**19. 🔥 Proposta de troca (P2P)** — "dou 10 trigo por 5 café": o outro aceita ou
recusa e liquida direto, sem book. *Diverte:* negociação humana, fora do automático.
*Ensina:* descoberta de preço por barganha — preço negociado vs. preço do book.
*Gancho:* endpoint novo + evento WS.

**20. ⚠️ Chat rápido** — 1 linha por jogador, 80 caracteres, admin pode limpar.
*Diverte:* muito. *Arriscada:* exige filtro contra spam — só vale se a turma for
confiável.

## 5. Professor / painel do admin

**21. 🔥 Roteiro de partida (presets)** — uma tela com "Fase 1: mercado calmo",
"Fase 2: choque do carvão", "Fase 3: frenesi" — aperta e roda a sequência de
shocks/freezes com intervalo automático. *Diverte:* o professor vira diretor de cena;
*gancho:* as chamadas de choque já existem, é agendar.

**22. ⭐ Exportar CSV** — histórico de preços, carteira e trades em `.csv`
(`/api/commodities/history` já serve os dados). *Ensina:* a turma abre na planilha e
faz a própria análise — vira aula de dados em cima do jogo.

**23. ⭐ Relógio da rodada + tela de fim** — "restam 12:34" no topo; quando acaba,
tela com estatísticas: maior lucro, maior volume, maior oscilação, "comprou no topo
do ano". *Diverte:* tensão e desfecho.

**24. Modo espectador** — tela read-only projetável (professor no data show) com tudo
aberto, sem poder comprar.

## 6. Relatórios & aprendizado

**25. 🔥 P&L na carteira** — com `avg_price` (já existe!) e preço atual: "10 café
comprados a R$ 4,80 — hoje valem R$ 5,10 → **+R$ 3,00 (não realizado)**". Cálculo
trivial, tela mais educativa do jogo. *Ensina:* lucro realizado × não realizado.

**26. ⭐ Marcadores dos seus trades no gráfico** — bolinhas ▲ (comprou) / ▼ (vendeu)
sobre o `PriceChart`, cruzando fills com o histórico. *Diverte:* ver "comprei no
topo" 😅. *Ensina:* timing.

**27. 🧠 Carteira vs. índice** — linha do "se você tivesse só comprado a média do
mercado" contra a sua carteira. *Ensina:* ativo vs. passivo em 10 segundos de aula.

**28. ⭐ Glossário dicas** — tooltip contextual ("o que é spread?", "o que é ordem
limit?") do lado do que o jogador está usando. *Ensina:* vocabulário sem exigir
página separada.

## 7. Economia & cadeia produtiva

**29. 🔥 Cadeia de produção** — receita: `2 Algodão → 1 Tecido`, `1 Carvão + 1 Aço →
peça industrial` (nova commodity + botão "produzir"). *Ensina:* valor agregado e
demanda derivada. *Diverte:* o jogo vira fábrica, não só mercado.

**30. 🧠 Sazonalidade no preço base** — trigo sobe na "safra" e cai na "entressafra"
(ciclo de N ticks). *Ensina:* ciclos — quem entra na reta antes lucra; *gancho:*
`_update_commodity_prices` já faz reversão ao nominal, é dar um seno no tempo.

**31. ⚠️ Custo de armazenagem** — estoque parado custa `0,1% por tick` (vira mais um
sink). *Ensina:* custo de carregar estoque (carry). *Arriscada:* toda regra que mexe
em saldo/estoque por tick precisa do mesmo cuidado do `_check_trade` + log no
`_apply_fill`.

**32. 🧠 Juros do saldo ocioso (ou inflação mais agressiva)** — ou rende um pouquinho
por tick se parado, ou o dinheiro enfraquece (a `tax.applied` já infla os preços).
*Ensina:* alternativa de oportunidade e por que dinheiro parado também tem custo.

## 8. Bots com personalidade

**33. 🔥 Bots temáticos** — "Siderúrgica União" compra carvão sempre que barato;
"Fazendeiro Joaquim" vende trigo na safra; "Importadora Marítima" faz arbitragem.
Com nome e cor no ticker. *Diverte:* o mercado vira castelo de gente — a "IA" é só
estratégia + cron; *gancho:* o loop em `bots_activity.py` já existe.

**34. ⭐ Bots reagem a manchetes** — quando o "embargo" rola, os bots enchem estoque
antes do público. *Ensina:* quem tem informação move o preço primeiro.

## 9. Extras rápidos (o polimento)

**35. ⭐ Feedback na execução** — flash/sonidinho na tela do balcão quando a ordem
casa (evento de fill já passa pelo WS). São 10 linhas e mudam a sensação de acertar.

**36. ⭐ Toast "sua ordem executou"** — aviso mesmo com a aba em segundo plano (PWA).

**37. ⭐ Humor do mercado em 1 linha** — topo: "☕ Café +12% (fogando)" com emoji/cor
por variação. Leitura de 1 segundo.

**38. Tutorial da primeira rodada** — objetivos: criar 1 ordem, cancelar 1 ordem, ver o
book → badge de iniciado. *Diverte:* reduz o choque da tela cheia de número.

---

## 🏆 Top 5 pra começar (diversão ÷ esforço)

1. **P&L na carteira (25)** — o `avg_price` já está lá; dá sentido pra tudo o resto.
2. **Ranking + patentes (12)** — a corrida é o coração de um jogo multiusuário.
3. **Cartas de evento (7)** — é o `shock` que já existe + narrativa; o professor vira
   mestre de cena.
4. **Ticker de movimentações (18)** — o mercado ganha vida no primeiro minuto.
5. **Ordem stop (1)** — a primeira "ferramenta de verdade" que o jogador aprende a usar.

## ⚠️ Regras a respeitar (depois do fix do saldo/estoque)

- Toda feature que **cria ordem** passa pelo `OrderController.create` (nunca direto no
  book): é lá que ficam `_check_trade` (desconta comprometido), `_check_limit` e o
  `order_book.locked()`.
- Feature que mexer em **saldo/estoque fora do match** (empréstimo, armazenagem, cash
  de recompensa) precisa da mesma disciplina: nunca deixar negativo sem `logger.warning`
  — é o padrão do `_apply_fill`.
- Evento que mexe em preço usa `shock`/`shock_prices` **sob o lock do book**.
- Rotas literais antes das parametrizadas (ex.: `/leaderboard` antes de `/{id}`).
