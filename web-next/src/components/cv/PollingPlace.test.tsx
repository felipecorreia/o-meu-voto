import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {InsetField} from './InsetField';
import {LinkCard} from './LinkCard';
import {StatusBadge} from './StatusBadge';
import {LoadingState} from './LoadingState';
import {SearchSummaryPill} from './SearchSummaryPill';
import {PlaceHero} from './PlaceHero';
import {SlidingTabs} from './SlidingTabs';

describe('polling place accessibility contracts', () => {
  it('associates the numeric field, its error and native validation state', () => {
    const html = renderToStaticMarkup(<InsetField label="Zona eleitoral" value="abc" onChange={() => {}} placeholder="ex.: 009" error="Use só números." />);
    expect(html).toMatch(/<label[^>]*>.*Zona eleitoral.*<input/);
    expect(html).toContain('inputMode="numeric"');
    expect(html).toContain('autoComplete="off"');
    expect(html).toContain('aria-invalid="true"');
    const id = html.match(/aria-describedby="([^"]+)"/)![1];
    expect(html).toContain(`id="${id}"`);
  });
  it('names the edit action with the complete search and announces loading', () => {
    const html = renderToStaticMarkup(<SearchSummaryPill zone="009" section="0422" state="São Paulo" round="Próximo turno" onEdit={() => {}} />);
    expect(html).toContain('aria-label="Editar busca: Zona 009 · Seção 0422, São Paulo · Próximo turno"');
    expect(renderToStaticMarkup(<LoadingState />)).toContain('aria-live="polite"');
  });
  it('preserves the original name for the screen reader and makes the result heading focusable', () => {
    const html = renderToStaticMarkup(<PlaceHero name="Colégio Objetivo" originalName="COLÉGIO OBJETIVO" addressLine1="Rua A" addressLine2="São Paulo - SP" chips={null} />);
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain('aria-label="COLÉGIO OBJETIVO"');
  });
  it('keeps existing links external and follows hash links in the current tab', () => {
    const props = {icon: null, title: 'Link', caption: 'Caption'};
    expect(renderToStaticMarkup(<LinkCard {...props} href="https://example.com" />)).toContain('target="_blank"');
    const internal = renderToStaticMarkup(<LinkCard {...props} href="#/locais?uf=SP" tone="accent" />);
    expect(internal).not.toContain('target=');
    expect(internal).toContain('cv-linkcard-accent');
  });
  it('lets an explicit tone override the candidate status mapping and kind', () => {
    const html = renderToStaticMarkup(<StatusBadge status="Com acessibilidade" kind="bad" tone="ok" />);
    expect(html).toContain('cv-status-ok');
    expect(html).toContain('Com acessibilidade');
    expect(renderToStaticMarkup(<StatusBadge status="Local bloqueado pelo TSE" tone="wait" />)).toContain('Local bloqueado pelo TSE');
  });
  it('uses tab semantics for rounds while keeping prior radio semantics by default', () => {
    const props = {options: [{value: '1', label: '1º turno'}], value: '1', onChange: () => {}, ariaLabel: 'Turno'};
    const tabs = renderToStaticMarkup(<SlidingTabs {...props} role="tablist" ariaLabelledby="turno" />);
    expect(tabs).toContain('role="tablist"');
    expect(tabs).toContain('aria-labelledby="turno"');
    expect(tabs).toContain('aria-selected="true"');
    expect(tabs).not.toContain('aria-checked=');
    const radios = renderToStaticMarkup(<SlidingTabs {...props} />);
    expect(radios).toContain('role="radiogroup"');
    expect(radios).toContain('aria-checked="true"');
  });
});
