import { utcDate } from '../../utils/utcDate';
import { useState, useMemo } from 'react';
import { Terminal, Check, X, Clock, ChevronDown, ChevronRight, Copy, Search } from '../icons';

const CommandHistory = ({ commands }) => {
  const [expandedCommands, setExpandedCommands] = useState(new Set());
  const [filter, setFilter] = useState('all'); // all, success, failed
  const [searchTerm, setSearchTerm] = useState('');
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);

  const toggleCommand = (id) => {
    const newSet = new Set(expandedCommands);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setExpandedCommands(newSet);
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const filteredCommands = useMemo(() => {
    let filtered = commands.filter(cmd => {
      if (filter === 'success') return cmd.success;
      if (filter === 'failed') return !cmd.success;
      return true;
    });

    if (searchTerm) {
      filtered = filtered.filter(cmd =>
        cmd.command.toLowerCase().includes(searchTerm.toLowerCase()) ||
        cmd.phase?.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    return filtered;
  }, [commands, filter, searchTerm]);

  // Pagination
  const totalPages = Math.ceil(filteredCommands.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedCommands = filteredCommands.slice(startIndex, startIndex + itemsPerPage);

  const stats = {
    total: commands.length,
    success: commands.filter(c => c.success).length,
    failed: commands.filter(c => !c.success).length,
    avgTime: commands.reduce((acc, c) => acc + (c.execution_time || 0), 0) / commands.length || 0
  };

  if (commands.length === 0) {
    return (
      <div className="py-8 text-center">
        <Terminal className="w-8 h-8 mx-auto text-gray-300 dark:text-neutral-600 mb-3" />
        <h3 className="text-sm font-medium text-gray-900 dark:text-neutral-100 mb-1">No Commands Yet</h3>
        <p className="text-xs text-gray-500 dark:text-neutral-400">
          Commands will appear here once you start executing them via Claude
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header compact avec contrôles */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 dark:text-neutral-400">
            {stats.total} total • {stats.success} success • {stats.failed} failed
          </span>
        </div>

        {/* Contrôles compacts */}
        <div className="flex items-center gap-2">
          {/* Recherche */}
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2 top-1/2 transform -translate-y-1/2 text-gray-400 dark:text-neutral-500" />
            <input
              type="text"
              placeholder="Search commands..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-7 pr-3 py-1 text-xs border border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-gray-900 dark:text-neutral-100 placeholder-gray-400 dark:placeholder-neutral-500 rounded w-32 focus:outline-none focus:border-gray-300 dark:focus:border-neutral-600"
            />
          </div>

          {/* Filtres compacts */}
          <div className="flex gap-1">
            {[
              { key: 'all', label: 'All', count: stats.total },
              { key: 'success', label: '✓', count: stats.success },
              { key: 'failed', label: '✗', count: stats.failed },
            ].map(({ key, label, count }) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-2 py-1 text-xs rounded border transition-colors ${filter === key
                  ? 'bg-blue-500 text-white border-blue-500'
                  : 'bg-white dark:bg-neutral-900 text-gray-600 dark:text-neutral-300 border-gray-200 dark:border-neutral-700 hover:border-gray-300 dark:hover:border-neutral-600'
                  }`}
                title={`${label} (${count})`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Commands List Compact */}
      <div className="space-y-1">
        {paginatedCommands.map((cmd) => {
          const isExpanded = expandedCommands.has(cmd.id);

          return (
            <div key={cmd.id} id={`command-${cmd.id}`} className="border border-gray-200 dark:border-neutral-700 rounded bg-white dark:bg-neutral-900 hover:border-gray-300 dark:hover:border-neutral-600 transition-colors">
              {/* Command Header Compact */}
              <div
                onClick={() => toggleCommand(cmd.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleCommand(cmd.id); }}
                className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-gray-50 dark:hover:bg-neutral-800 transition-colors cursor-pointer"
              >
                {/* Status Indicator */}
                <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cmd.success ? 'bg-green-500' : 'bg-red-500'
                  }`} />

                {/* Command */}
                <div className="flex-1 min-w-0">
                  {cmd.command_type === 'python' ? (
                    <span className="inline-flex items-center gap-1.5 min-w-0">
                      <span className="flex-shrink-0 px-1.5 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 rounded font-mono">python</span>
                      <code className="text-xs font-mono text-gray-500 dark:text-neutral-400 truncate">
                        {(cmd.source_code?.split('\n').find(l => l.trim()) || 'python script').slice(0, 60)}
                      </code>
                    </span>
                  ) : cmd.command_type === 'http' ? (
                    <span className="inline-flex items-center gap-1.5 min-w-0">
                      <span className="flex-shrink-0 px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded font-mono">http</span>
                      <code className="text-xs font-mono text-gray-500 dark:text-neutral-400 truncate">
                        {cmd.command?.length > 60 ? cmd.command.substring(0, 60) + '...' : cmd.command}
                      </code>
                    </span>
                  ) : (
                    <code className="text-xs font-mono text-gray-900 dark:text-neutral-100 break-all">
                      {cmd.command}
                    </code>
                  )}
                </div>

                {/* Metadata Compact */}
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-neutral-400 flex-shrink-0">
                  {cmd.execution_time && (
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {cmd.execution_time.toFixed(1)}s
                    </span>
                  )}
                  {cmd.phase && (
                    <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-neutral-800 text-gray-700 dark:text-neutral-300 rounded text-xs">
                      {cmd.phase.replace('Phase ', 'P')}
                    </span>
                  )}
                  <span>{utcDate(cmd.created_at).toLocaleTimeString()}</span>
                </div>

                {/* Status, Copy & Expand */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  {/* Copy Button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation(); // Prevent expanding when copying
                      copyToClipboard(cmd.command);
                    }}
                    className="p-1 hover:bg-gray-200 dark:hover:bg-neutral-700 rounded text-gray-400 dark:text-neutral-500 hover:text-gray-600 dark:hover:text-neutral-300 transition-colors"
                    title="Copy command"
                  >
                    <Copy className="w-3 h-3" />
                  </button>

                  {/* Status */}
                  {cmd.success ? (
                    <Check className="w-3 h-3 text-green-600" />
                  ) : (
                    <X className="w-3 h-3 text-red-600" />
                  )}

                  {/* Expand */}
                  {isExpanded ? (
                    <ChevronDown className="w-3 h-3 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-3 h-3 text-gray-400" />
                  )}
                </div>
              </div>

              {/* Expanded Content Compact */}
              {isExpanded && (
                <div className="px-3 pb-3 border-t border-gray-100 dark:border-neutral-800 bg-gray-50/30 dark:bg-neutral-900/30">
                  <div className="pt-2 space-y-2">
                    {/* Python source code block */}
                    {cmd.command_type === 'python' && cmd.source_code && (
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                            Python Code
                          </h4>
                          <button
                            onClick={() => copyToClipboard(cmd.source_code)}
                            className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 px-1.5 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-neutral-800 transition-colors"
                          >
                            <Copy className="w-3 h-3" />
                            Copy
                          </button>
                        </div>
                        <pre className="bg-gray-900 dark:bg-black text-emerald-300 p-2 rounded font-mono text-xs max-h-48 overflow-auto whitespace-pre-wrap">
                          {cmd.source_code}
                        </pre>
                      </div>
                    )}

                    {/* HTTP generated script block */}
                    {cmd.command_type === 'http' && cmd.source_code && (
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="text-xs font-semibold text-blue-700 dark:text-blue-400 flex items-center gap-1">
                            HTTP Script
                          </h4>
                          <button
                            onClick={() => copyToClipboard(cmd.source_code)}
                            className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 px-1.5 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-neutral-800 transition-colors"
                          >
                            <Copy className="w-3 h-3" />
                            Copy
                          </button>
                        </div>
                        <pre className="bg-gray-900 dark:bg-black text-blue-300 p-2 rounded font-mono text-xs max-h-48 overflow-auto whitespace-pre-wrap">
                          {cmd.source_code}
                        </pre>
                      </div>
                    )}

                    {/* Output Compact */}
                    {cmd.stdout && (
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="text-xs font-semibold text-gray-700 dark:text-neutral-300">Output</h4>
                          <button
                            onClick={() => copyToClipboard(cmd.stdout)}
                            className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 px-1.5 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-neutral-800 transition-colors"
                          >
                            <Copy className="w-3 h-3" />
                            Copy
                          </button>
                        </div>
                        <pre className="bg-gray-900 dark:bg-black text-gray-100 dark:text-neutral-200 p-2 rounded font-mono text-xs max-h-32 overflow-auto whitespace-pre-wrap">
                          {cmd.stdout}
                        </pre>
                      </div>
                    )}

                    {/* Error Output Compact */}
                    {cmd.stderr && (
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <h4 className="text-xs font-semibold text-red-700 dark:text-red-400">Error</h4>
                          <button
                            onClick={() => copyToClipboard(cmd.stderr)}
                            className="flex items-center gap-1 text-xs text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 px-1.5 py-0.5 rounded hover:bg-gray-200 dark:hover:bg-neutral-800 transition-colors"
                          >
                            <Copy className="w-3 h-3" />
                            Copy
                          </button>
                        </div>
                        <pre className="bg-red-900 dark:bg-red-950 text-red-100 dark:text-red-200 p-2 rounded font-mono text-xs max-h-32 overflow-auto whitespace-pre-wrap">
                          {cmd.stderr}
                        </pre>
                      </div>
                    )}

                    {/* Command Details Compact */}
                    <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-neutral-400 pt-1 border-t border-gray-200 dark:border-neutral-800">
                      <span>Code: {cmd.returncode}</span>
                      {cmd.container_name && <span>Container: {cmd.container_name}</span>}
                      <span>{utcDate(cmd.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pagination et contrôles */}
      {filteredCommands.length > 0 && (
        <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-neutral-700">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-neutral-400">
            <span>Showing {startIndex + 1}-{Math.min(startIndex + itemsPerPage, filteredCommands.length)} of {filteredCommands.length}</span>
            {stats.avgTime > 0 && (
              <span>• Avg time: {stats.avgTime.toFixed(1)}s</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Items per page */}
            <select
              value={itemsPerPage}
              onChange={(e) => {
                setItemsPerPage(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="text-xs border border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-gray-900 dark:text-neutral-100 rounded px-2 py-1"
            >
              <option value={10}>10/page</option>
              <option value={20}>20/page</option>
              <option value={50}>50/page</option>
              <option value={100}>100/page</option>
            </select>

            {/* Pagination */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className="px-2 py-1 text-xs border border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-gray-900 dark:text-neutral-100 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-neutral-800"
              >
                ←
              </button>

              <span className="px-2 py-1 text-xs text-gray-600 dark:text-neutral-300">
                {currentPage} / {totalPages}
              </span>

              <button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className="px-2 py-1 text-xs border border-gray-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-gray-900 dark:text-neutral-100 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50 dark:hover:bg-neutral-800"
              >
                →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CommandHistory;
