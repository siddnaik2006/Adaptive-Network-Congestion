"""Local HTTP service serving dashboard and REST APIs with strict UTF-8 encoding."""
import argparse
import csv
import io
import json
import os
import secrets
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Any

from .engine import Engine
from .topologies import list_topologies, TOPOLOGIES

ROOT = Path(__file__).resolve().parents[1]

def serve(source: str = 'simulation', port: int = 8080, topology: str = 'diamond'):
    engine = Engine(ROOT, source=source, topology=topology)
    token = os.environ.get('CN_AGENT_TOKEN', '')
    
    if source == 'mininet' and len(token) < 16:
        raise SystemExit('Set CN_AGENT_TOKEN to a shared secret of at least 16 characters for Mininet mode.')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code: int, data: Any, kind: str = 'application/json'):
            """Send HTTP response with explicit UTF-8 encoding and headers."""
            if kind == 'application/json':
                text = json.dumps(data)
            elif isinstance(data, str):
                text = data
            else:
                text = str(data)
                
            payload = text.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', f"{kind}; charset=utf-8")
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self) -> bool:
            return bool(token) and secrets.compare_digest(self.headers.get('Authorization', ''), f"Bearer {token}")

        def do_GET(self):
            route = self.path.split('?')[0]
            
            if route == '/api/state':
                return self.reply(200, engine.state())
                
            if route == '/api/topologies':
                return self.reply(200, list_topologies())
                
            if route == '/api/export':
                return self.reply(200, engine.csv_text(), 'text/csv')
                
            if route == '/api/controller/route':
                if not self.authorized():
                    return self.reply(401, {'error': 'Agent token required'})
                return self.reply(200, {'route': engine.state()['route']})

            files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
            if route in files:
                name = files[route]
                kind = {'html': 'text/html', 'js': 'application/javascript', 'css': 'text/css'}[name.split('.')[-1]]
                file_path = ROOT / 'web' / name
                if not file_path.exists():
                    return self.reply(404, {'error': f"File not found: {name}"})
                # Explicit UTF-8 read prevents Windows ANSI / CP1252 corruption
                content = file_path.read_text(encoding='utf-8')
                return self.reply(200, content, kind)

            self.reply(404, {'error': 'Not found'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            host = self.headers.get('Host')
            if origin and host and origin != f"http://{host}":
                return self.reply(403, {'error': 'Cross-origin control rejected'})
                
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size > 500000:
                    return self.reply(413, {'error': 'Request too large'})
                body_bytes = self.rfile.read(size) if size > 0 else b'{}'
                data = json.loads(body_bytes.decode('utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('JSON object required')
                    
                if self.path in ['/api/telemetry', '/api/controller/ack', '/api/probe']:
                    if not self.authorized():
                        return self.reply(401, {'error': 'Agent token required'})
                    if self.path == '/api/telemetry':
                        engine.ingest(data)
                    elif self.path == '/api/controller/ack':
                        engine.acknowledge(data.get('route'))
                    else:
                        engine.probe(data)
                    return self.reply(200, {'ok': True})

                if self.path == '/api/control':
                    with engine.lock:
                        engine.configure(
                            mode=data.get('mode'),
                            scenario=data.get('scenario'),
                            topology=data.get('topology'),
                            foreground_mbps=data.get('foreground_mbps'),
                            link_capacity=data.get('link_capacity'),
                            duration=data.get('duration')
                        )
                        action = data.get('action')
                        if action == 'start':
                            engine.running = True
                        elif action == 'pause':
                            engine.running = False
                        elif action == 'step':
                            engine.step()
                        elif action == 'reset':
                            engine.archive()
                            engine.running = False
                            engine.reset()
                        elif action == 'save':
                            return self.reply(200, {'file': engine.archive()})
                        elif action is not None:
                            raise ValueError(f"Unknown control action '{action}'")
                    return self.reply(200, {'ok': True})

                if self.path == '/api/comparison/run':
                    duration = int(data.get('duration', 60))
                    seed = int(data.get('seed', 42))
                    scenario = data.get('scenario')
                    topology = data.get('topology')
                    results = engine.run_comparison(duration=duration, seed=seed, scenario=scenario, topology=topology)
                    return self.reply(200, results)

                self.reply(404, {'error': 'Not found'})
            except (ValueError, TypeError, KeyError) as e:
                self.reply(400, {'error': str(e)})

    def loop():
        while True:
            time.sleep(1)
            if engine.running:
                engine.step()

    threading.Thread(target=loop, daemon=True).start()
    print(f"Adaptive CN server listening on http://127.0.0.1:{port} | source={source} | topology={topology}", flush=True)
    
    try:
        ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
    except KeyboardInterrupt:
        engine.archive()

if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Adaptive CN Server')
    p.add_argument('--source', choices=['simulation', 'mininet'], default='simulation')
    p.add_argument('--port', type=int, default=8080)
    p.add_argument('--topology', choices=list(TOPOLOGIES.keys()), default='diamond')
    a = p.parse_args()
    serve(a.source, a.port, a.topology)
