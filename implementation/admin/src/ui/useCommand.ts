/**
 * Sends pause, resume and dock. Anything that interrupts a running task asks first.
 * The robot may refuse: its reason is shown as it came. The emergency stop does not go through
 * here: it has its own independent path (`src/estop`).
 */
import { useState } from 'react'
import { backend } from '../lib/backend'
import { errorMessage } from '../lib/format'
import { useStore } from '../state/store'
import type { Robot } from '../types'
import { askConfirm } from './confirm'

export type SoftCommand = 'pause' | 'resume' | 'dock'

const VERB: Record<SoftCommand, string> = { pause: 'Pause', resume: 'Resume', dock: 'Send to dock' }

export function useCommand(): { run: (robot: Robot, name: SoftCommand) => Promise<void>; pending: string | null } {
  const [pending, setPending] = useState<string | null>(null)
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)

  const run = async (robot: Robot, name: SoftCommand): Promise<void> => {
    if (!token) return
    const rearm = robot.state === 'estop' && name === 'resume'
    if (rearm) {
      const confirmed = await askConfirm({ title: `Re-arm ${robot.id}?`, body: 'The robot will be able to move again. Check that the area around it is safe.', confirmLabel: 'Re-arm robot', danger: true })
      if (!confirmed) return
    }
    const interrupts = Boolean(robot.taskId) && (name === 'pause' || name === 'dock')
    if (interrupts) {
      const body = name === 'pause'
        ? `${robot.id} is working on ${robot.taskId}. It will stand still where it is until you resume it.`
        : `${robot.id} is working on ${robot.taskId}. The task goes back to the queue and another robot may take it.`
      const confirmed = await askConfirm({ title: `${VERB[name]} ${robot.id}?`, body, confirmLabel: VERB[name], danger: name === 'dock' })
      if (!confirmed) return
    }
    setPending(`${robot.id}:${name}`)
    try {
      const outcome = await backend.sendCommand(token, robot.id, name)
      if (outcome.accepted) toast('success', rearm ? `${robot.id} is re-armed.` : `${robot.id} accepted “${VERB[name].toLowerCase()}”.`)
      else toast('warning', `${robot.id} refused “${VERB[name].toLowerCase()}”: ${outcome.reason ?? 'no reason given.'}`)
    } catch (reason) {
      toast('danger', `${VERB[name]} not delivered to ${robot.id}: ${errorMessage(reason)}`)
    } finally {
      setPending(null)
    }
  }

  return { run, pending }
}
