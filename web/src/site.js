// Site profile from /api/meta (server: monishield/domain/services.py): the service folder name of each role and the
// pattern of the site's own network. Set once after sign-in (App.svelte); components read $site instead of fixed names.
import { writable } from 'svelte/store';

export const NGINX = 'nginx-ingress-controller';
const DEFAULT = { roles: { frontend: 'web-frontend', events: 'event-api', auth: 'auth-service', report: 'report-service', reference: 'reference-service' }, ownOrg: null };

export const site = writable(DEFAULT);

/** meta = the /api/meta answer. An invalid own-network pattern is ignored (the server validates it too). */
export function setSite(meta) {
  let ownOrg = null;
  try { ownOrg = meta?.own_org ? new RegExp(meta.own_org, 'i') : null; } catch { /* invalid pattern: no tag */ }
  site.set({ roles: { ...DEFAULT.roles, ...(meta?.roles || {}) }, ownOrg });
}

/** Does the network owner name belong to the site's own network? */
export const ownNetwork = (s, org) => !!(s.ownOrg && org && s.ownOrg.test(org));
