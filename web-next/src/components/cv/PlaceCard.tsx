import {ChevronRight, Map, MapPin} from 'lucide-react';
import type {PollingPlace} from '../../api';
import {href} from '../../router';
import {mapsUrl} from '../../lib/links';
import {toTitleCase} from '../../lib/titleCase';
import {NumberPill} from './NumberPill';
import {StatusBadge} from './StatusBadge';

export function PlaceCard({place, showDistance, uf, municipality, cardRef}: {
  place: PollingPlace; showDistance: boolean; uf: string; municipality: {name: string; uf: string}; cardRef?: React.Ref<HTMLElement>;
}) {
  const name = toTitleCase(place.name);
  const address = [place.address, place.neighborhood].filter(Boolean).map(toTitleCase).join(' · ');
  const originalAddress = [place.address, place.neighborhood].filter(Boolean).join(' · ');
  return <article ref={cardRef} className="cv-placecard cv-voting-enter" tabIndex={-1}>
    <div className="cv-placecard-head">
      <span className="cv-placecard-pin" aria-hidden><MapPin size={23} /></span>
      <div className="cv-placecard-title"><h2 aria-label={place.name}>{name}</h2><p aria-label={originalAddress}>{address}</p></div>
      {showDistance && place.distance_km != null ? <span className="cv-placecard-distance">{place.distance_km.toFixed(1).replace('.', ',')} km</span> : null}
    </div>
    <div className="cv-placecard-chips">
      {place.zone != null ? <NumberPill n={`Zona ${place.zone}`} /> : null}
      <StatusBadge status={`${place.section_count} ${place.section_count === 1 ? 'seção' : 'seções'}`} tone="neutral" />
      {place.accessible_section_count > 0 ? <StatusBadge status={`${place.accessible_section_count} com acessibilidade`} tone="ok" /> : null}
      {place.status !== 'ativo' ? <StatusBadge status="Local bloqueado pelo TSE" tone="wait" /> : null}
    </div>
    <div className="cv-placecard-actions">
      {place.zone != null ? <a className="cv-placecard-section" href={href('/onde-voto', {uf, zone: place.zone})}>Sei minha seção<ChevronRight size={18} aria-hidden /></a> : <span />}
      <a className="cv-placecard-map" href={mapsUrl({...place, municipality})} target="_blank" rel="noopener" aria-label={`Ver ${name} no mapa, abre em nova aba`}><Map size={19} aria-hidden />Mapa</a>
    </div>
  </article>;
}
