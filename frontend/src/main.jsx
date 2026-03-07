import React from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyTheme, resolveInitialTheme } from "./lib/theme";
import "./styles.css";

applyTheme(resolveInitialTheme());

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
