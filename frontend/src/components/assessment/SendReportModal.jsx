import { useState, useEffect } from 'react';
import { X, Send, CheckCircle, AlertCircle, MessageSquare, Mail, Hash, FileText } from 'lucide-react';
import notificationService from '../../services/notificationService';

const CHANNELS = [
  { id: 'telegram', label: 'Telegram', icon: MessageSquare, color: 'bg-blue-500' },
  { id: 'slack', label: 'Slack', icon: Hash, color: 'bg-purple-500' },
  { id: 'email', label: 'Email', icon: Mail, color: 'bg-red-500' },
];

export default function SendReportModal({ assessmentId, assessmentName, onClose }) {
  const [configs, setConfigs] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState('');
  const [customMessage, setCustomMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadConfigs();
  }, []);

  const loadConfigs = async () => {
    setLoading(true);
    try {
      const data = await notificationService.listConfigs();
      setConfigs(data);
      const enabled = data.find(c => c.enabled);
      if (enabled) setSelectedChannel(enabled.channel);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const getChannelStatus = (channelId) => {
    const cfg = configs.find(c => c.channel === channelId);
    if (!cfg) return 'not_configured';
    if (!cfg.enabled) return 'disabled';
    return 'ready';
  };

  const handleSend = async () => {
    if (!selectedChannel) return;
    setSending(true);
    setResult(null);
    try {
      const res = await notificationService.sendReport(assessmentId, {
        channel: selectedChannel,
        custom_message: customMessage || undefined,
      });
      setResult(res);
    } catch (e) {
      setResult({ success: false, message: e.response?.data?.detail || 'Failed to send' });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-md bg-white dark:bg-neutral-800 rounded-xl shadow-2xl border border-neutral-200 dark:border-neutral-700 overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-200 dark:border-neutral-700">
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Send PDF Report</h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{assessmentName}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700">
            <X className="w-4 h-4 text-neutral-400" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* PDF info */}
          <div className="flex items-center gap-3 px-3 py-2.5 bg-neutral-50 dark:bg-neutral-900 rounded-lg border border-neutral-200 dark:border-neutral-700">
            <FileText className="w-8 h-8 text-red-500 shrink-0" />
            <div>
              <p className="text-xs font-medium text-neutral-900 dark:text-neutral-100">AIDA_Report_{assessmentName.replace(/[^a-zA-Z0-9]/g, '_')}.pdf</p>
              <p className="text-[10px] text-neutral-500 dark:text-neutral-400 mt-0.5">Full PDF report with findings, statistics, recon data, and methodology</p>
            </div>
          </div>

          {/* Channel selection */}
          <div>
            <label className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">Send via</label>
            <div className="flex gap-2 mt-2">
              {CHANNELS.map(ch => {
                const status = getChannelStatus(ch.id);
                const Icon = ch.icon;
                const isSelected = selectedChannel === ch.id;
                const isAvailable = status === 'ready';

                return (
                  <button
                    key={ch.id}
                    onClick={() => isAvailable && setSelectedChannel(ch.id)}
                    disabled={!isAvailable}
                    className={`flex-1 flex flex-col items-center gap-1.5 px-3 py-3 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                        : isAvailable
                          ? 'border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600'
                          : 'border-neutral-100 dark:border-neutral-800 opacity-40 cursor-not-allowed'
                    }`}
                  >
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${isSelected ? ch.color : 'bg-neutral-200 dark:bg-neutral-700'} text-white`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">{ch.label}</span>
                    <span className={`text-[9px] ${
                      status === 'ready' ? 'text-green-600 dark:text-green-400' :
                      status === 'disabled' ? 'text-yellow-600 dark:text-yellow-400' :
                      'text-neutral-400'
                    }`}>
                      {status === 'ready' ? 'Ready' : status === 'disabled' ? 'Disabled' : 'Not configured'}
                    </span>
                  </button>
                );
              })}
            </div>
            {!configs.some(c => c.enabled) && !loading && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                No channels configured. Go to Settings &rarr; Notifications to set up a channel.
              </p>
            )}
            {selectedChannel === 'slack' && (
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
                Slack webhooks don't support file attachments. A notification with a link will be sent instead.
              </p>
            )}
          </div>

          {/* Custom message */}
          <div>
            <label className="text-[10px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">Message (optional)</label>
            <textarea
              value={customMessage}
              onChange={e => setCustomMessage(e.target.value)}
              placeholder="Add a note..."
              rows={2}
              className="mt-1 w-full text-sm px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 resize-none"
            />
          </div>

          {/* Result */}
          {result && (
            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
              result.success
                ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
            }`}>
              {result.success ? <CheckCircle className="w-3.5 h-3.5 shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 shrink-0" />}
              <span>{result.message}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-neutral-200 dark:border-neutral-700 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={!selectedChannel || sending}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-3.5 h-3.5" />
            {sending ? 'Generating PDF...' : 'Send PDF'}
          </button>
        </div>
      </div>
    </div>
  );
}
