"""Local coach with loopback HTTP and stdio transports. Load weights from disk."""
import argparse
import json
import os
import queue
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from protocol import messages, validate_rating, validate_review
from run_metrics import baseline_rating, summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, help='Local instruct-model directory')
    parser.add_argument('--adapter', help='Local PEFT LoRA directory, trained on the same base')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--context', type=int, default=8192)
    parser.add_argument('--rating-only', action='store_true', help='Ask for a numeric review')
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
    mode_path = Path(args.adapter) / "coach_mode.json" if args.adapter else None
    mode = json.loads(mode_path.read_text(encoding="utf-8")) if mode_path and mode_path.is_file() else {}
    rating_only = args.rating_only or mode.get("rating_only", False)
    include_summary = not args.adapter or mode.get("run_summary", False)
    model.eval()
    if args.check_model:
        return
    context = min(args.context, getattr(model.config, 'max_position_embeddings', args.context))
    source = 'local LoRA model' if args.adapter else 'local base model (no LoRA adapter)'

    def generate(run, score_only, condensed=False):
        chat = messages(run, rating_only=score_only, include_summary=include_summary, condensed=condensed)
        prompt = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        max_output = 48 if score_only else 650
        tokens = tokenizer(prompt, return_tensors='pt', add_special_tokens=False).to(device)
        prompt_limit = min(context, mode.get("condense_context", context))
        if tokens.input_ids.shape[1] + max_output > prompt_limit:
            return None
        with torch.inference_mode():
            output = model.generate(**tokens, max_new_tokens=max_output, do_sample=False,
                                    pad_token_id=tokenizer.eos_token_id)
        raw = tokenizer.decode(output[0, tokens.input_ids.shape[1]:], skip_special_tokens=True).strip()
        if raw.startswith('```') and '\n' in raw:
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        return raw

    def rubric_review(run, notice):
        return {'rating': baseline_rating(summarize(run)), 'source': 'gameplay rubric',
                'notice': notice}

    def review(run):
        required = ('inputs', 'hits', 'level', 'duration', 'completed')
        if not isinstance(run, dict) or not all(key in run for key in required):
            raise ValueError('missing gameplay data')

        condensed = False
        raw = generate(run, rating_only)
        if raw is None and "condense_context" in mode:
            condensed = True
            raw = generate(run, rating_only, condensed=True)
        if raw is None:
            return rubric_review(run, 'The full replay exceeded the model input limit. Scored using the gameplay rubric.')

        summary_notice = "The coach rated this long replay using its input summary." if condensed else None
        try:
            decoded = json.loads(raw)
            if rating_only and type(decoded) is int:
                decoded = {'rating': decoded}
            result = validate_rating(decoded)
        except (ValueError, TypeError):
            if not rating_only:
                retry = generate(run, True, condensed=condensed)
                try:
                    score = json.loads(retry) if retry else None
                    result = validate_rating({'rating': score} if type(score) is int else score)
                    return dict(result, source=source,
                                notice=summary_notice or 'The first model reply was invalid. The coach retried for a rating.')
                except (ValueError, TypeError):
                    pass
            return rubric_review(run, 'The model did not return a valid rating. Scored using the gameplay rubric.')

        if not rating_only:
            try:
                result = validate_review(decoded)
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                return dict(result, source=source,
                            notice=f'{summary_notice or "The coach rated the run."} Its proposed level was rejected: {error}.')
        if summary_notice:
            return dict(result, source=source, notice=summary_notice)
        return dict(result, source=source)

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
