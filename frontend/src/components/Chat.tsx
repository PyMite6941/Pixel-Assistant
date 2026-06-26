import React, { useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '../App'

interface ChatProps {
  messages: Message[]
  streaming: boolean
  input: string
  onInput: (v: string) => void
  onSend: (text: string) => void
  onToggleSidebar: () => void
  onToggleTheme: () => void
  theme: string
  onClearHistory: () => void
}

export default function Chat({
  messages,
  streaming,
  input,
  onInput,
  onSend,
  onToggleSidebar,
  onToggleTheme,
  theme,
  onClearHistory,
}: ChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, streaming, scrollToBottom])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        onSend(input)
      }
    },
    [input, onSend],
  )

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onInput(e.target.value)
      const el = e.target
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 160) + 'px'
    },
    [onInput],
  )

  const handleCopyCode = useCallback((code: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(code).catch(() => {})
    }
  }, [])

  const renderMessageContent = useCallback(
    (content: string, isStreaming?: boolean) => {
      if (isStreaming) {
        return (
          <span>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content || ''}
            </ReactMarkdown>
            <span className="cursor" />
          </span>
        )
      }
      return (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            pre: ({ children, ...props }) => {
              const codeEl = (children as any)?.[0]
              const codeString = codeEl?.props?.children?.[0] || ''
              return (
                <pre {...props}>
                  <button
                    className="copy-btn"
                    onClick={() => handleCopyCode(String(codeString))}
                  >
                    copy
                  </button>
                  {children}
                </pre>
              )
            },
            code: ({ className, children, ...props }) => {
              const match = /language-(\w+)/.exec(className || '')
              const isInline = !className
              if (isInline) {
                return <code {...props}>{children}</code>
              }
              return (
                <code className={className} {...props}>
                  {match && (
                    <span className="lang-label">{match[1]}</span>
                  )}
                  {children}
                </code>
              )
            },
          }}
        >
          {content || ''}
        </ReactMarkdown>
      )
    },
    [handleCopyCode],
  )

  const hasMessages = messages.length > 0

  return (
    <>
      <div className="topbar">
        <div className="topbar-left">
          <button
            className="sidebar-toggle"
            onClick={onToggleSidebar}
            title="Toggle sidebar"
          >
            &#x2630;
          </button>
          <span className="topbar-title">Pixel Assistant</span>
        </div>
        <div className="topbar-right">
          <button
            className="theme-toggle"
            onClick={onToggleTheme}
            title="Toggle theme"
          >
            {theme === 'dark' ? '\u{1F319}' : '\u2600\uFE0F'}
          </button>
          <div className="topbar-actions">
            <button className="icon-btn" onClick={() => onSend('/calendar today')}>
              &#x1F4C5; Today
            </button>
            <button className="icon-btn" onClick={() => onSend('/email ')}>
              &#x2709; Email
            </button>
            <button className="icon-btn" onClick={onClearHistory}>
              &#x1F5D1; Clear
            </button>
          </div>
        </div>
      </div>
      <div className="messages">
        {!hasMessages && !streaming && (
          <div className="empty-state">
            <div className="big-dot" />
            <h2>Hello, I&apos;m Pixel.</h2>
            <p>
              Ask me anything, or use a command from the sidebar. Type /help for
              all commands.
            </p>
          </div>
        )}
        {messages.map((msg, i) => {
          if (msg.role === 'system') {
            return (
              <div key={i} className="msg system">
                <div className="msg-bubble">{msg.content}</div>
              </div>
            )
          }
          const role = msg.role === 'user' ? 'user' : 'pixel'
          const isStreaming = msg.role === 'assistant' && msg.content === '__streaming__'
          const displayContent = isStreaming ? '' : msg.content
          return (
            <div key={i} className={`msg ${role}`}>
              <div className="msg-avatar">
                {role === 'user' ? 'U' : 'P'}
              </div>
              <div className="msg-bubble">
                {renderMessageContent(displayContent, isStreaming)}
              </div>
            </div>
          )
        })}
        <div ref={messagesEndRef} />
      </div>
      <div className="input-area">
        <textarea
          ref={textareaRef}
          className="chat-input"
          rows={1}
          placeholder="Message Pixel\u2026 (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
        />
        <button
          className="send-btn"
          disabled={streaming || !input.trim()}
          onClick={() => onSend(input)}
        >
          Send
        </button>
      </div>
    </>
  )
}
