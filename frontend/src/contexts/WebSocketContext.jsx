/* eslint-disable react-refresh/only-export-components -- context hooks are the public API */
/**
 * WebSocket Context Provider
 * Provides global WebSocket connection to all components
 */
import React, { createContext, useContext } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';

const WebSocketContext = createContext(null);

export function WebSocketProvider({ children, assessmentId = null }) {
  const websocket = useWebSocket(assessmentId);

  return (
    <WebSocketContext.Provider value={websocket}>
      {children}
    </WebSocketContext.Provider>
  );
}

/**
 * Hook to access WebSocket context
 * @returns {Object} WebSocket methods and state
 */
export function useWebSocketContext() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within WebSocketProvider');
  }
  return context;
}
