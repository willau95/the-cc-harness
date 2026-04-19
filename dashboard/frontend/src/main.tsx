import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import { LiveUpdatesProvider } from "./context/LiveUpdatesProvider";
import { TooltipProvider } from "./components/ui/tooltip";
import { BreadcrumbProvider } from "./context/BreadcrumbContext";
import { SidebarProvider } from "./context/SidebarContext";
import { DialogProvider } from "./context/DialogContext";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <ToastProvider>
            <LiveUpdatesProvider>
              <TooltipProvider>
                <BreadcrumbProvider>
                  <SidebarProvider>
                    <DialogProvider>
                      <App />
                    </DialogProvider>
                  </SidebarProvider>
                </BreadcrumbProvider>
              </TooltipProvider>
            </LiveUpdatesProvider>
          </ToastProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
