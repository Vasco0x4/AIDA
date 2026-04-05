/**
 * WebSocket Hook for Real-Time Updates
 * Provides WebSocket connection and event subscription
 */
import { useEffect, useRef, useCallback, useState } from 'react';

const WS_URL = import.meta.env.VITE_API_URL?.replace('http', 'ws') || 'ws://localhost:8001/api';
const RECONNECT_DELAY = 3000; // 3 seconds
const MAX_RECONNECT_ATTEMPTS = 10;

export function useWebSocket(assessmentId = null) {
  const ws = useRef(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeout = useRef(null);
  const eventHandlers = useRef(new Map());
  const [isConnected, setIsConnected] = useState(false);
  const [lastError, setLastError] = useState(null);
  const [lastMessage, setLastMessage] = useState(null);

  // Build WebSocket URL based on assessment ID
  const getWebSocketUrl = useCallback(() => {
    if (assessmentId) {
      return `${WS_URL}/ws/assessment/${assessmentId}`;
    }
    return `${WS_URL}/ws`;
  }, [assessmentId]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    // Prevent multiple connections
    if (ws.current?.readyState === WebSocket.OPEN || ws.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const url = getWebSocketUrl();
      // console.log(`[WebSocket] Connecting to ${url}...`);
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        // console.log('[WebSocket] Connected');
        setIsConnected(true);
        setLastError(null);
        reconnectAttempts.current = 0;
      };

      ws.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          // console.log('[WebSocket] Received:', message.type, message);

          // Update lastMessage state for reactive consumers
          setLastMessage(message);

          // Call all registered handlers for this event type
          const handlers = eventHandlers.current.get(message.type) || [];
          handlers.forEach(handler => {
            try {
              handler(message.data, message);
            } catch (error) {
              console.error('[WebSocket] Handler error:', error);
            }
          });
        } catch (error) {
          console.error('[WebSocket] Message parse error:', error);
        }
      };

      ws.current.onerror = (error) => {
        // Quietly handle errors, set state but don't spam console
        // console.error('[WebSocket] Error:', error);
        setLastError('Connection error');
      };

      ws.current.onclose = (event) => {
        // console.log('[WebSocket] Disconnected:', event.code, event.reason);
        setIsConnected(false);

        // Attempt to reconnect if not closed intentionally
        if (event.code !== 1000 && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++;
          // console.log(`[WebSocket] Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS})...`);

          reconnectTimeout.current = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY);
        } else if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
          setLastError('Max reconnection attempts reached');
        }
      };

    } catch (error) {
      console.error('[WebSocket] Connection error:', error);
      setLastError(error.message);
    }
  }, [getWebSocketUrl]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
      reconnectTimeout.current = null;
    }

    if (ws.current) {
      // Prevent "WebSocket is closed before the connection is established"
      // error by removing handlers if closing while connecting
      if (ws.current.readyState === WebSocket.CONNECTING) {
        ws.current.onopen = null;
        ws.current.onclose = null;
        ws.current.onerror = null;
        ws.current.onmessage = null;
      }

      // Close silently - don't log in development (React StrictMode causes multiple connects/disconnects)
      try {
        ws.current.close(1000, 'Client disconnect');
      } catch {
        // Ignore errors when closing
      }
      ws.current = null;
    }

    setIsConnected(false);
  }, []);

  // Subscribe to an event type
  const subscribe = useCallback((eventType, handler) => {
    // console.log('[WebSocket] Subscribing to:', eventType);

    // Add handler to the map
    if (!eventHandlers.current.has(eventType)) {
      eventHandlers.current.set(eventType, []);
    }
    eventHandlers.current.get(eventType).push(handler);

    // Return unsubscribe function
    return () => {
      // console.log('[WebSocket] Unsubscribing from:', eventType);
      const handlers = eventHandlers.current.get(eventType) || [];
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    };
  }, []);

  // Send a message to the server
  const send = useCallback((message) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
      // console.log('[WebSocket] Sent:', message);
    } else {
      console.warn('[WebSocket] Cannot send message, not connected');
    }
  }, []);

  // Send ping to keep connection alive
  const ping = useCallback(() => {
    send({ type: 'ping' });
  }, [send]);

  // Auto-connect on mount
  useEffect(() => {
    connect();

    // Ping every 30 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ping();
      }
    }, 30000);

    // Cleanup on unmount
    return () => {
      clearInterval(pingInterval);
      disconnect();
    };
  }, [connect, disconnect, ping]);

  // Reconnect when assessmentId changes
  useEffect(() => {
    if (assessmentId) {
      disconnect();
      connect();
    }
  }, [assessmentId, connect, disconnect]);

  return {
    isConnected,
    lastError,
    lastMessage,
    subscribe,
    send,
    ping,
    connect,
    disconnect
  };
}
