// Local time zone of the site (S4_TIMEZONE_OFFSET / S4_TIMEZONE_LABEL), from /api/meta (site.js). Times from the API are
// already local; this only names the zone and converts the few UTC values (server clock) and "today".
export const TZ = { minutes: 7 * 60, label: 'WIB' };

export function setTimezone(z) {
  if (z && Number.isFinite(z.minutes)) TZ.minutes = z.minutes;
  if (z && typeof z.label === 'string' && z.label) TZ.label = z.label;
}

/** Today's date in the site's zone: 'YYYY-MM-DD' (a folder date). */
export const localToday = () => new Date(Date.now() + TZ.minutes * 60e3).toISOString().slice(0, 10);
