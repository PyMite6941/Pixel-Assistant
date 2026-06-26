"""
Agent system for Pixel Assistant.
Autonomous sub-agents with tool use, agent-to-agent delegation, and auto-routing.
"""
import json
import re
import subprocess as _subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

_AGENTS_DIR = Path(__file__).parent.parent / "functionalities" / "agents"
_AGENT_CONTEXTS_DIR = _AGENTS_DIR / "contexts"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_KILLED_AGENTS: set[str] = set()
_FILE_LOCK = threading.Lock()


AGENT_PERSONAS = {
    "orchestrator": (
        "You are an Orchestrator agent. You break complex tasks into subtasks "
        "and delegate them to specialized sub-agents.\n\n"
        "Tools:\n"
        "  [SEARCH: <query>]           — search the web\n"
        "  [FETCH: <url>]              — fetch a web page\n"
        "  [READ: <path>]              — read a project file\n"
        "  [IMAGINE: <prompt>]         — generate an AI image from a description\n"
        "  [IMAGES: <keyword>]         — list locally stored AI-generated images\n"
        "  [API: <GET|POST|PUT|DELETE> <url> <json_body?>] — call any external REST API\n"
        "  [SPAWN: <type> <task>]      — delegate to a sub-agent\n"
        "    Types: explorer (research), coder (write/read code), planner (analyze/design),\n"
        "           debugger (find/fix bugs)\n"
        "  [DONE: <answer>]            — final answer\n\n"
        "Strategy: Analyze the user's request, break it into steps, spawn sub-agents "
        "for each step, then synthesize their results. Always spawn agents for "
        "non-trivial subtasks instead of doing everything yourself."
    ),
    "explorer": (
        "You are an Explorer agent. Research topics thoroughly.\n"
        "Tools:\n"
        "  [SEARCH: <query>]           — search the web via DuckDuckGo\n"
        "  [FETCH: <url>]              — fetch and read a web page\n"
        "  [IMAGINE: <prompt>]         — generate an AI image related to your research\n"
        "  [IMAGES: <keyword>]         — check local image library for relevant visuals\n"
        "  [API: <GET|POST> <url> <body?>] — query external data APIs\n"
        "  [SPAWN: <type> <task>]      — delegate sub-research to another agent\n"
        "  [DONE: <answer>]            — final answer\n\n"
        "Always cite sources. Use [IMAGINE] to create diagrams or illustrations. "
        "Be thorough. When you have enough info, output [DONE: your answer]."
    ),
    "coder": (
        "You are a Coder agent. Write, read, and modify code.\n"
        "Tools:\n"
        "  [READ: <path>]             — read a project file\n"
        "  [WRITE: <path>]\n<content>\n  — write code to a file (content follows on next lines)\n"
        "  [RUN: <command>]           — run a shell command\n"
        "  [GLOB: <pattern>]          — list files\n"
        "  [GREP: <pattern>]          — search file contents\n"
        "  [IMAGINE: <prompt>]        — generate an AI image (e.g., UI mockups, diagrams)\n"
        "  [IMAGES: <keyword>]        — check existing generated images\n"
        "  [API: <GET|POST> <url> <body?>] — call external APIs for testing\n"
        "  [SPAWN: <type> <task>]     — delegate sub-task to another agent\n"
        "  [DONE: <result>]           — final answer\n\n"
        "Write clean, working code following project conventions. "
        "When done, output [DONE: your result]."
    ),
    "planner": (
        "You are a Planner agent. Analyze and design solutions.\n"
        "Tools:\n"
        "  [SEARCH: <query>]           — search the web\n"
        "  [READ: <path>]              — read a project file\n"
        "  [GLOB: <pattern>]           — list files\n"
        "  [IMAGINE: <prompt>]         — generate diagrams, architecture visuals\n"
        "  [IMAGES: <keyword>]         — browse existing visuals for inspiration\n"
        "  [API: <GET> <url>]          — query reference APIs for data\n"
        "  [SPAWN: <type> <task>]      — delegate detailed work to a sub-agent\n"
        "  [DONE: <plan>]              — output your final plan\n\n"
        "Structure plans with steps, dependencies, and rationale. "
        "When done, output [DONE: your plan]."
    ),
    "debugger": (
        "You are a Debugger agent. Find and fix bugs systematically.\n"
        "Tools:\n"
        "  [READ: <path>]             — read a source file\n"
        "  [GREP: <pattern>]          — search code\n"
        "  [RUN: <command>]           — run tests or commands\n"
        "  [WRITE: <path>]\n<content>\n  — write a fix to a file\n"
        "  [IMAGINE: <prompt>]        — generate a screenshot or visual test output\n"
        "  [API: <GET|POST> <url> <body?>] — test API endpoints\n"
        "  [SPAWN: <type> <task>]     — delegate sub-task to another agent\n"
        "  [DONE: <resolution>]       — final answer\n\n"
        "Reproduce the bug, identify root cause, then fix it. "
        "When done, output [DONE: your resolution]."
    ),
}


