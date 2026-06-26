import React from 'react'
import type { StatusInfo } from '../App'

interface SidebarProps {
  open: boolean
  activeTab: string
  onTabChange: (tab: string) => void
  onToggle: () => void
  connected: boolean
  status: StatusInfo
  children: React.ReactNode
}

const TABS = [
  { id: 'notes', label: 'Notes' },
  { id: 'todos', label: 'Todos' },
  { id: 'cmds', label: 'Cmds' },
  { id: 'agents', label: 'Agents' },
  { id: 'system', label: 'System' },
  { id: 'p2p', label: 'P2P' },
  { id: 'settings', label: '\u2699' },
]

export default function Sidebar({
  open,
  activeTab,
  onTabChange,
  onToggle,
  connected,
  status,
  children,
}: SidebarProps) {
  return (
    <>
      <aside className={`sidebar ${open ? '' : 'collapsed'}`}>
        <div className="sidebar-header">
          <div>
            <h1>&#x2B21; Pixel Assistant</h1>
            <div className="status-bar">
              <span className={`status-dot ${connected ? 'connected' : ''}`} />
              <span className="status-text">
                {connected
                  ? `${status.provider} \u00B7 ${status.model} \u00B7 ${status.turns} turns`
                  : 'Disconnected...'}
              </span>
            </div>
          </div>
        </div>
        <div className="sidebar-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => onTabChange(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className={`tab-panel ${activeTab ? 'active' : ''}`}>
          {children}
        </div>
      </aside>
      {!open && (
        <div className="sidebar-backdrop visible" onClick={onToggle} />
      )}
    </>
  )
}
