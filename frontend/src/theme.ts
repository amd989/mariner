import { createTheme, Theme } from "@material-ui/core/styles";

export const lightTheme: Theme = createTheme({
  palette: {
    type: "light",
    primary: {
      main: "#b71c1c",
    },
    secondary: {
      main: "#b71c1c",
    },
  },
});

export const darkTheme: Theme = createTheme({
  palette: {
    type: "dark",
    primary: {
      main: "#e57373",
    },
    secondary: {
      main: "#e57373",
    },
    background: {
      default: "#121212",
      paper: "#1e1e1e",
    },
  },
});

export default lightTheme;
