import React from 'react'
import type { AgentData } from '../App'

interface AgentViewerProps {
  agents: AgentData[]
}

const COLORS: Record<string, string> = {
  explorer: '#00bcd4',
  coder: '#4caf50',
  planner: '#e040fb',
  debugger: '#f44336',
  orchestrator: '#ffc107',
}

function timeAgo(startTime: string): string {
  const start = new Date(startTime).getTime()
  const now = Date.now()
  const diff = Math.floor((now - start) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export default function AgentViewer({ agents }: AgentViewerProps) {
  if (agents.length === 0) {
    return (
      <div className="agent-empty">
        <div className="agent-empty-icon">&#x1F916;</div>
        <span>No active agents</span>
      </div>
    )
  }

  return (
    <div className="agent-list">
      {agents.map((agent, i) => {
        const type = (agent.type || agent.agent_type || 'unknown').toLowerCase()
        const color = COLORS[type] || '#40a0ff'
        const elapsed = agent.start_time ? timeAgo(agent.start_time) : ''
        return (
          <div
            key={i}
            className="agent-card"
            style={{ borderLeftColor: color }}
          >
            <div className="agent-type" style={{ color }}>
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </div>
            <div className="agent-task">
              {agent.task || agent.summary || 'Working...'}
            </div>
            <div className="agent-meta">
              {agent.start_time && (
                <span>
                  Started: {new Date(agent.start_time).toLocaleTimeString()}
                </span>
              )}
              {elapsed && <span>Elapsed: {elapsed}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
