"""Read-only Unity prefab extraction. All generated data stays outside the project."""
from __future__ import annotations
import base64
import copy
import hashlib
import io
import json
import math
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'vendor'))
import yaml
from PIL import Image, ImageChops

UI_IMAGE_GUID = 'fe87c0e1cc204ed48ad3b37840f39efc'
HEAD = re.compile(r'^--- !u!(\d+) &(-?\d+)([^\n]*)\n', re.M)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

def relative_file(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        raise ValueError('Đường dẫn asset không hợp lệ.')
    parts = name.split('/')
    if not parts or parts[0] != 'Assets' or any(p in ('', '.', '..') for p in parts):
        raise ValueError('Đường dẫn phải nằm trong Assets và không chứa ..')
    result = (root / name).resolve()
    if not inside(result, root / 'Assets'):
        raise ValueError('Asset nằm ngoài thư mục Assets.')
    return result

def load_docs(path):
    text = path.read_text(encoding='utf-8-sig')
    heads = list(HEAD.finditer(text))
    docs = {}
    for i, head in enumerate(heads):
        body = text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        payload = yaml.safe_load(body) or {}
        kind = next(iter(payload), '')
        value = payload.get(kind) or {}
        value.update(_class=int(head[1]), _kind=kind, _id=head[2], _stripped='stripped' in head[3])
        docs[head[2]] = value
    return docs

def set_property(target, property_path, value):
    property_path = re.sub(r'\.Array\.data\[(\d+)\]', r'.\1', property_path)
    keys = property_path.split('.')
    current = target
    for key in keys[:-1]:
        if isinstance(current, list):
            current = current[int(key)]
        else:
            current = current.setdefault(key, {})
    if isinstance(current, list):
        current[int(keys[-1])] = value
    else:
        current[keys[-1]] = value

def references(value):
    if isinstance(value, dict):
        if 'fileID' in value:
            yield value
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)

