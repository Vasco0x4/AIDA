// Etc/GMT uses POSIX signs: Etc/GMT-5 is UTC+05:00.
export const UTC_ZONES = Array.from({ length: 27 }, (_, index) => {
  const offset = index - 12;
  return { value: offset === 0 ? 'UTC' : `Etc/GMT${offset > 0 ? '-' : '+'}${Math.abs(offset)}`,
    label: offset === 0 ? 'UTC+00:00' : `UTC${offset > 0 ? '+' : '-'}${String(Math.abs(offset)).padStart(2, '0')}:00` };
});
export function timezoneLabel(zone = 'UTC') {
  return UTC_ZONES.find(item => item.value === zone)?.label || zone;
}

// Legacy API timestamps are naive UTC, never browser-local wall time.
export function scheduleDate(value) {
  if (!value) return null;
  const text = String(value);
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text) ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatScheduleTime(value, timezone = 'UTC') {
  const date = scheduleDate(value);
  if (!date) return '—';
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone || 'UTC', dateStyle: 'medium', timeStyle: 'short',
    }).format(date);
  } catch { return date.toISOString(); }
}
