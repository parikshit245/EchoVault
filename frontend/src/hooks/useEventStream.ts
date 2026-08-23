/**
 * useEventStream — Reusable WebSocket hook for EchoVault real-time events.
 *
 * Part 7: Stream-Oriented Communication
 *
 * Single shared hook — used by every page that needs live events.
 * Do NOT create separate WebSocket connections in individual pages.
 *
 * Features:
 *  - Connects to /ws/events
 *  - Sends subscribe/unsubscribe commands
 *  - Ping/pong heartbeat every 30s
 *  - Exponential backoff reconnection: 1s → 2s → 4s → 8s → 16s → 30s (cap)
 *  - Re-sends active subscriptions on reconnect
 *  - Cleans up on component unmount
 *  - Exposes connection status, received events, and control functions
 *
 * Architecture note:
 *  WebSocket is a best-effort real-time delivery channel.
 *  Persistent history is available via GET /api/v1/messaging/messages.
 *  On reconnect, consumers can fetch recent messages for replay.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type WsStatus = "connecting" | "connected" | "disconnected" | "error";

export type WsFilters = {
  event_types?: string[];
  source_node_ids?: string[];
  incident_ids?: string[];
};

export type WsEvent = {
  type: "event";
  message_id: string;
  event_type: string;
  source_node_id: string;
  timestamp: string;
  incident_id: string | null;
  payload: Record<string, unknown>;
  latency_ms: number | null;
};

type WsInboundMessage =
  | { type: "connected"; connection_id: string; node_id: string; timestamp: string }
  | { type: "pong"; timestamp: string }
  | { type: "subscription.updated"; filters: WsFilters }
  | WsEvent
  | { type: "error"; code: string; message: string };

const backendUrl =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// Convert http(s):// to ws(s)://
function toWsUrl(base: string, path: string): string {
  return base.replace(/^http/, "ws") + path;
}

const WS_URL = toWsUrl(backendUrl, "/ws/events");
const PING_INTERVAL_MS = 30_000;
const MAX_EVENTS = 200; // keep latest N events in memory
const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;

export interface UseEventStreamOptions {
  /** Initial filters to subscribe with on connection. */
  filters?: WsFilters;
  /** Called for every received event. */
  onEvent?: (event: WsEvent) => void;
  /** Set to false to disable the hook (e.g. on server-side render). */
  enabled?: boolean;
  /** Maximum number of events to keep in the events array. */
  maxEvents?: number;
}

export interface UseEventStreamReturn {
  status: WsStatus;
  connectionId: string | null;
  events: WsEvent[];
  subscribe: (filters: WsFilters) => void;
  unsubscribe: (filters: WsFilters) => void;
  clearEvents: () => void;
  ping: () => void;
  activeFilters: WsFilters;
}

export function useEventStream(
  options: UseEventStreamOptions = {}
): UseEventStreamReturn {
  const { filters, onEvent, enabled = true, maxEvents = MAX_EVENTS } = options;

  const [status, setStatus] = useState<WsStatus>("disconnected");
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [activeFilters, setActiveFilters] = useState<WsFilters>(filters ?? {});

  const wsRef = useRef<WebSocket | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const mountedRef = useRef<boolean>(true);
  const activeFiltersRef = useRef<WsFilters>(filters ?? {});
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const clearEvents = useCallback(() => setEvents([]), []);

  const sendCommand = useCallback((cmd: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const subscribe = useCallback(
    (f: WsFilters) => {
      setActiveFilters((prev) => {
        const merged: WsFilters = {
          event_types: Array.from(new Set([...(prev.event_types ?? []), ...(f.event_types ?? [])])),
          source_node_ids: Array.from(new Set([...(prev.source_node_ids ?? []), ...(f.source_node_ids ?? [])])),
          incident_ids: Array.from(new Set([...(prev.incident_ids ?? []), ...(f.incident_ids ?? [])])),
        };
        activeFiltersRef.current = merged;
        return merged;
      });
      sendCommand({ type: "subscribe", filters: f });
    },
    [sendCommand]
  );

  const unsubscribe = useCallback(
    (f: WsFilters) => {
      setActiveFilters((prev) => {
        const updated: WsFilters = {
          event_types: (prev.event_types ?? []).filter((x) => !(f.event_types ?? []).includes(x)),
          source_node_ids: (prev.source_node_ids ?? []).filter((x) => !(f.source_node_ids ?? []).includes(x)),
          incident_ids: (prev.incident_ids ?? []).filter((x) => !(f.incident_ids ?? []).includes(x)),
        };
        activeFiltersRef.current = updated;
        return updated;
      });
      sendCommand({ type: "unsubscribe", filters: f });
    },
    [sendCommand]
  );

  const ping = useCallback(() => sendCommand({ type: "ping" }), [sendCommand]);

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return;
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    setStatus("connecting");
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      backoffRef.current = INITIAL_BACKOFF_MS;
      setStatus("connected");

      // Re-apply subscriptions from before reconnect
      const f = activeFiltersRef.current;
      const hasFilters =
        (f.event_types?.length ?? 0) > 0 ||
        (f.source_node_ids?.length ?? 0) > 0 ||
        (f.incident_ids?.length ?? 0) > 0;
      if (hasFilters) {
        ws.send(JSON.stringify({ type: "subscribe", filters: f }));
      }

      // Start ping/pong heartbeat
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(event.data as string) as WsInboundMessage;

        if (msg.type === "connected") {
          setConnectionId(msg.connection_id);
        } else if (msg.type === "event") {
          const wsEvent = msg as WsEvent;
          setEvents((prev) => [wsEvent, ...prev].slice(0, maxEvents));
          onEventRef.current?.(wsEvent);
        }
        // pong, subscription.updated, error — no local state change needed
      } catch {
        // Ignore parse errors
      }
    };

    ws.onerror = () => {
      if (!mountedRef.current) return;
      setStatus("error");
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("disconnected");
      setConnectionId(null);
      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }
      // Exponential backoff reconnect
      const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS);
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      reconnectTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    };
  }, [enabled, maxEvents]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) connect();

    return () => {
      mountedRef.current = false;
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [enabled, connect]);

  return {
    status,
    connectionId,
    events,
    subscribe,
    unsubscribe,
    clearEvents,
    ping,
    activeFilters,
  };
}
