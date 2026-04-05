import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Search, Command, X, FileText, Terminal, Shield, Eye, Info, Target, Clock, Filter as FilterIcon } from '../icons';
import searchService from '../../services/searchService';

const SEVERITY_OPTIONS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const STATUS_OPTIONS = ['confirmed', 'potential', 'untested'];
const SEVERITY_COLORS = {
  CRITICAL: 'bg-red-500 text-white',
  HIGH: 'bg-orange-500 text-white',
  MEDIUM: 'bg-yellow-500 text-white',
  LOW: 'bg-blue-500 text-white',
  INFO: 'bg-neutral-400 text-white',
};

const GlobalSearch = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [groupedResults, setGroupedResults] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeFilter, setActiveFilter] = useState('all'); // 'all', 'assessment', 'command', 'finding', 'recon'
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [filterSeverity, setFilterSeverity] = useState([]);
  const [filterStatus, setFilterStatus] = useState([]);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [searchMeta, setSearchMeta] = useState({ total: 0, execution_time: 0 });
  const navigate = useNavigate();
  const location = useLocation();
  const inputRef = useRef(null);
  const resultsContainerRef = useRef(null);
  const selectedItemRef = useRef(null);
  const modalRef = useRef(null); // For click outside detection

  // Close search completely
  const handleClose = useCallback(() => {
    setIsOpen(false);
    setQuery('');
    setResults([]);
    setGroupedResults({});
    setSelectedIndex(0);
    setActiveFilter('all');
    setShowAdvanced(false);
    setFilterSeverity([]);
    setFilterStatus([]);
    setDateFrom('');
    setDateTo('');
  }, []);

  // Close on route change
  useEffect(() => {
    handleClose();
  }, [location.pathname, handleClose]);

  // Click outside to close
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event) => {
      if (modalRef.current && !modalRef.current.contains(event.target)) {
        handleClose();
      }
    };

    // Use mousedown instead of click for better UX
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, handleClose]);

  // Open with Ctrl+K or Cmd+K
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape') {
        handleClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Search with debounce
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setGroupedResults({});
      setSearchMeta({ total: 0, execution_time: 0 });
      return;
    }

    const timeoutId = setTimeout(async () => {
      setIsLoading(true);
      try {
        const hasAdvancedFilters = filterSeverity.length > 0 || filterStatus.length > 0 || dateFrom || dateTo;

        if (hasAdvancedFilters || activeFilter !== 'all') {
          // Use advanced search with filters
          const data = await searchService.searchAdvanced(query, {
            types: activeFilter !== 'all' ? [activeFilter] : undefined,
            severity: filterSeverity.length > 0 ? filterSeverity : undefined,
            status: filterStatus.length > 0 ? filterStatus : undefined,
            dateFrom: dateFrom || undefined,
            dateTo: dateTo || undefined,
          });
          const searchResults = data.results || [];
          setResults(searchResults);
          setSearchMeta({ total: data.total || 0, execution_time: data.execution_time || 0 });

          const grouped = searchResults.reduce((acc, result) => {
            const type = result.type;
            if (!acc[type]) acc[type] = [];
            acc[type].push(result);
            return acc;
          }, {});
          setGroupedResults(grouped);
        } else {
          const searchResults = await searchService.searchAll(query);
          setResults(searchResults);
          setSearchMeta({ total: searchResults.length, execution_time: 0 });

          const grouped = searchResults.reduce((acc, result) => {
            const type = result.type;
            if (!acc[type]) acc[type] = [];
            acc[type].push(result);
            return acc;
          }, {});
          setGroupedResults(grouped);
        }

        setSelectedIndex(0);
      } catch (error) {
        console.error('Search error:', error);
        setResults([]);
        setGroupedResults({});
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [query, activeFilter, filterSeverity, filterStatus, dateFrom, dateTo]);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (results[selectedIndex]) {
          handleResultClick(results[selectedIndex]);
        }
      } else if (e.key === 'Escape') {
        handleClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex]);

  // Auto-scroll to selected item
  useEffect(() => {
    if (selectedItemRef.current && resultsContainerRef.current) {
      const container = resultsContainerRef.current;
      const selectedItem = selectedItemRef.current;

      const containerRect = container.getBoundingClientRect();
      const itemRect = selectedItem.getBoundingClientRect();

      const isVisible = itemRect.top >= containerRect.top && itemRect.bottom <= containerRect.bottom;

      if (!isVisible) {
        const scrollTop = selectedItem.offsetTop - container.offsetTop - (container.clientHeight / 2) + (itemRect.height / 2);
        container.scrollTo({
          top: Math.max(0, scrollTop),
          behavior: 'smooth'
        });
      }
    }
  }, [selectedIndex, results]);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  const getIcon = (type) => {
    switch (type) {
      case 'assessment': return FileText;
      case 'command': return Terminal;
      case 'finding': return Shield;
      case 'observation': return Eye;
      case 'info': return Info;
      case 'recon': return Target;
      default: return Search;
    }
  };

  const getTypeLabel = (type) => {
    const labels = {
      assessment: 'Assessments',
      command: 'Commands',
      finding: 'Findings',
      observation: 'Observations',
      info: 'Information',
      recon: 'Recon Data'
    };
    return labels[type] || type;
  };

  const getTypeColor = (type) => {
    const colors = {
      assessment: 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20',
      command: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20',
      finding: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20',
      observation: 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20',
      info: 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-900/20',
      recon: 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20'
    };
    return colors[type] || 'text-neutral-600 dark:text-neutral-400 bg-neutral-50 dark:bg-neutral-800';
  };

  const handleResultClick = (result) => {
    navigate(result.url);

    // Handle anchor scrolling
    setTimeout(() => {
      const hash = result.url.split('#')[1];
      if (hash) {
        const element = document.getElementById(hash);
        if (element) {
          element.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
            inline: 'nearest'
          });

          // Highlight effect
          element.style.transition = 'background-color 0.3s ease';
          element.style.backgroundColor = '#f0f9ff';
          setTimeout(() => {
            element.style.backgroundColor = '';
          }, 2000);
        }
      }
    }, 100);

    handleClose();
  };

  const filterOptions = [
    { value: 'all', label: 'All', icon: Search },
    { value: 'assessment', label: 'Assessments', icon: FileText },
    { value: 'command', label: 'Commands', icon: Terminal },
    { value: 'finding', label: 'Findings', icon: Shield },
    { value: 'recon', label: 'Recon', icon: Target }
  ];

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="w-full max-w-md flex items-center gap-3 px-4 py-2 bg-neutral-50 dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded-lg text-sm text-neutral-500 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-neutral-500 hover:bg-white dark:hover:bg-neutral-600 transition-all"
      >
        <Search className="w-4 h-4" />
        <span>Search assessments, commands...</span>
        <kbd className="ml-auto px-2 py-0.5 bg-white dark:bg-neutral-600 border border-neutral-200 dark:border-neutral-500 dark:text-neutral-200 rounded text-xs font-mono">
          <Command className="w-3 h-3 inline" />K
        </kbd>
      </button>
    );
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 dark:bg-black/50 backdrop-blur-sm z-50 animate-in fade-in duration-200"
        onClick={(e) => {
          e.stopPropagation();
          handleClose();
        }}
      />

      {/* Search modal */}
      <div ref={modalRef} className="fixed top-20 left-1/2 -translate-x-1/2 w-full max-w-2xl z-[60] animate-in slide-in-from-top-4 duration-300">
        <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
          {/* Search input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
            <Search className="w-5 h-5 text-neutral-400 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search assessments, commands, findings... (fuzzy search enabled)"
              className="flex-1 bg-transparent outline-none text-sm dark:text-neutral-100 dark:placeholder:text-neutral-400"
              autoFocus
            />
            {isLoading && (
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-neutral-300 border-t-primary-600"></div>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleClose();
              }}
              className="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded transition-colors"
            >
              <X className="w-4 h-4 text-neutral-400" />
            </button>
          </div>

          {/* Filter chips */}
          <div className="px-3 py-2 bg-neutral-50 dark:bg-neutral-900/50 border-b border-neutral-200 dark:border-neutral-700 flex items-center gap-2 overflow-x-auto">
            {filterOptions.map(option => {
              const Icon = option.icon;
              const isActive = activeFilter === option.value;
              return (
                <button
                  key={option.value}
                  onClick={() => setActiveFilter(option.value)}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all whitespace-nowrap ${isActive
                    ? 'bg-primary-600 text-white shadow-sm'
                    : 'bg-white dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-600 border border-neutral-200 dark:border-neutral-600'
                    }`}
                >
                  <Icon className="w-3 h-3" />
                  {option.label}
                </button>
              );
            })}
            <div className="flex-1" />
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium transition-all whitespace-nowrap ${showAdvanced
                ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              <FilterIcon className="w-3 h-3" />
              Filters
              {(filterSeverity.length > 0 || filterStatus.length > 0 || dateFrom || dateTo) && (
                <span className="w-1.5 h-1.5 rounded-full bg-primary-500" />
              )}
            </button>
          </div>

          {/* Advanced filters panel */}
          {showAdvanced && (
            <div className="px-4 py-3 bg-neutral-50 dark:bg-neutral-900/50 border-b border-neutral-200 dark:border-neutral-700 space-y-3">
              {/* Severity */}
              <div>
                <label className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">Severity</label>
                <div className="flex gap-1.5 mt-1 flex-wrap">
                  {SEVERITY_OPTIONS.map(sev => (
                    <button
                      key={sev}
                      onClick={() => setFilterSeverity(prev => prev.includes(sev) ? prev.filter(s => s !== sev) : [...prev, sev])}
                      className={`px-2 py-0.5 text-[10px] font-semibold rounded transition-colors ${
                        filterSeverity.includes(sev)
                          ? SEVERITY_COLORS[sev]
                          : 'bg-white dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-600'
                      }`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>

              {/* Status */}
              <div>
                <label className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">Status</label>
                <div className="flex gap-1.5 mt-1 flex-wrap">
                  {STATUS_OPTIONS.map(st => (
                    <button
                      key={st}
                      onClick={() => setFilterStatus(prev => prev.includes(st) ? prev.filter(s => s !== st) : [...prev, st])}
                      className={`px-2 py-0.5 text-[10px] font-medium rounded capitalize transition-colors ${
                        filterStatus.includes(st)
                          ? 'bg-primary-500 text-white'
                          : 'bg-white dark:bg-neutral-700 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-600'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>

              {/* Date range */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">From</label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={e => setDateFrom(e.target.value)}
                    className="mt-1 w-full text-xs px-2 py-1.5 rounded border border-neutral-200 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[10px] font-semibold text-neutral-500 uppercase tracking-wider">To</label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={e => setDateTo(e.target.value)}
                    className="mt-1 w-full text-xs px-2 py-1.5 rounded border border-neutral-200 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300"
                  />
                </div>
              </div>

              {/* Clear filters */}
              {(filterSeverity.length > 0 || filterStatus.length > 0 || dateFrom || dateTo) && (
                <button
                  onClick={() => { setFilterSeverity([]); setFilterStatus([]); setDateFrom(''); setDateTo(''); }}
                  className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                >
                  Clear all filters
                </button>
              )}
            </div>
          )}

          {/* Results */}
          <div ref={resultsContainerRef} className="max-h-96 overflow-y-auto">
            {query.length === 0 ? (
              <div className="px-4 py-12 text-center text-sm text-neutral-500 dark:text-neutral-400">
                <Search className="w-8 h-8 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
                <p className="font-medium mb-1">Start typing to search</p>
                <p className="text-xs">Search across all assessments, commands, findings, and recon data</p>
              </div>
            ) : isLoading ? (
              <div className="px-4 py-12 text-center text-sm text-neutral-500 dark:text-neutral-400">
                <div className="animate-spin w-6 h-6 border-2 border-neutral-300 border-t-primary-600 rounded-full mx-auto mb-3"></div>
                <p>Searching...</p>
              </div>
            ) : results.length === 0 ? (
              <div className="px-4 py-12 text-center text-sm text-neutral-500 dark:text-neutral-400">
                <Search className="w-8 h-8 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
                <p className="font-medium mb-1">No results found</p>
                <p className="text-xs">Try different keywords or check your filters</p>
              </div>
            ) : (
              <div className="p-2">
                {/* Grouped results */}
                {Object.entries(groupedResults).map(([type, groupResults], groupIndex) => (
                  <div key={type} className={groupIndex > 0 ? 'mt-4' : ''}>
                    {/* Group header */}
                    <div className={`flex items-center gap-2 px-3 py-1.5 mb-1 ${getTypeColor(type)} rounded-lg`}>
                      {(() => {
                        const Icon = getIcon(type);
                        return <Icon className="w-3.5 h-3.5" />;
                      })()}
                      <span className="text-xs font-semibold uppercase tracking-wide">
                        {getTypeLabel(type)} ({groupResults.length})
                      </span>
                    </div>

                    {/* Group items */}
                    <div className="space-y-1">
                      {groupResults.map((result, index) => {
                        const IconComponent = getIcon(result.type);
                        const globalIndex = results.indexOf(result);
                        const isSelected = globalIndex === selectedIndex;

                        return (
                          <button
                            key={`${result.type}-${result.id}`}
                            ref={isSelected ? selectedItemRef : null}
                            onClick={() => handleResultClick(result)}
                            className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-150 ${isSelected
                              ? 'bg-primary-100/50 dark:bg-primary-900/20 border-2 border-primary-400 dark:border-primary-700 shadow-sm'
                              : 'hover:bg-neutral-50 dark:hover:bg-neutral-800'
                              }`}
                          >
                            <IconComponent className={`w-4 h-4 mt-0.5 flex-shrink-0 ${result.type === 'assessment' ? 'text-blue-500' :
                              result.type === 'command' ? 'text-green-500' :
                                result.type === 'finding' ? 'text-red-500' :
                                  result.type === 'observation' ? 'text-purple-500' :
                                    result.type === 'info' ? 'text-cyan-500' :
                                      result.type === 'recon' ? 'text-orange-500' :
                                        'text-neutral-400'
                              }`} />

                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium text-neutral-900 dark:text-neutral-100 truncate">
                                {result.title}
                              </div>
                              <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                                {result.subtitle}
                              </div>
                              {result.description && (
                                <div className="text-xs text-neutral-400 dark:text-neutral-500 mt-1 line-clamp-1">
                                  {result.description}
                                </div>
                              )}
                            </div>

                            {result.metadata && (
                              <div className="flex-shrink-0 text-xs">
                                {result.metadata.severity && (
                                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${result.metadata.severity === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                                    result.metadata.severity === 'HIGH' ? 'bg-orange-100 text-orange-700' :
                                      result.metadata.severity === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                                        result.metadata.severity === 'LOW' ? 'bg-green-100 text-green-700' :
                                          'bg-neutral-100 text-neutral-700'
                                    }`}>
                                    {result.metadata.severity}
                                  </span>
                                )}
                                {result.metadata.executionTime && (
                                  <div className="flex items-center gap-1 mt-1 text-neutral-400">
                                    <Clock className="w-3 h-3" />
                                    <span>{result.metadata.executionTime.toFixed(2)}s</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 bg-neutral-50 dark:bg-neutral-900/50 border-t border-neutral-200 dark:border-neutral-700 flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400">
            <div className="flex items-center gap-4">
              {searchMeta.total > 0 && (
                <span>{searchMeta.total} results{searchMeta.execution_time > 0 ? ` in ${searchMeta.execution_time}s` : ''}</span>
              )}
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 dark:text-neutral-200 rounded font-mono">↑↓</kbd>
                Navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-1.5 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 dark:text-neutral-200 rounded font-mono">↵</kbd>
                Select
              </span>
            </div>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 dark:text-neutral-200 rounded font-mono">ESC</kbd>
              Close
            </span>
          </div>
        </div>
      </div>
    </>
  );
};

export default GlobalSearch;
