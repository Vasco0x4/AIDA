/** Streamable-HTTP MCP client adapters. Secrets appear only in the one-time key modal. */

const shellQuote = (value) => `'${String(value).replaceAll("'", `'"'"'`)}'`;

const jsonConfig = (url, token) => JSON.stringify({
  mcpServers: {
    aida: {
      url,
      headers: { Authorization: `Bearer ${token}` },
    },
  },
}, null, 2);

const exportKey = (token) => `export AIDA_MCP_API_KEY=${shellQuote(token)}`;

export const MCP_CLIENT_ADAPTERS = [
  {
    id: 'claude-code',
    label: 'Claude Code',
    description: 'Run in the project directory. Claude Code registers the project-scoped HTTP server.',
    build: (url, token) => `${exportKey(token)}\nclaude mcp add --transport http aida ${shellQuote(url)} --header "Authorization: Bearer \${AIDA_MCP_API_KEY}"`,
  },
  {
    id: 'codex',
    label: 'Codex',
    description: 'Codex CLI reads the bearer from your environment. The AIDA launcher also supports --cli codex without changing persistent MCP config.',
    build: (url, token) => `${exportKey(token)}\ncodex mcp add aida --url ${shellQuote(url)} --bearer-token-env-var AIDA_MCP_API_KEY`,
  },
  {
    id: 'gemini',
    label: 'Gemini CLI',
    description: 'Registers a project-scoped server in .gemini/settings.json. Trust the project when Gemini prompts; tool approval remains controlled by Gemini CLI.',
    build: (url, token) => `${exportKey(token)}\ngemini mcp add --scope project --transport http --header "Authorization: Bearer \${AIDA_MCP_API_KEY}" aida ${shellQuote(url)}`,
  },
  {
    id: 'cursor',
    label: 'Cursor',
    description: 'Save as .cursor/mcp.json in the project (or merge with your existing mcpServers), then reload Cursor. Works for Cursor and Cursor CLI MCP discovery.',
    build: jsonConfig,
  },
  {
    id: 'claude-desktop',
    label: 'Claude Desktop',
    description: 'Merge mcpServers into claude_desktop_config.json and restart Claude Desktop. Remote HTTP MCP support depends on your Desktop version.',
    build: jsonConfig,
  },
  {
    id: 'generic',
    label: 'Generic MCP',
    description: 'For a client that supports Streamable HTTP MCP and an Authorization header. No client-specific support is implied.',
    build: jsonConfig,
  },
];

export function getMcpClientAdapter(id) {
  return MCP_CLIENT_ADAPTERS.find((adapter) => adapter.id === id) || MCP_CLIENT_ADAPTERS[0];
}

export function buildClientSnippet(id, url, token) {
  return getMcpClientAdapter(id).build(url, token);
}

export function resolveMcpUrl(policy, {
  configuredUrl = '',
  port = '8000',
  location = window.location,
} = {}) {
  if (configuredUrl) return configuredUrl.replace(/\/$/, '');
  const hostname = policy === 'localhost' ? 'localhost' : location.hostname;
  const host = hostname.includes(':') && !hostname.startsWith('[') ? `[${hostname}]` : hostname;
  const protocol = location.protocol === 'https:' ? 'https:' : 'http:';
  return `${protocol}//${host}:${port}/mcp`;
}
