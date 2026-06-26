import React, { useMemo } from 'react'
import type { SysData } from '../App'

interface SystemDashboardProps {
  sysData: SysData
  onRefresh: () => void
  onSend: (text: string) => void
}

function fmtBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i]
}

function getUptime(bootTime?: number): string {
  if (!bootTime) return '--'
  const diff = Math.floor(Date.now() / 1000 - bootTime)
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  return `${h}h ${m}m`
}

export default function SystemDashboard({ sysData, onRefresh, onSend }: SystemDashboardProps) {
  const cpu = sysData.cpu || {}
  const mem = sysData.memory || {}
  const disk = (sysData.disk && sysData.disk[0]) || {}
  const net = sysData.network || {}
  const bat = sysData.battery || {}

  const statCards = useMemo(() => [
    {
      label: 'CPU',
      value: cpu.percent != null ? `${cpu.percent}%` : '--',
      detail: `${cpu.count || '--'} cores${cpu.freq?.current ? ` | ${cpu.freq.current} MHz` : ''}`,
      percent: cpu.percent,
      color: '#00bcd4',
    },
    {
      label: 'Memory',
      value: mem.percent != null ? `${mem.percent}%` : '--',
      detail: `${fmtBytes(mem.used)} / ${fmtBytes(mem.total)}`,
      percent: mem.percent,
      color: '#4caf50',
    },
    {
      label: 'Disk',
      value: disk.percent != null ? `${disk.percent}% used` : '--',
      detail: `${fmtBytes(disk.free)} free`,
      percent: disk.percent,
      color: '#ffc107',
    },
    {
      label: 'Network',
      value: `${fmtBytes(net.bytes_sent || 0)} \u2191`,
      detail: `${fmtBytes(net.bytes_recv || 0)} \u2193 | ${net.connections_count || 0} connections`,
      color: '#e040fb',
    },
    {
      label: 'Battery',
      value: bat.percent != null ? `${bat.percent}%` : '--',
      detail: bat.power_plugged ? '(plugged in)' : '',
      percent: bat.percent,
      color: bat.power_plugged ? '#30d158' : '#ffd60a',
    },
    {
      label: 'Uptime',
      value: getUptime(sysData.boot_time),
      detail: 'since boot',
      color: '#40a0ff',
    },
  ], [cpu, mem, disk, net, bat, sysData.boot_time])

  return (
    <div className="system-dashboard">
      <div className="setting-section-title">System Dashboard</div>
      <div className="stat-grid">
        {statCards.map((card) => (
          <div key={card.label} className="stat-card">
            <div className="stat-card-header">
              <span className="stat-card-label">{card.label}</span>
              <span className="stat-card-value" style={{ color: card.color }}>
                {card.value}
              </span>
            </div>
            <div className="stat-card-detail">{card.detail}</div>
            {card.percent != null && (
              <div className="stat-bar">
                <div
                  className="stat-bar-fill"
                  style={{
                    width: `${Math.min(card.percent, 100)}%`,
                    backgroundColor: card.color,
                  }}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <button className="icon-btn" style={{ width: '100%' }} onClick={onRefresh}>
          Refresh
        </button>
      </div>

      <div className="setting-section-title" style={{ marginTop: 12 }}>
        Quick Actions
      </div>
      <div className="quick-actions">
        <button className="icon-btn" onClick={() => onSend('/screenshot')}>
          Screenshot
        </button>
        <button className="icon-btn" onClick={() => onSend('/sys')}>
          Full Report
        </button>
        <button className="icon-btn" onClick={() => onSend('/ps')}>
          Processes
        </button>
        <button className="icon-btn" onClick={() => onSend('/battery')}>
          Battery
        </button>
      </div>
    </div>
  )
}
