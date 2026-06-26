import React, { useCallback } from 'react'

interface CommandsPanelProps {
  onSend: (text: string) => void
}

interface CmdSection {
  title: string
  items: Array<{ label: string; command: string }>
}

const SECTIONS: CmdSection[] = [
  {
    title: 'Chat',
    items: [
      { label: '/help', command: '/help' },
      { label: '/status', command: '/status' },
      { label: '/smart', command: '/smart' },
      { label: '/clear', command: '/clear' },
    ],
  },
  {
    title: 'Tools',
    items: [
      { label: '/weather', command: '/weather' },
      { label: '/sys', command: '/sys' },
      { label: '/calc', command: '/calc ' },
      { label: '/remind', command: '/remind ' },
      { label: '/timer', command: '/timer ' },
      { label: '/wiki', command: '/wiki ' },
      { label: '/code', command: '/code ' },
      { label: '/pomodoro', command: '/pomodoro' },
      { label: '/clip', command: '/clip' },
      { label: '/journal', command: '/journal' },
      { label: '/journal +', command: '/journal ' },
    ],
  },
  {
    title: 'Learn',
    items: [
      { label: '/teach', command: '/teach ' },
      { label: '/teach quiz', command: '/teach quiz' },
      { label: '/teach topics', command: '/teach topics' },
    ],
  },
  {
    title: 'Translate & Define',
    items: [
      { label: '/translate', command: '/translate Spanish ' },
      { label: '/define', command: '/define ' },
      { label: '/summarize', command: '/summarize' },
    ],
  },
  {
    title: 'Documents',
    items: [
      { label: '/slides', command: '/slides ' },
      { label: '/pdf', command: '/pdf ' },
      { label: '/email', command: '/email ' },
      { label: '/themes', command: '/themes' },
    ],
  },
  {
    title: 'Calendar',
    items: [
      { label: '/calendar', command: '/calendar' },
      { label: '/calendar today', command: '/calendar today' },
      { label: '/cal add', command: '/calendar add ' },
    ],
  },
  {
    title: 'Proactive',
    items: [
      { label: '/morning', command: '/morning' },
      { label: '/check', command: '/check' },
    ],
  },
  {
    title: 'Memory',
    items: [
      { label: '/memories', command: '/memories' },
      { label: '/remember', command: '/remember ' },
      { label: '/forget', command: '/forget ' },
    ],
  },
  {
    title: 'Language Learning',
    items: [
      { label: '/lang learn', command: '/lang learn ' },
      { label: '/lang vocab', command: '/lang vocab ' },
      { label: '/lang lesson', command: '/lang lesson ' },
      { label: '/lang conversation', command: '/lang conversation ' },
      { label: '/lang progress', command: '/lang progress' },
      { label: '/lang download', command: '/lang download ' },
      { label: '/lang offline', command: '/lang offline' },
    ],
  },
  {
    title: 'Translation',
    items: [
      { label: '/translate', command: '/translate Spanish ' },
      { label: '/translate --explain', command: '/translate --explain ' },
      { label: '/translate file', command: '/translate file ' },
      { label: '/lang auto', command: '/lang auto' },
      { label: '/lang off', command: '/lang off' },
    ],
  },
  {
    title: 'Self-update',
    items: [
      { label: '/update check', command: '/update check' },
      { label: '/update feature', command: '/update feature ' },
      { label: '/update log', command: '/update log' },
    ],
  },
]

export default function CommandsPanel({ onSend }: CommandsPanelProps) {
  return (
    <div className="cmd-panel">
      {SECTIONS.map((section) => (
        <div key={section.title} className="cmd-section">
          <h4>{section.title}</h4>
          {section.items.map((item) => (
            <span
              key={item.label}
              className="cmd-chip"
              onClick={() => onSend(item.command)}
            >
              {item.label}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}
