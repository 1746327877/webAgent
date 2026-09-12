import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { applyTheme, useUiStore } from "@/stores/ui";
import './index.css'
import App from './App.tsx'

applyTheme(useUiStore.getState().theme); // 首屏前落 class，避免暗色闪烁

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
