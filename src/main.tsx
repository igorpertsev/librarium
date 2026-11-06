
  import { createRoot } from "react-dom/client";
  import App from "./app/App.tsx";
  import { initTheme } from "./app/utils/theme";
  import "./styles/index.css";

  // Before the first render, so the page never flashes in the wrong theme.
  initTheme();
  createRoot(document.getElementById("root")!).render(<App />);
  