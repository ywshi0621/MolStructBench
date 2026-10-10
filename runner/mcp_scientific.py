"""Minimal MCP stdio server exposing one sandboxed scientific shell tool."""
import json
import os
import sys
from runner.sandbox import execute

WORKSPACE = os.environ["SCIBENCH_WORKSPACE"]
VENV = os.environ["SCIBENCH_VENV"]
TIMEOUT = int(os.environ.get("SCIBENCH_TOOL_TIMEOUT", "180"))
MAX_CALLS = int(os.environ.get("SCIBENCH_MAX_TOOL_CALLS", "32"))
CALLS = 0

TOOL = {
    "name": "shell",
    "description": (
        "Execute a Linux shell command in an isolated scientific computing workspace. "
        "Python, NumPy, SciPy, pandas, NetworkX, RDKit and Open Babel are available. "
        "The current public task is at /workspace/input/task.json (read-only). "
        "Writable paths are /workspace/output and /workspace/tmp. The shell has no network access."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "Shell command to execute"}},
        "required": ["command"],
        "additionalProperties": False,
    },
}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def result(req_id, payload):
    send({"jsonrpc": "2.0", "id": req_id, "result": payload})


def error(req_id, code, message):
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(msg):
    global CALLS
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion") or "2024-11-05"
        result(req_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "scibench-scientific", "version": "1.0.0"},
        })
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return
    elif method == "ping":
        result(req_id, {})
    elif method == "tools/list":
        result(req_id, {"tools": [TOOL]})
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != "shell":
            error(req_id, -32602, "Unknown tool")
            return
        command = args.get("command")
        if not isinstance(command, str) or not command:
            error(req_id, -32602, "command must be a non-empty string")
            return
        CALLS += 1
        if CALLS > MAX_CALLS:
            result(req_id, {"content": [{"type": "text", "text": json.dumps({"status":"error","output":"tool call budget exhausted"}, separators=(",",":"))}], "isError": True})
            return
        try:
            out = execute(WORKSPACE, VENV, command, TIMEOUT)
        except Exception as exc:
            out = {"exit_code": None, "status": "error", "output": f"scientific sandbox unavailable: {type(exc).__name__}"}
        text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
        result(req_id, {"content": [{"type": "text", "text": text}], "isError": out.get("status") != "ok"})
    elif req_id is not None:
        error(req_id, -32601, "Method not found")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if isinstance(msg, dict):
                handle(msg)
        except Exception as exc:
            # stderr is safe for MCP diagnostics; never write non-protocol text to stdout.
            print(type(exc).__name__, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
