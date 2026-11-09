import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createNvdService } from './nvdService.js';

test('getDigest returns the cached digest from the existing endpoint', async () => {
  const digest = { items: [], item_count: 0, status: 'stale' };
  const calls = [];
  const client = {
    async get(url) {
      calls.push(url);
      return { data: digest };
    },
  };

  const result = await createNvdService(client).getDigest();

  assert.equal(result, digest);
  assert.deepEqual(calls, ['/nvd/digest']);
});

test('getStatus returns schedule and freshness metadata without inventing fields', async () => {
  const status = { enabled: true, next_refresh_at: '2026-11-06T12:00:00Z' };
  const calls = [];
  const client = {
    async get(url) {
      calls.push(url);
      return { data: status };
    },
  };

  const result = await createNvdService(client).getStatus();

  assert.equal(result, status);
  assert.deepEqual(calls, ['/nvd/status']);
});

test('refresh posts to the admin refresh endpoint and returns the updated digest', async () => {
  const digest = { refreshed: true, items: [{ cve_id: 'CVE-2026-0001' }] };
  const calls = [];
  const client = {
    async post(...args) {
      calls.push(args);
      return { data: digest };
    },
  };

  const result = await createNvdService(client).refresh();

  assert.equal(result, digest);
  assert.deepEqual(calls, [['/nvd/refresh']]);
});

test('updateSchedule sends only caller-provided schedule fields to the existing endpoint', async () => {
  const status = { enabled: true, refresh_interval_hours: 12 };
  const changes = { enabled: true, refresh_interval_hours: 12 };
  const calls = [];
  const client = {
    async put(...args) {
      calls.push(args);
      return { data: status };
    },
  };

  const result = await createNvdService(client).updateSchedule(changes);

  assert.equal(result, status);
  assert.deepEqual(calls, [['/nvd/schedule', changes]]);
});