class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not (self.root / 'Assets').is_dir() or not (self.root / 'ProjectSettings').is_dir():
            raise ValueError('Chọn thư mục gốc project Unity có Assets và ProjectSettings.')
        self.guid_paths = {}
        self.cache = {}
        self.hashes = {}
        self.metadata_indexed = False
        self.project_id = digest(str(self.root).casefold().encode())[:16]
        from addressable_ui import AddressableUI
        self.discovery = AddressableUI(self)

    def valid_asset(self, path):
        return inside(path, self.root / 'Assets')

    def index_metadata(self):
        if self.metadata_indexed:
            return
        # Index GUID/path metadata, not arbitrary prefab, texture or source-code contents.
        import os
        for directory, folders, filenames in os.walk(self.root / 'Assets', followlinks=False):
            folders[:] = [name for name in folders if name not in
                          ('Library', 'Temp', 'Logs', 'Build', 'Builds', 'obj', '.git')
                          and self.valid_asset(Path(directory) / name)]
            for name in filenames:
                if name.endswith('.meta'):
                    self._index_meta(Path(directory) / name)
        self.metadata_indexed = True

    def resolve_many(self, guids):
        needed = {str(value) for value in guids if value and not str(value).startswith('00000000')}
        if needed - self.guid_paths.keys():
            self.index_metadata()
        for guid in needed:
            self.guid_paths.setdefault(guid, None)

    def _index_meta(self, meta):
        if not inside(meta, self.root / 'Assets'):
            return
        with meta.open(encoding='utf-8-sig', errors='replace') as handle:
            for _ in range(5):
                line = handle.readline()
                match = re.match(r'guid:\s*([a-f0-9]{32})', line)
                if match:
                    self.guid_paths[match[1]] = Path(str(meta)[:-5])
                    break

    def resolve(self, guid):
        if not guid or str(guid).startswith('00000000'):
            return None
        guid = str(guid)
        self.resolve_many([guid])
        return self.guid_paths.get(guid)

    def read(self, path):
        path = path.resolve()
        if not inside(path, self.root / 'Assets'):
            raise ValueError('Chỉ đọc nguồn trong Assets.')
        data = path.read_bytes()
        self.hashes[path.relative_to(self.root).as_posix()] = digest(data)
        return data

    def catalog(self, refresh=False):
        if refresh:
            self.guid_paths.clear()
            self.metadata_indexed = False
        return self.discovery.catalog(refresh=refresh)

    def expand(self, path, chain=()):
        rel = path.relative_to(self.root).as_posix()
        if rel in chain or len(chain) >= 16:
            raise ValueError(f'Prefab lồng nhau bị vòng lặp hoặc quá sâu: {rel}')
        self.read(path)
        docs = load_docs(path)
        for obj in docs.values():
            obj['_source'] = rel
            obj['_sourceId'] = obj['_id']
        aliases = {}
        warnings = []
        for inst_id, inst in list(docs.items()):
            if inst['_class'] != 1001:
                continue
            source = self.resolve(inst.get('m_SourcePrefab', {}).get('guid'))
            if not source or source.suffix != '.prefab':
                warnings.append(f'Không tìm được prefab con của instance {inst_id}.')
                continue
            if not self.discovery.is_ui(source):
                warnings.append(f'Bỏ qua prefab ngoài UI: {source.name}.')
                continue
            nested, notes = self.expand(source, (*chain, rel))
            warnings.extend(notes)
            mod = inst.get('m_Modification', {})
            for override in mod.get('m_Modifications', []) or []:
                target = nested.get(str(override.get('target', {}).get('fileID')))
                if target is None:
                    continue
                object_ref = override.get('objectReference', {})
                value = object_ref if object_ref.get('fileID') else override.get('value', '')
                if not isinstance(value, dict):
                    try:
                        parsed = yaml.safe_load(str(value))
                        value = parsed if not isinstance(parsed, (dict, list)) else value
                    except yaml.YAMLError:
                        pass
                try:
                    set_property(target, override['propertyPath'], value)
                except (TypeError, IndexError, KeyError, ValueError):
                    warnings.append(f'Chưa áp dụng override {override.get("propertyPath")} trong {source.name}.')
            removed_components = {str(r.get('fileID')) for r in mod.get('m_RemovedComponents', []) or []}
            removed_gos = {str(r.get('fileID')) for r in mod.get('m_RemovedGameObjects', []) or []}
            for key in list(nested):
                obj = nested[key]
                if key in removed_components or key in removed_gos:
                    nested.pop(key)
            rename = {key: f'{inst_id}/{key}' for key in nested}
            for key, obj in docs.items():
                if obj.get('_stripped') and str(obj.get('m_PrefabInstance', {}).get('fileID')) == inst_id:
                    original = str(obj.get('m_CorrespondingSourceObject', {}).get('fileID'))
                    if original in rename:
                        aliases[key] = rename[original]
            parent = mod.get('m_TransformParent', {'fileID': 0})
            roots = []
            for key, obj in nested.items():
                is_root = obj['_class'] in (4, 224) and not obj.get('m_Father', {}).get('fileID')
                for ref in references(obj):
                    original = str(ref.get('fileID'))
                    if not ref.get('guid') and original in rename:
                        ref['fileID'] = rename[original]
                obj['_id'] = rename[key]
                if is_root:
                    obj['m_Father'] = copy.deepcopy(parent)
                    roots.append(rename[key])
                docs[rename[key]] = obj
            for root_id in roots:
                parent_obj = docs.get(str(parent.get('fileID')))
                if parent_obj:
                    refs = parent_obj.setdefault('m_Children', [])
                    stripped_ids = {key for key, value in aliases.items() if value == root_id}
                    if not any(str(ref.get('fileID')) in stripped_ids for ref in refs):
                        refs.append({'fileID': root_id})
            for added in mod.get('m_AddedGameObjects', []) or []:
                target_id = rename.get(str(added.get('targetCorrespondingSourceObject', {}).get('fileID')))
                if target_id:
                    children = docs[target_id].setdefault('m_Children', [])
                    pos = int(added.get('insertIndex', -1))
                    children.insert(pos if pos >= 0 else len(children), added.get('addedObject', {}))
        for obj in docs.values():
            for ref in references(obj):
                key = str(ref.get('fileID'))
                if not ref.get('guid') and key in aliases:
                    ref['fileID'] = aliases[key]
        docs = {key: obj for key, obj in docs.items() if not obj.get('_stripped') and obj['_class'] != 1001}
        return docs, warnings