def _save_agent_log(agent_type: str, task: str, result: str):
    _AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _AGENTS_DIR / "agent_log.json"
    with _FILE_LOCK:
        log = []
        if log_file.exists():
            try:
                log = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        log.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "type": agent_type,
            "task": task[:200],
            "result": result[:500],
        })
        if len(log) > 100:
            log = log[-100:]
        log_file.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_active_agents(agents: list[dict]):
    _AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    active_file = _AGENTS_DIR / "active.json"
    with _FILE_LOCK:
        active_file.write_text(json.dumps(agents, indent=2), encoding="utf-8")


def _load_active_agents() -> list[dict]:
    active_file = _AGENTS_DIR / "active.json"
    with _FILE_LOCK:
        if active_file.exists():
            try:
                return json.loads(active_file.read_text(encoding="utf-8"))
            except Exception:
                pass
    return []


def _save_context(agent_type: str, task: str, result: str, summary: str):
    _AGENT_CONTEXTS_DIR.mkdir(parents=True, exist_ok=True)
    ctx_file = _AGENT_CONTEXTS_DIR / f"{agent_type}.json"
    with _FILE_LOCK:
        ctx = []
        if ctx_file.exists():
            try:
                ctx = json.loads(ctx_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        ctx.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "task": task[:200],
            "result": result[:500],
            "summary": summary[:200],
        })
        if len(ctx) > 50:
            ctx = ctx[-50:]
        ctx_file.write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_context(agent_type: str) -> list:
    ctx_file = _AGENT_CONTEXTS_DIR / f"{agent_type}.json"
    if ctx_file.exists():
        try:
            return json.loads(ctx_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _get_context_summary(agent_type: str) -> str:
    ctx = _load_context(agent_type)
    if not ctx:
        return ""
    lines = ["## Past Context"]
    for entry in ctx[-5:]:
        date = entry.get("date", "?")
        task = entry.get("task", "?")[:60]
        summary = entry.get("summary", "")[:120]
        lines.append(f"- ({date}) {task}: {summary}")
    return "\n".join(lines)


def kill_agent(agent_type: str, task_prefix: str = ""):
    key = f"{agent_type}:{task_prefix}"
    _KILLED_AGENTS.add(key)


class AgentResult:
    def __init__(self, agent_type: str, task: str, answer: str,
                 tool_calls: int = 0, elapsed: float = 0.0,
                 sub_agent_results: list = None, spawn_count: int = 0):
        self.agent_type = agent_type
        self.task = task
        self.answer = answer
        self.tool_calls = tool_calls
        self.elapsed = elapsed
        self.sub_agent_results = sub_agent_results or []
        self.spawn_count = spawn_count

    def __str__(self) -> str:
        parts = [
            f"[{self.agent_type}] {self.elapsed:.1f}s, {self.tool_calls} tools"
        ]
        if self.sub_agent_results:
            parts.append(f"  spawned {len(self.sub_agent_results)} sub-agent(s)")
        parts.append(self.answer)
        return "\n".join(parts)


class Agent:
    """Autonomous agent with tool use, sub-agent spawning, and isolated context."""

    MAX_TOOL_CALLS = 20
    MAX_TURNS = 40
    MAX_EXECUTION_TIME = 120
    MAX_SUB_AGENT_DEPTH = 3
    MAX_SUB_AGENTS = 10

    def __init__(self, agent_type: str, llm_fn, parent=None, depth=0):
        if agent_type not in AGENT_PERSONAS:
            raise ValueError(
                f"Unknown agent type '{agent_type}'. "
                f"Choose: {', '.join(AGENT_PERSONAS)}"
            )
        self.agent_type = agent_type
        self.llm_fn = llm_fn
        self.parent = parent
        self.depth = depth
        self.project_root = Path(__file__).parent.parent.parent
        persona = AGENT_PERSONAS[agent_type]
        context_summary = _get_context_summary(agent_type)
        if context_summary:
            persona = persona + "\n\n" + context_summary
        self.messages = [{"role": "system", "content": persona}]
        self.tool_calls = 0
        self.start_time = time.time()
        self.sub_agent_results = []
        self.spawn_count = 0
        if parent is None:
            self._total_spawned = 0

    def _execute_tool(self, text: str) -> str | None:
        # WRITE (multiline, must be first since it spans multiple lines)
        write_match = re.search(r'\[WRITE:\s*(.*?)\]\s*\n(.*?)(?=\n\[|\Z)', text, re.DOTALL)
        if write_match:
            path = write_match.group(1).strip()
            content = write_match.group(2).strip()
            return self._tool_write(path, content)

        # SPAWN — delegate to a sub-agent
        m = re.search(r'\[SPAWN:\s*(\w+)\s+(.*?)\]', text, re.DOTALL)
        if m:
            sub_type = m.group(1).strip().lower()
            sub_task = m.group(2).strip()
            return self._tool_spawn(sub_type, sub_task)

        # IMAGINE — generate an AI image from a prompt
        m = re.search(r'\[IMAGINE:\s*(.*?)\]', text)
        if m:
            return self._tool_imagine(m.group(1).strip())

        # IMAGES — list locally stored generated images
        m = re.search(r'\[IMAGES(?::\s*(.*?))?\]', text)
        if m:
            return self._tool_list_images(m.group(1).strip() if m.group(1) else "")

        # API — call an external REST API
        m = re.search(r'\[API:\s*(\w+)\s+(https?://\S+)(?:\s+(.*?))?\]', text)
        if m:
            method = m.group(1).strip().upper()
            url = m.group(2).strip()
            body_str = m.group(3).strip() if m.group(3) else ""
            return self._tool_api(method, url, body_str)

        # SEARCH
        m = re.search(r'\[SEARCH:\s*(.*?)\]', text)
        if m:
            return self._tool_search(m.group(1).strip())

        # FETCH
        m = re.search(r'\[FETCH:\s*(.*?)\]', text)
        if m:
            return self._tool_fetch(m.group(1).strip())

        # READ
        m = re.search(r'\[READ:\s*(.*?)\]', text)
        if m:
            return self._tool_read(m.group(1).strip())

        # RUN
        m = re.search(r'\[RUN:\s*(.*?)\]', text)
        if m:
            return self._tool_run(m.group(1).strip())

        # GLOB
        m = re.search(r'\[GLOB:\s*(.*?)\]', text)
        if m:
            return self._tool_glob(m.group(1).strip())

        # GREP
        m = re.search(r'\[GREP:\s*(.*?)\]', text)
        if m:
            return self._tool_grep(m.group(1).strip())

        return None

    def _tool_search(self, query: str) -> str:
        self.tool_calls += 1
        try:
            from search import Search
            result = Search(query).search(max_results=5)
            return (f"[SEARCH RESULT: {query}]\n{result}"
                    if result else f"[SEARCH] No results for '{query}'")
        except Exception as e:
            return f"[SEARCH ERROR] {e}"

    def _tool_fetch(self, url: str) -> str:
        self.tool_calls += 1
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15)
            return f"[FETCH: {url}]\n{r.text[:3000]}"
        except Exception as e:
            return f"[FETCH ERROR] {e}"

    def _tool_read(self, path: str) -> str:
        self.tool_calls += 1
        full = self.project_root / path
        try:
            if not full.exists():
                full = Path(path).resolve()
            if full.exists() and full.is_file():
                content = full.read_text(encoding="utf-8", errors="replace")
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"
                rel = full.relative_to(self.project_root) if self.project_root in full.parents else full
                return f"[FILE: {rel}]\n{content}"
            return f"[ERROR] File not found: {path}"
        except Exception as e:
            return f"[READ ERROR] {e}"

    def _tool_write(self, path: str, content: str) -> str:
        self.tool_calls += 1
        full = self.project_root / path
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            rel = full.relative_to(self.project_root) if self.project_root in full.parents else full
            return f"[WRITTEN] {rel} ({len(content)} bytes)"
        except Exception as e:
            return f"[WRITE ERROR] {e}"

    def _tool_run(self, cmd: str) -> str:
        self.tool_calls += 1
        try:
            result = _subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=30, cwd=self.project_root,
            )
            out = (result.stdout or "")[:2000]
            err = (result.stderr or "")[:1000]
            parts = []
            if out:
                parts.append(f"[STDOUT]\n{out}")
            if err:
                parts.append(f"[STDERR]\n{err}")
            return "\n".join(parts) if parts else "(no output)"
        except _subprocess.TimeoutExpired:
            return "[ERROR] Command timed out after 30s"
        except Exception as e:
            return f"[RUN ERROR] {e}"

    def _tool_glob(self, pattern: str) -> str:
        self.tool_calls += 1
        try:
            files = list(self.project_root.glob(pattern))
            if not files:
                files = list(Path().glob(pattern))
            if files:
                lines = []
                for f in files[:30]:
                    rel = f.relative_to(self.project_root) if self.project_root in f.parents else f
                    lines.append(str(rel))
                return f"[GLOB: {pattern}] ({len(lines)} match(es))\n" + "\n".join(lines)
            return f"[GLOB] No files matching '{pattern}'"
        except Exception as e:
            return f"[GLOB ERROR] {e}"

    def _tool_grep(self, pattern: str) -> str:
        self.tool_calls += 1
        try:
            matches = []
            for f in self.project_root.rglob("*.py"):
                if not f.is_file():
                    continue
                try:
                    for i, line in enumerate(
                        f.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                    ):
                        if re.search(pattern, line, re.IGNORECASE):
                            rel = f.relative_to(self.project_root)
                            matches.append(f"{rel}:{i}: {line.strip()[:120]}")
                            if len(matches) >= 20:
                                break
                except Exception:
                    pass
                if len(matches) >= 20:
                    break
            if matches:
                return f"[GREP: '{pattern}'] ({len(matches)})\n" + "\n".join(matches)
            return f"[GREP] No matches for '{pattern}'"
        except Exception as e:
            return f"[GREP ERROR] {e}"

    def _tool_imagine(self, prompt: str) -> str:
        """Generate an AI image via the image_gen skill."""
        self.tool_calls += 1
        try:
            from skills.image_gen import generate_image
            path = generate_image(prompt)
            rel = path.relative_to(self.project_root) if self.project_root in path.parents else path
            return f"[IMAGINE: {prompt[:60]}]\nGenerated: {rel} ({path.stat().st_size:,} bytes)"
        except Exception as e:
            return f"[IMAGINE ERROR] {e}"

    def _tool_list_images(self, query: str = "") -> str:
        """List locally stored generated images, optionally filtered by keyword."""
        self.tool_calls += 1
        try:
            gen_dir = self.project_root / "generated"
            if not gen_dir.exists():
                return "[IMAGES] No generated images directory found."
            images = sorted(gen_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            if query:
                images = [p for p in images if query.lower() in p.stem.lower()]
            if not images:
                return f"[IMAGES] No images found{' for: ' + query if query else ''}."
            lines = [f"[IMAGES] Found {len(images)} image(s):"]
            for img in images[:20]:
                size = img.stat().st_size
                name = img.relative_to(self.project_root)
                lines.append(f"  {name} ({size:,}b)")
            return "\n".join(lines)
        except Exception as e:
            return f"[IMAGES ERROR] {e}"

    def _tool_api(self, method: str, url: str, body_str: str = "") -> str:
        """Call an external REST API with GET/POST/PUT/DELETE."""
        self.tool_calls += 1
        try:
            headers = {"User-Agent": "PixelAssistant/1.0", "Accept": "application/json"}
            body = None
            if body_str:
                import json as _json
                try:
                    body = _json.loads(body_str)
                    headers["Content-Type"] = "application/json"
                except _json.JSONDecodeError:
                    body = body_str

            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=15)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=body, timeout=15)
            elif method == "PUT":
                resp = requests.put(url, headers=headers, json=body, timeout=15)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=15)
            else:
                return f"[API ERROR] Unsupported method: {method}"

            content_type = resp.headers.get("Content-Type", "")
            if "image" in content_type:
                return f"[API: {method} {url}]\nHTTP {resp.status_code} ({len(resp.content)} bytes, {content_type})"
            try:
                text = resp.text[:3000]
                return f"[API: {method} {url}]\nHTTP {resp.status_code}\n{text}"
            except Exception:
                return f"[API: {method} {url}]\nHTTP {resp.status_code} ({len(resp.content)} bytes)"
        except requests.RequestException as e:
            return f"[API ERROR] {e}"
        except Exception as e:
            return f"[API ERROR] {e}"

    def _tool_spawn(self, sub_type: str, sub_task: str) -> str:
        """Spawn a sub-agent and return its result."""
        self.tool_calls += 1
        if sub_type not in AGENT_PERSONAS:
            return f"[SPAWN ERROR] Unknown agent type '{sub_type}'"
        if (self.depth or 0) >= Agent.MAX_SUB_AGENT_DEPTH:
            return "[SPAWN ERROR] Max sub-agent depth reached"
        root = self
        while root.parent:
            root = root.parent
        if not hasattr(root, '_total_spawned'):
            root._total_spawned = 0
        if root._total_spawned >= Agent.MAX_SUB_AGENTS:
            return "[SPAWN ERROR] Max sub-agents limit reached"
        try:
            sub = Agent(sub_type, self.llm_fn, parent=self, depth=self.depth + 1)
            result = sub.run(sub_task, max_turns=15)
            self.sub_agent_results.append(result)
            self.spawn_count += 1
            root._total_spawned += 1
            return (
                f"[SPAWN RESULT from {sub_type} agent]\n"
                f"Task: {sub_task[:100]}\n"
                f"Result: {result.answer[:1000]}"
            )
        except Exception as e:
            return f"[SPAWN ERROR] {e}"

    def run(self, task: str, max_turns: int | None = None) -> AgentResult:
        max_turns = max_turns or self.MAX_TURNS
        self.start_time = time.time()

        depth_prefix = "  " * getattr(self, '_depth', 0)
        _save_active_agents(_load_active_agents() + [
            {"type": self.agent_type, "task": task[:100],
             "started": datetime.now().strftime("%H:%M:%S")}
        ])

        self.messages.append({"role": "user", "content": task})

        for turn in range(max_turns):
            # Kill switch check
            for killed_key in list(_KILLED_AGENTS):
                k_type, k_prefix = killed_key.split(":", 1) if ":" in killed_key else (killed_key, "")
                if self.agent_type == k_type and task.startswith(k_prefix):
                    msg = "Killed."
                    _save_agent_log(self.agent_type, task, msg)
                    _save_context(self.agent_type, task, msg, msg)
                    return AgentResult(
                        self.agent_type, task, msg,
                        self.tool_calls, time.time() - self.start_time,
                        self.sub_agent_results,
                    )

            # Timeout check
            if time.time() - self.start_time > Agent.MAX_EXECUTION_TIME:
                msg = "Timeout: max execution time reached."
                _save_agent_log(self.agent_type, task, msg)
                _save_context(self.agent_type, task, msg, msg)
                return AgentResult(
                    self.agent_type, task, msg,
                    self.tool_calls, time.time() - self.start_time,
                    self.sub_agent_results,
                )

            result = self.llm_fn(self.messages)

            # DONE
            done_match = re.search(r'\[DONE:\s*(.*?)\]', result, re.DOTALL)
            if done_match:
                answer = done_match.group(1).strip()
                _save_agent_log(self.agent_type, task, answer)
                _save_context(self.agent_type, task, answer, answer[:200])
                return AgentResult(
                    self.agent_type, task, answer,
                    self.tool_calls, time.time() - self.start_time,
                    self.sub_agent_results,
                )

            # Tool execution
            tool_result = self._execute_tool(result)
            if tool_result:
                self.messages.append({"role": "assistant", "content": result})
                self.messages.append({"role": "user", "content": tool_result})
                continue

            # No tool, no DONE — final answer
            _save_agent_log(self.agent_type, task, result)
            _save_context(self.agent_type, task, result, result[:200])
            return AgentResult(
                self.agent_type, task, result,
                self.tool_calls, time.time() - self.start_time,
                self.sub_agent_results,
            )

        msg = "Max turns reached."
        _save_agent_log(self.agent_type, task, msg)
        _save_context(self.agent_type, task, msg, msg)
        return AgentResult(
            self.agent_type, task, msg,
            self.tool_calls, time.time() - self.start_time,
            self.sub_agent_results,
        )

    def run_async(self, task: str, callback=None) -> threading.Thread:
        def _run():
            result = self.run(task)
            if callback:
                callback(result)
            active = [a for a in _load_active_agents()
                      if a.get("type") != self.agent_type or a.get("task") != task[:100]]
            _save_active_agents(active)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t


