import { useEffect, useRef, useState } from 'react';
import { Play, FileText, Trash2, Loader2, Download } from '../icons';
import artifactService from '../../services/artifactService';

/**
 * EvidenceGallery — shows evidence artifacts attached to a finding: screenshots
 * inline, PoC videos with a player, other files as download links. Binary content
 * is auth-fetched as blob object URLs (revoked on unmount).
 */
export default function EvidenceGallery({ assessmentId, cardId, refreshKey = 0 }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const urls = useRef({}); // artifactId -> objectURL (for cleanup)

  const revokeAll = () => {
    Object.values(urls.current).forEach((u) => { try { URL.revokeObjectURL(u); } catch { /* */ } });
    urls.current = {};
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const list = await artifactService.list(assessmentId, cardId);
        if (cancelled) return;
        // Resolve blob URLs for renderable media (images/videos).
        await Promise.all(list.map(async (a) => {
          if (a.content_type?.startsWith('image/') || a.content_type?.startsWith('video/')) {
            try { urls.current[a.id] = await artifactService.contentUrl(a.id); } catch { /* */ }
          }
        }));
        if (!cancelled) setItems(list);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; revokeAll(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessmentId, cardId, refreshKey]);

  const remove = async (id) => {
    await artifactService.remove(id);
    if (urls.current[id]) { URL.revokeObjectURL(urls.current[id]); delete urls.current[id]; }
    setItems((prev) => prev.filter((a) => a.id !== id));
  };

  const downloadFile = async (a) => {
    const cached = urls.current[a.id];
    const url = cached || await artifactService.contentUrl(a.id);
    const link = document.createElement('a');
    link.href = url; link.download = a.filename; link.click();
    // Revoke only URLs we created here (cached ones are freed on unmount).
    if (!cached) setTimeout(() => URL.revokeObjectURL(url), 10000);
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-xs text-neutral-400 py-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading evidence…</div>;
  }
  if (!items.length) return null;

  return (
    <div>
      <h4 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300 mb-2">
        Evidence <span className="text-neutral-400 font-normal">({items.length})</span>
      </h4>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {items.map((a) => {
          const isImg = a.content_type?.startsWith('image/');
          const isVid = a.content_type?.startsWith('video/');
          const src = urls.current[a.id];
          return (
            <div key={a.id} className="relative group bg-white dark:bg-neutral-800 rounded border border-neutral-200 dark:border-neutral-700 overflow-hidden">
              <button onClick={() => remove(a.id)} title="Delete evidence"
                className="absolute top-1.5 right-1.5 z-10 p-1 rounded bg-black/40 hover:bg-red-600 text-white opacity-0 group-hover:opacity-100 transition-opacity">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              {isVid && src && (
                <div className="relative">
                  <video src={src} controls preload="metadata" className="w-full max-h-64 bg-black" />
                  <span className="absolute top-1.5 left-1.5 flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-purple-600/90 text-white">
                    <Play className="w-3 h-3" /> PoC video
                  </span>
                </div>
              )}
              {isImg && src && (
                <img src={src} alt={a.caption || a.filename} className="w-full max-h-64 object-contain bg-neutral-50 dark:bg-neutral-900" />
              )}
              {!isImg && !isVid && (
                <button onClick={() => downloadFile(a)}
                  className="flex items-center gap-2 w-full p-3 text-left text-sm text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700">
                  <FileText className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate flex-1">{a.filename}</span>
                  <Download className="w-3.5 h-3.5 text-neutral-400" />
                </button>
              )}
              {(a.caption || isVid || isImg) && (
                <div className="px-2 py-1.5 text-[11px] text-neutral-500 dark:text-neutral-400 truncate border-t border-neutral-100 dark:border-neutral-700">
                  {a.caption || a.filename}
                  {a.size_bytes ? ` · ${(a.size_bytes / 1024).toFixed(0)} KB` : ''}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
