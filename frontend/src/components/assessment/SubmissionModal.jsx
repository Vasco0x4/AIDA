import { useEffect, useState } from 'react';
import { X, Copy, Check, Loader2, FileText, ExternalLink, Download, AlertCircle, Send } from '../icons';
import submissionService from '../../services/submissionService';

/**
 * SubmissionModal — generate a submission-ready bug-bounty report for a finding,
 * grounded in disclosed precedent from the knowledge base. Pick a platform,
 * generate, then copy or save the Markdown as evidence.
 */
export default function SubmissionModal({ isOpen, onClose, card, onSaved }) {
  const [platforms, setPlatforms] = useState([{ id: 'hackerone', label: 'Hackerone' }]);
  const [platform, setPlatform] = useState('hackerone');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState('');
  const [precedents, setPrecedents] = useState([]);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [save, setSave] = useState(true);
  const [savedId, setSavedId] = useState(null);
  const [pdfBusy, setPdfBusy] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setReport(''); setPrecedents([]); setError(''); setSavedId(null);
    submissionService.platforms().then(setPlatforms).catch(() => {});
  }, [isOpen, card?.id]);

  if (!isOpen) return null;

  const generate = async () => {
    setLoading(true); setError(''); setReport(''); setSavedId(null);
    try {
      const res = await submissionService.generate(card.id, { platform, save });
      setReport(res.report_markdown || '');
      setPrecedents(res.precedents || []);
      if (res.artifact_id) { setSavedId(res.artifact_id); onSaved && onSaved(); }
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Generation failed');
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(report);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  const download = () => {
    const blob = new Blob([report], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `submission-${platform}-card${card.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPdf = async () => {
    setPdfBusy(true);
    try {
      const blob = await submissionService.renderPdf(report, {
        title: card?.title, filename: `submission-${platform}-card${card.id}`, cardId: card.id,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `submission-${platform}-card${card.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'PDF render failed');
    } finally {
      setPdfBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
         onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Submission-ready report</h3>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded text-neutral-400">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Controls */}
        <div className="px-6 py-3 border-b border-neutral-100 dark:border-neutral-700 flex flex-wrap items-center gap-3">
          <span className="text-sm text-neutral-500 dark:text-neutral-400 truncate max-w-[40%]" title={card?.title}>
            {card?.title}
          </span>
          <div className="flex items-center gap-2 ml-auto">
            <select value={platform} onChange={(e) => setPlatform(e.target.value)}
              className="text-sm px-2 py-1.5 rounded border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-800 dark:text-neutral-200">
              {platforms.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
            <label className="flex items-center gap-1.5 text-sm text-neutral-500 dark:text-neutral-400">
              <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} />
              Save PDF to evidence
            </label>
            <button onClick={generate} disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-60">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              {loading ? 'Generating…' : (report ? 'Regenerate' : 'Generate')}
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {error && (
            <div className="flex items-start gap-2 p-3 rounded bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {!report && !loading && !error && (
            <div className="text-center text-sm text-neutral-400 py-10">
              Pick a platform and click <span className="font-medium">Generate</span> to draft a
              submission-ready report grounded in similar disclosed reports.
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 text-neutral-400 py-10">
              <Loader2 className="w-5 h-5 animate-spin" /> Drafting report from the model…
            </div>
          )}

          {report && (
            <>
              <div className="flex items-center gap-2">
                <button onClick={copy}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600">
                  {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Copied' : 'Copy Markdown'}
                </button>
                <button onClick={downloadPdf} disabled={pdfBusy}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-60">
                  {pdfBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                  Download PDF
                </button>
                <button onClick={download}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600">
                  <Download className="w-3.5 h-3.5" /> .md
                </button>
                {savedId && (
                  <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                    <Check className="w-3.5 h-3.5" /> Saved PDF to evidence (#{savedId})
                  </span>
                )}
              </div>
              <div className="overflow-x-auto bg-neutral-50 dark:bg-neutral-900 rounded border border-neutral-200 dark:border-neutral-700">
                <pre className="p-4 text-xs font-mono text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-words">{report}</pre>
              </div>
            </>
          )}

          {precedents.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-neutral-400 mb-2">Grounded in disclosed reports</h4>
              <ul className="space-y-1">
                {precedents.map((p, i) => (
                  <li key={i} className="text-sm">
                    {p.url ? (
                      <a href={p.url} target="_blank" rel="noreferrer"
                        className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline">
                        <ExternalLink className="w-3 h-3" /> {p.title}
                      </a>
                    ) : <span className="text-neutral-500">{p.title}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
