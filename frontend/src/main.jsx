import React from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyTheme, resolveInitialThemeMode } from "./lib/theme";
import "./styles.css";

applyTheme(resolveInitialThemeMode());

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
