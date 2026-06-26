import React, { useState, useCallback } from 'react'
import type { Note } from '../App'

interface NotesPanelProps {
  notes: Note[]
  onAdd: (text: string) => void
  onDelete: (id: number) => void
}

export default function NotesPanel({ notes, onAdd, onDelete }: NotesPanelProps) {
  const [text, setText] = useState('')

  const handleAdd = useCallback(() => {
    if (!text.trim()) return
    onAdd(text.trim())
    setText('')
  }, [text, onAdd])

  const handleKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') handleAdd()
    },
    [handleAdd],
  )

  return (
    <>
      <div className="panel-add">
        <input
          placeholder="Add a note\u2026"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
        />
        <button onClick={handleAdd}>+</button>
      </div>
      <div className="item-list">
        {notes.length === 0 && (
          <div className="list-empty">No notes yet</div>
        )}
        {notes.map((note) => (
          <div key={note.id} className="list-item">
            <span className="item-text">{note.text}</span>
            <button
              className="item-btn"
              onClick={() => onDelete(note.id)}
              title="Delete"
            >
              &#x2715;
            </button>
          </div>
        ))}
      </div>
    </>
  )
}