# ── Auto-detection ─────────────────────────────────────────────────────────────

def detect_agent_type(query: str) -> str | None:
    """Automatically detect the best agent type for a query.
    Returns None if the query is simple enough for normal chat."""
    q = query.lower().strip()

    # Simple queries — no agent needed
    simple_patterns = [
        r"^(hi|hello|hey|what.up|how.are.you|thanks|goodbye|bye)$",
        r"^(yes|no|ok|okay|sure|maybe)$",
        r"^(what|who|when|where)\s+(is|was|are|were)\s+\w+[?.]?$",
        r"^(what's|what is|who is)\s+\w+[?.]?$",
        r"^\w+\s+(means|mean|definition|define)\??$",
    ]
    for pat in simple_patterns:
        if re.match(pat, q):
            return None

    # Detect agent type based on keywords
    signals = {
        "explorer": [
            "research", "find out", "look up", "search for", "investigate",
            "what is", "tell me about", "explain", "summarize", "news about",
            "latest", "trends", "information on", "facts about",
        ],
        "coder": [
            "write code", "create a", "implement", "build a", "develop",
            "program", "script", "function", "class", "module",
            "refactor", "add feature", "fix this code", "generate code",
        ],
        "planner": [
            "plan", "design", "strategy", "architecture", "blueprint",
            "roadmap", "steps to", "how to", "approach", "outline",
            "analyze", "break down", "structure",
        ],
        "debugger": [
            "debug", "bug", "error", "not working", "broken", "crash",
            "fix this", "issue", "problem", "failing", "traceback",
            "exception", "doesn't work",
        ],
    }

    scores = {}
    for agent_type, keywords in signals.items():
        scores[agent_type] = sum(1 for kw in keywords if kw in q)

    if not any(scores.values()):
        return None

    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else None


