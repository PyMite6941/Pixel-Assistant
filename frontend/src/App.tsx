import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useWebSocket } from './api/ws'
import { apiGet, apiPost, apiPut, apiDelete, apiPatch } from './api/rest'
import Sidebar from './components/Sidebar'
import Chat from './components/Chat'
import NotesPanel from './components/NotesPanel'
import TodosPanel from './components/TodosPanel'
import CommandsPanel from './components/CommandsPanel'
import AgentViewer from './components/AgentViewer'
import SystemDashboard from './components/SystemDashboard'
import DeviceManager from './components/DeviceManager'
import P2PNetwork from './components/P2PNetwork'
import SettingsPanel from './components/SettingsPanel'

export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: number
}

export interface Note {
  id: number
  text: string
  created_at?: string
}

export interface Todo {
  id: number
  task: string
  done: boolean
  created_at?: string
}

export interface StatusInfo {
  provider: string
  model: string
  turns: number
  smart?: boolean
}

export interface AgentData {
  agent_type: string
  task?: string
  summary?: string
  start_time?: string
  type?: string
}

export interface SysData {
  cpu?: { percent?: number; count?: number; freq?: { current?: number } }
  memory?: { percent?: number; used?: number; total?: number }
  disk?: Array<{ percent?: number; free?: number; total?: number; mount?: string }>
  network?: { bytes_sent?: number; bytes_recv?: number; connections_count?: number }
  battery?: { percent?: number; power_plugged?: boolean }
  boot_time?: number
}

export interface Settings {
  provider?: string
  model?: string
  smart_model?: string
  smart_mode?: boolean
  max_history?: number
  debug?: boolean
  log_conversations?: boolean
  slide_theme?: string
  pdf_theme?: string
}

export interface DeviceData {
  id: string
  name: string
  type: string
  value?: string | number
  status?: string
}

