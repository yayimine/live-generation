"""Local coach with loopback HTTP and stdio transports. Load weights from disk."""
import argparse
import json
import os
import queue
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from protocol import messages, validate_review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, help='Local instruct-model directory')
    parser.add_argument('--adapter', help='Local PEFT LoRA directory, trained on the same base')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--context', type=int, default=8192)
    parser.add_argument('--stdio', action='store_true', help='Exchange JSON lines with a parent process')
    parser.add_argument('--check-model', action='store_true', help='Load the model and adapter, then exit')
    args = parser.parse_args()
    if args.stdio:
        replies = sys.stdout
        sys.stdout = sys.stderr
        requests = queue.Queue(maxsize=1)

        def read_requests():
            for line in sys.stdin:
                requests.put(line)
            # The player closes stdin on exit, even if it was terminated.
            os._exit(0)

        threading.Thread(target=read_requests, daemon=True).start()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True,
        torch_dtype=torch.float32 if device == 'cpu' else torch.float16).to(device)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter, local_files_only=True)
    model.eval()
    if args.check_model:
        return
    context = min(args.context, getattr(model.config, 'max_position_embeddings', args.context))
    source = 'local LoRA model' if args.adapter else 'local base model (no LoRA adapter)'

    def review(run):
        if not isinstance(run, dict) or not all(k in run for k in ('inputs','hits','level','duration')):
            raise ValueError('missing gameplay data')
        prompt = tokenizer.apply_chat_template(messages(run), tokenize=False, add_generation_prompt=True)
        tokens = tokenizer(prompt, return_tensors='pt', add_special_tokens=False).to(device)
        if tokens.input_ids.shape[1] + 650 > context:
            raise ValueError('Full replay exceeds context. Use a larger context/model; replay was not truncated.')
        with torch.inference_mode():
            output = model.generate(**tokens, max_new_tokens=650, do_sample=False,
                                    pad_token_id=tokenizer.eos_token_id)
        raw = tokenizer.decode(output[0, tokens.input_ids.shape[1]:], skip_special_tokens=True).strip()
        # Permit a markdown fence, but never silently repair gameplay geometry.
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        result = validate_review(json.loads(raw))
        result['source'] = source
        return result

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            self.reply(200 if self.path == '/health' else 404, {'source': source, 'device': device})

        def do_POST(self):
            if self.path != '/review':
                return self.reply(404, {'error': 'unknown route'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2_000_000:
                    raise ValueError('invalid payload size')
                run = json.loads(self.rfile.read(size))
                self.reply(200, review(run))
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                self.reply(422, {'error': str(error)})
            except Exception as error:
                self.reply(500, {'error': str(error)})

    if args.stdio:
        print(json.dumps({'ready': True}), file=replies, flush=True)
        while True:
            try:
                result = review(json.loads(requests.get()))
            except Exception as error:
                result = {'error': str(error)}
            print(json.dumps(result, allow_nan=False), file=replies, flush=True)

    print(f'Coach ready: http://127.0.0.1:{args.port} | {source} | {device}', flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()

if __name__ == '__main__':
    main()
