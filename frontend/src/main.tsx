import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { createApiSource } from "./api/client";
import { createDemoSource } from "./api/demo";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <App source={import.meta.env.MODE === "demo" ? createDemoSource(`${import.meta.env.BASE_URL}demo-data`) : createApiSource(import.meta.env.VITE_API_BASE ?? "/api")} />
  </StrictMode>,
);
