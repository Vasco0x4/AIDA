import { describe, it, expect } from 'vitest';
import { scheduleDate, formatScheduleTime, UTC_ZONES, timezoneLabel } from './scheduleTime';

describe('Schedule timestamps', () => {
  it('interprets naive API timestamps as UTC', () => {
    expect(scheduleDate('2026-11-09T03:00:00').toISOString()).toBe('2026-11-09T03:00:00.000Z');
  });
  it('preserves explicit timezone offsets', () => {
    expect(scheduleDate('2026-11-09T08:00:00+05:00').toISOString()).toBe('2026-11-09T03:00:00.000Z');
  });
  it('formats in the selected timezone and handles missing values', () => {
    const expected = new Intl.DateTimeFormat(undefined, { timeZone: 'Asia/Qyzylorda', dateStyle: 'medium', timeStyle: 'short' }).format(new Date('2026-11-09T03:00:00Z'));
    expect(formatScheduleTime('2026-11-09T03:00:00', 'Asia/Qyzylorda')).toBe(expected);
    expect(formatScheduleTime(null)).toBe('—');
  });
  it('maps every displayed UTC offset to the correct actual hour', () => {
    const instant = new Date('2026-11-09T12:00:00Z');
    UTC_ZONES.forEach((zone, index) => {
      const actual = Number(new Intl.DateTimeFormat('en-GB', {
        timeZone: zone.value, hour: '2-digit', hourCycle: 'h23',
      }).format(instant));
      expect(actual).toBe((12 + index - 12 + 24) % 24);
      expect(timezoneLabel(zone.value)).toBe(zone.label);
    });
    expect(timezoneLabel('Asia/Tashkent')).toBe('Asia/Tashkent');
  });
});
