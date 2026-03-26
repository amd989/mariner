export interface PrinterTheme {
  id: string;
  name: string;
  accent: string; // preview swatch color (hex)
  vars: {
    primary: string;
    "primary-foreground": string;
    accent: string;
    "accent-foreground": string;
    ring: string;
    "sidebar-primary": string;
    "sidebar-ring": string;
  };
}

export const themes: PrinterTheme[] = [
  {
    id: "default",
    name: "ChiTu Cyan",
    accent: "#1ab5a0",
    vars: {
      primary: "175 70% 45%",
      "primary-foreground": "220 20% 6%",
      accent: "175 70% 45%",
      "accent-foreground": "220 20% 6%",
      ring: "175 70% 45%",
      "sidebar-primary": "175 70% 45%",
      "sidebar-ring": "175 70% 45%",
    },
  },
  {
    id: "mars",
    name: "Elegoo Mars",
    accent: "#dc2626",
    vars: {
      primary: "0 72% 51%",
      "primary-foreground": "0 0% 100%",
      accent: "0 72% 51%",
      "accent-foreground": "0 0% 100%",
      ring: "0 72% 51%",
      "sidebar-primary": "0 72% 51%",
      "sidebar-ring": "0 72% 51%",
    },
  },
  {
    id: "saturn",
    name: "Elegoo Saturn",
    accent: "#eab308",
    vars: {
      primary: "48 96% 53%",
      "primary-foreground": "48 96% 8%",
      accent: "48 96% 53%",
      "accent-foreground": "48 96% 8%",
      ring: "48 96% 53%",
      "sidebar-primary": "48 96% 53%",
      "sidebar-ring": "48 96% 53%",
    },
  },
  {
    id: "photon",
    name: "Anycubic Photon",
    accent: "#22c55e",
    vars: {
      primary: "142 71% 45%",
      "primary-foreground": "142 71% 6%",
      accent: "142 71% 45%",
      "accent-foreground": "142 71% 6%",
      ring: "142 71% 45%",
      "sidebar-primary": "142 71% 45%",
      "sidebar-ring": "142 71% 45%",
    },
  },
];

const THEME_KEY = "mariner-theme";

export function getStoredThemeId(): string {
  return localStorage.getItem(THEME_KEY) || "default";
}

export function applyTheme(themeId: string) {
  const theme = themes.find((t) => t.id === themeId) || themes[0];
  // Apply to both :root and the .dark container so variables aren't shadowed
  const targets = [
    document.documentElement,
    document.querySelector(".dark"),
  ].filter(Boolean) as HTMLElement[];
  targets.forEach((el) => {
    Object.entries(theme.vars).forEach(([key, value]) => {
      el.style.setProperty(`--${key}`, value);
    });
  });
  localStorage.setItem(THEME_KEY, theme.id);
}
