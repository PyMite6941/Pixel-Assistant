"""
Pixel Assistant — Streamlit Dashboard.
Shows real-time system vitals, device browser, and LLM-powered health insights.

Usage:
  streamlit run dashboard.py
  python run.py dashboard
"""
import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="Pixel Dashboard",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Config ────────────────────────────────────────────────────────────────

DEFAULT_API = "http://localhost:8000"
REFRESH_RATES = {"Fast": 2, "Normal": 5, "Slow": 15}
HISTORY_WINDOW = 120  # seconds of history to keep

# ── Session state ─────────────────────────────────────────────────────────

if "history" not in st.session_state:
    st.session_state.history = {"cpu": [], "memory": [], "network_up": [], "network_down": []}
if "peers" not in st.session_state:
    st.session_state.peers = []
if "last_fetch" not in st.session_state:
    st.session_state.last_fetch = 0


# ── API helpers ───────────────────────────────────────────────────────────

def api_get(path: str, base: str = None) -> dict:
    base = base or st.session_state.get("api_url", DEFAULT_API)
    try:
        r = requests.get(f"{base}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def fetch_peers(base: str) -> list:
    data = api_get("/api/peers", base)
    if isinstance(data, list):
        return data
    return []


def fetch_sys(base: str) -> dict:
    return api_get("/api/sys", base)


def fetch_processes(base: str, limit: int = 30) -> list:
    data = api_get(f"/api/processes?limit={limit}", base)
    if isinstance(data, list):
        return data
    return []


def fetch_status(base: str) -> dict:
    return api_get("/api/status", base)


# ── LLM insight ───────────────────────────────────────────────────────────

def get_llm_insight(sys_data: dict, base: str) -> str:
    """Ask the assistant to analyze system vitals."""
    cpu = (sys_data.get("cpu") or {}).get("percent", 0)
    mem = (sys_data.get("memory") or {}).get("percent", 0)
    disk = ((sys_data.get("disk") or [{}])[0] or {}).get("percent", 0)
    bat = (sys_data.get("battery") or {})
    uptime = (sys_data.get("boot_time") or 0)
    up_secs = int(time.time() - uptime) if uptime else 0
    up_str = f"{up_secs // 3600}h {(up_secs % 3600) // 60}m" if up_secs else "unknown"

    prompt = (
        "You are a system health analyst. Given these vitals, provide a brief "
        "1-2 sentence health assessment and one specific recommendation:\n\n"
        f"- CPU: {cpu}%\n- Memory: {mem}%\n- Disk: {disk}%\n"
        f"- Battery: {bat.get('percent', 'N/A')}% {'(plugged in)' if bat.get('power_plugged') else '(on battery)'}\n"
        f"- Uptime: {up_str}\n\n"
        "Reply concisely. Example: 'System healthy. Consider closing unused browser tabs to reduce memory pressure.'"
    )

    try:
        r = requests.post(
            f"{base}/api/teach",
            json={"topic": prompt},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            text = data.get("lesson", "") or data.get("result", "")
            if text:
                return text
    except Exception:
        pass

    # Fallback: rule-based insight
    issues = []
    if cpu and cpu > 80:
        issues.append(f"CPU at {cpu}% — consider closing heavy apps")
    if mem and mem > 80:
        issues.append(f"Memory at {mem}% — close unused programs")
    if disk and disk > 90:
        issues.append(f"Disk at {disk}% — free up space")
    if bat and not bat.get("power_plugged") and bat.get("percent", 100) < 20:
        issues.append(f"Battery at {bat['percent']}% — plug in soon")
    if issues:
        return "⚠️ " + issues[0]
    return "✅ System looks healthy."


# ── Charts ────────────────────────────────────────────────────────────────

def cpu_chart(history: list) -> go.Figure:
    if not history:
        return go.Figure()
    df = pd.DataFrame(history)
    fig = px.line(df, x="t", y="v", title="CPU %", markers=False)
    fig.update_traces(line=dict(color="#00bcd4", width=2), fill="tozeroy")
    fig.update_layout(yaxis_range=[0, 100], height=180, margin=dict(t=30, b=10, l=10, r=10))
    fig.update_layout(showlegend=False)
    return fig


def memory_chart(history: list) -> go.Figure:
    if not history:
        return go.Figure()
    df = pd.DataFrame(history)
    fig = px.line(df, x="t", y="v", title="Memory %", markers=False)
    fig.update_traces(line=dict(color="#4caf50", width=2), fill="tozeroy")
    fig.update_layout(yaxis_range=[0, 100], height=180, margin=dict(t=30, b=10, l=10, r=10))
    fig.update_layout(showlegend=False)
    return fig


def network_chart(up: list, down: list) -> go.Figure:
    fig = go.Figure()
    if up:
        df_up = pd.DataFrame(up)
        fig.add_trace(go.Scatter(
            x=df_up["t"], y=df_up["v"], mode="lines",
            name="Upload", line=dict(color="#e040fb", width=2),
        ))
    if down:
        df_down = pd.DataFrame(down)
        fig.add_trace(go.Scatter(
            x=df_down["t"], y=df_down["v"], mode="lines",
            name="Download", line=dict(color="#40a0ff", width=2),
            fill="tonexty",
        ))
    fig.update_layout(
        title="Network I/O (MB)",
        height=180, margin=dict(t=30, b=10, l=10, r=10),
        yaxis=dict(type="log", title="MB"),
    )
    return fig


def disk_gauge(percent: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=percent,
        title={"text": "Disk Usage"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#ffc107"},
            "steps": [
                {"range": [0, 50], "color": "#1c2540"},
                {"range": [50, 80], "color": "#2a3560"},
                {"range": [80, 100], "color": "#3a2040"},
            ],
            "threshold": {
                "line": {"color": "#ff453a", "width": 4},
                "thickness": 0.75,
                "value": 90,
            },
        },
    ))
    fig.update_layout(height=200, margin=dict(t=30, b=10, l=10, r=10))
    return fig


def battery_gauge(percent, plugged) -> go.Figure:
    color = "#30d158" if plugged else "#ffd60a"
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=percent or 0,
        title={"text": "Battery"},
        delta={"reference": 100, "increasing": {"color": color}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 20], "color": "#3a2020"},
                {"range": [20, 80], "color": "#2a3020"},
                {"range": [80, 100], "color": "#203a20"},
            ],
        },
    ))
    status = "🔌 Plugged in" if plugged else "🔋 On battery"
    fig.update_layout(
        height=200, margin=dict(t=30, b=10, l=10, r=10),
        annotations=[dict(text=status, showarrow=False, y=-0.1, font=dict(size=12))],
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────

def render_sidebar():
    st.sidebar.markdown("## ⬡ Pixel Dashboard")

    api_url = st.sidebar.text_input(
        "API URL",
        value=st.session_state.get("api_url", DEFAULT_API),
        placeholder="http://localhost:8000",
    )
    st.session_state.api_url = api_url.rstrip("/")

    refresh_label = st.sidebar.selectbox(
        "Refresh rate", list(REFRESH_RATES.keys()), index=1
    )
    st.session_state.refresh_interval = REFRESH_RATES[refresh_label]

    st.sidebar.markdown("---")

    # Discovered devices
    st.sidebar.markdown("### 🌐 Devices")
    peers = fetch_peers(api_url)
    st.session_state.peers = peers

    device_options = {"This device (local)": api_url}
    for p in peers:
        label = f"{p.get('hostname', '?')} ({p.get('ip', '?')})"
        url = f"http://{p.get('ip', '')}:{p.get('port', 8000)}"
        device_options[label] = url

    selected_device = st.sidebar.radio(
        "Select device", list(device_options.keys()), index=0,
    )
    st.session_state.device_url = device_options[selected_device]

    status = fetch_status(st.session_state.device_url)
    if isinstance(status, dict) and "error" not in status:
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Provider:** {status.get('provider','?')}")
        st.sidebar.markdown(f"**Model:** {status.get('model','?')}")
        st.sidebar.markdown(f"**Turns:** {status.get('turns',0)}")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<small>Press **R** to refresh · Auto-refreshes based on rate</small>",
        unsafe_allow_html=True,
    )


