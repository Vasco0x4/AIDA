import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Drawer({ open, onClose, title, children, wide = false }) {
  const panel = useRef(null);
  const restore = useRef(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    restore.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const first = panel.current?.querySelector('[data-initial-focus]')
      || panel.current?.querySelector(FOCUSABLE);
    first?.focus();

    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = Array.from(panel.current?.querySelectorAll(FOCUSABLE) || []);
      if (!items.length) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      restore.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className={`h-full w-full ${wide ? 'max-w-3xl' : 'max-w-xl'} overflow-y-auto bg-white dark:bg-neutral-800 shadow-2xl`}>
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-5 py-4">
          <h2 id={titleId} className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close dialog"
            className="rounded p-2 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-700 focus:outline-none focus:ring-2 focus:ring-primary-500">
            <X aria-hidden="true" className="h-4 w-4" />
          </button>
        </header>
        <div className="p-5">{children}</div>
      </section>
    </div>
  );
}
