import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { errorText } from "./net/socket";
import { notifyError } from "./state/store";
import "./styles.css";

// a request that failed with nobody to catch it (a 409 on a brain swap, a refused resume...) gets a toast with the
// server's reason instead of a line in the console (issue #63)
window.addEventListener("unhandledrejection", (ev) => {
  if (/^\d{3} /.test(String(ev.reason?.message ?? ""))) { notifyError(errorText(ev.reason)); ev.preventDefault(); }
});

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
