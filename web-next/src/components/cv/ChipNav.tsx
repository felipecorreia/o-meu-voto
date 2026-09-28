export type ChipNavItem = {id: string; label: string};

/**
 * A row of chips that scroll to anchors of the same page (Tela 7 spec, 5.3): `<button>`s, never
 * `<a href="#…">`, because the router is hash-based and a fragment link would change the route.
 * The row scrolls sideways on phones; the page's CSS may stack it (the desktop column of
 * Dúvidas). `activeId` marks the anchor in view with `aria-current`; the parent decides when.
 */
export function ChipNav({items, activeId, onSelect, label = 'Temas'}: {items: ChipNavItem[]; activeId?: string | null; onSelect: (id: string) => void; label?: string}) {
  return <nav aria-label={label} className="cv-chipnav">
    <div className="cv-chipnav-row">
      {items.map(item => (
        <button key={item.id} type="button" className="cv-chipnav-chip" aria-current={activeId === item.id ? 'true' : undefined} onClick={() => onSelect(item.id)}>
          {item.label}
        </button>
      ))}
    </div>
  </nav>;
}
