import type { ClinicRoom, RoomDevice, RoomPatient } from '../types'

const rooms: ClinicRoom[] = [
  { id: 'room-212', label: 'Room 212', wing: 'North wing', floor: 2, patient: null, device: null },
  { id: 'room-213', label: 'Room 213', wing: 'North wing', floor: 2, patient: null, device: null },
  { id: 'room-216', label: 'Room 216', wing: 'North wing', floor: 2, patient: null, device: null },
]

let patientSequence = 1
let deviceSequence = 1

function cloneRoom(room: ClinicRoom): ClinicRoom {
  return { ...room, patient: room.patient ? { ...room.patient } : null, device: room.device ? { ...room.device } : null }
}

export function getRoomControl(): ClinicRoom[] {
  return rooms.map(cloneRoom)
}

export function admitDemoPatient(input: { firstName: string; medicalRecordRef: string; roomId: string }): { patient: RoomPatient; roomId: string } {
  const room = rooms.find((entry) => entry.id === input.roomId)
  if (!room) throw new Error('This room does not exist.')
  if (room.patient) throw new Error('Discharge the current patient before assigning another patient to this room.')
  const duplicate = rooms.some((entry) => entry.patient?.medicalRecordRef.toLowerCase() === input.medicalRecordRef.toLowerCase())
  if (duplicate) throw new Error('This medical record reference is already assigned.')
  const patient: RoomPatient = { id: `demo-patient-${patientSequence++}`, firstName: input.firstName.trim(), medicalRecordRef: input.medicalRecordRef.trim(), status: 'admitted', admittedAt: new Date().toISOString() }
  room.patient = patient
  return { patient: { ...patient }, roomId: room.id }
}

function code(): string {
  return `DEMO-${String(deviceSequence++).padStart(4, '0')}`
}

export function createDemoDevice(input: { roomId: string; label: string }): { device: RoomDevice; pairingCode: string } {
  const room = rooms.find((entry) => entry.id === input.roomId)
  if (!room) throw new Error('This room does not exist.')
  if (room.device?.paired) throw new Error('This room already has a paired tablet.')
  const pairingCode = code()
  const device: RoomDevice = { id: room.device?.id || `demo-device-${deviceSequence}`, roomId: room.id, label: input.label.trim() || `Tablet ${room.label}`, online: false, paired: false, pairingCode }
  deviceSequence += 1
  room.device = device
  return { device: { ...device }, pairingCode }
}

export function dischargeDemoRoom(roomId: string): void {
  const room = rooms.find((entry) => entry.id === roomId)
  if (!room) throw new Error('This room does not exist.')
  if (!room.patient) throw new Error('There is no admitted patient in this room.')
  room.patient = null
  room.device = null
}
