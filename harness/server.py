from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import secrets
import shutil
import threading
from urllib.parse import urlsplit, unquote
import uuid

from .common import ROOT, DATA, now, read_json, write_json, safe_name, under, runtime
from .engine import Runner
from .materials import SUPPORTED, IMAGES

MAX_UPLOAD = 40 * 1024 * 1024


class Manager:
    def __init__(self, root=DATA):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.active, self.credentials = {}, {}
        self.lock = threading.RLock()
        for path in self.root.glob('*/state.json'):
            state = read_json(path)
            if state['status'] in ('running', 'queued'):
                state['status'], state['stage'] = 'paused', '上次运行已保存，可继续'
                write_json(path, state)

    def directory(self, run_id):
        if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
            raise ValueError('作业编号无效')
        path = under(self.root, run_id)
        if not (path / 'state.json').exists():
            raise FileNotFoundError()
        return path

    def upload(self, path, files, offset=0):
        result, size = [], 0
        folder = path / 'uploads'
        folder.mkdir(exist_ok=True)
        if len(files) > 30:
            raise ValueError('每次最多上传 30 个文件。')
        for i, item in enumerate(files):
            role = item.get('role')
            if role not in ('question', 'material', 'template'):
                raise ValueError('文件用途无效')
            name = safe_name(item.get('name', 'file'))
            suffix = Path(name).suffix.lower()
            if suffix not in SUPPORTED or role == 'question' and suffix not in IMAGES:
                raise ValueError('题目请上传 PNG、JPG 或 WebP；材料支持 DOCX、PDF、XLSX、文本与图片。')
            raw = base64.b64decode(item.get('data', ''), validate=True)
            size += len(raw)
            if size > MAX_UPLOAD:
                raise ValueError('单次文件总量请控制在 40 MB 以内。')
            relative = 'uploads/' + str(offset+i) + '-' + name
            (path / relative).write_bytes(raw)
            result.append({'name': name, 'role': role, 'path': relative})
        return result

    def create(self, payload):
        files = payload.get('files', [])
        if not any(f.get('role') == 'question' for f in files):
            raise ValueError('请先上传当次题目图片。')
        config = payload.get('config', {})
        if config.get('provider', 'codex') not in ('codex', 'api'):
            raise ValueError('模型连接方式无效')
        run_id = uuid.uuid4().hex
        path = self.root / run_id
        path.mkdir()
        stored = self.upload(path, files)
        private = {k: v for k, v in config.items() if k == 'api_key'}
        public = {k: v for k, v in config.items() if k in ('provider', 'model', 'api_base', 'web_search', 'call_timeout')}
        metadata = payload.get('metadata', {})
        for key in ('word_min', 'word_max', 'slide_count'):
            metadata[key] = max(0, int(metadata.get(key) or 0))
        state = {'id': run_id, 'status': 'queued', 'stage': '准备开始', 'started_at': now(),
                 'updated_at': now(), 'metadata': metadata, 'config': public, 'files': stored,
                 'steps': {}, 'events': [], 'timings': [], 'answers': [], 'questions': [],
                 'problem_statement': '', 'feedback': '', 'model_calls': []}
        write_json(path / 'state.json', state)
        self.credentials[run_id] = private
        self.start(run_id)
        return self.snapshot(run_id)

    def start(self, run_id):
        with self.lock:
            if run_id in self.active:
                raise ValueError('这份作业正在运行，请勿重复开始。')
            runner = Runner(self.directory(run_id), self.credentials.get(run_id, {}))
            self.active[run_id] = runner
        def work():
            try:
                runner.execute()
            finally:
                with self.lock:
                    self.active.pop(run_id, None)
        self.pool.submit(work)

    def resume(self, run_id, payload):
        with self.lock:
            if run_id in self.active:
                raise ValueError('请先暂停当前运行。')
            path = self.directory(run_id)
            state = read_json(path / 'state.json')
            feedback, statement = payload.get('feedback', ''), payload.get('statement', '')
            new_files = payload.get('files', [])
            if payload.get('api_key'):
                self.credentials[run_id] = {'api_key': payload['api_key']}
            if feedback or statement or new_files:
                history = path / 'history' / uuid.uuid4().hex[:10]
                history.mkdir(parents=True)
                write_json(history / 'state.json', state)
                if (path / 'calls').exists():
                    shutil.move(str(path / 'calls'), str(history / 'calls'))
                state['feedback'] += '\n' + feedback
                if statement and statement != state['problem_statement']:
                    state['statement_override'] = statement
                    state['steps'] = {}
                elif feedback and state['steps'].get('transcription', {}).get('unclear'):
                    state['steps'] = {}
                else:
                    state['steps'] = {k: v for k, v in state['steps'].items() if k == 'transcription'}
                state['files'] += self.upload(path, new_files, len(state['files']))
                state['answers'] = []
                state.pop('finished_at', None)
                state.pop('web_cache', None)
            state['status'] = 'queued'
            write_json(path / 'state.json', state)
        self.start(run_id)
        return self.snapshot(run_id)

    def snapshot(self, run_id):
        state = read_json(self.directory(run_id) / 'state.json')
        from datetime import datetime, timezone
        end = datetime.fromisoformat(state['finished_at']) if state.get('finished_at') else datetime.now(timezone.utc)
        elapsed = (end - datetime.fromisoformat(state['started_at'])).total_seconds()
        outputs = state.get('steps', {}).get('export', {}) if state['status'] == 'completed' else {}
        return {k: state.get(k) for k in ['id', 'status', 'stage', 'started_at', 'updated_at', 'metadata',
                 'problem_statement', 'questions', 'questions_for_user', 'events', 'timings', 'error', 'time']} | {
                     'elapsed_seconds': elapsed, 'answered': len(state.get('answers', [])),
                     'outputs': outputs,
                     'files': [{'name': f['name'], 'role': f['role']} for f in state['files']]}

    def list_runs(self):
        return sorted([self.snapshot(p.parent.name) for p in self.root.glob('*/state.json')],
                      key=lambda s: s['started_at'], reverse=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = unquote(urlsplit(self.path).path)
        try:
            if route == '/api/config':
                return self.respond({'token': self.server.token, 'default_provider': 'codex',
                                     'has_codex': bool(shutil.which('codex') or Path('/opt/homebrew/bin/codex').exists())})
            if route == '/api/runs':
                return self.respond(self.server.manager.list_runs())
            parts = route.strip('/').split('/')
            if len(parts) == 3 and parts[:2] == ['api', 'runs']:
                return self.respond(self.server.manager.snapshot(parts[2]))
            if len(parts) >= 4 and parts[:2] == ['download', 'runs']:
                directory = self.server.manager.directory(parts[2])
                if read_json(directory / 'state.json')['status'] != 'completed':
                    raise ValueError('文件正在处理，请完成后下载。')
                path = under(directory / 'output', '/'.join(parts[3:]))
            else:
                path = under(ROOT / 'static', route.lstrip('/') or 'index.html')
            if not path.is_file():
                raise FileNotFoundError()
            data = path.read_bytes()
            self.send_response(200)
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.respond({'error': '找不到文件或作业'}, 404)
        except ValueError as exc:
            self.respond({'error': str(exc)}, 400)

    def do_POST(self):
        if self.headers.get('X-Harness-Token') != self.server.token:
            return self.respond({'error': '请刷新页面后重试'}, 403)
        try:
            size = int(self.headers.get('Content-Length', 0))
            if size <= 0 or size > 60 * 1024 * 1024:
                raise ValueError('请求大小超出范围')
            payload = json.loads(self.rfile.read(size))
            route = urlsplit(self.path).path
            if route == '/api/runs':
                return self.respond(self.server.manager.create(payload), 201)
            parts = route.strip('/').split('/')
            if len(parts) == 4 and parts[:2] == ['api', 'runs']:
                run_id, action = parts[2:]
                if action == 'resume':
                    return self.respond(self.server.manager.resume(run_id, payload))
                if action == 'pause':
                    runner = self.server.manager.active.get(run_id)
                    if runner:
                        runner.stop.set()
                    return self.respond({'ok': True})
            raise ValueError('操作无效')
        except (ValueError, KeyError) as exc:
            self.respond({'error': str(exc)}, 400)
        except FileNotFoundError:
            self.respond({'error': '找不到作业'}, 404)
        except Exception:
            self.respond({'error': '操作未完成，请检查本地运行窗口。'}, 500)


def serve(port=8787):
    manager = Manager()
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', candidate), Handler)
            break
        except OSError:
            if candidate == port + 9:
                raise
    server.manager, server.token = manager, secrets.token_urlsafe(32)
    print(f'MIS303 已启动：http://127.0.0.1:{server.server_port}', flush=True)
    print('关闭此窗口即可停止服务。', flush=True)
    try:
        server.serve_forever()
    finally:
        for runner in list(manager.active.values()):
            runner.stop.set()
        manager.pool.shutdown(wait=True, cancel_futures=True)
        server.server_close()
