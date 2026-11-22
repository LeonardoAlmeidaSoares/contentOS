import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

try {
  if (localStorage.getItem("contentos-motion") === "reduced")
    document.documentElement.dataset.motion = "reduced";
} catch {
  /* Navegação com armazenamento desativado usa a preferência do dispositivo. */
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
