import {Badge} from '@astryxdesign/core/Badge';
import {Collapsible} from '@astryxdesign/core/Collapsible';
import {Text} from '@astryxdesign/core/Text';
import {PageHeader, ExternalLink} from '../components/common';

/**
 * FAQ in plain voter language (captain decision, inbox 002 of 2026-09-25 12:54Z). DRAFT COPY,
 * marked as such in the UI. Groups: the comparator's terms, assets and growth, privacy, where and
 * when. Accordion styled after the TSE portal's (palette section 5): grey container, white item,
 * question 16px/700 navy.
 */
interface Item { id: string; q: string; a: React.ReactNode }
interface Group { id: string; title: string; items: Item[] }

const GROUPS: Group[] = [
  {id: 'comparador', title: 'Sobre a comparação', items: [
    {id: 'destino', q: 'O que significam "voto válido", "anulado sub judice" e "nulo técnico"?', a: (
      <>
        <Text as="p">São os termos que o TSE usa para dizer o que acontece com o voto dado a uma candidatura.</Text>
        <ul className="faq-list">
          <li><b>Válido</b>: a candidatura está registrada e na urna. O voto conta para ela e para o partido ou federação.</li>
          <li><b>Anulado sub judice</b>: o registro foi negado, mas a candidatura ainda recorre na Justiça Eleitoral. O voto fica guardado como anulado até a decisão final: se o registro for aceito, passa a contar; se não, fica nulo.</li>
          <li><b>Nulo técnico</b>: o registro foi negado e não há mais recurso, ou a candidatura saiu da disputa. O voto não conta para ninguém.</li>
        </ul>
        <Text as="p">Mostramos o termo do TSE e, ao lado, esta explicação. Não é opinião sobre a pessoa: é a situação do registro naquele dia.</Text>
      </>
    )},
    {id: 'porque', q: 'Por que comparar candidaturas aqui, e não no site do TSE?', a: (
      <>
        <Text as="p">O DivulgaCandContas, do TSE, compara só receitas e despesas de campanha. Aqui a comparação é do que cada candidatura declarou ao se registrar: partido, aliança, chapa, situação do registro, ocupação, bens e redes.</Text>
        <Text as="p">Sem ranking, sem nota, sem recomendação de voto. A ordem é sempre a do número de urna. Os dados são os arquivos abertos do TSE, com a data em que o TSE os gerou.</Text>
      </>
    )},
    {id: 'campos', q: 'O que entra e o que não entra na comparação?', a: (
      <>
        <Text as="p">Entra o que a candidatura declarou ao TSE e é público: nome, número, partido, federação ou coligação, vice ou suplentes, situação do registro e destino dos votos, ocupação, total de bens, redes sociais e o link para a ficha oficial.</Text>
        <Text as="p">Não entra nunca: gênero, cor/raça, estado civil, escolaridade, idade, local de nascimento e a descrição de cada bem. Esses dados existem nos arquivos do TSE, mas não servem para comparar pessoas.</Text>
      </>
    )},
  ]},
  {id: 'bens', title: 'Bens declarados', items: [
    {id: 'evolucao', q: 'Como é calculada a evolução dos bens?', a: (
      <>
        <Text as="p">Comparamos o total de bens declarado em 2026 com a última declaração anterior da mesma pessoa em uma eleição de 2018, 2020, 2022 ou 2024, seja qual for o cargo disputado. Mostramos o ano e o cargo dessa declaração ao lado do valor, para ninguém comparar 2 anos com 8 sem saber.</Text>
        <Text as="p">A diferença aparece de duas formas: em reais, como está nos arquivos, e corrigida pela inflação (IPCA de agosto do ano da declaração anterior até agosto de 2026, o mês do registro). Não mostramos porcentagem: com valores pequenos ela vira um número enorme que não diz nada.</Text>
        <Text as="p">Os valores são os que a pessoa declarou ao TSE, pelo custo de aquisição, não pelo valor de mercado. Uma diferença entre duas declarações pode ser venda, herança, mudança de regime de bens ou só uma declaração refeita.</Text>
      </>
    )},
    {id: 'patrimonio', q: 'O total de bens é o patrimônio real da pessoa?', a: (
      <>
        <Text as="p">Não necessariamente. É o que foi declarado à Justiça Eleitoral, em geral pelo valor de compra, como na declaração do imposto de renda. Quem declarou não ter bens aparece assim; quem não informou aparece como "sem informação".</Text>
        <Text as="p">O detalhe de cada bem está na ficha oficial no DivulgaCandContas. Aqui mostramos só o total.</Text>
      </>
    )},
    {id: 'fonte', q: 'De onde vêm os dados e de quando são?', a: (
      <>
        <Text as="p">Do <ExternalLink href="https://dadosabertos.tse.jus.br/">Portal de Dados Abertos do TSE</ExternalLink> (candidaturas, bens, locais de votação), com licença CC-BY. Em toda resposta dizemos quando o TSE gerou o arquivo; se tiver mais de 48 horas, avisamos. Datas e horários da eleição vêm da Resolução TSE nº 23.760/2026.</Text>
      </>
    )},
  ]},
  {id: 'privacidade', title: 'Privacidade', items: [
    {id: 'cpf', q: 'Vocês pedem CPF, título ou nome?', a: (
      <>
        <Text as="p">Não. Para saber onde você vota, pedimos só UF, zona e seção, que estão impressas no título. Para comparar candidaturas, nada. Nada do que você digita é guardado.</Text>
        <Text as="p">"Perto de mim" usa a localização uma vez, no seu navegador, só para ordenar a lista de locais; ela não fica guardada.</Text>
      </>
    )},
    {id: 'candidatos', q: 'E os dados dos candidatos?', a: (
      <>
        <Text as="p">Mostramos o que o TSE publica sobre a candidatura. O número do título de eleitor do candidato existe nos arquivos do TSE e é usado só por um instante, para reconhecer a mesma pessoa entre eleições diferentes (a evolução dos bens); não é guardado nem mostrado.</Text>
        <Text as="p">Gênero, cor/raça, estado civil e escolaridade aparecem só na ficha individual, nunca em listas ou na comparação. A descrição de cada bem (endereços, placas, contas) não entra no nosso índice.</Text>
      </>
    )},
    {id: 'oficial', q: 'Este site é do TSE?', a: (
      <>
        <Text as="p">Não. É um projeto independente, de código aberto (licença MIT), feito com os dados abertos do TSE. Para serviços oficiais (título, local de votação pelo CPF, justificativa) use o e-Título e o site do TSE.</Text>
      </>
    )},
  ]},
  {id: 'votar', title: 'Onde e quando votar', items: [
    {id: 'zona', q: 'Como descubro minha zona e seção?', a: <Text as="p">No título de eleitor ou no aplicativo e-Título. Este site não consulta o cadastro eleitoral: com a zona e a seção, dizemos o local de votação; sem elas, listamos os locais da sua cidade.</Text>},
    {id: 'mudou', q: 'Meu local de votação mudou?', a: <Text as="p">Quando o TSE registra que uma seção mudou de prédio, avisamos na resposta de "Onde voto" com o local anterior. Confira no e-Título antes de sair de casa.</Text>},
  ]},
];

export function FaqPage({open}: {open?: string | null}) {
  return (
    <div className="page">
      <PageHeader title="Dúvidas frequentes" lead="Em linguagem de eleitor: o que os termos da comparação querem dizer, como contamos os bens e o que fazemos (e não fazemos) com os seus dados.">
        <div className="chips chips-compact"><Badge variant="warning" label="Texto em rascunho" /><Text size="sm" color="secondary">Redação provisória para revisão; a versão final entra com a página.</Text></div>
      </PageHeader>
      {GROUPS.map(g => (
        <section key={g.id} aria-labelledby={`faq-${g.id}`}>
          <h2 id={`faq-${g.id}`} className="h2">{g.title}</h2>
          <div className="faq">
            {g.items.map(it => (
              <div key={it.id} className="faq-item" id={`faq-${it.id}`}>
                <Collapsible defaultIsOpen={open === it.id} chevronPosition="end" trigger={<span className="faq-q">{it.q}</span>}>
                  <div className="faq-a">{it.a}</div>
                </Collapsible>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