class Assets:
    def __init__(self, project):
        self.project = project
        self.assets = {}
        self.renders = {}

    def texture(self, path):
        rel = path.relative_to(self.project.root).as_posix()
        key = digest(rel.encode())[:24]
        if key not in self.assets:
            data = self.project.read(path)
            with Image.open(io.BytesIO(data)) as image:
                w, h = image.size
            if w > 4096 or h > 4096:
                raise ValueError(f'Ảnh lớn hơn giới hạn 4096px: {rel}')
            meta_path = Path(str(path) + '.meta')
            meta = yaml.safe_load(self.project.read(meta_path).decode('utf-8-sig')) if meta_path.exists() else {}
            importer = meta.get('TextureImporter', {})
            self.assets[key] = {'id': key, 'path': rel, 'width': w, 'height': h,
                                'guid': meta.get('guid'), 'sha256': digest(data),
                                'border': importer.get('spriteBorder', {}),
                                'importer': importer, 'bytes': base64.b64encode(data).decode()}
        return self.assets[key]

    def image(self, ref, width, height, image_type=0, tint=None, crop=None):
        path = self.project.resolve(ref.get('guid'))
        if not path or path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            return None
        asset = self.texture(path)
        sprite_rect = crop
        file_id = str(ref.get('fileID', 21300000))
        if sprite_rect is None and int(asset['importer'].get('spriteMode', 1)) == 2:
            sprites = asset['importer'].get('spriteSheet', {}).get('sprites', [])
            names = asset['importer'].get('internalIDToNameTable', [])
            name = next((v.get('second') for v in names if file_id in {str(n) for n in (v.get('first') or {}).values()}), None)
            record = next((v for v in sprites if str(v.get('internalID')) == file_id or v.get('name') == name), None)
            if not record:
                raise ValueError(f'Không xác định được sprite {file_id} trong atlas {asset["path"]}.')
            rect = record['rect']
            sprite_rect = [rect['x'], asset['height'] - rect['y'] - rect['height'], rect['width'], rect['height'], 0]
            border = record.get('border', {})
        else:
            border = asset['border']
        spec = {'assetId': asset['id'], 'width': max(1, round(width)), 'height': max(1, round(height)),
                'crop': sprite_rect, 'border': border if image_type == 1 else {},
                'tint': tint or {'r': 1, 'g': 1, 'b': 1, 'a': 1}}
        render_id = digest(json.dumps(spec, sort_keys=True).encode())[:24]
        self.renders[render_id] = spec
        return {'imageKey': render_id, 'assetId': asset['id'], 'spritePath': asset['path'],
                'spriteGuid': ref.get('guid'), 'spriteFileID': file_id}

    def render_all(self, overrides=None):
        images = {}
        for key, spec in self.renders.items():
            asset = self.assets[spec['assetId']]
            data = (overrides or {}).get(spec['assetId'])
            if data is None:
                data = base64.b64decode(asset['bytes'])
            images[key] = base64.b64encode(render_sprite(data, spec)).decode()
        return images

def render_sprite(data, spec):
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert('RGBA')
    crop = spec.get('crop')
    if crop:
        x, y, w, h = [int(v) for v in crop[:4]]
        angle = int(crop[4]) if len(crop) > 4 else 0
        rw, rh = (h, w) if angle == 90 else (w, h)
        image = image.crop((x, y, x + rw, y + rh))
        if angle:
            image = image.rotate(angle, expand=True)
    width, height = int(spec['width']), int(spec['height'])
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        raise ValueError('Kích thước sprite hiển thị ngoài phạm vi hỗ trợ.')
    border = spec.get('border') or {}
    left, bottom, right, top = [max(0, int(border.get(k, 0))) for k in ('x', 'y', 'z', 'w')]
    if any((left, bottom, right, top)):
        iw, ih = image.size
        sx, sy = [0, left, iw - right, iw], [0, top, ih - bottom, ih]
        xs = min(1, width / max(1, left + right))
        ys = min(1, height / max(1, top + bottom))
        dx = [0, round(left * xs), width - round(right * xs), width]
        dy = [0, round(top * ys), height - round(bottom * ys), height]
        result = Image.new('RGBA', (width, height))
        for y in range(3):
            for x in range(3):
                sw, sh = sx[x + 1] - sx[x], sy[y + 1] - sy[y]
                dw, dh = dx[x + 1] - dx[x], dy[y + 1] - dy[y]
                if min(sw, sh, dw, dh) > 0:
                    patch = image.crop((sx[x], sy[y], sx[x + 1], sy[y + 1]))
                    result.paste(patch.resize((dw, dh), Image.Resampling.BILINEAR), (dx[x], dy[y]))
        image = result
    else:
        image = image.resize((width, height), Image.Resampling.BILINEAR)
    tint = spec.get('tint') or {}
    multipliers = [max(0, min(1, tint.get(k, 1))) for k in ('r', 'g', 'b', 'a')]
    if any(v != 1 for v in multipliers):
        image = Image.merge('RGBA', [channel.point([round(i * value) for i in range(256)])
                                     for channel, value in zip(image.split(), multipliers)])
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()

