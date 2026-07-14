from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL = None
TOKENIZER = None
MODEL_ID = ""
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
LOCK = threading.Lock()


def load_model(model_id: str) -> None:
    global MODEL, TOKENIZER, MODEL_ID
    if MODEL is not None:
        return
    MODEL_ID = model_id
    print(f"[local-llm] loading {model_id} on {DEVICE}", flush=True)
    TOKENIZER = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    kwargs: dict[str, Any] = {"trust_remote_code": True}
    if DEVICE == "cuda":
        kwargs["torch_dtype"] = torch.float16
    MODEL = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    MODEL.to(DEVICE)
    MODEL.eval()
    print("[local-llm] ready", flush=True)


def generate_chat(messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str:
    assert MODEL is not None and TOKENIZER is not None
    if hasattr(TOKENIZER, "apply_chat_template"):
        prompt = TOKENIZER.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages) + "\nassistant:"
    inputs = TOKENIZER(prompt, return_tensors="pt").to(DEVICE)
    input_len = inputs["input_ids"].shape[-1]
    do_sample = temperature > 0
    with LOCK, torch.inference_mode():
        output = MODEL.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=do_sample,
            temperature=temperature if do_sample else None,
            top_p=0.9 if do_sample else None,
            repetition_penalty=1.05,
            pad_token_id=TOKENIZER.eos_token_id,
        )
    return TOKENIZER.decode(output[0][input_len:], skip_special_tokens=True).strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "StateWeaverLocalLLM/1.0"

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            return self.json_response({
                "object": "list",
                "data": [{"id": MODEL_ID, "object": "model", "owned_by": "local"}],
            })
        if self.path.rstrip("/") == "/health":
            return self.json_response({"ok": True, "model": MODEL_ID, "device": DEVICE})
        return self.json_response({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self.json_response({"error": "not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            messages = payload.get("messages", [])
            max_tokens = int(payload.get("max_tokens", 512))
            temperature = float(payload.get("temperature", 0.2))
            start = time.time()
            content = generate_chat(messages, max_tokens=max_tokens, temperature=temperature)
            return self.json_response({
                "id": f"chatcmpl-local-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": MODEL_ID,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                "stateweaver_elapsed_sec": round(time.time() - start, 3),
            })
        except Exception as exc:
            return self.json_response({"error": str(exc)}, status=500)

    def json_response(self, obj: dict, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tiny OpenAI-compatible local LLM server for StateWeaver.")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8016)
    args = parser.parse_args()
    load_model(args.model)
    print(f"[local-llm] serving http://{args.host}:{args.port}/v1", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
