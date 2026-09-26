import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {PrivateDataPanel} from './PrivateDataPanel';
import {StatusBadge, statusKind} from './StatusBadge';
import {CompareColumnHeader} from './CompareColumnHeader';

describe('profile status', () => {
  it.each([
    ['DEFERIDO', 'ok'], ['INDEFERIDO COM RECURSO', 'bad'], ['CASSADO', 'bad'],
    ['RENÚNCIA', 'bad'], ['CANCELADO', 'bad'], ['CANCELADA', 'bad'],
    ['PENDENTE', 'wait'], ['AGUARDANDO JULGAMENTO', 'wait'], ['DEFERIDO COM RECURSO', 'wait'],
  ])('maps %s to %s with a decorative icon', (status, kind) => {
    expect(statusKind(status)).toBe(kind);
    const html = renderToStaticMarkup(<StatusBadge status={status} />);
    expect(html).toContain(`cv-status-${kind}`);
    expect(html).toContain('<svg');
    expect(html).toContain('aria-hidden="true"');
  });
  it('keeps ballot badges neutral without an icon', () => {
    const html = renderToStaticMarkup(<StatusBadge status="Na urna" kind="neutral" />);
    expect(html).toContain('cv-status-neutral');
    expect(html).not.toContain('<svg');
  });
});
describe('private data panel', () => {
  it('starts closed with an associated region and no personal values mounted', () => {
    const html = renderToStaticMarkup(<PrivateDataPanel candidate={{gender: 'private-gender', race_color: 'private-race', marital_status: 'private-status', education: 'private-education'}} />);
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls=');
    expect(html).toContain('role="region"');
    expect(html).toContain('aria-labelledby=');
    expect(html).toContain('hidden=""');
    for (const value of ['private-gender', 'private-race', 'private-status', 'private-education']) expect(html).not.toContain(value);
  });
});
describe('comparison profile link', () => {
  it('retains the supplied context and slot', () => {
    const html = renderToStaticMarkup(<CompareColumnHeader c={{sq_candidato: 2, ballot_name: 'MARIA SILVA', number: 11, party: {number: 11, acronym: 'PP', name: 'Party'}, photo_url: null}} slot={2} profileHref="#/candidato/2?uf=AC&office=governador&cmp=3,2,1&pair=1,2&tab=ocupacao" />);
    expect(html).toContain('data-slot="2"');
    for (const param of ['cmp=3,2,1', 'pair=1,2', 'tab=ocupacao']) expect(html).toContain(param);
  });
});
