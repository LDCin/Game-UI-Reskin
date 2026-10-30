"""Discover UI from active Addressables settings, then follow UI-only prefab references."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import re

class AddressableUI:
    def __init__(self, project):
        self.project = project
        self.ui_cache = {}
        self.docs_cache = {}
        self.notes = []
        self.entries = {}
        self.graph = {}
        self.catalog_cache = None

    def docs(self, path):
        from unity_source import load_docs
        key = str(path)
        if key not in self.docs_cache:
            self.project.read(path)
            self.docs_cache[key] = load_docs(path)
        return self.docs_cache[key]

    def is_ui(self, path, chain=()):
        path = Path(path).resolve()
        key = str(path)
        if key in self.ui_cache:
            return self.ui_cache[key]
        if path.suffix.lower() != '.prefab' or key in chain or not path.is_file():
            return False
        # Only inspect transform/instance blocks to classify; do not parse gameplay objects.
        from unity_source import HEAD
        transform_result = None
        instances = []
        block = []
        kind = None
        def classify_block(class_id, lines):
            body = ''.join(lines)
            if class_id in (4, 224):
                if re.search(r'^  m_Father: \{fileID: 0\}', body, re.M):
                    return class_id == 224
            elif class_id == 1001:
                parent = re.search(r'm_TransformParent: \{fileID: (-?\d+)\}', body)
                source = re.search(r'm_SourcePrefab: \{fileID: [^,}]+, guid: ([a-f0-9]{32})', body)
                if parent and parent[1] == '0' and source:
                    instances.append(source[1])
            return None
        with path.open(encoding='utf-8-sig') as handle:
            for line in handle:
                head = HEAD.match(line)
                if head:
                    if kind is not None:
                        transform_result = classify_block(kind, block)
                        if transform_result is not None:
                            break
                    kind = int(head[1]) if int(head[1]) in (4, 224, 1001) and 'stripped' not in head[3] else None
                    block = []
                elif kind is not None:
                    block.append(line)
            else:
                if kind is not None:
                    transform_result = classify_block(kind, block)
        result = transform_result
        if result is None:
            result = False
            for guid in instances:
                source = self.project.resolve(guid)
                if source and self.is_ui(source, (*chain, key)):
                    result = True
                    break
        self.ui_cache[key] = result
        return result

    def mono(self, path):
        return next((v for v in self.docs(path).values() if v['_class'] == 114), {})

    def roots(self):
        project = self.project
        data = project.root / 'Assets' / 'AddressableAssetsData'
        default = data / 'DefaultObject.asset'
        settings = None
        if default.is_file():
            guid = self.mono(default).get('m_AddressableAssetSettingsGuid')
            settings = project.resolve(guid)
        if settings is None:
            fallback = data / 'AddressableAssetSettings.asset'
            if fallback.is_file():
                settings = fallback
        if settings is None:
            # Metadata paths only; content is read solely for candidates matching Addressables settings.
            project.index_metadata()
            candidates = sorted(set(path for path in project.guid_paths.values() if path
                                    and path.name == 'AddressableAssetSettings.asset'))
            if len(candidates) == 1:
                settings = candidates[0]
        if settings is None:
            raise ValueError('Không tìm thấy AddressableAssetSettings đang dùng trong project.')
        settings_data = self.mono(settings)
        groups = settings_data.get('m_GroupAssets', []) or []
        project.resolve_many([value.get('guid') for value in groups])
        entries = []
        for group_ref in groups:
            group_path = project.resolve(group_ref.get('guid'))
            if not group_path:
                self.notes.append('Không tìm được Addressables group ' + str(group_ref.get('guid')))
                continue
            group = self.mono(group_path)
            group_name = group.get('m_GroupName') or group_path.stem
            for entry in group.get('m_SerializeEntries', []) or []:
                # Built-in Resources/EditorSceneList entries are not asset GUIDs.
                if re.fullmatch('[a-f0-9]{32}', str(entry.get('m_GUID', ''))):
                    entries.append((entry, group_name))
        project.resolve_many([entry.get('m_GUID') for entry, _ in entries])
        seeds = []
        # Explicit entries override folder-derived addresses, including excluded/moved assets.
        explicit = {str(entry.get('m_GUID')) for entry, _ in entries}
        for entry, group_name in entries:
            source = project.resolve(entry.get('m_GUID'))
            if not source:
                self.notes.append('Không tìm được Addressable ' + str(entry.get('m_Address', entry.get('m_GUID'))))
                continue
            if source.is_dir():
                candidates = sorted(source.rglob('*.prefab'))
                for candidate in candidates:
                    if not project.valid_asset(candidate):
                        continue
                    meta = Path(str(candidate) + '.meta')
                    if meta.is_file():
                        project._index_meta(meta)
                        text = meta.read_text(encoding='utf-8-sig', errors='replace')[:300]
                        match = re.search(r'^guid:\s*([a-f0-9]{32})', text, re.M)
                        if match and match[1] in explicit:
                            continue
                    address = str(entry.get('m_Address', '')) + '/' + candidate.relative_to(source).as_posix()
                    seeds.append((candidate, address, group_name, str(entry.get('m_GUID')), True))
            elif source.suffix.lower() == '.prefab':
                seeds.append((source, str(entry.get('m_Address', source.stem)), group_name,
                              str(entry.get('m_GUID')), False))
        return seeds

    def prefab_dependencies(self, path):
        from unity_source import references
        project = self.project
        docs = self.docs(path)
        # Only Unity UI components or source-prefab links may lead the dependency graph.
        ui_gos = {str(v.get('m_GameObject', {}).get('fileID')) for v in docs.values() if v['_class'] == 224}
        refs = []
        excluded = {'m_Script', 'm_Material', 'm_fontAsset', 'm_sharedMaterial', 'm_Font', 'm_FontData',
                    'm_CorrespondingSourceObject', 'm_PrefabAsset'}
        for obj in docs.values():
            if obj['_class'] == 1001:
                refs.extend(references(obj.get('m_SourcePrefab', {})))
                # Prefab-valued instance overrides can replace runtime UI prefabs.
                for override in obj.get('m_Modification', {}).get('m_Modifications', []) or []:
                    refs.extend(references(override.get('objectReference', {})))
            elif obj['_class'] == 114 and str(obj.get('m_GameObject', {}).get('fileID')) in ui_gos:
                for field, value in obj.items():
                    if field not in excluded and not field.startswith('_'):
                        refs.extend(references(value))
        targets = {ref.get('guid') for ref in refs if ref.get('guid')}
        def asset_reference_guids(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == 'm_AssetGUID' and isinstance(child, str) and re.fullmatch('[a-f0-9]{32}', child):
                        yield child
                    elif key not in excluded:
                        yield from asset_reference_guids(child)
            elif isinstance(value, list):
                for child in value:
                    yield from asset_reference_guids(child)
        for obj in docs.values():
            if obj['_class'] == 114 and str(obj.get('m_GameObject', {}).get('fileID')) in ui_gos:
                targets.update(asset_reference_guids(obj))
        project.resolve_many(targets)
        found = set()
        configs = deque()
        seen_configs = set()
        def consider(guid):
            target = project.resolve(guid)
            if not target:
                return
            if target.suffix.lower() == '.prefab':
                if self.is_ui(target):
                    found.add(target)
                # Stop at non-UI prefab: do not traverse its objects/dependencies.
            elif target.suffix.lower() == '.asset' and target.stat().st_size <= 4 * 1024 * 1024:
                configs.append(target)
        for guid in targets:
            consider(guid)
        while configs:
            config = configs.popleft()
            if config in seen_configs:
                continue
            seen_configs.add(config)
            for obj in self.docs(config).values():
                for field, value in obj.items():
                    if field in excluded or field.startswith('_'):
                        continue
                    for ref in references(value):
                        consider(ref.get('guid'))
                    for guid in asset_reference_guids(value):
                        consider(guid)
        found.discard(path.resolve())
        return sorted(found)

    def catalog(self, refresh=False):
        if self.catalog_cache is not None and not refresh:
            return self.catalog_cache
        if refresh:
            self.ui_cache.clear()
            self.docs_cache.clear()
        self.notes = []
        self.entries = {}
        self.graph = {}
        seeds = self.roots()
        queue = deque()
        paths = {}
        for path, address, group, guid, folder_entry in seeds:
            if not self.is_ui(path):
                continue
            rel = path.relative_to(self.project.root).as_posix()
            self.entries.setdefault(rel, []).append({'address': address, 'group': group,
                                                    'entryGuid': guid, 'folderEntry': folder_entry})
            paths[rel] = path
            queue.append(rel)
        visited = set()
        while queue:
            rel = queue.popleft()
            if rel in visited:
                continue
            visited.add(rel)
            children = self.prefab_dependencies(paths[rel])
            self.graph[rel] = []
            for child in children:
                child_rel = child.relative_to(self.project.root).as_posix()
                paths[child_rel] = child
                self.graph[rel].append(child_rel)
                if child_rel not in visited:
                    queue.append(child_rel)
        parents = {key: [] for key in paths}
        for parent, children in self.graph.items():
            for child in children:
                parents[child].append(parent)
        result = []
        for rel in sorted(paths, key=lambda value: (value not in self.entries, paths[value].stem.casefold())):
            addressable = rel in self.entries
            is_battle = rel == 'Assets/GameCore/Presentation/Prefabs/BattlePass/BattlePassModal.prefab'
            result.append({'id': rel, 'name': paths[rel].stem, 'group': paths[rel].parent.name,
                           'isScreen': addressable, 'isAddressable': addressable,
                           'addresses': self.entries.get(rel, []),
                           'dependencies': self.graph.get(rel, []), 'referencedBy': sorted(parents[rel]),
                           'runtimeReady': is_battle,
                           'states': [{'id': 'season-start', 'name': 'Đầu mùa, chưa mua pass'}] if is_battle
                           else [{'id': 'prefab', 'name': 'Cấu trúc prefab — chưa xác minh runtime'}]})
        self.catalog_cache = result
        return result
