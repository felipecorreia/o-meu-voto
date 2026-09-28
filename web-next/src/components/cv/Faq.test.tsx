import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {FAQ} from '../../content/faq';
import {FaqScreen} from '../../pages/Faq';
import {AccordionGroup, AccordionItem} from './Accordion';
import {ChipNav} from './ChipNav';
import {TermList} from './TermList';

const ids = ['destino', 'porque', 'campos', 'evolucao', 'patrimonio', 'fonte', 'cpf', 'candidatos', 'oficial', 'zona', 'mudou'];
const screen = (open: string | null = null, draft = true) => renderToStaticMarkup(<FaqScreen open={open} draft={draft} groups={FAQ} />);
const expanded = (html: string, id: string) => new RegExp(`id="b-${id}" type="button" aria-expanded="(true|false)"`).exec(html)?.[1];

describe('the Dúvidas screen', () => {
  it('opens as an index with everything closed, the draft notice and the four chips (criterion 1)', () => {
    const html = screen();
    expect(html).toContain('<h1>Dúvidas <span>frequentes</span></h1>');
    expect(html).toContain('Respostas curtas sobre a comparação, os dados e o dia da votação.');
    expect(html).toContain('cv-notice cv-notice-wait');
    expect(html).toContain('<span class="cv-notice-title">Texto em rascunho</span><p>Redação provisória, ainda em revisão.</p>');
    expect(html).toContain('<nav aria-label="Temas" class="cv-chipnav">');
    expect(html.match(/class="cv-chipnav-chip"/g)).toHaveLength(4);
    for (const label of ['Comparação', 'Bens', 'Privacidade', 'Votar']) expect(html).toContain(`>${label}</button>`);
    expect(html).not.toContain('aria-current');
    for (const id of ids) expect(expanded(html, id)).toBe('false');
    expect(html).not.toContain('role="region"');
  });
  it('keeps the eleven ids in the order other screens link to, inside the four theme sections', () => {
    const html = screen();
    const positions = ids.map(id => html.indexOf(`id="q-${id}"`));
    expect(positions.every(p => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    const sections = ['tema-comparacao', 'tema-bens', 'tema-privacidade', 'tema-votar'].map(id => html.indexOf(`<section id="${id}" class="cv-accordion-group" aria-labelledby="${id}-title">`));
    expect(sections.every(p => p >= 0)).toBe(true);
    expect([...sections].sort((a, b) => a - b)).toEqual(sections);
    expect(html).toContain('<h2 id="tema-privacidade-title" tabindex="-1">Privacidade</h2>');
  });
  it('renders ?abrir=zona open, with its action link and the copy button (criteria 2 and 9)', () => {
    const html = screen('zona');
    expect(expanded(html, 'zona')).toBe('true');
    for (const id of ids.filter(id => id !== 'zona')) expect(expanded(html, id)).toBe('false');
    expect(html).toContain('<div id="r-zona" role="region" aria-labelledby="b-zona" class="cv-accordion-panel">');
    expect(html).toContain('<p>No título de eleitor ou no app e-Título. Se não tiver nenhum dos dois à mão, veja os locais de votação da sua cidade.</p>');
    expect(html).toContain('<a href="#/locais">Ver locais da cidade<svg');
    expect(html).toContain('>Copiar link</button>');
    expect(html).toContain('<span class="cv-sr-only" aria-live="polite"></span>');
    expect(html).not.toContain('Não deu para copiar');
    expect(screen('mudou')).toContain('<a href="#/onde-voto">Consultar onde voto<svg');
  });
  it('ignores an unknown ?abrir= (criterion 4)', () => {
    const html = screen('xyz');
    for (const id of ids) expect(expanded(html, id)).toBe('false');
    expect(html).not.toContain('role="region"');
  });
  it('shows the three vote-destination terms with the explanations of the old page (criterion 8)', () => {
    const html = screen('destino');
    expect(html).toContain('<p>É como o TSE classifica os votos dados a uma candidatura, conforme a situação do registro.</p>');
    const dl = /<dl class="cv-termlist">(.*?)<\/dl>/.exec(html)?.[1] ?? '';
    expect(dl.match(/<dt>/g)).toHaveLength(3);
    expect(dl).toContain('<dt>Válido</dt><dd>A candidatura está registrada e na urna. O voto conta para ela e para o partido ou federação.</dd>');
    expect(dl).toContain('<dt>Anulado sub judice</dt><dd>O registro foi negado, mas a candidatura ainda recorre na Justiça Eleitoral. O voto fica guardado como anulado até a decisão final: se o registro for aceito, passa a contar; se não, fica nulo.</dd>');
    expect(dl).toContain('<dt>Nulo técnico</dt><dd>O registro foi negado e não há mais recurso, ou a candidatura saiu da disputa. O voto não conta para ninguém.</dd>');
    expect(html.indexOf('<dl')).toBeGreaterThan(html.indexOf('<p>É como o TSE'));
    expect(html.indexOf('cv-accordion-actions')).toBeGreaterThan(html.indexOf('</dl>'));
  });
  it('hides the draft notice with FAQ_DRAFT off (criterion 10)', () => {
    const html = screen(null, false);
    expect(html).not.toContain('Texto em rascunho');
    expect(html).not.toContain('cv-notice');
    expect(html).toContain('<nav aria-label="Temas"');
  });
  it('keeps the old page\'s answers where the spec says to', () => {
    const html = screen('porque');
    expect(html).toContain('<p>O DivulgaCandContas, do TSE, compara só receitas e despesas de campanha.');
    expect(html).toContain('<p>Sem ranking, sem nota, sem recomendação de voto.');
    expect(screen('candidatos')).toContain('<p>Mostramos o que o TSE publica sobre a candidatura.');
    expect(screen('mudou')).toContain('<p>Quando o TSE registra que uma seção mudou de prédio,');
  });
  it('never puts HTML, markdown or a technical code in the copy', () => {
    for (const g of FAQ) for (const item of g.items) {
      for (const text of [item.q, ...item.a, ...(item.terms ?? []).flatMap(t => [t.t, t.d])]) {
        expect(text).not.toMatch(/[<>*_`]/);
        expect(text.trim()).toBe(text);
        expect(text.length).toBeGreaterThan(0);
      }
    }
  });
});

describe('the Tela 7 pieces', () => {
  it('AccordionItem follows the WAI-ARIA accordion pattern', () => {
    const closed = renderToStaticMarkup(<AccordionGroup id="g" title="Grupo"><AccordionItem id="x" question="Q?" open={false} onToggle={() => {}}>A</AccordionItem></AccordionGroup>);
    expect(closed).toContain('<h3><button id="b-x" type="button" aria-expanded="false" aria-controls="r-x">');
    expect(closed).toContain('<span class="cv-accordion-chevron" aria-hidden="true">');
    expect(closed).not.toContain('id="r-x"');
    const open = renderToStaticMarkup(<AccordionItem id="x" question="Q?" open onToggle={() => {}}>A</AccordionItem>);
    expect(open).toContain('aria-expanded="true"');
    expect(open).toContain('<div id="r-x" role="region" aria-labelledby="b-x" class="cv-accordion-panel">A</div>');
  });
  it('ChipNav renders buttons, never fragment links, and marks the active one', () => {
    const html = renderToStaticMarkup(<ChipNav items={[{id: 'a', label: 'A'}, {id: 'b', label: 'B'}]} activeId="b" onSelect={() => {}} />);
    expect(html).not.toContain('<a ');
    expect(html).toContain('<button type="button" class="cv-chipnav-chip">A</button>');
    expect(html).toContain('<button type="button" class="cv-chipnav-chip" aria-current="true">B</button>');
  });
  it('TermList is a <dl> of blocks', () => {
    expect(renderToStaticMarkup(<TermList terms={[{t: 'T', d: 'D'}]} />)).toBe('<dl class="cv-termlist"><div><dt>T</dt><dd>D</dd></div></dl>');
  });
});
