import { useEffect, useRef, useState } from 'react';

/**
 * Live inbox socket with polling fallback.
 * Returns `live` (true when WS is connected) and a `tick` counter
 * that increments on every incoming event or poll change.
 */
export function useInboxSocket(activeId: number | null, onEvent: () => void) {
  const [live, setLive] = useState(false);
  const [tick, setTick] = useState(0);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let poll: number | null = null;
    let closed = false;

    const fire = () => {
      if (!closed) {
        setTick(t => t + 1);
        cb.current();
      }
    };

    try {
      const wsProtocol = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${wsProtocol}://${location.host}/ws/inbox`);
      ws.onopen = () => !closed && setLive(true);
      ws.onmessage = fire;
      ws.onclose = () => !closed && setLive(false);
      ws.onerror = () => { try { ws?.close(); } catch { /* noop */ } };
    } catch {
      setLive(false);
    }

    // Fallback: poll every 10s when socket isn't live
    poll = window.setInterval(() => {
      if (!live) fire();
    }, 10000);

    return () => {
      closed = true;
      try { ws?.close(); } catch { /* noop */ }
      if (poll) window.clearInterval(poll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  return { live, tick };
}
