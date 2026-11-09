import { describe, expect, it } from 'vitest';
import { utcDate } from './utcDate';
describe('API timestamp interpretation', () => {
  it('keeps naive UTC timestamps at the same instant in all display zones', () => {
    const timestamp = utcDate('2026-11-09T10:30:00.123456');
    expect(timestamp.toISOString()).toBe('2026-11-09T10:30:00.123Z');
    for (const [timeZone, hour] of [['Asia/Qyzylorda','15'],['Asia/Tashkent','15'],['Europe/Moscow','13'],['UTC','10']]) {
      expect(new Intl.DateTimeFormat('en-GB',{timeZone,hour:'2-digit'}).format(timestamp)).toBe(hour);
    }
    expect(utcDate('2026-11-09T10:31:00Z') - timestamp).toBe(59877);
  });
  it('preserves offsets and native constructor behavior', () => {
    expect(utcDate('2026-11-09T15:30:00+05:00').toISOString()).toBe('2026-11-09T10:30:00.000Z');
    expect(utcDate(0).getTime()).toBe(0);
    expect(utcDate(new Date(123)).getTime()).toBe(123);
    expect(Number.isNaN(utcDate('invalid').getTime())).toBe(true);
    expect(utcDate(2026,0,2).getDate()).toBe(2);
  });
});
