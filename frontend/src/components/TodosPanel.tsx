import React, { useState, useCallback } from 'react'
import type { Todo } from '../App'

interface TodosPanelProps {
  todos: Todo[]
  onAdd: (task: string) => void
  onToggle: (id: number) => void
  onDelete: (id: number) => void
}

export default function TodosPanel({ todos, onAdd, onToggle, onDelete }: TodosPanelProps) {
  const [task, setTask] = useState('')

  const handleAdd = useCallback(() => {
    if (!task.trim()) return
    onAdd(task.trim())
    setTask('')
  }, [task, onAdd])

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
          placeholder="Add a task\u2026"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          onKeyDown={handleKey}
        />
        <button onClick={handleAdd}>+</button>
      </div>
      <div className="item-list">
        {todos.length === 0 && (
          <div className="list-empty">No tasks yet</div>
        )}
        {todos.map((todo) => (
          <div key={todo.id} className="list-item">
            <button
              className="item-btn done-btn"
              onClick={() => onToggle(todo.id)}
              title="Toggle done"
            >
              &#x2713;
            </button>
            <span className={`item-text ${todo.done ? 'done' : ''}`}>
              {todo.task}
            </span>
            <button
              className="item-btn"
              onClick={() => onDelete(todo.id)}
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
