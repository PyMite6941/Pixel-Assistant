import React from 'react'
import type { DeviceData } from '../App'

interface DeviceManagerProps {
  devices: DeviceData[]
}

export default function DeviceManager({ devices }: DeviceManagerProps) {
  if (devices.length === 0) {
    return (
      <div className="agent-empty">
        <div className="agent-empty-icon">&#x1F4E1;</div>
        <span>No IoT devices discovered</span>
      </div>
    )
  }

  return (
    <div className="device-list">
      {devices.map((device) => (
        <div key={device.id} className="device-card">
          <div className="device-card-header">
            <span
              className={`device-status ${device.status === 'online' ? 'online' : 'offline'}`}
            />
            <span className="device-name">{device.name}</span>
          </div>
          <div className="device-meta">
            <span className="device-type">{device.type}</span>
            {device.value != null && (
              <span className="device-value">{device.value}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
