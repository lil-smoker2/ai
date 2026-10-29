import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { AuthProvider } from "./features/auth/AuthProvider";
import { applyMode, getStoredMode } from "./lib/theme";
import "./styles.css";

// Paint the saved theme before the first render so nothing flashes in the wrong
// colours, and keep following the OS while the user is on "system".
applyMode(getStoredMode());
window
  .matchMedia("(prefers-color-scheme: dark)")
  .addEventListener?.("change", () => {
    if (getStoredMode() === "system") applyMode("system");
  });

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 30_000 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
