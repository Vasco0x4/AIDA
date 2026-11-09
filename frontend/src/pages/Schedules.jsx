import { Link } from 'react-router-dom';
import { LayoutGrid, Activity } from 'lucide-react';
import SchedulesSection from '../components/settings/SchedulesSection';

export default function Schedules() {
  return <div className="space-y-6 max-w-7xl mx-auto">
    <header className="aida-page-header flex flex-wrap justify-between gap-4 items-start">
      <div><p className="text-xs uppercase tracking-[0.2em] text-primary-600 dark:text-primary-400 mb-2">Continuous assessment</p>
        <h1 className="text-2xl font-bold">Scheduled scans</h1>
        <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">Plan recurring checks. Follow each run from the queue to its findings and evidence.</p></div>
      <div className="flex gap-2"><Link to="/board" className="btn btn-secondary"><LayoutGrid size={16} /> Task Board</Link>
        <Link to="/runs" className="btn btn-secondary"><Activity size={16} /> Run history</Link></div>
    </header>
    <section className="card"><SchedulesSection /></section>
  </div>;
}
