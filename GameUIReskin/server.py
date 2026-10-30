"""Read-only extraction and reviewed PNG updates; exports and backups stay outside Unity."""
from __future__ import annotations
import argparse
import base64
import copy
import hmac
import io
import json
import os
import secrets
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from unity_source import BASE, Project, Assets, PrefabScene, digest, inside, relative_file, render_sprite
from PIL import Image

RUNTIME = BASE / 'runtime'
RUNTIME.mkdir(exist_ok=True)
MAX_REQUEST = 192 * 1024 * 1024
BATTLE_PASS = 'Assets/GameCore/Presentation/Prefabs/BattlePass/BattlePassModal.prefab'


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

def png_info(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('File nhận được không phải PNG.')
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        rgba = image.convert('RGBA')
    # Ignore undefined RGB in fully transparent pixels when detecting an unchanged export.
    rgba.paste((0, 0, 0, 0), mask=rgba.getchannel('A').point(lambda v: 255 if v == 0 else 0))
    return rgba.size, digest(rgba.tobytes())

class Connector:
    def __init__(self, project=None, output=None):
        self.lock = threading.RLock()
        self.project = Project(project) if project else None
        self.output = Path(output or RUNTIME / 'ReskinOutput').resolve()
        self.sessions = {}
        self.validate_output(self.output)

    def validate_output(self, output):
        resolved = Path(output).resolve()
        if self.project and (inside(resolved, self.project.root) or inside(self.project.root, resolved)):
            raise ValueError('Folder xuất phải nằm ngoài project Unity và không chứa project bên trong.')
        # Reject a different Unity project's folder as well.
        for ancestor in (resolved, *resolved.parents):
            if (ancestor / 'Assets').is_dir() and (ancestor / 'ProjectSettings').is_dir():
                raise ValueError('Không xuất trực tiếp vào bất kỳ project Unity nào.')
        if resolved == BASE or inside(BASE, resolved) or inside(BASE / 'plugin', resolved):
            raise ValueError('Chọn một folder xuất riêng, không phải thư mục chứa công cụ.')
        return resolved

    def status(self):
        return {'name': 'Game UI Reskin', 'version': '1.1.0',
                'project': str(self.project.root) if self.project else '',
                'projectId': self.project.project_id if self.project else '', 'output': str(self.output),
                'sourceMode': 'addressables-ui',
                'readOnlyUnity': False, 'unityWriteMode': 'reviewed-png-only'}

    def configure(self, data):
        with self.lock:
            previous = self.project
            project = Project(data['project'])
            self.project = project
            try:
                output = self.validate_output(data.get('output') or self.output)
            except Exception:
                self.project = previous
                raise
            self.output = output
            (RUNTIME / 'settings.json').write_bytes(json_bytes(self.status()))
            return self.status()

    def require_project(self):
        if not self.project:
            raise ValueError('Chưa chọn project Unity.')
        return self.project

    def catalog(self):
        with self.lock:
            return self.require_project().catalog(refresh=True)

    def catalog_preview(self, data):
        from ui_thumbnail import preview_scene
        with self.lock:
            project = self.require_project()
            identifier = data.get('screenId')
            if identifier not in {row['id'] for row in project.catalog()}:
                raise ValueError('UI không nằm trong danh sách đã kết nối.')
            cache = getattr(project, '_thumbnail_cache', {})
            if identifier not in cache:
                registry = Assets(project)
                scene = (self.battle_scene(project, registry) if identifier == BATTLE_PASS
                         else PrefabScene(project, registry).extract(relative_file(project.root, identifier)))
                cache[identifier] = {'screenId': identifier, 'bytes': preview_scene(scene, registry),
                                     'kind': 'prefab-preview', 'runtimeReady': scene['runtimeReady']}
                project._thumbnail_cache = cache
            return cache[identifier]

    def refresh_source(self, data=None):
        with self.lock:
            current = self.require_project()
            # Recreate readers to discard GUID, document, font and discovery caches together.
            refreshed = Project(current.root)
            catalog = refreshed.catalog()
            self.project = refreshed
            return {'status': self.status(), 'catalog': catalog, 'refreshed': True,
                    'message': 'Đã đọc lại nguồn Unity. Frame và Assets gốc trong Figma được giữ nguyên.'}

    def battle_scene(self, project, registry):
        blueprint = json.loads((BASE / 'adapters/battlepass.scene.json').read_text(encoding='utf-8-sig'))
        specs = {r['key']: r for r in json.loads((BASE / 'adapters/battlepass.renders.json').read_text(encoding='utf-8-sig'))}
        warnings = list(blueprint['warnings'])
        verified = True
        for path, original_hash in blueprint['sourceHashes'].items():
            if Path(path).suffix not in ('.prefab', '.cs', '.asset') or '/Fonts/' in path:
                continue
            source = relative_file(project.root, path)
            if not source.exists() or digest(project.read(source)) != original_hash:
                verified = False
                warnings.append('Nguồn layout/runtime đã đổi so với adapter: ' + path)
        root = copy.deepcopy(blueprint['root'])
        def walk(node):
            if node.get('type') == 'IMAGE':
                spec = specs[node['imageKey']]
                source = relative_file(project.root, node['spritePath'])
                asset = registry.texture(source)
                project.guid_paths[node['spriteGuid']] = source
                border = dict(zip(('x', 'y', 'z', 'w'), spec.get('border') or [0, 0, 0, 0]))
                result = registry.image({'guid': node['spriteGuid'], 'fileID': node.get('spriteFileID', 21300000)},
                                        node['w'], node['h'], crop=spec.get('crop'))
                # The prepared adapter includes exact nine-slice borders and static Spine crops.
                render = registry.renders[result['imageKey']]
                render['border'] = border
                key = digest(json.dumps(render, sort_keys=True).encode())[:24]
                registry.renders[key] = copy.deepcopy(render)
                result['imageKey'] = key
                node.update(result)
            if node.get('type') == 'TEXT':
                node['font'] = blueprint['font']
            for child in node.get('children', []):
                walk(child)
        walk(root)
        # Drop render variants superseded while applying the adapter's border metadata.
        used = set()
        def collect(node):
            if 'imageKey' in node:
                used.add(node['imageKey'])
            for child in node.get('children', []):
                collect(child)
        collect(root)
        return {'id': BATTLE_PASS, 'name': 'Battle Pass', 'width': blueprint['width'], 'height': blueprint['height'],
                'state': 'season-start', 'runtimeReady': verified, 'root': root,
                'warnings': warnings, 'font': blueprint['font'], 'bakedTextExceptions': blueprint['bakedTextExceptions']}

    def extract(self, data):
        with self.lock:
            project = self.require_project()
            screen_ids = data.get('screenIds', [])
            if not screen_ids or len(screen_ids) > 12 or len(set(screen_ids)) != len(screen_ids):
                raise ValueError('Chọn từ 1 đến 12 màn khác nhau mỗi lần nhập.')
            allowed = {v['id'] for v in project.catalog()}
            if any(value not in allowed for value in screen_ids):
                raise ValueError('Màn không nằm trong danh sách prefab đã kết nối.')
            reference = str(data.get('reference', '')).strip()
            if reference and not __import__('re').match(r'^https://(www\.)?figma\.com/(design|file)/[A-Za-z0-9]+', reference):
                raise ValueError('Link Figma tham chiếu không hợp lệ.')
            registry = Assets(project)
            scenes = []
            for screen_id in screen_ids:
                scene = self.battle_scene(project, registry) if screen_id == BATTLE_PASS else PrefabScene(project, registry).extract(relative_file(project.root, screen_id))
                if not scene['runtimeReady'] and not data.get('allowPrefabOnly'):
                    raise ValueError(scene['name'] + ': chưa xác minh dữ liệu runtime. '
                                     'Chọn chế độ nhập cấu trúc prefab nếu muốn xem bản cơ sở.')
                scenes.append(scene)
            # Only payloads actually referenced by scenes are sent to Figma.
            used = set()
            def collect(node):
                if 'imageKey' in node:
                    used.add(node['imageKey'])
                for child in node.get('children', []):
                    collect(child)
            for scene in scenes:
                collect(scene['root'])
            registry.renders = {k: v for k, v in registry.renders.items() if k in used}
            used_assets = {v['assetId'] for v in registry.renders.values()}
            registry.assets = {k: v for k, v in registry.assets.items() if k in used_assets}
            session_id = uuid.uuid4().hex
            session = {'id': session_id, 'projectId': project.project_id, 'projectRoot': str(project.root),
                       'assets': registry.assets, 'renders': registry.renders, 'baseline': {},
                       'sourceHashes': copy.deepcopy(project.hashes), 'reference': reference,
                       'referenceStatus': 'link-only' if reference else 'none'}
            self.sessions[session_id] = session
            self.save_session(session)
            public_assets = [{k: v for k, v in asset.items() if k != 'importer'} for asset in registry.assets.values()]
            return {'sessionId': session_id, 'projectId': project.project_id, 'scenes': scenes,
                    'assets': public_assets, 'images': registry.render_all(), 'renders': copy.deepcopy(registry.renders),
                    'reference': reference, 'referenceStatus': session['referenceStatus']}

    def magic_bridge(self):
        from magic_reskin import MagicReskin
        with self.lock:
            if not hasattr(self, '_magic'):
                self._magic = MagicReskin(self.ai_bridge(), RUNTIME)
            return self._magic

    def magic_start(self, data):
        with self.lock:
            session = copy.deepcopy(self.session(data.get('sessionId')))
        return self.magic_bridge().start(data, session)

    def magic_approve(self, data):
        with self.lock:
            session = copy.deepcopy(self.session(data.get('sessionId')))
        return self.magic_bridge().approve(data, session)

    def unity_import(self):
        from unity_import import UnityImport
        return UnityImport(self, RUNTIME)

    def unity_prepare(self, data):
        return self.unity_import().prepare(data)

    def unity_apply(self, data):
        result = self.unity_import().apply(data)
        self.require_project()._thumbnail_cache = {}
        return result

    def unity_restore(self, data):
        result = self.unity_import().apply(data, restore=True)
        self.require_project()._thumbnail_cache = {}
        return result

    def ai_bridge(self):
        from ai_bridge import AiBridge
        with self.lock:
            if not hasattr(self, '_ai'):
                self._ai = AiBridge(RUNTIME)
            return self._ai

    def ai_start(self, data):
        with self.lock:
            session = copy.deepcopy(self.session(data.get('sessionId')))
        return self.ai_bridge().start(data, session)

    def browse(self, data):
        import tkinter as tk
        from tkinter import filedialog
        with self.lock:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            try:
                kind = data.get('kind')
                title = 'Chọn project Unity' if kind == 'project' else 'Chọn folder xuất ngoài project'
                path = filedialog.askdirectory(parent=root, title=title)
                return {'path': path or ''}
            finally:
                root.destroy()

    def save_session(self, session):
        (RUNTIME / ('session-' + session['id'] + '.json')).write_bytes(json_bytes(session))

    def session(self, session_id):
        if not isinstance(session_id, str) or not __import__('re').fullmatch('[a-f0-9]{32}', session_id):
            raise ValueError('Session không hợp lệ.')
        if session_id not in self.sessions:
            path = RUNTIME / ('session-' + session_id + '.json')
            if not path.is_file():
                raise ValueError('Không tìm thấy phiên nhập. Kết nối đúng công cụ local hoặc nhập lại.')
            self.sessions[session_id] = json.loads(path.read_text(encoding='utf-8'))
        session = self.sessions[session_id]
        if session['projectId'] != self.require_project().project_id:
            raise ValueError('Project đang kết nối khác với project của asset trong Figma.')
        return session

    def read_entries(self, session, entries):
        values = {}
        for entry in entries:
            asset_id = entry.get('assetId')
            if asset_id not in session['assets'] or asset_id in values:
                raise ValueError('Asset không thuộc phiên nhập hoặc bị trùng.')
            try:
                data = base64.b64decode(entry['bytes'], validate=True)
            except Exception as error:
                raise ValueError('Dữ liệu asset không hợp lệ.') from error
            asset = session['assets'][asset_id]
            size, pixel_hash = png_info(data)
            if size != (asset['width'], asset['height']):
                raise ValueError(f'{asset["path"]}: cần {asset["width"]}×{asset["height"]}, nhận {size[0]}×{size[1]}. '
                                 'Khôi phục kích thước Assets gốc trước khi xuất.')
            values[asset_id] = (data, pixel_hash)
        return values

    def baselines(self, data):
        with self.lock:
            session = self.session(data['sessionId'])
            values = self.read_entries(session, data.get('entries', []))
            for asset_id, (_, pixel_hash) in values.items():
                # Never overwrite an existing baseline with a later reskin.
                session['baseline'].setdefault(asset_id, pixel_hash)
            self.save_session(session)
            return {'registered': len(values)}

    def preview(self, data):
        with self.lock:
            session = self.session(data['sessionId'])
            values = self.read_entries(session, data.get('entries', []))
            images = {}
            for key, spec in session['renders'].items():
                if spec['assetId'] in values:
                    images[key] = base64.b64encode(render_sprite(values[spec['assetId']][0], spec)).decode()
            return {'images': images, 'updatedAssets': len(values)}

    def export(self, data):
        with self.lock:
            session = self.session(data['sessionId'])
            output = self.validate_output(self.output)
            values = self.read_entries(session, data.get('entries', []))
            if not values:
                raise ValueError('Chưa chọn asset để xuất.')
            staged = []
            skipped = []
            for asset_id, (png, pixel_hash) in values.items():
                asset = session['assets'][asset_id]
                if not asset['path'].lower().endswith('.png'):
                    raise ValueError('Hiện chỉ xuất đè đúng định dạng cho nguồn PNG: ' + asset['path'])
                if data.get('changedOnly', True):
                    baseline = session['baseline'].get(asset_id)
                    if not baseline:
                        raise ValueError('Chưa có baseline Figma cho ' + asset['path'] + '. Chọn xuất tất cả hoặc nhập lại.')
                    if pixel_hash == baseline:
                        skipped.append(asset['path'])
                        continue
                source = relative_file(self.project.root, asset['path'])
                if digest(source.read_bytes()) != session.get('unityHashes', {}).get(asset_id, asset['sha256']):
                    raise ValueError('Asset Unity đã thay đổi sau khi nhập: ' + asset['path'] + '. Cần cập nhật nguồn trước.')
                target = relative_file(output, asset['path'])
                if not inside(target, output) or inside(target, self.project.root):
                    raise ValueError('Đường dẫn xuất nằm ngoài folder đích.')
                staged.append((target, png, asset))
            # Validate the complete batch before touching output files.
            exported = []
            for target, png, asset in staged:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    temporary.write_bytes(png)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
                exported.append({'path': asset['path'], 'output': str(target), 'sha256': digest(png)})
            report = {'exportId': uuid.uuid4().hex, 'outputFolder': str(output), 'exported': exported, 'unchanged': skipped,
                      'sessionId': session['id'], 'projectId': session['projectId'],
                      'reference': session['reference'], 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')}
            output.mkdir(parents=True, exist_ok=True)
            exports = RUNTIME / 'exports'
            exports.mkdir(exist_ok=True)
            (exports / (report['exportId'] + '.json')).write_bytes(json_bytes(report))
            (output / 'reskin-export-report.json').write_bytes(json_bytes(report))
            return report

class Handler(BaseHTTPRequestHandler):
    server_version = 'GameUIReskin/1.0'
    def log_message(self, fmt, *args):
        print(time.strftime('%H:%M:%S'), fmt % args, flush=True)

    def headers_common(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Reskin-Token')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')

    def response(self, status, data):
        body = json_bytes(data)
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        host = self.headers.get('Host', '')
        expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        return host in expected and hmac.compare_digest(self.headers.get('X-Reskin-Token', ''), self.server.token)

    def do_OPTIONS(self):
        self.send_response(204)
        self.headers_common()
        self.end_headers()

    def dispatch(self, method):
        try:
            if not self.authorized():
                self.response(403, {'error': 'Mã kết nối local không đúng. Xem connection.txt trong thư mục công cụ.'})
                return
            route = urlsplit(self.path).path
            app = self.server.app
            if method == 'GET':
                routes = {'/api/status': app.status, '/api/catalog': app.catalog, '/api/ai/status': app.ai_bridge().status}
                if route not in routes:
                    self.response(404, {'error': 'Không tìm thấy endpoint.'})
                    return
                result = routes[route]()
            else:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= MAX_REQUEST:
                    raise ValueError('Kích thước yêu cầu không hợp lệ hoặc vượt quá 192MB.')
                data = json.loads(self.rfile.read(length))
                routes = {'/api/magic/latest': app.magic_bridge().latest, '/api/magic/start': app.magic_start, '/api/magic/job': app.magic_bridge().get,
                          '/api/magic/approve': app.magic_approve, '/api/magic/cancel': app.magic_bridge().cancel,
                          '/api/magic/result': app.magic_bridge().result, '/api/catalog-preview': app.catalog_preview, '/api/unity/prepare': app.unity_prepare, '/api/unity/apply': app.unity_apply,
                          '/api/unity/restore': app.unity_restore, '/api/ai/start': app.ai_start, '/api/ai/job': app.ai_bridge().get,
                          '/api/ai/cancel': app.ai_bridge().cancel, '/api/config': app.configure, '/api/refresh': app.refresh_source,
                          '/api/browse': app.browse, '/api/extract': app.extract,
                          '/api/baselines': app.baselines, '/api/preview': app.preview, '/api/export': app.export}
                if route not in routes:
                    self.response(404, {'error': 'Không tìm thấy endpoint.'})
                    return
                result = routes[route](data)
            self.response(200, result)
        except (ValueError, OSError, KeyError) as error:
            self.response(400, {'error': str(error)})
        except Exception as error:
            import traceback
            traceback.print_exc()
            self.response(500, {'error': f'{type(error).__name__}: {error}'})

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project')
    parser.add_argument('--output')
    parser.add_argument('--port', type=int, default=43127)
    args = parser.parse_args()
    saved = json.loads((RUNTIME / 'settings.json').read_text(encoding='utf-8')) if (RUNTIME / 'settings.json').exists() else {}
    app = Connector(args.project or saved.get('project'), args.output or saved.get('output'))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.app = app
    token_file = RUNTIME / 'pairing.json'
    token = json.loads(token_file.read_text())['token'] if token_file.exists() else secrets.token_urlsafe(24)
    token_file.write_bytes(json_bytes({'token': token}))
    server.token = token
    (BASE / 'connection.txt').write_text(f'URL: http://127.0.0.1:{args.port}\nMã kết nối: {token}\n', encoding='utf-8')
    print(f'Game UI Reskin: http://127.0.0.1:{args.port}', flush=True)
    print('Mã kết nối được lưu trong connection.txt. Unity được mở chỉ đọc.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