def auto_route(query: str, assistant) -> str | None:
    """Auto-detect and route a complex query to an agent.
    Returns the agent result string, or None if no agent is needed."""
    agent_type = detect_agent_type(query)
    if agent_type is None:
        return None

    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    console.print(Panel(
        f"[bold cyan]Auto-detected complex task[/bold cyan]\n"
        f"Routing to [bold]{agent_type}[/bold] agent...\n"
        f"[dim]Type: {query[:80]}[/dim]",
        border_style="cyan", expand=False,
    ))

    agent = Agent(agent_type, assistant._ask_llm)

    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]{agent_type} agent working...[/cyan]"),
        transient=True, console=console,
    ) as prog:
        prog.add_task("", total=None)
        result = agent.run(query)

    console.print(
        f"[bold green]{agent_type} done[/bold green] "
        f"({result.elapsed:.1f}s, {result.tool_calls} tools)"
    )
    if result.sub_agent_results:
        for sr in result.sub_agent_results:
            console.print(f"  [dim]↳ spawned {sr.agent_type} ({sr.elapsed:.1f}s)[/dim]")

    return str(result)


# ── UI helpers ─────────────────────────────────────────────────────────────────

def list_agent_types() -> str:
    lines = ["Available agents:\n"]
    for name, persona in AGENT_PERSONAS.items():
        desc = persona.split(".")[0]
        for prefix in ["You are an ", "You are a "]:
            if prefix in desc:
                desc = desc.split(prefix)[1]
                break
        lines.append(f"  {name:12s}  {desc}")
    lines.append("\nUsage: /agent <type> <task>")
    lines.append("       /agent auto <task>        auto-detect best agent")
    lines.append("       /agent background <type> <task>  run in background")
    lines.append("       /agent status             show active agents")
    lines.append("       /agent list               list agent types")
    lines.append("       /agent history             show past runs")
    return "\n".join(lines)


