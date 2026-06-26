import React, { useState, useEffect, useCallback } from 'react'
import type { Settings } from '../App'

interface SettingsPanelProps {
  settings: Settings
  theme: 'dark' | 'light'
  onSave: (s: Settings) => void
  onToggleTheme: () => void
  onClearHistory: () => void
}

export default function SettingsPanel({
  settings: initial,
  theme,
  onSave,
  onToggleTheme,
  onClearHistory,
}: SettingsPanelProps) {
  const [form, setForm] = useState<Settings>({})

  useEffect(() => {
    setForm({ ...initial })
  }, [initial])

  const set = useCallback(
    (key: keyof Settings, value: any) => {
      setForm((f) => ({ ...f, [key]: value }))
    },
    [],
  )

  const handleSave = useCallback(() => {
    onSave(form)
  }, [form, onSave])

  return (
    <div className="setting-section">
      <div className="setting-section-title">AI Models</div>

      <div className="settings-models-grid">
        <div className="section-hint">
          &#x26A1; GROQ - fastest, best for chat
        </div>
        {[
          {
            name: 'llama-3.3-70b-versatile',
            desc: 'Best overall \u2014 smart, fast, great reasoning. Default choice.',
            provider: 'groq',
          },
          {
            name: 'llama-3.1-8b-instant',
            desc: 'Fastest \u2014 instant replies, good for quick lookups.',
            provider: 'groq',
          },
          {
            name: 'deepseek-r1-distill-llama-70b',
            desc: 'Shows chain-of-thought. Best for hard math/logic problems.',
            provider: 'groq',
          },
          {
            name: 'gemma2-9b-it',
            desc: 'Google compact model \u2014 light tasks, efficient.',
            provider: 'groq',
          },
        ].map((m) => (
          <div
            key={m.name}
            className={`model-card ${
              form.provider === m.provider && form.model === m.name
                ? 'active'
                : ''
            }`}
            onClick={() => setForm((f) => ({ ...f, provider: m.provider, model: m.name }))}
          >
            <div className="model-card-name">{m.name}</div>
            <div className="model-card-desc">{m.desc}</div>
          </div>
        ))}

        <div className="section-hint">
          &#x1F310; GEMINI - long docs &amp; images
        </div>
        <div
          className={`model-card ${
            form.provider === 'gemini' && form.model === 'gemini-2.0-flash-exp'
              ? 'active'
              : ''
          }`}
          onClick={() =>
            setForm((f) => ({
              ...f,
              provider: 'gemini',
              model: 'gemini-2.0-flash-exp',
            }))
          }
        >
          <div className="model-card-name">gemini-2.0-flash-exp</div>
          <div className="model-card-desc">
            Massive context window \u2014 PDFs, images, long documents.
          </div>
        </div>

        <div className="section-hint">
          &#x1F512; MISTRAL - privacy &amp; multilingual
        </div>
        <div
          className={`model-card ${
            form.provider === 'mistral' && form.model === 'mistral-large-latest'
              ? 'active'
              : ''
          }`}
          onClick={() =>
            setForm((f) => ({
              ...f,
              provider: 'mistral',
              model: 'mistral-large-latest',
            }))
          }
        >
          <div className="model-card-name">mistral-large-latest</div>
          <div className="model-card-desc">
            Strong reasoning, multilingual, European privacy (GDPR).
          </div>
        </div>
      </div>

      <div className="setting-section-title">Configuration</div>

      <div className="setting-row">
        <label>Provider</label>
        <select
          value={form.provider || ''}
          onChange={(e) => set('provider', e.target.value)}
        >
          <option value="groq">Groq</option>
          <option value="gemini">Gemini</option>
          <option value="mistral">Mistral</option>
        </select>
      </div>

      <div className="setting-row">
        <label>Model</label>
        <input
          type="text"
          value={form.model || ''}
          onChange={(e) => set('model', e.target.value)}
          placeholder="e.g. llama-3.3-70b-versatile"
        />
      </div>

      <div className="setting-row">
        <label>Smart model</label>
        <input
          type="text"
          value={form.smart_model || ''}
          onChange={(e) => set('smart_model', e.target.value)}
          placeholder="e.g. llama-3.3-70b-versatile"
        />
      </div>

      <div className="setting-row">
        <label>Smart mode</label>
        <input
          type="checkbox"
          checked={form.smart_mode || false}
          onChange={(e) => set('smart_mode', e.target.checked)}
        />
      </div>

      <div className="setting-row">
        <label>Max history</label>
        <div className="setting-range">
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={form.max_history ?? 20}
            onChange={(e) => set('max_history', parseInt(e.target.value))}
          />
          <span className="setting-value">{form.max_history ?? 20}</span>
        </div>
      </div>

      <div className="setting-row">
        <label>Debug</label>
        <input
          type="checkbox"
          checked={form.debug || false}
          onChange={(e) => set('debug', e.target.checked)}
        />
      </div>

      <div className="setting-row">
        <label>Log conversations</label>
        <input
          type="checkbox"
          checked={form.log_conversations || false}
          onChange={(e) => set('log_conversations', e.target.checked)}
        />
      </div>

      <div className="setting-row">
        <label>Slide theme</label>
        <select
          value={form.slide_theme || 'dark'}
          onChange={(e) => set('slide_theme', e.target.value)}
        >
          <option value="dark">Dark</option>
          <option value="light">Light</option>
          <option value="corporate">Corporate</option>
          <option value="modern">Modern</option>
          <option value="warm">Warm</option>
        </select>
      </div>

      <div className="setting-row">
        <label>PDF theme</label>
        <select
          value={form.pdf_theme || 'light'}
          onChange={(e) => set('pdf_theme', e.target.value)}
        >
          <option value="light">Light</option>
          <option value="dark">Dark</option>
          <option value="corporate">Corporate</option>
          <option value="modern">Modern</option>
          <option value="warm">Warm</option>
        </select>
      </div>

      <div className="setting-row">
        <label>Theme</label>
        <button className="icon-btn" onClick={onToggleTheme}>
          {theme === 'dark' ? '\u{1F319} Dark' : '\u2600\uFE0F Light'}
        </button>
      </div>

      <div className="setting-row">
        <label>Clear history</label>
        <button
          className="clear-btn"
          onClick={() => {
            if (window.confirm('Clear conversation history?')) onClearHistory()
          }}
        >
          Clear
        </button>
      </div>

      <button className="setting-save-btn" onClick={handleSave}>
        Save Settings
      </button>
    </div>
  )
}
