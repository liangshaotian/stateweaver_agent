from __future__ import annotations

import json
import mimetypes
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from b1_runtime.runtime import AgentRuntime


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DEFAULT_CONFIG = ROOT / "configs" / "runtime_input.json"
UPLOAD_ROOT = ROOT / "uploads"
HOST = "127.0.0.1"
PORT = 8066
API_TOKEN = "stateweaver-20236533"


def safe_path(rel_path: str) -> Path:
    target = (ROOT / rel_path).resolve()
    if target != ROOT and ROOT not in target.parents:
        raise ValueError("path escapes project root")
    return target


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def upload_name(filename: str) -> str:
    name = Path(filename).name.strip().replace(" ", "_")
    name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    name = name.strip("._") or "upload"
    return name[:120]


def unique_upload_path(filename: str) -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = upload_name(filename)
    target = UPLOAD_ROOT / safe_name
    if not target.exists():
        return target
    stem = target.stem or "upload"
    suffix = target.suffix
    for i in range(1, 1000):
        candidate = UPLOAD_ROOT / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError("too many duplicate uploaded filenames")


def parse_multipart_files(body: bytes, content_type: str) -> list[tuple[str, bytes]]:
    match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if not match:
        raise ValueError("missing multipart boundary")
    boundary = match.group("boundary").strip().strip('"').encode("utf-8")
    files: list[tuple[str, bytes]] = []
    for part in body.split(b"--" + boundary):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", 1)
        headers = raw_headers.decode("utf-8", errors="replace")
        filename_match = re.search(r'filename="(?P<filename>[^"]*)"', headers)
        if not filename_match:
            continue
        filename = filename_match.group("filename")
        if not filename:
            continue
        if content.endswith(b"\r\n"):
            content = content[:-2]
        files.append((filename, content))
    return files


def trace_records() -> list[dict]:
    trace_path = ROOT / "traces" / "demo_001.jsonl"
    if not trace_path.exists():
        return []
    records = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def project_status() -> dict:
    files = {
        "config": "configs/runtime_input.json",
        "report": "outputs/demo_001/report.md",
        "summary": "outputs/demo_001/summary.json",
        "trace": "traces/demo_001.jsonl",
        "checkpoint": "checkpoints/demo_001.json",
        "memory": "configs/memory.json",
    }
    file_info = {}
    for key, rel in files.items():
        try:
            target = safe_path(rel)
            file_info[key] = {
                "path": rel,
                "exists": target.exists(),
                "size": target.stat().st_size if target.exists() else 0,
            }
        except Exception as exc:
            file_info[key] = {"path": rel, "exists": False, "size": 0, "error": str(exc)}
    trace = trace_records()[-20:]
    return {
        "project_root": str(ROOT),
        "status": "ready" if trace else "idle",
        "files": file_info,
        "trace": trace,
    }


