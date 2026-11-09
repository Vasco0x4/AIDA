/* eslint-disable react-refresh/only-export-components -- context hooks are the public API */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useWebSocketContext } from './WebSocketContext';
import commandSettingsService from '../services/commandSettingsService';

const PendingCommandsContext = createContext(null);

export const usePendingCommands = () => {
    const context = useContext(PendingCommandsContext);
    if (!context) {
        throw new Error('usePendingCommands must be used within PendingCommandsProvider');
    }
    return context;
};

export const PendingCommandsProvider = ({ children }) => {
    const [pendingCommands, setPendingCommands] = useState([]);
    const [pendingCount, setPendingCount] = useState(0);
    const [latestCommand, setLatestCommand] = useState(null);
    const [showBanner, setShowBanner] = useState(false);
    const { lastMessage } = useWebSocketContext();

    // Load pending commands
    const loadPendingCommands = useCallback(async () => {
        try {
            const data = await commandSettingsService.listPendingCommands();
            const pending = (data.commands || []).filter(c => c.status === 'pending');
            setPendingCommands(pending);
            setPendingCount(pending.length);

            // Show banner if there are pending commands (always show on reload)
            if (pending.length > 0) {
                // Always update to the most recent pending command
                setLatestCommand(pending[0]);
                setShowBanner(true);
            } else {
                // No pending commands, hide banner
                setShowBanner(false);
                setLatestCommand(null);
            }
        } catch (error) {
            console.error('Failed to load pending commands:', error);
        }
    }, []);

    // Initial load
    useEffect(() => {
        loadPendingCommands();
    }, [loadPendingCommands]);

    // Handle WebSocket messages
    useEffect(() => {
        if (lastMessage?.type === 'command_pending_approval') {
            const cmd = lastMessage.data;
            setLatestCommand(cmd);
            setShowBanner(true);
            setPendingCount(prev => prev + 1);
            loadPendingCommands();
        } else if (
            lastMessage?.type === 'command_approved' ||
            lastMessage?.type === 'command_rejected' ||
            lastMessage?.type === 'command_timeout'
        ) {
            // Reload to update counts and potentially hide banner
            loadPendingCommands();
        }
    }, [lastMessage, loadPendingCommands]);

    // Update tab title with badge
    useEffect(() => {
        const baseTitle = 'AIDA';
        if (pendingCount > 0) {
            document.title = `(${pendingCount}) ${baseTitle}`;
        } else {
            document.title = baseTitle;
        }
    }, [pendingCount]);

    const dismissBanner = useCallback(() => {
        setShowBanner(false);
        // Don't clear latestCommand, just hide the banner
    }, []);

    const value = {
        pendingCommands,
        pendingCount,
        latestCommand,
        showBanner,
        dismissBanner,
        loadPendingCommands
    };

    return (
        <PendingCommandsContext.Provider value={value}>
            {children}
        </PendingCommandsContext.Provider>
    );
};
