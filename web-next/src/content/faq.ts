/**
 * The Dúvidas page copy (Tela 7 spec, 5.1 and 5.6), kept out of the component. Plain text only:
 * no HTML or markdown. DRAFT COPY, marked as such in the UI while `FAQ_DRAFT` is true. The item
 * ids and the order of the four groups are stable: other screens link to them with
 * `#/duvidas?abrir=<id>`.
 */

/** Shows the "Texto em rascunho" notice until the captain reviews the copy. */
export const FAQ_DRAFT = true;

export type FaqTerm = {t: string; d: string};
export type FaqLink = {label: string; href: string};
export type FaqItem = {id: string; q: string; a: string[]; terms?: FaqTerm[]; link?: FaqLink};
export type FaqGroup = {id: string; title: string; short: string; items: FaqItem[]};

export const FAQ: FaqGroup[] = [
  {id: 'tema-comparacao', title: 'Sobre a comparação', short: 'Comparação', items: [
    {id: 'destino', q: 'O que significa o destino dos votos?',
      a: ['É como o TSE classifica os votos dados a uma candidatura, conforme a situação do registro.'],
      terms: [
        {t: 'Válido', d: 'A candidatura está registrada e na urna. O voto conta para ela e para o partido ou federação.'},
        {t: 'Anulado sub judice', d: 'O registro foi negado, mas a candidatura ainda recorre na Justiça Eleitoral. O voto fica guardado como anulado até a decisão final: se o registro for aceito, passa a contar; se não, fica nulo.'},
        {t: 'Nulo técnico', d: 'O registro foi negado e não há mais recurso, ou a candidatura saiu da disputa. O voto não conta para ninguém.'},
      ]},
    {id: 'porque', q: 'Por que não olhar só o site do TSE?',
      a: [
        'O DivulgaCandContas, do TSE, compara só receitas e despesas de campanha. Aqui a comparação é do que cada candidatura declarou ao se registrar: partido, aliança, chapa, situação do registro, ocupação, bens e redes.',
        'Sem ranking, sem nota, sem recomendação de voto. A ordem é sempre a do número de urna. Os dados são os arquivos abertos do TSE, com a data em que o TSE os gerou.',
      ]},
    {id: 'campos', q: 'O que entra e o que não entra na comparação?',
      a: ['Entra o que cada candidatura declarou ao TSE: partido, chapa, bens, ocupação e redes. Gênero, cor/raça, estado civil e escolaridade nunca entram na comparação; aparecem só na ficha de cada candidatura.']},
  ]},
  {id: 'tema-bens', title: 'Bens declarados', short: 'Bens', items: [
    {id: 'evolucao', q: 'Por que a evolução dos bens ainda não aparece?',
      a: ['Em preparação: a comparação com as declarações de 2018 a 2024 ainda não está no serviço. Até lá, aparece só o total de 2026.']},
    {id: 'patrimonio', q: 'O total de bens é o patrimônio real?',
      a: ['Não necessariamente. Os bens são declarados ao TSE pelo custo de aquisição, não pelo valor de mercado.']},
    {id: 'fonte', q: 'De onde vêm os dados?',
      a: ['Do Portal de Dados Abertos do TSE, conforme a Resolução TSE nº 23.760/2026. Quando os dados têm mais de 48 horas, o rodapé de cada tela avisa.']},
  ]},
  {id: 'tema-privacidade', title: 'Privacidade', short: 'Privacidade', items: [
    {id: 'cpf', q: 'Preciso informar CPF ou título?',
      a: ['Não. O site não pede CPF, título nem cadastro, e nada do que você faz aqui fica guardado.']},
    {id: 'candidatos', q: 'Que dados das candidaturas aparecem aqui?',
      a: [
        'Mostramos o que o TSE publica sobre a candidatura. O número do título de eleitor do candidato existe nos arquivos do TSE e é usado só por um instante, para reconhecer a mesma pessoa entre eleições diferentes (a evolução dos bens); não é guardado nem mostrado.',
        'Gênero, cor/raça, estado civil e escolaridade aparecem só na ficha individual, nunca em listas ou na comparação. A descrição de cada bem (endereços, placas, contas) não entra no nosso índice.',
      ]},
    {id: 'oficial', q: 'Este site é do TSE?',
      a: ['Não. É um projeto independente e não oficial, feito com os dados abertos do TSE.']},
  ]},
  {id: 'tema-votar', title: 'Onde e quando votar', short: 'Votar', items: [
    {id: 'zona', q: 'Onde acho minha zona e minha seção?',
      a: ['No título de eleitor ou no app e-Título. Se não tiver nenhum dos dois à mão, veja os locais de votação da sua cidade.'],
      link: {label: 'Ver locais da cidade', href: '#/locais'}},
    {id: 'mudou', q: 'Meu local de votação mudou. E agora?',
      a: ['Quando o TSE registra que uma seção mudou de prédio, avisamos na resposta de "Onde voto" com o local anterior. Confira no e-Título antes de sair de casa.'],
      link: {label: 'Consultar onde voto', href: '#/onde-voto'}},
  ]},
];