def openapi_schema() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "StateWeaver Agent API",
            "version": "1.0.0",
            "description": "Run and inspect a local traceable tool-calling Agent for document and table analysis.",
        },
        "servers": [{"url": "https://YOUR_PUBLIC_HTTPS_DOMAIN"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "token",
                }
            }
        },
        "security": [{"bearerAuth": []}],
        "paths": {
            "/api/agent/status": {
                "get": {
                    "operationId": "getAgentStatus",
                    "summary": "Get current StateWeaver Agent status and output file metadata.",
                    "responses": {
                        "200": {
                            "description": "Current agent status.",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
            "/api/agent/run": {
                "post": {
                    "operationId": "runStateWeaverAgent",
                    "summary": "Run the StateWeaver Agent with an optional task configuration override.",
                    "requestBody": {
                        "required": False,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "user_input": {
                                            "type": "string",
                                            "description": "Natural-language task instruction for the agent.",
                                        },
                                        "allowed_files": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "Relative local files the agent may read.",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Run result and updated status.",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
            "/api/agent/read_file": {
                "get": {
                    "operationId": "readAgentOutputFile",
                    "summary": "Read an output, trace, checkpoint, memory, or config file under the project directory.",
                    "parameters": [
                        {
                            "name": "path",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Relative path, for example outputs/demo_001/report.md.",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "File content.",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "StateWeaverWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_file(WEB_ROOT / "index.html")
        if parsed.path == "/openapi.json":
            return self.json_response(openapi_schema())
        if parsed.path.startswith("/static/"):
            return self.serve_file(WEB_ROOT / parsed.path.removeprefix("/static/"))
        if parsed.path == "/api/status":
            return self.json_response(project_status())
        if parsed.path == "/api/agent/status":
            if not self.authorized():
                return self.json_response({"error": "unauthorized"}, status=401)
            return self.json_response(project_status())
        if parsed.path == "/api/config":
            return self.json_response(read_json(DEFAULT_CONFIG))
        if parsed.path == "/api/file":
            qs = parse_qs(parsed.query)
            rel = qs.get("path", [""])[0]
            try:
                target = safe_path(rel)
                if not target.exists():
                    return self.json_response({"error": "file not found", "path": rel}, status=404)
                return self.json_response({"path": rel, "content": target.read_text(encoding="utf-8")})
            except Exception as exc:
                return self.json_response({"error": str(exc)}, status=400)
        if parsed.path == "/api/agent/read_file":
            if not self.authorized():
                return self.json_response({"error": "unauthorized"}, status=401)
            qs = parse_qs(parsed.query)
            rel = qs.get("path", [""])[0]
            return self.read_file_response(rel)
        return self.json_response({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/run":
            return self.run_agent()
        if parsed.path == "/api/upload":
            return self.upload_files()
        if parsed.path == "/api/agent/run":
            if not self.authorized():
                return self.json_response({"error": "unauthorized"}, status=401)
            return self.run_agent_action()
        if parsed.path == "/api/config":
            return self.save_config()
        return self.json_response({"error": "not found"}, status=404)

    def authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {API_TOKEN}"

    def run_agent(self) -> None:
        try:
            runtime = AgentRuntime(DEFAULT_CONFIG)
            result = runtime.run()
            return self.json_response({"ok": True, "result": result, "status": project_status()})
        except Exception:
            return self.json_response({"ok": False, "error": traceback.format_exc()}, status=500)

    def run_agent_action(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}") if length else {}
            if payload:
                cfg = read_json(DEFAULT_CONFIG)
                if "user_input" in payload:
                    cfg["user_input"] = payload["user_input"]
                if "allowed_files" in payload:
                    cfg["allowed_files"] = payload["allowed_files"]
                DEFAULT_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            runtime = AgentRuntime(DEFAULT_CONFIG)
            result = runtime.run()
            return self.json_response({
                "ok": True,
                "result": result,
                "status": project_status(),
                "suggested_files": [
                    "outputs/demo_001/report.md",
                    "outputs/demo_001/summary.json",
                    "traces/demo_001.jsonl",
                    "checkpoints/demo_001.json",
                    "configs/memory.json",
                ],
            })
        except Exception:
            return self.json_response({"ok": False, "error": traceback.format_exc()}, status=500)

    def read_file_response(self, rel: str) -> None:
        try:
            target = safe_path(rel)
            if not target.exists():
                return self.json_response({"error": "file not found", "path": rel}, status=404)
            return self.json_response({"path": rel, "content": target.read_text(encoding="utf-8")})
        except Exception as exc:
            return self.json_response({"error": str(exc)}, status=400)

    def save_config(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            DEFAULT_CONFIG.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return self.json_response({"ok": True, "config": payload})
        except Exception as exc:
            return self.json_response({"ok": False, "error": str(exc)}, status=400)

    def upload_files(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return self.json_response({"ok": False, "error": "empty upload"}, status=400)
            content_type = self.headers.get("Content-Type", "")
            files = parse_multipart_files(self.rfile.read(length), content_type)
            if not files:
                return self.json_response({"ok": False, "error": "no files found in upload"}, status=400)
            saved = []
            for original_name, content in files:
                target = unique_upload_path(original_name)
                target.write_bytes(content)
                rel_path = target.relative_to(ROOT).as_posix()
                saved.append({"name": original_name, "path": rel_path, "size": len(content)})
            return self.json_response({"ok": True, "files": saved})
        except Exception as exc:
            return self.json_response({"ok": False, "error": str(exc)}, status=400)

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            return self.json_response({"error": "file not found"}, status=404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, obj: dict | list, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    print(f"StateWeaver web UI: http://{HOST}:{PORT}")
    print(f"Project root: {ROOT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
