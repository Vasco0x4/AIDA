import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Terminal, Shield, Eye, Target, AlertCircle, ChevronDown, ChevronUp, Loader2, Settings, X } from 'lucide-react';
import apiClient from '../../services/api';

const TOOL_ICONS = {
  execute_command: Terminal,
  add_finding: Shield,
  add_observation: Eye,
  add_recon_data: Target,
};

const SEVERITY_COLORS = {
  CRITICAL: 'text-red-500',
  HIGH: 'text-orange-500',
  MEDIUM: 'text-yellow-500',
  LOW: 'text-blue-500',
  INFO: 'text-neutral-400',
};

function ToolCallCard({ call }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = TOOL_ICONS[call.tool] || Terminal;

  return (
    <div className="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-neutral-50 dark:bg-neutral-900 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
      >
        <Icon className="w-3.5 h-3.5 text-primary-500 shrink-0" />
        <span className="font-mono font-medium text-neutral-700 dark:text-neutral-300">{call.tool}</span>
        {call.tool === 'execute_command' && (
          <span className="font-mono text-neutral-500 truncate flex-1 text-left">
            {call.input?.command?.slice(0, 60)}
          </span>
        )}
        {call.tool === 'add_finding' && (
          <span className={`font-semibold ${SEVERITY_COLORS[call.input?.severity] || ''}`}>
            [{call.input?.severity}] {call.input?.title?.slice(0, 40)}
          </span>
        )}
        <span className="shrink-0">
          {expanded ? <ChevronUp className="w-3 h-3 text-neutral-400" /> : <ChevronDown className="w-3 h-3 text-neutral-400" />}
        </span>
      </button>
      {expanded && (
        <div className="px-3 py-2 space-y-2 bg-white dark:bg-neutral-800">
          <div>
            <span className="text-[10px] font-semibold text-neutral-500 uppercase">Input</span>
            <pre className="mt-1 text-[11px] font-mono text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap bg-neutral-50 dark:bg-neutral-900 p-2 rounded max-h-32 overflow-y-auto">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          {call.output && (
            <div>
              <span className="text-[10px] font-semibold text-neutral-500 uppercase">Output</span>
              <pre className="mt-1 text-[11px] font-mono text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap bg-neutral-50 dark:bg-neutral-900 p-2 rounded max-h-48 overflow-y-auto">
                {call.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AIChatPanel({ assessmentId, assessmentName }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [hasKey, setHasKey] = useState(null);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    checkAIConfig();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const checkAIConfig = async () => {
    try {
      const { data } = await apiClient.get('/ai/config');
      setHasKey(data.has_key);
    } catch {
      setHasKey(false);
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    setError(null);
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setLoading(true);

    try {
      const { data } = await apiClient.post('/ai/chat', {
        assessment_id: assessmentId,
        message: text,
      });

      if (data.error) {
        setError(data.error);
      }

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        tool_calls: data.tool_calls || [],
      }]);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to send message');
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '',
        error: e.response?.data?.detail || 'Failed to communicate with AI',
      }]);
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Floating button when closed
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-primary-600 hover:bg-primary-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-105 z-40"
        title="AI Assistant"
      >
        <Bot className="w-6 h-6" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 w-[440px] h-[600px] bg-white dark:bg-neutral-800 rounded-xl shadow-2xl border border-neutral-200 dark:border-neutral-700 flex flex-col z-40 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-700 bg-primary-600 text-white">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5" />
          <div>
            <h3 className="text-sm font-semibold">AIDA AI</h3>
            <p className="text-[10px] opacity-75">{assessmentName}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setMessages([])} className="p-1 rounded hover:bg-white/20" title="Clear chat">
            <Terminal className="w-4 h-4" />
          </button>
          <button onClick={() => setIsOpen(false)} className="p-1 rounded hover:bg-white/20">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {!hasKey && (
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg text-xs text-amber-700 dark:text-amber-400">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>API key not configured. Go to <strong>Settings &gt; AI</strong> to set up your Anthropic API key.</span>
          </div>
        )}

        {messages.length === 0 && hasKey && (
          <div className="text-center py-8">
            <Bot className="w-10 h-10 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
            <p className="text-sm font-medium text-neutral-600 dark:text-neutral-400">AI Security Assistant</p>
            <p className="text-xs text-neutral-500 dark:text-neutral-500 mt-1 max-w-xs mx-auto">
              Tell me what to scan or investigate. I'll execute commands, analyze results, and document findings.
            </p>
            <div className="flex flex-wrap gap-1.5 justify-center mt-4">
              {[
                'Run a full port scan',
                'Check for web vulnerabilities',
                'Enumerate subdomains',
                'Test for SQL injection',
              ].map(suggestion => (
                <button
                  key={suggestion}
                  onClick={() => { setInput(suggestion); setTimeout(() => inputRef.current?.focus(), 50); }}
                  className="px-2.5 py-1 text-[11px] bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded-full hover:bg-primary-100 dark:hover:bg-primary-900/30 hover:text-primary-700 dark:hover:text-primary-400 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="w-4 h-4 text-primary-600 dark:text-primary-400" />
              </div>
            )}
            <div className={`max-w-[85%] ${msg.role === 'user' ? 'order-first' : ''}`}>
              {msg.role === 'user' ? (
                <div className="bg-primary-600 text-white px-3 py-2 rounded-lg rounded-br-sm text-sm">
                  {msg.content}
                </div>
              ) : (
                <div className="space-y-2">
                  {msg.error && (
                    <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-red-50 dark:bg-red-900/20 rounded-lg text-xs text-red-600 dark:text-red-400">
                      <AlertCircle className="w-3 h-3 shrink-0" />
                      {msg.error}
                    </div>
                  )}
                  {msg.tool_calls?.length > 0 && (
                    <div className="space-y-1.5">
                      {msg.tool_calls.map((call, i) => (
                        <ToolCallCard key={i} call={call} />
                      ))}
                    </div>
                  )}
                  {msg.content && (
                    <div className="bg-neutral-100 dark:bg-neutral-700 px-3 py-2 rounded-lg rounded-bl-sm text-sm text-neutral-800 dark:text-neutral-200 whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  )}
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-neutral-200 dark:bg-neutral-600 flex items-center justify-center shrink-0 mt-0.5">
                <User className="w-4 h-4 text-neutral-600 dark:text-neutral-300" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-2.5">
            <div className="w-7 h-7 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-primary-600 dark:text-primary-400" />
            </div>
            <div className="bg-neutral-100 dark:bg-neutral-700 px-3 py-2 rounded-lg text-sm text-neutral-500 flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Thinking & executing...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-neutral-200 dark:border-neutral-700">
        {error && (
          <div className="mb-2 text-[10px] text-red-500 truncate">{error}</div>
        )}
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hasKey ? "Scan this target for vulnerabilities..." : "Configure API key first..."}
            disabled={!hasKey || loading}
            rows={1}
            className="flex-1 text-sm px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 resize-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading || !hasKey}
            className="px-3 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
