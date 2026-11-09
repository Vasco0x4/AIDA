/**
 * WebSocket Hook for Real-Time Updates
 * Provides WebSocket connection and event subscription
 */
import { useEffect, useRef, useCallback, useState } from 'react';

// In production (VITE_API_URL=/api), derive the WS host from the browser's
// current location so the connection works for any IP, not just localhost.
function resolveWsBaseUrl() {
  const apiUrl = import.meta.env.VITE_API_URL;
  if (!apiUrl || apiUrl.startsWith('/')) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/api`;
  }
  return apiUrl.replace(/^http/, 'ws');
}
const WS_URL = resolveWsBaseUrl();
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

  // Build WebSocket URL based on assessment ID. The JWT is passed via query
  // string because browser WebSocket clients can't set Authorization headers.
  const getWebSocketUrl = useCallback(() => {
    const token = localStorage.getItem('aida_token');
    const tokenQs = token ? `?token=${encodeURIComponent(token)}` : '';
    if (assessmentId) {
      return `${WS_URL}/ws/assessment/${assessmentId}${tokenQs}`;
    }
    return `${WS_URL}/ws${tokenQs}`;
  }, [assessmentId]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    // Prevent multiple connections
    if (ws.current?.readyState === WebSocket.OPEN || ws.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // Don't even try to connect without a token: the backend will close the
    // socket immediately and we'd burn through the reconnect budget.
    if (!localStorage.getItem('aida_token')) {
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
      const socket = ws.current;
      // Closing a CONNECTING browser socket produces a page-level
      // "WebSocket closed without opened" error in React StrictMode. Detach
      // handlers and close it normally as soon as the handshake completes.
      if (socket.readyState === WebSocket.CONNECTING) {
        socket.onopen = () => {
          try { socket.close(1000, 'Client disconnect'); } catch { /* already closed */ }
        };
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        ws.current = null;
        setIsConnected(false);
        return;
      }

      try {
        socket.close(1000, 'Client disconnect');
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

  // Connect on mount and whenever the target changes. `connect`/`disconnect`
  // identities change with assessmentId (via getWebSocketUrl), so this single
  // effect already tears down the old socket and opens the new one — a second
  // assessmentId effect previously double-connected on every mount/change.
  useEffect(() => {
    connect();

    // Ping every 30 seconds to keep connection alive
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ping();
      }
    }, 30000);

    // Cleanup on unmount / before reconnecting
    return () => {
      clearInterval(pingInterval);
      disconnect();
    };
  }, [connect, disconnect, ping]);

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
