import { Link, useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import product from '../guide-content/PRODUCT_GUIDE.md?raw';
import workflow from '../guide-content/KANBAN_SCHEDULER.md?raw';
import administration from '../guide-content/ADMIN_GUIDE.md?raw';
import clients from '../guide-content/AI_CLI_MCP.md?raw';
import operations from '../guide-content/OPERATIONS.md?raw';
import architecture from '../guide-content/LOCAL_ARCHITECTURE.md?raw';
import installation from '../guide-content/QUICK_START.md?raw';

import appsec from '../guide-content/APPSEC.md?raw';

const guides = [
  ['start', 'Getting started', 'PRODUCT_GUIDE.md', product],
  ['install', 'Installation', 'QUICK_START.md', installation],
  ['workflow', 'Kanban & Scheduler', 'KANBAN_SCHEDULER.md', workflow],
  ['appsec', 'Application Security', 'APPSEC.md', appsec],
  ['admin', 'Administration', 'ADMIN_GUIDE.md', administration],
  ['clients', 'AI CLI & MCP', 'AI_CLI_MCP.md', clients],
  ['operations', 'Operations', 'OPERATIONS.md', operations],
  ['architecture', 'Architecture', 'LOCAL_ARCHITECTURE.md', architecture],
];

function GuideLink({ href, children }) {
  const local = guides.find(guide => guide[2] === href?.split('#')[0]);
  if (local) return <Link to={`/guide?doc=${local[0]}`}>{children}</Link>;
  if (/^https?:\/\//.test(href || '')) return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
  return <span title="Available in the source documentation">{children}</span>;
}

function GuideImage({ src, alt }) {
  const image = src?.startsWith('../assets/docs/screenshots/')
    ? src.replace('../assets/docs/screenshots/', '/docs/screenshots/') : src;
  return <img src={image} alt={alt || ''} loading="lazy" decoding="async"
    className="my-5 h-auto w-full rounded-xl border border-neutral-200 dark:border-neutral-700 shadow-sm" />;
}

export default function Guide() {
  const [params] = useSearchParams();
  const current = guides.find(guide => guide[0] === params.get('doc')) || guides[0];
  return <div className="max-w-6xl mx-auto space-y-5">
    <header className="aida-page-header">
      <p className="text-xs uppercase tracking-[0.2em] text-primary-600 dark:text-primary-400 mb-2">AIDA handbook</p>
      <h1 className="text-2xl font-bold">User guide</h1>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">Understand the workflow, configure a scan and find the right next step.</p>
    </header>
    <nav aria-label="Guide chapters" className="flex flex-wrap gap-2">
      {guides.map(([id, title]) => <Link key={id} to={`/guide?doc=${id}`} aria-current={id === current[0] ? 'page' : undefined}
        className={`btn ${id === current[0] ? 'btn-primary' : 'btn-secondary'}`}>{title}</Link>)}
    </nav>
    <article className="card prose-custom leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: GuideLink, img: GuideImage }}>{current[3]}</ReactMarkdown>
    </article>
  </div>;
}
