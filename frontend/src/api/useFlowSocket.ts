// /ws/flow WebSocket 구독 훅: FlowEvent 를 실시간 누적.
import { useEffect, useRef, useState } from "react";
import type { FlowEvent } from "./types";

const MAX_EVENTS = 2000;

export function useFlowSocket(backfill = 200) {
  const [events, setEvents] = useState<FlowEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/flow?backfill=${backfill}`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as FlowEvent;
          setEvents((prev) => {
            const next = [...prev, ev];
            return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next;
          });
        } catch {
          /* ignore malformed */
        }
      };
    };
    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [backfill]);

  const clear = () => setEvents([]);
  return { events, connected, clear };
}
