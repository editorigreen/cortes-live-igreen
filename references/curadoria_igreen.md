# Curadoria iGreen — como escolher os melhores momentos de uma live

## Para quem e para quê
Somos o time de Marketing da iGreen. O objetivo principal de todo corte é o **sucesso do LICENCIADO iGreen**: quem indica
clientes, monta estrutura e constrói renda e carreira com a companhia. Um bom corte faz o Licenciado pensar
"eu quero (e consigo) ganhar isso, e vou agir agora". Por isso a pergunta-guia é sempre:
**"este trecho deixa o Licenciado motivado a ganhar dinheiro ou a aproveitar uma oportunidade nova?"**

## Prioridade de temas
1. **Ganho financeiro concreto**: valores em R$, bônus, rendas recorrentes, comissões, "quanto dá com X clientes", conta
   feita ao vivo. É o tema mais forte. *Ex. 14/11: "50 clientes, três rendas: R$ 40.490"; "Pix de R$ 30 mil no Natal".*
2. **Promoção/campanha com prazo**: desafio, Green Friday, condição especial, "nunca mais vou fazer", licença que volta.
   Urgência legítima. *Ex.: "Licenciado novo: 10 clientes e a licença volta".*
3. **Oportunidade de mercado / novidade do ecossistema**: lançamentos, novos produtos (telecom, seguro, solar, mobilidade,
   iGreen Club), novos estados, aquisições, visão de futuro. *Ex.: "A iGreen está comprando um banco".*
4. **Carreira e liderança**: níveis, estrutura, executivo/diretor/acionista, como o líder cresce com o time.
5. **Valores e transformação**: propósito, família, histórias de vida, "fazer história". Funciona melhor como fecho ou
   como virada emocional de um corte de ganho do que sozinho.

Num lote de cortes, varie os temas (não entregue 4 cortes com a mesma promessa) e coloque o tema 1 ou 2 primeiro.

## Checklist de um bom corte (0–2 pontos cada; ≥ 11 de 16 = cortar)
| critério | 2 pontos quando… |
|---|---|
| Gancho | os 3 primeiros segundos já têm a promessa/número/novidade ("10 clientes. Seu dinheiro de volta.") |
| Número concreto | há valor em R$, quantidade de clientes, prazo ou % dito pelo porta-voz |
| O que o Licenciado ganha | fica claro o benefício PARA ELE (não só para a empresa ou o cliente final) |
| Condição presente | prazo, estados, meta, regra estão no corte (ou o título só promete o que a fala diz) |
| Autossuficiente | quem não viu a live entende sem contexto (sem "aquela tabela", "como eu falei antes") |
| Energia | porta-voz convicto, ritmo bom, gesto/expressão forte |
| Duração | 25–35 s de fala depois do corte de respiros (máx. ~45 s) |
| Fecho | termina numa frase de impacto ("…nunca mais", "fazer história", "mais 30 mil"), nunca no meio da ideia |

## Sinais de alerta (não cortar ou tratar antes)
- **Promessa sem a regra**: se a regra está em outro momento da live, anexe esse trecho (2º item em `trechos`, entra com
  flash) — foi o que fizemos no corte do Pix (regra "15/11 a 24/12, 300 clientes em 40 dias"). Se não der, o título
  traz a condição.
- **Ressalva geográfica/temporal** dita antes do trecho (ex.: "nesses 6 estados"): avalie incluir; se não couber, avise
  o usuário na entrega.
- Fala com cara de bastidor ou confidencial ("não posso falar demais", "não conta pra ninguém"), números de terceiros,
  crítica a concorrentes/parceiros, piadas internas, problemas técnicos da live, leitura de comentários do chat.
- Fala do convidado: pode, mas troque o `credito` do corte (nome/cargo de quem fala) e confira o recorte do layout.

## Processo
1. `python "<skill>/scripts/mapear_momentos.py" --projeto P` (live inteira; ~11 min para uma live de 38 min).
2. Leia `03_analise/momentos_candidatos.md` (top 15) **e** o trecho correspondente em `transcricao_completa.txt` para ver
   o contexto antes/depois — a nota é só triagem por palavras-chave.
3. Pontue os melhores com o checklist e monte uma lista curta. Se o usuário pediu N cortes, escolha os N melhores com
   variedade de temas; se não disse quantos, proponha 4–6.
4. Apresente ao usuário uma tabela antes de cortar: minuto, tema, gancho (1ª frase), título proposto, por que motiva o
   Licenciado. Quando o pedido já define os temas (ou vier com referências), siga direto.
5. Defina `trechos` começando no gancho (não no "então, gente…") e terminando no fecho; inclua a condição.

## Títulos (3 linhas, a última em verde = a promessa)
- Fórmulas que funcionaram: **[quem/condição]: [ação simples] e [resultado]** · **[quantidade], [mecanismo]: [valor]** ·
  **[sujeito] está [novidade forte]** · **[meta] em [prazo]: [prêmio em R$]**.
- Exemplos aprovados: "LICENCIADO NOVO: / 10 CLIENTES E / A LICENÇA VOLTA." · "50 CLIENTES, / TRÊS RENDAS: / R$ 40.490." ·
  "A iGreen ESTÁ / COMPRANDO / UM BANCO." · "300 CLIENTES EM / 40 DIAS: UM PIX DE / R$ 30 MIL NO NATAL."
- O título só promete o que a fala do corte diz (R-020). Números exatos como foram ditos.

## Destaques e punches
`destaques`: valores, verbos de ganho (ganhar, receber, constrói), a palavra da novidade (banco, desafio, grátis).
`punch_palavras` (3): o número principal, a palavra da oportunidade e a palavra do fecho.
