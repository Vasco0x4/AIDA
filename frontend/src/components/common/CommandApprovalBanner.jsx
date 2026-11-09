import { utcDate } from '../../utils/utcDate';
import { useNavigate } from 'react-router-dom';
import { X, Terminal } from '../icons';
import { usePendingCommands } from '../../contexts/PendingCommandsContext';
import { useEffect, useState, useRef, useCallback } from 'react';
import commandSettingsService from '../../services/commandSettingsService';

const CommandApprovalToast = () => {
    const navigate = useNavigate();
    const { showBanner, dismissBanner, latestCommand, pendingCount, loadPendingCommands } = usePendingCommands();
    const [progressPercent, setProgressPercent] = useState(100);
    const [timeoutSec, setTimeoutSec] = useState(30);
    const [visible, setVisible] = useState(false);
    const [isClosing, setIsClosing] = useState(false);
    const intervalRef = useRef(null);
    const hasPlayedSound = useRef(false);

    // Fetch timeout setting
    useEffect(() => {
        commandSettingsService.getSettings()
            .then(s => setTimeoutSec(s.timeout_seconds || 30))
            .catch(() => setTimeoutSec(30));
    }, []);

    // Play notification sound
    const playSound = useCallback(() => {
        if (hasPlayedSound.current) return;
        hasPlayedSound.current = true;
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 800;
            osc.type = 'sine';
            gain.gain.setValueAtTime(0.2, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.2);
        } catch (e) { /* Audio is an optional notification enhancement. */ }
    }, []);

    // Handle visibility
    useEffect(() => {
        if (showBanner && pendingCount > 0) {
            setIsClosing(false);
            setVisible(true);
            playSound();
        } else if (visible && !isClosing) {
            setIsClosing(true);
            hasPlayedSound.current = false;
            const timer = setTimeout(() => {
                setVisible(false);
                setIsClosing(false);
            }, 300);
            return () => clearTimeout(timer);
        }
    }, [showBanner, pendingCount, visible, isClosing, playSound]);

    // Progress timer
    useEffect(() => {
        if (!visible || !latestCommand?.created_at) {
            return;
        }

        const startTime = utcDate(latestCommand.created_at).getTime();
        // Use command-specific timeout if available, otherwise use global setting
        const commandTimeout = latestCommand.timeout_seconds || timeoutSec;
        const totalMs = commandTimeout * 1000;

        const update = () => {
            const elapsed = Date.now() - startTime;
            const remaining = Math.max(0, totalMs - elapsed);
            const pct = (remaining / totalMs) * 100;
            setProgressPercent(pct);

            if (pct <= 0 && intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
                loadPendingCommands();
            }
        };

        update();
        intervalRef.current = setInterval(update, 100);

        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
            }
        };
    }, [visible, latestCommand?.created_at, latestCommand?.id, timeoutSec, loadPendingCommands]);

    const handleReview = () => {
        dismissBanner();
        navigate('/commands');
    };

    if (!visible) return null;

    const timeLeft = Math.max(0, Math.ceil((progressPercent / 100) * timeoutSec));

    return (
        <div
            className={`fixed bottom-4 right-4 z-50 transition-all duration-300 ${isClosing ? 'opacity-0 translate-y-4' : 'opacity-100 translate-y-0'
                }`}
        >
            <div className="w-72 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg shadow-lg overflow-hidden">
                {/* Progress bar */}
                <div className="h-1 bg-neutral-100 dark:bg-neutral-700 relative">
                    <div
                        className="absolute inset-y-0 left-0 bg-cyan-500 transition-[width] duration-100"
                        style={{ width: `${progressPercent}%` }}
                    />
                </div>

                <div className="p-4">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                            <Terminal className="w-4 h-4 text-cyan-500" />
                            <span className="text-sm font-medium text-neutral-900 dark:text-white">
                                Approval Required
                            </span>
                            {latestCommand?.risk_level === 'high' && (
                                <span
                                    className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide bg-red-600 text-white rounded"
                                    title={`Exploit-class (${latestCommand.risk_reason || 'PoC approval chain'}) — admin-only approval`}
                                >
                                    exploit
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-neutral-500">
                                {timeLeft}s
                            </span>
                            <button
                                onClick={dismissBanner}
                                className="p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-white rounded transition-colors"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                    </div>

                    {/* Command */}
                    {latestCommand?.command && (
                        <div className="px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-100 dark:border-neutral-700 rounded mb-3">
                            <code className="text-xs text-neutral-600 dark:text-neutral-400 font-mono block truncate">
                                {latestCommand.command}
                            </code>
                        </div>
                    )}

                    {/* Footer */}
                    <div className="flex items-center justify-between">
                        <button
                            onClick={handleReview}
                            className="px-3 py-1.5 bg-cyan-500 hover:bg-cyan-600 text-white text-xs font-medium rounded transition-colors"
                        >
                            Review
                        </button>
                        {pendingCount > 1 && (
                            <span className="text-xs text-neutral-500">
                                +{pendingCount - 1} more
                            </span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default CommandApprovalToast;
