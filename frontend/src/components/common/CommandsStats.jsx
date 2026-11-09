import { utcDate } from '../../utils/utcDate';
import React from 'react';
import { Terminal, Clock, CheckCircle, XCircle, TrendingUp, TrendingDown } from '../icons';

const CommandsStats = ({ commands = [], className = "" }) => {
  // Calculate command statistics
  const stats = React.useMemo(() => {
    const total = commands.length;
    const successful = commands.filter(c => c.success).length;
    const failed = total - successful;
    const successRate = total > 0 ? Math.round((successful / total) * 100) : 0;

    // Group by category
    const categories = commands.reduce((acc, cmd) => {
      const category = cmd.category || 'other';
      if (!acc[category]) {
        acc[category] = { total: 0, successful: 0, failed: 0 };
      }
      acc[category].total++;
      if (cmd.success) {
        acc[category].successful++;
      } else {
        acc[category].failed++;
      }
      return acc;
    }, {});

    // Calculate trends (last 7 days vs previous 7 days)
    const now = utcDate();
    const last7days = utcDate(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const last14days = utcDate(now.getTime() - 14 * 24 * 60 * 60 * 1000);

    const recentCommands = commands.filter(c => utcDate(c.created_at) > last7days).length;
    const previousCommands = commands.filter(c => {
      const date = utcDate(c.created_at);
      return date > last14days && date <= last7days;
    }).length;

    const trend = previousCommands > 0 
      ? Math.round(((recentCommands - previousCommands) / previousCommands) * 100)
      : recentCommands > 0 ? 100 : 0;

    return {
      total,
      successful,
      failed,
      successRate,
      categories,
      trend,
      recentCommands
    };
  }, [commands]);

  const categoryColors = {
    recon: { bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200' },
    exploitation: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200' },
    reporting: { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-200' },
    other: { bg: 'bg-neutral-100 dark:bg-neutral-700', text: 'text-neutral-700 dark:text-neutral-300', border: 'border-neutral-200 dark:border-neutral-700' }
  };

  return (
    <div className={`card ${className}`}>
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-neutral-900">Command Statistics</h3>
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5 text-neutral-400" />
          <span className="text-sm text-neutral-500">{stats.total} total</span>
        </div>
      </div>

      {/* Main Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="text-center p-4 bg-green-50 rounded-lg border border-green-200">
          <CheckCircle className="w-6 h-6 text-green-600 mx-auto mb-2" />
          <div className="text-2xl font-bold text-green-700">{stats.successful}</div>
          <div className="text-xs text-green-600">Successful</div>
        </div>
        
        <div className="text-center p-4 bg-red-50 rounded-lg border border-red-200">
          <XCircle className="w-6 h-6 text-red-600 mx-auto mb-2" />
          <div className="text-2xl font-bold text-red-700">{stats.failed}</div>
          <div className="text-xs text-red-600">Failed</div>
        </div>
        
        <div className="text-center p-4 bg-blue-50 rounded-lg border border-blue-200">
          <Clock className="w-6 h-6 text-blue-600 mx-auto mb-2" />
          <div className="text-2xl font-bold text-blue-700">{stats.successRate}%</div>
          <div className="text-xs text-blue-600">Success Rate</div>
        </div>
      </div>

      {/* Trend */}
      <div className="flex items-center justify-between mb-6 p-3 bg-neutral-50 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-neutral-700">Last 7 days</span>
          <span className="text-sm text-neutral-500">({stats.recentCommands} commands)</span>
        </div>
        <div className="flex items-center gap-1">
          {stats.trend >= 0 ? (
            <>
              <TrendingUp className="w-4 h-4 text-green-500" />
              <span className="text-sm font-medium text-green-600">+{stats.trend}%</span>
            </>
          ) : (
            <>
              <TrendingDown className="w-4 h-4 text-red-500" />
              <span className="text-sm font-medium text-red-600">{stats.trend}%</span>
            </>
          )}
        </div>
      </div>

      {/* Categories */}
      <div>
        <h4 className="text-sm font-semibold text-neutral-700 mb-3">By Category</h4>
        <div className="space-y-2">
          {Object.entries(stats.categories).map(([category, data]) => {
            const colors = categoryColors[category] || categoryColors.other;
            const successRate = data.total > 0 ? Math.round((data.successful / data.total) * 100) : 0;
            
            return (
              <div key={category} className="flex items-center justify-between p-3 rounded-lg border">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${colors.bg}`}></div>
                  <span className="text-sm font-medium text-neutral-700 capitalize">{category}</span>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-sm text-neutral-600">
                    {data.successful}/{data.total}
                  </div>
                  <div className="text-sm font-medium text-neutral-900">
                    {successRate}%
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default CommandsStats;



