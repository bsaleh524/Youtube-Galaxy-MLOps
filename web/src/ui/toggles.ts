export interface Settings {
  mode: "2d" | "3d";
  performance: boolean;
}

const KEY = "galaxy.settings";
const DEFAULTS: Settings = { mode: "2d", performance: false };

export function loadSettings(): Settings {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (s && (s.mode === "2d" || s.mode === "3d") && typeof s.performance === "boolean") return s;
  } catch {
    // storage blocked or junk: use defaults
  }
  return { ...DEFAULTS };
}

function save(s: Settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // storage blocked: settings just won't be remembered
  }
}

export function mountToggles(el: HTMLElement, initial: Settings, onChange: (s: Settings) => void): void {
  const s = { ...initial };
  const make = (label: string, title: string, pressed: () => boolean, flip: () => void) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "toggle";
    b.textContent = label;
    b.title = title;
    b.setAttribute("aria-pressed", String(pressed()));
    b.addEventListener("click", () => {
      flip();
      b.setAttribute("aria-pressed", String(pressed()));
      save(s);
      onChange({ ...s });
    });
    return b;
  };
  el.replaceChildren(
    make("3D", "Switch between the flat map and the 3D view", () => s.mode === "3d", () => {
      s.mode = s.mode === "3d" ? "2d" : "3d";
    }),
    make("Performance", "Smaller points, no lines, no animation", () => s.performance, () => {
      s.performance = !s.performance;
    }),
  );
}
