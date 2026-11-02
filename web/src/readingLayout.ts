import { useEffect, useRef, useState } from "react";

// Keep this boundary identical to the reading-desk CSS media query.
export function useCompactReadingLayout(beforeChange?: (compact: boolean) => void) {
  const callback = useRef(beforeChange);
  callback.current = beforeChange;
  const [compact, setCompact] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1080px)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 1080px)");
    const change = (event: MediaQueryListEvent) => { callback.current?.(event.matches); setCompact(event.matches); };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  return compact;
}