def list_agent_history() -> str:
    log_file = _AGENTS_DIR / "agent_log.json"
    if not log_file.exists():
        return "No agent runs recorded yet."
    try:
        log = json.loads(log_file.read_text(encoding="utf-8"))
    except Exception:
        return "Could not read agent log."
    if not log:
        return "No agent runs recorded."
    lines = ["Agent run history (last 20):\n"]
    for i, entry in enumerate(reversed(log[-20:]), 1):
        lines.append(
            f"  {i:>2}. [{entry['date']}] {entry['type']:12s} "
            f"{entry['task'][:60]}"
        )
    return "\n".join(lines)


def active_agent_status() -> str:
    active = _load_active_agents()
    if not active:
        return "No agents currently active."
    lines = ["Active agents:\n"]
    for a in active:
        lines.append(f"  [{a['type']}] {a['task'][:60]} — started {a['started']}")
    return "\n".join(lines)


# ── API helpers ─────────────────────────────────────────────────────────────────

def get_active_agents_json() -> str:
    return json.dumps(_load_active_agents(), indent=2, ensure_ascii=False)


def get_agent_history_json() -> str:
    log_file = _AGENTS_DIR / "agent_log.json"
    if log_file.exists():
        try:
            return log_file.read_text(encoding="utf-8")
        except Exception:
            pass
    return json.dumps([])


def get_context_json(agent_type: str) -> str:
    return json.dumps(_load_context(agent_type), indent=2, ensure_ascii=False)
