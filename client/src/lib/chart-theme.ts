// Chart colours that follow the light/dark theme.
//
// Recharts draws SVG, so it can use the CSS tokens from globals.css directly. lightweight-charts
// draws on a canvas, which cannot read CSS variables: CANVAS_COLORS mirrors the tokens per theme.

export const CHART = {
  axisTick: { fontSize: 10, fill: "var(--muted-foreground)" },
  grid: "var(--border)",
  line: "var(--foreground)",
  reference: "var(--muted-foreground)",
  cursor: "var(--muted)",
  gain: "var(--gain)",
  loss: "var(--loss)",
  tooltip: {
    fontSize: 12,
    borderRadius: 6,
    border: "1px solid var(--border)",
    background: "var(--popover)",
    color: "var(--popover-foreground)",
    boxShadow: "none",
  },
} as const;

export interface CanvasColors {
  surface: string; // the card the chart sits on
  text: string;
  grid: string;
  border: string;
  close: string;
  ema20: string;
  ema50: string;
  volume: string;
  gain: string;
  loss: string;
  crosshair: string;
}

export const CANVAS_COLORS: Record<"light" | "dark", CanvasColors> = {
  light: {
    surface: "#ffffff",
    text: "#737373",
    grid: "#f2f2f2",
    border: "#e5e5e5",
    close: "#171717",
    ema20: "#7a7a7a",
    ema50: "#2b2b2b",
    volume: "#d9d9d9",
    gain: "#16803c",
    loss: "#c8372d",
    crosshair: "#a3a3a3",
  },
  dark: {
    surface: "#171717",
    text: "#a1a1a1",
    grid: "#262626",
    border: "#2e2e2e",
    close: "#fafafa",
    ema20: "#a3a3a3",
    ema50: "#d4d4d4",
    volume: "#3a3a3a",
    gain: "#3fbf6e",
    loss: "#f2705e",
    crosshair: "#737373",
  },
};
