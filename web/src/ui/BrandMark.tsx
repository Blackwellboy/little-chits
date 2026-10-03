import type { JSX } from "react";
import { useUI } from "../state/store";
import type { ThemeId } from "../theme";

/** The Norse theme's mark: a fjord between hills and a timber gable. No flags, no helmets. */
function Fjordmark({ className }: { className: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path d="M2 22 10 7l6 9 6-12 8 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="m9 24 3 4h9l3-4ZM16 15v8m0-8 5 6h-5" fill="currentColor" />
      <path d="M3 30h26" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

const MARKS: Record<ThemeId, (className: string, block: boolean) => JSX.Element> = {
  default: (className, block) => (block ? <div className={className}>●</div> : <span className={className}>●</span>),
  norse: (className) => <Fjordmark className={className} />,
};

/** The theme's brand mark (the glowing dot by default). `block` for the boot card. */
export function BrandMark({ className = "logo", block = false }: { className?: string; block?: boolean }) {
  const theme = useUI((s) => s.theme);
  return MARKS[theme](className, block);
}
