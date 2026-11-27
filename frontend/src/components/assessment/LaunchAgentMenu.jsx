import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, Copy, Play, Terminal } from '../icons';
import {
  canLaunchOnHost,
  isHostHelperAvailable,
  launchAidaOnHost,
  launchCommand,
} from '../../services/hostHelperService';

/**
 * "Launch agent" button of the assessment page.
 *
 * Asks the host helper (tools/helper.py, started by `aida start`) to open a
 * terminal running `aida run "<assessment>"`: Claude Code inside the
 * assessment's own container, bound to this assessment. When the helper
 * can't do it (not running, UI opened from another machine, name it
 * rejects), shows the command to copy instead.
 */

const CommandLine = ({ command }) => {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable (plain http from another machine): the
      // command stays selectable.
    }
  };
  return (
    <div className="relative">
      <pre className="text-[11px] font-mono bg-neutral-900 text-green-400 pl-3 pr-8 py-2 rounded-lg overflow-x-auto select-all">{command}</pre>
      <button
        onClick={copy}
        className="absolute top-1 right-1 p-1 rounded bg-neutral-700 hover:bg-neutral-600"
        title="Copy command"
        aria-label="Copy command"
      >
        {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3 text-neutral-400" />}
      </button>
    </div>
  );
};

const LaunchAgentMenu = ({ assessmentName }) => {
  const [open, setOpen] = useState(false);
  // null while checking, then whether the host helper answered.
  const [helperUp, setHelperUp] = useState(null);
  const [launching, setLaunching] = useState(null); // 'agent' | 'cli' | null
  const [result, setResult] = useState(null); // {type: 'success'|'error', mode, text}
  const ref = useRef(null);

  const launchable = canLaunchOnHost(assessmentName);
  const agentCommand = launchCommand(assessmentName, 'agent');
  const cliCommand = launchCommand(assessmentName, 'cli');

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setHelperUp(null);
    isHostHelperAvailable().then((up) => { if (!cancelled) setHelperUp(up); });
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      cancelled = true;
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = () => {
    // Start fresh each time: a previous success would hide the buttons.
    if (!open) setResult(null);
    setOpen(!open);
  };

  const launch = async (mode) => {
    setLaunching(mode);
    setResult(null);
    try {
      const data = await launchAidaOnHost(assessmentName, mode);
      setResult(data.success
        ? { type: 'success', mode }
        : { type: 'error', mode, text: data.error || 'Could not open a terminal.' });
    } catch (e) {
      const detail = e.response?.data?.error;
      setResult({
        type: 'error',
        mode,
        text: detail
          ? `Could not open a terminal: ${detail}. Run the command below instead.`
          : 'The AIDA helper did not answer. Run the command below instead.',
      });
      if (!e.response) setHelperUp(false);
    } finally {
      setLaunching(null);
    }
  };

  const canOpenTerminal = helperUp === true && launchable;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 border border-primary-600 rounded-md transition-colors"
        title="Run Claude Code on this assessment, inside its own container"
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <Play className="w-3.5 h-3.5" />
        <span>Launch agent</span>
      </button>

      {open && (
        <div role="dialog" aria-label="Launch agent" className="absolute right-0 top-full mt-2 w-96 bg-white dark:bg-neutral-800 rounded-lg shadow-xl border border-neutral-200 dark:border-neutral-700 p-4 z-50">
          <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Launch agent</h4>
          <p className="mt-1 mb-3 text-[11px] leading-snug text-neutral-500 dark:text-neutral-400">
            Claude Code runs inside this assessment&apos;s own container and only sees this assessment.
            The first launch downloads the agent image and asks you to log in to AIDA and Claude.
          </p>

          {result?.type === 'success' && result.mode === 'agent' ? (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-xs">
              <Check className="w-4 h-4 flex-shrink-0" />
              <span>
                Terminal opened with the agent. Detach with <kbd className="font-mono">Ctrl-b d</kbd>: it keeps working,
                and Launch agent re-attaches.
              </span>
            </div>
          ) : (
            <>
              {canOpenTerminal && (
                <button
                  onClick={() => launch('agent')}
                  disabled={launching !== null}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                  <Terminal className="w-4 h-4" />
                  {launching === 'agent' ? 'Opening terminal…' : 'Open in terminal'}
                </button>
              )}

              {result?.type === 'error' && result.mode === 'agent' && (
                <div className="mt-2 flex items-start gap-1.5 px-2.5 py-1.5 rounded text-xs bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400">
                  <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>{result.text}</span>
                </div>
              )}

              <div className={canOpenTerminal ? 'mt-3' : ''}>
                <p className="text-[10px] text-neutral-500 dark:text-neutral-400 mb-1.5">
                  {helperUp === null && 'Checking for the AIDA helper…'}
                  {helperUp === true && !launchable && 'This name can’t be opened from the browser. Run in a terminal:'}
                  {helperUp === true && launchable && 'Or run it yourself:'}
                  {helperUp === false && 'Run this in a terminal on the machine running AIDA:'}
                </p>
                <CommandLine command={agentCommand} />
              </div>
            </>
          )}

          {/* AI CLI installed on this machine */}
          <details className="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700 group">
            <summary className="text-[11px] text-neutral-600 dark:text-neutral-300 cursor-pointer select-none">
              Use an AI CLI on this machine instead (Codex, Kimi, Qwen…)
            </summary>
            <div className="mt-2 space-y-2">
              <CommandLine command={cliCommand} />
              {canOpenTerminal && (
                <button
                  onClick={() => launch('cli')}
                  disabled={launching !== null}
                  className="text-[11px] text-primary-600 dark:text-primary-400 hover:underline disabled:opacity-50"
                >
                  {launching === 'cli' ? 'Opening terminal…' : 'Open in terminal'}
                </button>
              )}
              {result?.mode === 'cli' && (
                <p className={`text-[11px] ${result.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {result.type === 'success' ? 'Terminal opened.' : result.text}
                </p>
              )}
            </div>
          </details>

          <p className="mt-3 text-[10px] text-neutral-500 dark:text-neutral-400">
            Commands requiring approval appear in the <strong>Commands</strong> page.
          </p>
        </div>
      )}
    </div>
  );
};

export default LaunchAgentMenu;
