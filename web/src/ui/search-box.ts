import type { Galaxy } from "../data";

/** ARIA combobox over creator titles. Arrow keys move, Enter picks, Escape closes. */
export function mountSearchBox(
  el: HTMLElement,
  g: Galaxy,
  search: (q: string, limit?: number) => number[],
  onPick: (i: number) => void,
): { focus(): void } {
  el.replaceChildren();
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = `Search ${g.ids.length.toLocaleString("en-GB")} creators`;
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-label", "Search creators");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", "search-results");
  const list = document.createElement("ul");
  list.id = "search-results";
  list.className = "search-results";
  list.setAttribute("role", "listbox");
  list.hidden = true;
  el.append(input, list);

  let results: number[] = [];
  let active = -1;

  function close() {
    results = []; // a later Enter must not pick from a stale list
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function setActive(k: number) {
    active = k;
    list.querySelectorAll("li").forEach((li, j) => li.setAttribute("aria-selected", String(j === k)));
    if (k >= 0) {
      input.setAttribute("aria-activedescendant", `search-opt-${k}`);
      list.children[k]?.scrollIntoView?.({ block: "nearest" });
    }
  }

  function pick(k: number) {
    const i = results[k];
    if (i === undefined) return;
    input.value = g.titles[i];
    close();
    onPick(i);
  }

  input.addEventListener("input", () => {
    results = search(input.value, 10);
    list.replaceChildren(
      ...results.map((i, k) => {
        const li = document.createElement("li");
        li.id = `search-opt-${k}`;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        const t = document.createElement("span");
        t.textContent = g.titles[i];
        const c = document.createElement("span");
        c.className = "sub";
        c.textContent = g.clusters[g.cluster[i]].name;
        li.append(t, c);
        li.addEventListener("mousedown", (e) => {
          e.preventDefault(); // keep focus in the input
          pick(k);
        });
        return li;
      }),
    );
    if (input.value.trim() && !results.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "No creators found";
      list.append(li);
    }
    list.hidden = !input.value.trim();
    input.setAttribute("aria-expanded", String(!list.hidden));
    setActive(results.length ? 0 : -1);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" && results.length) {
      e.preventDefault();
      if (list.hidden) input.dispatchEvent(new Event("input"));
      else setActive((active + 1) % results.length);
    } else if (e.key === "ArrowUp" && results.length) {
      e.preventDefault();
      setActive((active - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(active >= 0 ? active : 0);
    } else if (e.key === "Escape") {
      close();
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 100));
  return { focus: () => input.focus() };
}
