import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { createApiSource } from "./api/client";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <App source={createApiSource(import.meta.env.VITE_API_BASE ?? "/api")} />
  </StrictMode>,
);