# ── Main content ──────────────────────────────────────────────────────────

def render_dashboard():
    base = st.session_state.get("device_url", DEFAULT_API)
    interval = st.session_state.get("refresh_interval", 5)
    now = time.time()

    # Auto-refresh
    if now - st.session_state.last_fetch >= interval:
        st.session_state.last_fetch = now
        sys_data = fetch_sys(base)
        st.session_state.sys_data = sys_data
        st.session_state.processes = fetch_processes(base)

        # Update history
        cpu_pct = (sys_data.get("cpu") or {}).get("percent")
        mem_pct = (sys_data.get("memory") or {}).get("percent")
        net = sys_data.get("network") or {}

        def _to_mb(b):
            return round(b / (1024 * 1024), 2) if b else 0

        ts = datetime.now().isoformat()
        history = st.session_state.history
        if cpu_pct is not None:
            history["cpu"].append({"t": ts, "v": cpu_pct})
        if mem_pct is not None:
            history["memory"].append({"t": ts, "v": mem_pct})
        if net.get("bytes_sent") is not None:
            history["network_up"].append({"t": ts, "v": _to_mb(net["bytes_sent"])})
        if net.get("bytes_recv") is not None:
            history["network_down"].append({"t": ts, "v": _to_mb(net["bytes_recv"])})

        # Trim history
        cutoff = now - HISTORY_WINDOW
        for key in history:
            history[key] = [p for p in history[key] if _parse_ts(p["t"]) >= cutoff]

    sys_data = st.session_state.get("sys_data", {})
    processes = st.session_state.get("processes", [])
    history = st.session_state.history

    # Title
    device_label = st.session_state.get("device_url", base)
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"## 📊 System Dashboard — `{device_label}`")
    with col2:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.session_state.last_fetch = 0
            st.rerun()

    # Top row: CPU + Memory
    c1, c2 = st.columns(2)
    with c1:
        cpu_fig = cpu_chart(history["cpu"])
        st.plotly_chart(cpu_fig, use_container_width=True, key="cpu_chart")
    with c2:
        mem_fig = memory_chart(history["memory"])
        st.plotly_chart(mem_fig, use_container_width=True, key="mem_chart")

    # Second row: Network + Disk + Battery
    c1, c2, c3 = st.columns(3)
    with c1:
        net_fig = network_chart(history["network_up"], history["network_down"])
        st.plotly_chart(net_fig, use_container_width=True, key="net_chart")
    with c2:
        disk_pct = ((sys_data.get("disk") or [{}])[0] or {}).get("percent", 0)
        st.plotly_chart(disk_gauge(disk_pct), use_container_width=True, key="disk_chart")
    with c3:
        bat = sys_data.get("battery") or {}
        st.plotly_chart(
            battery_gauge(bat.get("percent"), bat.get("power_plugged")),
            use_container_width=True, key="bat_chart",
        )

    # LLM Health Insight
    st.markdown("---")
    st.markdown("### 🤖 Health Insight")
    insight_placeholder = st.empty()
    if st.button("Analyze with AI", type="primary", use_container_width=True):
        with st.spinner("Asking assistant…"):
            insight = get_llm_insight(sys_data, base)
        insight_placeholder.info(insight)
    else:
        if sys_data:
            insight = get_llm_insight(sys_data, base)
            insight_placeholder.info(insight)

    # Process table
    st.markdown("---")
    st.markdown("### 📋 Top Processes")
    if processes:
        df = pd.DataFrame(processes)
        cols = [c for c in ["name", "pid", "cpu_percent", "memory_percent", "status"] if c in df.columns]
        if cols:
            display = df[cols].head(15)
            display.columns = ["Name", "PID", "CPU %", "Mem %", "Status"]
            st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.caption("No process data available.")

    # Raw system info
    with st.expander("📄 Raw System Info"):
        st.json(sys_data)


def _parse_ts(ts_str: str) -> float:
    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except Exception:
        return 0


# ── Entry ─────────────────────────────────────────────────────────────────

def main():
    render_sidebar()
    render_dashboard()


if __name__ == "__main__":
    main()