class PrefabScene:
    def __init__(self, project, registry, width=1080, height=2448):
        self.project, self.registry = project, registry
        self.width, self.height = width, height
        self.warnings = []
        self.fonts = set()
        self.components = {}
        self.dynamic = set()

    def extract(self, path):
        docs, self.warnings = self.project.expand(path)
        self.docs = docs
        for obj in docs.values():
            if obj.get('_class') == 114:
                self.components.setdefault(str(obj.get('m_GameObject', {}).get('fileID')), []).append(obj)
        transforms = [v for v in docs.values() if v['_class'] in (4, 224) and 'm_GameObject' in v]
        roots = [v for v in transforms if not v.get('m_Father', {}).get('fileID')]
        root = {'name': path.stem, 'key': path.stem, 'x': 0, 'y': 0, 'w': self.width, 'h': self.height,
                'children': [], 'clip': True}
        for transform in roots:
            value = self.node(transform, self.width, self.height, root=True)
            if value:
                root['children'].append(value)
        if self.dynamic:
            self.warnings.append('Có tham chiếu prefab tạo lúc chạy: ' + ', '.join(sorted(self.dynamic)[:8]))
        return {'id': path.relative_to(self.project.root).as_posix(), 'name': path.stem,
                'width': self.width, 'height': self.height, 'root': root,
                'runtimeReady': False, 'state': 'prefab', 'fonts': list(self.fonts),
                'warnings': list(dict.fromkeys(self.warnings + ['Trạng thái runtime chưa được xác minh; đây là cấu trúc prefab.']))}

    def node(self, tr, pw, ph, trail='', root=False, scale=(1, 1)):
        if tr.get('_class') != 224:
            return None
        go = self.docs.get(str(tr.get('m_GameObject', {}).get('fileID')))
        if not go or (not root and not go.get('m_IsActive', 1)):
            return None
        name = str(go.get('m_Name', 'GameObject'))
        trail = trail + '/' + name
        amin, amax = tr.get('m_AnchorMin', {}), tr.get('m_AnchorMax', {})
        pv, delta = tr.get('m_Pivot', {'x': .5, 'y': .5}), tr.get('m_SizeDelta', {})
        ap, ls = tr.get('m_AnchoredPosition', {}), tr.get('m_LocalScale', {'x': 1, 'y': 1})
        w = (amax.get('x', .5) - amin.get('x', .5)) * pw + delta.get('x', 0)
        h = (amax.get('y', .5) - amin.get('y', .5)) * ph + delta.get('y', 0)
        x = (amin.get('x', .5) + (amax.get('x', .5) - amin.get('x', .5)) * pv['x']) * pw
        x += ap.get('x', 0) - pv['x'] * w
        y = ph - (amin.get('y', .5) + (amax.get('y', .5) - amin.get('y', .5)) * pv['y']) * ph
        y -= ap.get('y', 0) + (1 - pv['y']) * h
        if root:
            x = y = 0
            if w <= 0 or h <= 0:
                w, h = pw, ph
        sx, sy = scale
        lx, ly = abs(ls.get('x', 1)), abs(ls.get('y', 1))
        x += pv['x'] * w * (1 - lx)
        y += (1 - pv['y']) * h * (1 - ly)
        node = {'name': name, 'key': tr['_id'], 'path': trail, 'sourcePrefab': tr['_source'],
                'fileID': tr['_sourceId'], 'x': x * sx, 'y': y * sy,
                'w': max(.001, w * lx * sx), 'h': max(.001, h * ly * sy), 'children': []}
        comps = self.components.get(str(tr['m_GameObject']['fileID']), [])
        for c in comps:
            if not c.get('m_Enabled', 1):
                continue
            script = self.project.resolve(c.get('m_Script', {}).get('guid'))
            kind = c.get('m_EditorClassIdentifier', '') or (script.stem if script else '')
            if 'Mask' in kind:
                node['clip'] = True
            if 'SkeletonGraphic' in kind or 'skeletonDataAsset' in c:
                self.warnings.append(f'Spine chưa được dựng cho {trail}.')
            for ref in references(c):
                target = self.project.resolve(ref.get('guid'))
                if target and target.suffix == '.prefab' and self.project.discovery.is_ui(target):
                    self.dynamic.add(target.stem)
            if 'm_Sprite' in c:
                ref = c['m_Sprite'] or {}
                ww, hh = node['w'], node['h']
                dx = dy = 0
                try:
                    path = self.project.resolve(ref.get('guid'))
                    if path and c.get('m_PreserveAspect'):
                        asset = self.registry.texture(path)
                        ratio = min(ww / asset['width'], hh / asset['height'])
                        iw, ih = asset['width'] * ratio, asset['height'] * ratio
                        dx, dy = (ww - iw) * pv['x'], (hh - ih) * (1 - pv['y'])
                        ww, hh = iw, ih
                    image = self.registry.image(ref, ww, hh, int(c.get('m_Type', 0)), c.get('m_Color'))
                    if image:
                        node['children'].append({'name': name + ' / Sprite', 'type': 'IMAGE',
                                                 'key': tr['_id'] + '/image', 'x': dx, 'y': dy,
                                                 'w': ww, 'h': hh, **image})
                    elif not ref.get('fileID'):
                        col = c.get('m_Color', {})
                        if col.get('a', 1) > 0:
                            node['color'] = col
                    elif not str(ref.get('guid', '')).startswith('00000000'):
                        self.warnings.append(f'Không đọc được sprite: {trail}.')
                    if c.get('m_Type') == 3:
                        self.warnings.append(f'Image Filled cần trạng thái runtime: {trail}.')
                except (ValueError, OSError) as error:
                    self.warnings.append(str(error))
            if 'm_text' in c or 'm_Text' in c:
                font = self.font(c)
                self.fonts.add(json.dumps(font, sort_keys=True))
                text = str(c.get('m_text', c.get('m_Text', '')) or '')
                if re.search(r'<[^>]+>', text):
                    self.warnings.append(f'Rich text được chuyển sang text thuần: {trail}.')
                    text = re.sub(r'<[^>]+>', '', text)
                style = int(c.get('m_fontStyle', 0))
                if style & 16:
                    text = text.upper()
                margin = c.get('m_margin') or {}
                text_sx, text_sy = sx * lx, sy * ly
                left, top, right, bottom = [float(margin.get(k, 0)) for k in ('x', 'y', 'z', 'w')]
                wrap_mode = c.get('m_TextWrappingMode')
                # TMP 0/2 disable wrapping; 1/3/4 enable normal or preserved-whitespace wrapping.
                wrap = bool(c.get('m_enableWordWrapping', True)) if wrap_mode is None else int(wrap_mode) not in (0, 2)
                auto_size = bool(c.get('m_enableAutoSizing', 0))
                node['children'].append({'name': name + ' / Text', 'type': 'TEXT',
                    'key': tr['_id'] + '/text', 'x': left * text_sx, 'y': top * text_sy,
                    'w': max(.001, node['w'] - (left + right) * text_sx),
                    'h': max(.001, node['h'] - (top + bottom) * text_sy),
                    'textLayout': {'wrap': wrap, 'overflow': int(c.get('m_overflowMode', 0)),
                                   'autoSize': auto_size,
                                   'fontSizeMin': float(c.get('m_fontSizeMin', 18)) * text_sx,
                                   'fontSizeMax': float(c.get('m_fontSizeMax', c.get('m_fontSize', 40))) * text_sx},
                    'unityMargins': {'left': left, 'top': top, 'right': right, 'bottom': bottom},
                    'text': text, 'font': font, 'fontSize': float(c.get('m_fontSize', c.get('m_FontData', {}).get('m_FontSize', 30))) * sx * lx,
                    'color': c.get('m_fontColor', c.get('m_Color', {'r': 1, 'g': 1, 'b': 1, 'a': 1})),
                    'align': {1: 'LEFT', 2: 'CENTER', 4: 'RIGHT'}.get(c.get('m_HorizontalAlignment'), 'CENTER'),
                    'vertical': {256: 'TOP', 512: 'CENTER', 1024: 'BOTTOM'}.get(c.get('m_VerticalAlignment'), 'CENTER')})
        for ref in tr.get('m_Children', []) or []:
            child = self.docs.get(str(ref.get('fileID')))
            if child:
                value = self.node(child, w, h, trail, scale=(sx * lx, sy * ly))
                if value:
                    node['children'].append(value)
        self.layout(node, comps, sx * lx, sy * ly)
        if ls.get('x', 1) < 0 or ls.get('y', 1) < 0:
            self.warnings.append(f'Transform có scale âm cần đối chiếu: {trail}.')
        return node

    def font(self, component):
        path = self.project.resolve(component.get('m_fontAsset', {}).get('guid'))
        if path:
            data = self.project.read(path).decode('utf-8-sig')
            family = re.search(r'^\s*m_FamilyName:\s*(.+)$', data, re.M)
            style = re.search(r'^\s*m_StyleName:\s*(.+)$', data, re.M)
            if family:
                return {'family': family[1].strip(), 'style': style[1].strip() if style else 'Regular'}
        self.warnings.append('Không xác định được font gốc; cần chọn font trước khi nhập.')
        return {'family': 'Arial', 'style': 'Regular'}

    def layout(self, node, comps, sx, sy):
        children = [c for c in node['children'] if c.get('type') not in ('IMAGE', 'TEXT')]
        for comp in comps:
            if not comp.get('m_Enabled', 1):
                continue
            if 'm_ChildAlignment' not in comp or 'm_Spacing' not in comp or not children:
                continue
            script = self.project.resolve(comp.get('m_Script', {}).get('guid'))
            kind = comp.get('m_EditorClassIdentifier', '') or (script.stem if script else '')
            if 'GridLayoutGroup' in kind:
                self.warnings.append(f'GridLayout cần kiểm tra tại {node["path"]}.')
                continue
            if 'HorizontalLayoutGroup' not in kind and 'VerticalLayoutGroup' not in kind:
                continue
            vertical = 'VerticalLayoutGroup' in kind
            dim, cross = ('h', 'w') if vertical else ('w', 'h')
            axis, cross_axis = ('y', 'x') if vertical else ('x', 'y')
            scale = sy if vertical else sx
            pad = comp.get('m_Padding', {})
            start = pad.get('m_Top' if vertical else 'm_Left', 0) * scale
            end = pad.get('m_Bottom' if vertical else 'm_Right', 0) * scale
            space = comp.get('m_Spacing', 0) * scale
            total = sum(c[dim] for c in children) + space * (len(children) - 1)
            available = node[dim] - start - end
            force = comp.get('m_ChildForceExpandHeight' if vertical else 'm_ChildForceExpandWidth', 0)
            align = int(comp.get('m_ChildAlignment', 4))
            factor = (align // 3 if vertical else align % 3) / 2
            extra = max(0, available - total) / len(children) if force else 0
            cursor = start + (0 if extra else (available - total) * factor)
            control = comp.get('m_ChildControlHeight' if vertical else 'm_ChildControlWidth', 0)
            if control:
                self.warnings.append(f'Layout có kích thước preferred cần đối chiếu tại {node["path"]}.')
            for child in children:
                child[axis] = cursor + extra / 2
                cross_factor = (align % 3 if vertical else align // 3) / 2
                child[cross_axis] = (node[cross] - child[cross]) * cross_factor
                cursor += child[dim] + extra + space
