import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Self-hosted brand fonts per demo-ui.md §4. Self-hosting (vs. Google
// Fonts CDN) keeps the demo working in air-gapped environments.
import "@fontsource/fraunces/400.css";
import "@fontsource/fraunces/600.css";
import "@fontsource/inter-tight/400.css";
import "@fontsource/inter-tight/500.css";
import "@fontsource/inter-tight/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/amiri/400.css";
import "@fontsource/amiri/700.css";

import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
