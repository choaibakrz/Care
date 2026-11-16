/** The panel itself, loaded after the emergency controls (see `main.tsx`). */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { captureBootLogin } from './ui/boot'

export function startApp(container: HTMLElement): void {
  // Take what was typed in the static login screen before React replaces it.
  captureBootLogin()
  createRoot(container).render(
    <StrictMode>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}>
        <App />
      </BrowserRouter>
    </StrictMode>,
  )
}
