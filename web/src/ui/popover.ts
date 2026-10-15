import { useEffect, useRef, useState, type RefObject } from "react";
import { ESC_MENU, onEscape } from "./escape";

/** A menu hung from a button in the top bar, drawn in the page (the bar scrolls sideways and its backdrop filter
 *  would clip it): where the button is now, kept up to date as the window resizes or the bar scrolls, and closed by a
 *  click outside it or by Escape (the top layer of escape.ts, so the Escape goes no further). */
export function useAnchor(open: boolean, close: () => void, btn: RefObject<HTMLElement>, menu: RefObject<HTMLElement>): DOMRect | null {
  const [rect, setRect] = useState<DOMRect | null>(null);
  const shut = useRef(close);
  shut.current = close;
  useEffect(() => {
    if (!open) { setRect(null); return; }
    const place = () => setRect((old) => {
      const r = btn.current?.getBoundingClientRect() ?? null;
      return r && old && r.left === old.left && r.bottom === old.bottom && r.right === old.right ? old : r;
    });
    const off = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !btn.current?.contains(t)) shut.current();
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);  // (capture: the bar's own sideways scroll too)
    window.addEventListener("mousedown", off);
    // (and anything else that moves the button: a chip or a note appearing beside it in the bar)
    const t = setInterval(place, 250);
    const unEsc = onEscape(ESC_MENU, () => { shut.current(); return true; });
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("mousedown", off);
      clearInterval(t);
      unEsc();
    };
  }, [open]);
  return open ? rect : null;
}
