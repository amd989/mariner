import { createTheme, Theme } from "@material-ui/core/styles";

export const lightTheme: Theme = createTheme({
  palette: {
    type: "light",
    primary: {
      main: "#2563eb", // Modern blue
      light: "#60a5fa",
      dark: "#1d4ed8",
    },
    secondary: {
      main: "#f59e0b", // Vibrant amber for accents
      light: "#fbbf24",
      dark: "#d97706",
    },
    background: {
      default: "#f8fafc",
      paper: "#ffffff",
    },
    text: {
      primary: "#1e293b",
      secondary: "#64748b",
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontWeight: 700,
    },
    h2: {
      fontWeight: 600,
    },
    h3: {
      fontWeight: 600,
    },
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
  },
  shape: {
    borderRadius: 12,
  },
});

export const darkTheme: Theme = createTheme({
  palette: {
    type: "dark",
    primary: {
      main: "#3b82f6", // Bright blue for dark mode
      light: "#60a5fa",
      dark: "#2563eb",
    },
    secondary: {
      main: "#f59e0b", // Amber accent
      light: "#fbbf24",
      dark: "#d97706",
    },
    background: {
      default: "#0f172a", // Dark slate
      paper: "#1e293b",
    },
    text: {
      primary: "#f1f5f9",
      secondary: "#94a3b8",
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontWeight: 700,
    },
    h2: {
      fontWeight: 600,
    },
    h3: {
      fontWeight: 600,
    },
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 600,
    },
    h6: {
      fontWeight: 600,
    },
  },
  shape: {
    borderRadius: 12,
  },
});

export default lightTheme;
