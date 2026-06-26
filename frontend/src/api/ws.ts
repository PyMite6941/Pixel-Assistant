import { useRef, useEffect, useCallback } from 'react'

export function useWebSocket(
  onMessage: (msg: any) => void,
  onOpen?: () => void,
  onClose?: () => void,
) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const pingInterval = useRef<ReturnType<typeof setInterval>>()
  const isClosing = useRef(false)

  const connect = useCallback(() => {
    if (isClosing.current) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = proto + '://' + location.host + '/ws'

    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
    }

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      clearTimeout(reconnectTimer.current)
      clearInterval(pingInterval.current)
      pingInterval.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        }
      }, 20000)
      onOpen?.()
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'pong') return
        onMessage(msg)
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      clearInterval(pingInterval.current)
      onClose?.()
      if (!isClosing.current) {
        reconnectTimer.current = setTimeout(connect, 2000)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [onMessage, onOpen, onClose])

  useEffect(() => {
    isClosing.current = false
    connect()
    return () => {
      isClosing.current = true
      clearTimeout(reconnectTimer.current)
      clearInterval(pingInterval.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { send, wsRef }
}
