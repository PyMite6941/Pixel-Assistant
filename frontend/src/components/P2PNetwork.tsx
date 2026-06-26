import React from 'react'
import type { PeerData } from '../App'

interface P2PNetworkProps {
  peers: PeerData[]
  onConnect: (id: string) => void
  onDisconnect: (id: string) => void
}

function fmtUptime(seconds?: number): string {
  if (!seconds) return '--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export default function P2PNetwork({ peers, onConnect, onDisconnect }: P2PNetworkProps) {
  if (peers.length === 0) {
    return (
      <div className="agent-empty">
        <div className="agent-empty-icon">&#x1F310;</div>
        <span>No peers discovered</span>
      </div>
    )
  }

  return (
    <div className="peer-list">
      {peers.map((peer) => (
        <div key={peer.id} className="peer-card">
          <div className="peer-card-header">
            <span
              className={`peer-status ${peer.status === 'connected' ? 'connected' : 'disconnected'}`}
            />
            <span className="peer-hostname">{peer.hostname}</span>
          </div>
          <div className="peer-meta">
            <span>IP: {peer.ip}</span>
            <span>Uptime: {fmtUptime(peer.uptime)}</span>
          </div>
          <div className="peer-actions">
            {peer.status === 'connected' ? (
              <button
                className="icon-btn disconnect-btn"
                onClick={() => onDisconnect(peer.id)}
              >
                Disconnect
              </button>
            ) : (
              <button
                className="icon-btn connect-btn"
                onClick={() => onConnect(peer.id)}
              >
                Connect
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
