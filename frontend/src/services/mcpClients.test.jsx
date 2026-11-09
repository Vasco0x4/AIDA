import { describe, expect, it } from 'vitest';
import {
  MCP_CLIENT_ADAPTERS,
  buildClientSnippet,
  getMcpClientAdapter,
  resolveMcpUrl,
} from './mcpClients';

const URL = 'http://localhost:8001/mcp';
const KEY = 'aida_test-only-key';

describe('MCP client adapters', () => {
  it('provides explicit Codex, Gemini, Cursor, and generic MCP adapters', () => {
    expect(MCP_CLIENT_ADAPTERS.map((adapter) => adapter.id)).toEqual(expect.arrayContaining([
      'codex', 'gemini', 'cursor', 'generic',
    ]));
  });

  it('keeps the Codex bearer out of argv and uses the supported CLI flags', () => {
    const snippet = buildClientSnippet('codex', URL, KEY);
    expect(snippet).toContain(`export AIDA_MCP_API_KEY='${KEY}'`);
    expect(snippet).toContain(`codex mcp add aida --url '${URL}' --bearer-token-env-var AIDA_MCP_API_KEY`);
    expect(snippet.split('\n')[1]).not.toContain(KEY);
  });

  it('uses the Gemini CLI project-scoped Streamable HTTP registration', () => {
    const snippet = buildClientSnippet('gemini', URL, KEY);
    expect(snippet).toContain('gemini mcp add --scope project --transport http');
    expect(snippet).toContain('--header "Authorization: Bearer ${AIDA_MCP_API_KEY}"');
    expect(snippet).toContain(`aida '${URL}'`);
  });

  it.each(['cursor', 'claude-desktop', 'generic'])('builds valid MCP JSON for %s', (id) => {
    const config = JSON.parse(buildClientSnippet(id, URL, KEY));
    expect(config.mcpServers.aida).toEqual({
      url: URL,
      headers: { Authorization: `Bearer ${KEY}` },
    });
    expect(getMcpClientAdapter(id).description.length).toBeGreaterThan(20);
  });

  it('shell-quotes values instead of interpolating unsafe text', () => {
    const snippet = buildClientSnippet('codex', "http://localhost/mcp'$(bad)", "key'value");
    expect(snippet).toContain(`'http://localhost/mcp'"'"'$(bad)'`);
    expect(snippet).toContain(`'key'"'"'value'`);
  });
});

describe('resolveMcpUrl', () => {
  const location = { protocol: 'http:', hostname: '192.168.1.20' };

  it('uses loopback only for the localhost policy', () => {
    expect(resolveMcpUrl('localhost', { location, port: '8001' })).toBe('http://localhost:8001/mcp');
    expect(resolveMcpUrl('lan', { location, port: '8001' })).toBe('http://192.168.1.20:8001/mcp');
  });

  it('preserves HTTPS and formats IPv6 hosts', () => {
    expect(resolveMcpUrl('any', {
      location: { protocol: 'https:', hostname: '2001:db8::1' }, port: '8443',
    })).toBe('https://[2001:db8::1]:8443/mcp');
  });

  it('allows an explicit TLS/reverse-proxy endpoint', () => {
    expect(resolveMcpUrl('any', {
      location, configuredUrl: 'https://security.example/mcp/',
    })).toBe('https://security.example/mcp');
  });
});
