"""Reviewed PNG updates with external backups; never write Unity metadata or run Unity."""
import json
import os
from pathlib import Path
import re
import uuid
from unity_source import digest, inside, relative_file


class UnityImport:
    def __init__(self, connector, runtime):
        self.app = connector
        self.root = Path(runtime) / 'unity-imports'
        self.root.mkdir(parents=True, exist_ok=True)

    def check_root(self, project):
        if inside(self.root, project.root) or inside(project.root, self.root):
            raise ValueError('Folder sao lưu phải nằm ngoài project Unity.')

    def load(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('Mã cập nhật không hợp lệ.')
        folder = self.root / identifier
        record = json.loads((folder / 'plan.json').read_text(encoding='utf-8'))
        session = self.app.session(record['sessionId'])
        project = self.app.require_project()
        self.check_root(project)
        if str(project.root.resolve()) != record['projectRoot'] or project.project_id != record['projectId']:
            raise ValueError('Project hiện tại khác với project đã duyệt.')
        return folder, record, session

    def save(self, folder, record):
        temporary = folder / 'plan.pending'
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, folder / 'plan.json')

    def public(self, folder, record):
        return {'planId': folder.name, 'sessionId': record['sessionId'], 'state': record['state'],
                'project': record['projectRoot'], 'backupFolder': str(folder / 'before'),
                'files': [{'path': item['path'], 'width': item['width'], 'height': item['height']}
                          for item in record['files']], 'skipped': record.get('skipped', [])}

    def prepare(self, data):
        from server import png_info
        with self.app.lock:
            identifier = data.get('exportId')
            if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
                raise ValueError('Xuất reskin ra folder trước khi cập nhật Unity.')
            export_path = self.root.parent / 'exports' / (identifier + '.json')
            report = json.loads(export_path.read_text(encoding='utf-8'))
            session = self.app.session(report['sessionId'])
            project = self.app.require_project()
            self.check_root(project)
            output = self.app.validate_output(Path(report['outputFolder']))
            if report['projectId'] != project.project_id:
                raise ValueError('Bản xuất thuộc project khác.')
            assets = {asset['path']: asset for asset in session['assets'].values()}
            staged, skipped = [], []
            for entry in report['exported']:
                asset = assets.get(entry['path'])
                if not asset or not asset['path'].lower().endswith('.png'):
                    raise ValueError('Chỉ cập nhật PNG có mapping trong phiên nhập.')
                source = relative_file(project.root, asset['path'])
                target = relative_file(output, asset['path'])
                before, after = source.read_bytes(), target.read_bytes()
                expected = session.get('unityHashes', {}).get(asset['id'], asset['sha256'])
                if digest(before) != expected:
                    raise ValueError('PNG Unity đã đổi sau lần đọc trước: ' + asset['path'] + '. Lấy lại nguồn trước.')
                if digest(after) != entry['sha256']:
                    raise ValueError('File xuất đã đổi sau khi xuất từ Figma: ' + asset['path'])
                size, pixels = png_info(after)
                if size != (asset['width'], asset['height']):
                    raise ValueError('Kích thước PNG không khớp Unity: ' + asset['path'])
                if png_info(before)[1] == pixels:
                    skipped.append(asset['path'])
                    continue
                meta = relative_file(project.root, asset['path'] + '.meta')
                if not meta.is_file():
                    raise ValueError('Thiếu .meta nguồn; chưa cập nhật: ' + asset['path'])
                staged.append((asset, before, after, meta.read_bytes()))
            folder = self.root / uuid.uuid4().hex
            folder.mkdir()
            record = {'sessionId': session['id'], 'projectId': project.project_id,
                      'projectRoot': str(project.root.resolve()), 'state': 'prepared', 'files': [], 'skipped': skipped}
            for asset, before, after, metadata in staged:
                for name, raw in [('before', before), ('after', after)]:
                    destination = relative_file(folder / name, asset['path'])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(raw)
                meta_backup = relative_file(folder / 'before', asset['path'] + '.meta')
                meta_backup.write_bytes(metadata)
                record['files'].append({'assetId': asset['id'], 'path': asset['path'],
                                        'width': asset['width'], 'height': asset['height'],
                                        'beforeHash': digest(before), 'afterHash': digest(after),
                                        'metaHash': digest(metadata)})
            self.save(folder, record)
            return self.public(folder, record)

    def replace_png(self, target, raw):
        # https://docs.unity3d.com/Manual/SpecialFolders.html
        # Unity ignores filenames beginning with a dot and ending in ~; stage on the same volume.
        temporary = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '~')
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def apply(self, data, restore=False):
        with self.app.lock:
            folder, record, session = self.load(data.get('planId'))
            expected_state = 'applied' if restore else 'prepared'
            if record['state'] != expected_state:
                raise ValueError('Bản cập nhật đã xử lý hoặc không còn ở trạng thái phù hợp.')
            before_key, after_key = ('after', 'before') if restore else ('before', 'after')
            staged = []
            for item in record['files']:
                asset = session['assets'].get(item.get('assetId'))
                if not asset or item['path'] != asset['path'] or not item['path'].lower().endswith('.png'):
                    raise ValueError('Danh sách cập nhật có file ngoài mapping PNG của phiên nhập.')
                target = relative_file(Path(record['projectRoot']), item['path'])
                metadata = relative_file(Path(record['projectRoot']), item['path'] + '.meta')
                current = target.read_bytes()
                if digest(current) != item[before_key + 'Hash']:
                    raise ValueError('PNG đã thay đổi sau khi duyệt; chưa ghi file nào: ' + item['path'])
                if digest(metadata.read_bytes()) != item['metaHash']:
                    raise ValueError('.meta đã thay đổi; chưa ghi file nào: ' + item['path'])
                raw = relative_file(folder / after_key, item['path']).read_bytes()
                if digest(raw) != item[after_key + 'Hash']:
                    raise ValueError('Bản sao lưu hoặc PNG đã duyệt không còn nguyên vẹn: ' + item['path'])
                staged.append((target, raw, current, item))
            written = []
            previous_hashes = dict(session.get('unityHashes', {}))
            try:
                for target, raw, previous, item in staged:
                    if digest(target.read_bytes()) != item[before_key + 'Hash']:
                        raise ValueError('PNG vừa thay đổi trong lúc cập nhật: ' + item['path'])
                    metadata = relative_file(Path(record['projectRoot']), item['path'] + '.meta')
                    if digest(metadata.read_bytes()) != item['metaHash']:
                        raise ValueError('.meta vừa thay đổi trong lúc cập nhật: ' + item['path'])
                    self.replace_png(target, raw)
                    written.append((target, previous, item))
                    session.setdefault('unityHashes', {})[item['assetId']] = item[after_key + 'Hash']
                self.app.save_session(session)
                record['state'] = 'restored' if restore else 'applied'
                self.save(folder, record)
            except Exception as failure:
                failed = []
                for target, previous, item in reversed(written):
                    try:
                        if digest(target.read_bytes()) != item[after_key + 'Hash']:
                            raise ValueError('File bị sửa bởi tiến trình khác.')
                        self.replace_png(target, previous)
                    except Exception:
                        failed.append(item['path'])
                session['unityHashes'] = previous_hashes
                try:
                    self.app.save_session(session)
                except Exception:
                    failed.append('session.json')
                record['state'] = 'recovery-needed' if failed else expected_state
                record['error'] = str(failure)
                self.save(folder, record)
                detail = (' Khôi phục thủ công từ ' + str(folder / before_key) if failed
                          else ' Đã khôi phục PNG đã ghi.')
                raise ValueError('Cập nhật thất bại: ' + str(failure) + detail) from failure
            result = self.public(folder, record)
            result['updated'] = len(written)
            return result
