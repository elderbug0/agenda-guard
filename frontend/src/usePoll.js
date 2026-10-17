import { useEffect, useRef } from "react";

// Calls `fn` immediately and then every `ms` while `active` is true.
// Overlapping calls are skipped, so a slow response never piles up requests.
export function usePoll(fn, ms, active = true) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!active) return undefined;
    let stopped = false;
    let busy = false;
    const run = async () => {
      if (busy || stopped) return;
      busy = true;
      try {
        await saved.current();
      } finally {
        busy = false;
      }
    };
    run();
    const t = setInterval(run, ms);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [ms, active]);
}