export interface PeerData {
  id: string
  hostname: string
  ip: string
  status: string
  uptime?: number
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [connected, setConnected] = useState(false)
  const [activeTab, setActiveTab] = useState('notes')
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('pixel-theme') as 'dark' | 'light') || 'dark'
  })
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [status, setStatus] = useState<StatusInfo>({ provider: '', model: '', turns: 0 })
  const [notes, setNotes] = useState<Note[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [agents, setAgents] = useState<AgentData[]>([])
  const [peers, setPeers] = useState<PeerData[]>([])
  const [devices, setDevices] = useState<DeviceData[]>([])
  const [sysData, setSysData] = useState<SysData>({})
  const [settings, setSettings] = useState<Settings>({})

  const streamContentRef = useRef('')
  const initializedRef = useRef(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('pixel-theme', theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((o) => !o)
  }, [])

  const onWsMessage = useCallback((msg: any) => {
    if (msg.type === 'start') {
      setStreaming(true)
      streamContentRef.current = ''
    } else if (msg.type === 'token') {
      streamContentRef.current += msg.content || ''
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.content === '__streaming__') {
          return prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, content: streamContentRef.current } : m,
          )
        }
        return prev
      })
    } else if (msg.type === 'done' || msg.type === 'response') {
      const text = msg.content || streamContentRef.current
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.content === '__streaming__') {
          return prev.map((m, i) =>
            i === prev.length - 1
              ? { ...m, content: text || '', timestamp: Date.now() }
              : m,
          )
        }
        if (text) {
          return [
            ...prev,
            { role: 'assistant', content: text, timestamp: Date.now() },
          ]
        }
        return prev
      })
      setStreaming(false)
    } else if (msg.type === 'error') {
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.content === '__streaming__') {
          return prev.map((m, i) =>
            i === prev.length - 1
              ? { ...m, content: `Error: ${msg.content}`, timestamp: Date.now() }
              : m,
          )
        }
        return [
          ...prev,
          { role: 'assistant', content: `Error: ${msg.content}`, timestamp: Date.now() },
        ]
      })
      setStreaming(false)
    } else if (msg.type === 'system') {
      setMessages((prev) => [
        ...prev,
        { role: 'system', content: msg.content, timestamp: Date.now() },
      ])
    }
  }, [])

  const onWsOpen = useCallback(() => {
    setConnected(true)
    loadStatus()
  }, [])

  const onWsClose = useCallback(() => {
    setConnected(false)
  }, [])

  const { send: wsSend } = useWebSocket(onWsMessage, onWsOpen, onWsClose)

  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim() || streaming) return
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: text, timestamp: Date.now() },
        { role: 'assistant', content: '__streaming__', timestamp: Date.now() },
      ])
      wsSend({ type: 'message', content: text })
      setInput('')
    },
    [streaming, wsSend],
  )

  const loadStatus = useCallback(async () => {
    try {
      const d = await apiGet<StatusInfo>('/status')
      setStatus(d)
    } catch { /* ignore */ }
  }, [])

  const loadNotes = useCallback(async () => {
    try {
      const d = await apiGet<Note[]>('/notes')
      setNotes(Array.isArray(d) ? d : [])
    } catch { setNotes([]) }
  }, [])

  const addNote = useCallback(async (text: string) => {
    try {
      await apiPost('/notes', { text })
      loadNotes()
    } catch { /* ignore */ }
  }, [loadNotes])

  const deleteNote = useCallback(async (id: number) => {
    try {
      await apiDelete(`/notes/${id}`)
      loadNotes()
    } catch { /* ignore */ }
  }, [loadNotes])

  const loadTodos = useCallback(async () => {
    try {
      const d = await apiGet<Todo[]>('/todos')
      setTodos(Array.isArray(d) ? d : [])
    } catch { setTodos([]) }
  }, [])

  const addTodo = useCallback(async (task: string) => {
    try {
      await apiPost('/todos', { task })
      loadTodos()
    } catch { /* ignore */ }
  }, [loadTodos])

  const toggleTodo = useCallback(async (id: number) => {
    try {
      await apiPatch(`/todos/${id}/done`)
      loadTodos()
    } catch { /* ignore */ }
  }, [loadTodos])

  const deleteTodo = useCallback(async (id: number) => {
    try {
      await apiDelete(`/todos/${id}`)
      loadTodos()
    } catch { /* ignore */ }
  }, [loadTodos])

  const loadAgents = useCallback(async () => {
    try {
      const d = await apiGet<AgentData[]>('/agents')
      setAgents(Array.isArray(d) ? d : [])
    } catch { setAgents([]) }
  }, [])

  const loadSysData = useCallback(async () => {
    try {
      const d = await apiGet<SysData>('/sys')
      setSysData(d)
    } catch { /* ignore */ }
  }, [])

  const loadDevices = useCallback(async () => {
    try {
      const d = await apiGet<DeviceData[]>('/iot/devices')
      setDevices(Array.isArray(d) ? d : [])
    } catch { setDevices([]) }
  }, [])

  const loadPeers = useCallback(async () => {
    try {
      const d = await apiGet<PeerData[]>('/peers')
      setPeers(Array.isArray(d) ? d : [])
    } catch { setPeers([]) }
  }, [])

  const loadSettings = useCallback(async () => {
    try {
      const d = await apiGet<Settings>('/settings')
      setSettings(d)
    } catch { /* ignore */ }
  }, [])

  const saveSettings = useCallback(async (s: Settings) => {
    try {
      await apiPut('/settings', s)
      setSettings(s)
      loadStatus()
    } catch { /* ignore */ }
  }, [loadStatus])

  const clearHistory = useCallback(async () => {
    try {
      await apiDelete('/history')
      setMessages([])
    } catch { /* ignore */ }
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const d = await apiGet<Message[]>('/history')
      if (Array.isArray(d) && d.length > 0) {
        setMessages(d.map((m) => ({
          ...m,
          role: m.role === 'assistant' ? 'assistant' : m.role === 'user' ? 'user' : 'system',
          timestamp: m.timestamp || Date.now(),
        })))
      }
    } catch { /* ignore */ }
  }, [])

  const connectToPeer = useCallback(async (id: string) => {
    try {
      await apiPost('/p2p/connect', { peer_id: id })
      loadPeers()
    } catch { /* ignore */ }
  }, [loadPeers])

  const disconnectPeer = useCallback(async (id: string) => {
    try {
      await apiPost('/p2p/disconnect', { peer_id: id })
      loadPeers()
    } catch { /* ignore */ }
  }, [loadPeers])

  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true
      loadHistory()
      loadNotes()
      loadTodos()
      loadAgents()
      loadSysData()
      loadDevices()
      loadPeers()
      loadSettings()
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'agents') loadAgents()
    else if (activeTab === 'system') loadSysData()
    else if (activeTab === 'settings') loadSettings()
  }, [activeTab, loadAgents, loadSysData, loadSettings])

  useEffect(() => {
    if (activeTab !== 'agents') return
    const interval = setInterval(loadAgents, 5000)
    return () => clearInterval(interval)
  }, [activeTab, loadAgents])

  useEffect(() => {
    if (activeTab !== 'system') return
    const interval = setInterval(loadSysData, 10000)
    return () => clearInterval(interval)
  }, [activeTab, loadSysData])

  const tabComponents: Record<string, React.ReactNode> = useMemo(() => ({
    notes: (
      <NotesPanel
        notes={notes}
        onAdd={addNote}
        onDelete={deleteNote}
      />
    ),
    todos: (
      <TodosPanel
        todos={todos}
        onAdd={addTodo}
        onToggle={toggleTodo}
        onDelete={deleteTodo}
      />
    ),
    cmds: <CommandsPanel onSend={sendMessage} />,
    agents: <AgentViewer agents={agents} />,
    system: (
      <SystemDashboard
        sysData={sysData}
        onRefresh={loadSysData}
        onSend={sendMessage}
      />
    ),
    p2p: (
      <P2PNetwork
        peers={peers}
        onConnect={connectToPeer}
        onDisconnect={disconnectPeer}
      />
    ),
    settings: (
      <SettingsPanel
        settings={settings}
        theme={theme}
        onSave={saveSettings}
        onToggleTheme={toggleTheme}
        onClearHistory={clearHistory}
      />
    ),
  }), [notes, todos, agents, peers, sysData, settings, theme, addNote, deleteNote, addTodo, toggleTodo, deleteTodo, sendMessage, loadSysData, saveSettings, toggleTheme, clearHistory, connectToPeer, disconnectPeer])

  return (
    <div className="app-root">
      <Sidebar
        open={sidebarOpen}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onToggle={toggleSidebar}
        connected={connected}
        status={status}
      >
        {tabComponents[activeTab]}
      </Sidebar>
      <main className="main-area">
        <Chat
          messages={messages}
          streaming={streaming}
          input={input}
          onInput={setInput}
          onSend={sendMessage}
          onToggleSidebar={toggleSidebar}
          onToggleTheme={toggleTheme}
          theme={theme}
          onClearHistory={clearHistory}
        />
      </main>
    </div>
  )
}
