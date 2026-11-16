/**
 * Start-up, in order of importance.
 *
 * 1. The emergency controls (stop and emergency mode), in their own root. This file and what it
 *    imports statically are the first thing the browser downloads: nothing else delays them.
 * 2. The backend (the real server client, or the demo clinic), loaded on its own.
 * 3. The rest of the panel: router, store, pages. Each page is its own download.
 */
import './styles/tokens.css'
import './styles/base.css'
// The login screen is in index.html: its styles come with the first stylesheet.
import './ui/kit.css'
import './ui/login.css'
import { mountEmergencyStop } from './estop/EmergencyStop'
import { initBackend } from './lib/backend'

mountEmergencyStop(document.getElementById('estop-root'))

async function startPanel(): Promise<void> {
  const root = document.getElementById('root')
  if (!root) return
  try {
    const [{ startApp }] = await Promise.all([import('./start'), initBackend()])
    startApp(root)
  } catch {
    // The emergency controls above keep working; tell the operator why the rest is missing.
    root.innerHTML = '<p class="boot-failed">The panel could not load. Reload the page. The emergency stop, top right, still works.</p>'
  }
}

void startPanel()
