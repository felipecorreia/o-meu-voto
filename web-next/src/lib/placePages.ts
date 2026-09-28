import type {PollingPlace} from '../api';

export const PLACES_PAGE_SIZE = 20;

/** Append an offset page without repeating a place if the service includes an overlap. */
export async function appendPlacesPage(
  current: PollingPlace[],
  fetchPage: (offset: number, limit: number) => Promise<PollingPlace[]>,
): Promise<{places: PollingPlace[]; added: number}> {
  const page = await fetchPage(current.length, PLACES_PAGE_SIZE);
  const seen = new Set(current.map(place => `${place.zone}-${place.number}`));
  const added = page.filter(place => {
    const key = `${place.zone}-${place.number}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return {places: [...current, ...added], added: added.length};
}
