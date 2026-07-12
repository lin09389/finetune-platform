/**
 * Backwards-compatible shell metadata entrypoint.
 *
 * The canonical labels live in navigation/routeMetadata so the browser title,
 * header, desktop sidebar and mobile navigation cannot drift independently.
 */
import { ROUTE_METADATA, getRouteTitle } from '../navigation/routeMetadata';

export const ROUTE_TITLES: Readonly<Record<string, string>> = Object.freeze(
  Object.fromEntries(ROUTE_METADATA.map((route) => [route.path, route.label])),
);

export { getRouteTitle };
