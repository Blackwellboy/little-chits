// The Knowledge list's memory of where its reader was.
//
// An entry opens below the whole table, so the panel scrolls down to it; closing it puts the reader back where they
// were when they opened it. Opening a second entry while one is open is opening the entry now showing: the place to go
// back to is where the reader was at that click, not where they were for the first one.

export type ListMemory = { open: string | null; top: number | null };

/** A click on a row: the entry now open (none when the open one was clicked again), and the list position to go back
 *  to when it closes. `top` is where the list is scrolled to at the click (null when it can't be read). */
export function rowClicked(m: ListMemory, key: string, top: number | null): ListMemory {
  if (m.open === key) return { open: null, top: m.top };
  return { open: key, top: top ?? m.top };
}
