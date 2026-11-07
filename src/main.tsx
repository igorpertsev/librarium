
  import { createRoot } from "react-dom/client";
  import App from "./app/App.tsx";
  import { initTheme } from "./app/utils/theme";
  import "./styles/index.css";

  // Before the first render, so the page never flashes in the wrong theme.
  initTheme();
  createRoot(document.getElementById("root")!).render(<App />);

  // Installable app that opens offline (public/sw.js). Not in development: it would keep old
  // files around while you edit them.
  if (import.meta.env.PROD && "serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    });
  }
  