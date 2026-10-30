figma.showUI(__html__, { width: 860, height: 700 });
const APP = 'game-ui-reskin-v1';
const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
let running = false;
let active = null;
function post(type, values = {}) { figma.ui.postMessage(Object.assign({ type }, values)); }
function decode(value) {
    const bytes = new Uint8Array(Math.floor(value.length * 3 / 4)
        - (value.endsWith('==') ? 2 : value.endsWith('=') ? 1 : 0));
    let acc = 0, bits = 0, offset = 0;
    for (let i = 0; i < value.length; i++) {
        const digit = alphabet.indexOf(value[i]);
        if (digit < 0) { continue; }
        acc = (acc << 6) | digit;
        bits += 6;
        if (bits >= 8) { bits -= 8; bytes[offset++] = (acc >> bits) & 255; }
    }
    return bytes;
}
function encode(bytes) {
    const parts = [];
    for (let i = 0; i < bytes.length; i += 3) {
        const n = (bytes[i] << 16) | ((bytes[i + 1] || 0) << 8) | (bytes[i + 2] || 0);
        parts.push(alphabet[(n >> 18) & 63] + alphabet[(n >> 12) & 63]
            + (i + 1 < bytes.length ? alphabet[(n >> 6) & 63] : '=')
            + (i + 2 < bytes.length ? alphabet[n & 63] : '='));
    }
    return parts.join('');
}
function data(node, key) { return node && !node.removed ? node.getPluginData(key) : ''; }
function mark(node, values) {
    node.setPluginData('guiApp', APP);
    for (const key of Object.keys(values)) { node.setPluginData(key, String(values[key])); }
}
function progress(text) { post('progress', { text }); }
function geometry(node, spec) {
    node.resize(Math.max(.001, spec.w), Math.max(.001, spec.h));
    node.x = spec.x;
    node.y = spec.y;
    if (spec.rotation) {
        const a = spec.rotation * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
        const cx = spec.w / 2, cy = spec.h / 2;
        node.relativeTransform = [[c, -s, spec.x + cx - c * cx + s * cy],
            [s, c, spec.y + cy - s * cx - c * cy]];
    }
}
function applyTextLayout(node, spec) {
    const layout = spec.textLayout;
    if (!layout) { return; }
    // Measure using Figma's font engine; never guess glyph widths or shrink the source RectTransform.
    const width = Math.max(.001, spec.w), height = Math.max(.001, spec.h);
    const measure = size => {
        node.textAutoResize = 'NONE';
        node.fontSize = size;
        node.resize(width, height);
        node.textAutoResize = layout.wrap ? 'HEIGHT' : 'WIDTH_AND_HEIGHT';
        return node.height <= height + .01 && (layout.wrap || node.width <= width + .01);
    };
    if (layout.autoSize) {
        let minimum = Math.max(1, layout.fontSizeMin || 1);
        let maximum = Math.max(minimum, layout.fontSizeMax || spec.fontSize);
        if (!measure(maximum)) {
            if (measure(minimum)) {
                for (let i = 0; i < 9; i++) {
                    const middle = (minimum + maximum) / 2;
                    if (measure(middle)) { minimum = middle; } else { maximum = middle; }
                }
            }
            measure(minimum);
        }
    } else if (layout.overflow === 0) {
        measure(spec.fontSize);
    } else {
        // Retain the source fixed box for non-overflow modes until truncation/masking is supported.
        node.textAutoResize = 'NONE';
        node.resize(width, height);
    }
    if (node.textAutoResize !== 'NONE') {
        const horizontal = spec.align === 'RIGHT' ? 1 : spec.align === 'CENTER' ? .5 : 0;
        const vertical = spec.vertical === 'BOTTOM' ? 1 : spec.vertical === 'CENTER' ? .5 : 0;
        node.x = spec.x + (width - node.width) * horizontal;
        node.y = spec.y + (height - node.height) * vertical;
        node.textAlignVertical = 'TOP';
    }
    node.setPluginData('unityTextLayout', JSON.stringify({ sourceBox: {
        x: spec.x, y: spec.y, width, height }, settings: layout, margins: spec.unityMargins || {} }));
}
function paint(color) {
    return [{ type: 'SOLID', color: { r: color.r || 0, g: color.g || 0, b: color.b || 0 },
        opacity: color.a === undefined ? 1 : color.a }];
}
function walkSpec(spec, callback) {
    callback(spec);
    for (const child of spec.children || []) { walkSpec(child, callback); }
}
async function preflightFonts(payload) {
    const fonts = new Map();
    fonts.set('Inter/Regular', { family: 'Inter', style: 'Regular' });
    for (const scene of payload.scenes) {
        walkSpec(scene.root, spec => {
            if (spec.type === 'TEXT') {
                const font = spec.font || scene.font;
                if (!font) { throw new Error('Không xác định được font cho ' + spec.name); }
                fonts.set(JSON.stringify(font), font);
            }
        });
    }
    for (const font of fonts.values()) {
        try { await figma.loadFontAsync(font); }
        catch (error) { throw new Error('Thiếu font ' + font.family + ' / ' + font.style + '. Cài font gốc rồi thử lại.'); }
    }
}
function restoreActive() {
    for (const selection of figma.currentPage.selection || []) {
        let node = selection;
        while (node && node.type !== 'PAGE' && node.type !== 'DOCUMENT') {
            const session = data(node, 'guiSession');
            if (session) {
                const lib = figma.currentPage.children.find(n => data(n, 'guiLibrary') === session);
                if (lib) { active = JSON.parse(data(lib, 'guiManifest')); return active; }
            }
            node = node.parent;
        }
    }
    const libraries = figma.currentPage.children.filter(n => data(n, 'guiApp') === APP && data(n, 'guiLibrary'));
    if (libraries.length) {
        active = JSON.parse(data(libraries[libraries.length - 1], 'guiManifest'));
        return active;
    }
    throw new Error('Không tìm thấy Assets gốc trên trang này. Mở trang đã nhập hoặc nhập UI trước.');
}
function requireActive() {
    if (!active) { restoreActive(); }
    const library = figma.currentPage.children.find(n => data(n, 'guiLibrary') === active.sessionId);
    if (!library) { active = null; return restoreActive(); }
    return active;
}
function assetLabel(parent, text, x, y, width, size = 18) {
    const label = figma.createText();
    parent.appendChild(label);
    label.fontName = { family: 'Inter', style: 'Regular' };
    label.fontSize = size;
    label.characters = text;
    label.textAutoResize = 'HEIGHT';
    label.resize(Math.max(1, width), 24);
    label.x = x;
    label.y = y;
    return label;
}
function organizeAssets(library, payload, masters) {
    let offset = 0;
    const groups = [];
    for (const scene of payload.scenes) {
        const used = new Set();
        walkSpec(scene.root, spec => { if (spec.assetId) { used.add(spec.assetId); } });
        const assets = payload.assets.filter(asset => used.has(asset.id));
        const group = figma.createFrame();
        library.appendChild(group);
        group.name = scene.name + ' — Assets';
        group.fills = [];
        group.clipsContent = false;
        group.x = offset;
        group.y = 0;
        mark(group, { guiAssetGroup: scene.id, guiSession: payload.sessionId });
        const widths = [280, 280, 280];
        assets.forEach((asset, index) => { widths[index % 3] = Math.max(widths[index % 3], asset.width + 32); });
        const width = widths.reduce((sum, value) => sum + value, 0) + 80;
        assetLabel(group, group.name, 0, 0, width, 26);
        let y = 70;
        for (let row = 0; row < assets.length; row += 3) {
            const items = assets.slice(row, row + 3);
            const height = Math.max(...items.map(asset => asset.height)) + 100;
            let x = 0;
            items.forEach((asset, column) => {
                const master = masters.get(asset.id);
                const owned = master.parent === library;
                const card = figma.createFrame();
                group.appendChild(card);
                card.name = asset.path.split('/').pop();
                card.resize(widths[column], height);
                card.x = x;
                card.y = y;
                card.fills = [];
                card.clipsContent = false;
                mark(card, { guiAssetCard: asset.id, guiSession: payload.sessionId, guiPath: asset.path });
                const view = owned ? master : master.createInstance();
                card.appendChild(view);
                view.x = 16;
                view.y = 60;
                if (!owned) { mark(view, { guiSharedAsset: asset.id, guiSession: payload.sessionId }); }
                assetLabel(card, card.name + (owned ? '' : ' · dùng chung'), 16, 8, widths[column] - 32);
                x += widths[column] + 40;
            });
            y += height + 32;
        }
        group.resizeWithoutConstraints(width, Math.max(120, y));
        groups.push({ sceneId: scene.id, x: offset, width, height: group.height });
        offset += width + 160;
    }
    library.resizeWithoutConstraints(Math.max(1, offset - 160), Math.max(120, ...groups.map(group => group.height)));
    return groups;
}
function linkedSprite(spec, render, master) {
    if (!master || !render) { return null; }
    const tint = render.tint || {};
    const crop = render.crop || [0, 0, master.width, master.height, 0];
    if (crop[4] || ['r', 'g', 'b'].some(key => Math.abs((tint[key] === undefined ? 1 : tint[key]) - 1) > .000001)) {
        return null;
    }
    const node = figma.createFrame();
    node.resize(Math.max(.001, spec.w), Math.max(.001, spec.h));
    node.fills = [];
    node.clipsContent = true;
    node.opacity = (spec.opacity === undefined ? 1 : spec.opacity) * (tint.a === undefined ? 1 : tint.a);
    const border = render.border || {};
    const left = Math.max(0, Math.trunc(border.x || 0)), right = Math.max(0, Math.trunc(border.z || 0));
    const top = Math.max(0, Math.trunc(border.w || 0)), bottom = Math.max(0, Math.trunc(border.y || 0));
    const w = render.width, h = render.height;
    const sx = [0, left, crop[2] - right, crop[2]], sy = [0, top, crop[3] - bottom, crop[3]];
    const kx = Math.min(1, w / Math.max(1, left + right)), ky = Math.min(1, h / Math.max(1, top + bottom));
    const dx = [0, Math.round(left * kx), w - Math.round(right * kx), w];
    const dy = [0, Math.round(top * ky), h - Math.round(bottom * ky), h];
    const sliced = left || right || top || bottom;
    const regions = [];
    if (sliced) {
        for (let y = 0; y < 3; y++) {
            for (let x = 0; x < 3; x++) {
                regions.push([sx[x], sy[y], sx[x + 1] - sx[x], sy[y + 1] - sy[y],
                    dx[x], dy[y], dx[x + 1] - dx[x], dy[y + 1] - dy[y]]);
            }
        }
    } else { regions.push([0, 0, crop[2], crop[3], 0, 0, w, h]); }
    for (const region of regions) {
        if (Math.min(region[2], region[3], region[6], region[7]) <= 0) { continue; }
        const patch = figma.createFrame();
        node.appendChild(patch);
        patch.name = sliced ? 'Nine-slice · ' + region[0] + ',' + region[1] : 'Sprite liên kết';
        const scaleX = region[6] / region[2] * spec.w / w;
        const scaleY = region[7] / region[3] * spec.h / h;
        patch.resize(region[6] * spec.w / w, region[7] * spec.h / h);
        patch.x = region[4] * spec.w / w;
        patch.y = region[5] * spec.h / h;
        patch.fills = [];
        patch.clipsContent = true;
        const instance = master.createInstance();
        patch.appendChild(instance);
        instance.resize(master.width * scaleX, master.height * scaleY);
        instance.x = -(crop[0] + region[0]) * scaleX;
        instance.y = -(crop[1] + region[1]) * scaleY;
    }
    mark(node, { guiLiveAsset: spec.assetId, guiPreviewMode: 'component-instance' });
    return node;
}
async function importScenes(payload, mode) {
    if (aiPendingMasters().length) { throw new Error('Áp dụng hoặc hủy xem thử AI trước khi nhập màn khác.'); }
    if (!payload.renders) { throw new Error('Local connector đang chạy bản cũ. Bấm Khởi động lại local rồi nhập lại.'); }
    await preflightFonts(payload);
    const created = [];
    const old = mode === 'replace' ? figma.currentPage.children.filter(n => data(n, 'guiProject') === payload.projectId
        && payload.scenes.some(scene => data(n, 'guiScreen') === scene.id)) : [];
    try {
        const images = {};
        for (const key of Object.keys(payload.images)) { images[key] = figma.createImage(decode(payload.images[key])).hash; }
        const library = figma.createFrame();
        created.push(library);
        library.name = 'Assets gốc · ' + payload.sessionId.slice(0, 8);
        library.fills = [];
        library.clipsContent = false;
        library.resize(3200, 100);
        library.x = Math.round(figma.viewport.center.x - 540
            + payload.scenes.reduce((sum, scene) => sum + scene.width + 100, 0) + 200);
        library.y = Math.round(figma.viewport.center.y);
        const manifest = { sessionId: payload.sessionId, projectId: payload.projectId,
            assets: payload.assets.map(({ id, path, width, height, sha256 }) => ({ id, path, width, height, sha256 })),
            reference: payload.reference, referenceStatus: payload.referenceStatus };
        mark(library, { guiLibrary: payload.sessionId, guiSession: payload.sessionId,
            guiProject: payload.projectId, guiManifest: JSON.stringify(manifest) });
        const masters = new Map();
        for (const asset of payload.assets) {
            const master = figma.createComponent();
            library.appendChild(master);
            master.name = asset.path.split('/').pop();
            master.resize(asset.width, asset.height);
            master.x = 0;
            master.y = 0;
            master.constraints = { horizontal: 'MIN', vertical: 'MIN' };
            master.fills = [];
            master.clipsContent = true;
            mark(master, { guiAsset: asset.id, guiSession: payload.sessionId, guiPath: asset.path,
                guiWidth: asset.width, guiHeight: asset.height, guiSourceHash: asset.sha256 });
            const rectangle = figma.createRectangle();
            master.appendChild(rectangle);
            rectangle.name = 'Sprite gốc — thay ảnh hoặc chỉnh thiết kế bên trong';
            rectangle.resize(asset.width, asset.height);
            rectangle.x = rectangle.y = 0;
            rectangle.fills = [{ type: 'IMAGE', imageHash: figma.createImage(decode(asset.bytes)).hash, scaleMode: 'FILL' }];
            rectangle.constraints = { horizontal: 'STRETCH', vertical: 'STRETCH' };
            masters.set(asset.id, master);
        }
        const groups = organizeAssets(library, payload, masters);
        const mapping = [];
        const roots = [];
        function make(spec, parent, scene, origin) {
            let node;
            const source = spec.sourcePrefab ? { sourcePrefab: spec.sourcePrefab, fileID: spec.fileID, path: spec.path } : origin;
            if (spec.type === 'TEXT') {
                node = figma.createText();
                parent.appendChild(node);
                node.fontName = spec.font || scene.font;
                node.fontSize = spec.fontSize;
                node.characters = spec.uppercase ? spec.text.toUpperCase() : spec.text;
                node.textAutoResize = 'NONE';
                node.textAlignHorizontal = spec.align || 'CENTER';
                node.textAlignVertical = spec.vertical || 'CENTER';
                node.fills = paint(spec.color || { r: 1, g: 1, b: 1, a: 1 });
                if (spec.outline) {
                    node.strokes = paint({ r: .1254902, g: .16470589, b: .4156863, a: 1 });
                    node.strokeWeight = spec.outline;
                    node.strokeAlign = 'OUTSIDE';
                }
            } else if (spec.type === 'IMAGE') {
                node = linkedSprite(spec, (payload.renders || {})[spec.imageKey], masters.get(spec.assetId));
                if (!node) {
                    node = figma.createRectangle();
                    node.fills = [{ type: 'IMAGE', imageHash: images[spec.imageKey], scaleMode: 'FILL' }];
                    node.opacity = spec.opacity === undefined ? 1 : spec.opacity;
                    mark(node, { guiPreviewMode: 'sync-required' });
                }
                parent.appendChild(node);
            } else {
                node = figma.createFrame();
                parent.appendChild(node);
                node.fills = spec.color ? paint(spec.color) : [];
                node.clipsContent = !!spec.clip;
            }
            node.name = spec.name;
            geometry(node, spec);
            if (spec.type === 'TEXT') { applyTextLayout(node, spec); }
            mark(node, { guiSession: payload.sessionId, guiProject: payload.projectId, guiKey: spec.key || '' });
            if (source) { node.setPluginData('unitySource', JSON.stringify(source)); }
            if (spec.assetId) { mark(node, { guiAssetReference: spec.assetId, guiRender: spec.imageKey }); }
            const record = Object.assign({}, source || {}, { nodeId: node.id, name: node.name, type: node.type,
                assetId: spec.assetId, spritePath: spec.spritePath, spriteGuid: spec.spriteGuid,
                spriteFileID: spec.spriteFileID, renderId: spec.imageKey, screenId: scene.id,
                masterNodeId: masters.has(spec.assetId) ? masters.get(spec.assetId).id : undefined,
                previewMode: spec.type === 'IMAGE' ? data(node, 'guiPreviewMode') : undefined });
            mapping.push(record);
            for (const child of spec.children || []) { make(child, node, scene, source); }
            return node;
        }
        let sceneX = Math.round(figma.viewport.center.x - 540);
        for (let i = 0; i < payload.scenes.length; i++) {
            const scene = payload.scenes[i];
            progress('Đang dựng ' + scene.name + ' (' + (i + 1) + '/' + payload.scenes.length + ')');
            const wrapper = figma.createFrame();
            created.push(wrapper);
            wrapper.name = scene.name + ' · ' + scene.state + (scene.runtimeReady ? '' : ' · Prefab cơ sở');
            wrapper.fills = [];
            wrapper.clipsContent = true;
            wrapper.resize(scene.width, scene.height);
            wrapper.x = sceneX;
            wrapper.y = Math.round(figma.viewport.center.y - scene.height / 2);
            const group = library.children.find(child => data(child, 'guiAssetGroup') === scene.id);
            const column = groups[i];
            group.x = sceneX + scene.width + 100 - library.x;
            group.y = wrapper.y - library.y;
            sceneX += scene.width + column.width + 260;
            mark(wrapper, { guiScreen: scene.id, guiSession: payload.sessionId, guiProject: payload.projectId,
                guiState: scene.state, guiRuntimeReady: scene.runtimeReady,
                guiWarnings: JSON.stringify(scene.warnings), guiReference: payload.reference || '' });
            make(scene.root, wrapper, scene, null);
            roots.push({ id: wrapper.id, screenId: scene.id, name: wrapper.name, warnings: scene.warnings });
        }
        const assetGroups = library.children.filter(child => data(child, 'guiAssetGroup'));
        const minX = Math.min(...assetGroups.map(group => group.x));
        const minY = Math.min(...assetGroups.map(group => group.y));
        library.x += minX;
        library.y += minY;
        for (const group of assetGroups) { group.x -= minX; group.y -= minY; }
        library.resizeWithoutConstraints(Math.max(...assetGroups.map(group => group.x + group.width)),
            Math.max(...assetGroups.map(group => group.y + group.height)));
        progress('Đang ghi baseline asset gốc…');
        const baselines = [];
        let index = 0;
        for (const asset of payload.assets) {
            progress('Baseline ' + (++index) + '/' + payload.assets.length);
            const bytes = await masters.get(asset.id).exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 }, useAbsoluteBounds: true });
            baselines.push({ assetId: asset.id, bytes: encode(bytes) });
        }
        for (const root of roots) {
            const wrapper = created.find(n => n.id === root.id);
            wrapper.setPluginData('unityMapping', JSON.stringify(mapping.filter(row => row.screenId === root.screenId)));
        }
        for (const previous of old) { previous.remove(); }
        active = manifest;
        figma.currentPage.selection = created.filter(n => roots.some(root => root.id === n.id));
        figma.viewport.scrollAndZoomIntoView(figma.currentPage.selection);
        post('imported', { manifest, baselines, mapping, roots, assetCount: payload.assets.length,
            linkedCount: mapping.filter(row => row.previewMode === 'component-instance').length,
            syncCount: mapping.filter(row => row.previewMode === 'sync-required').length });
    } catch (error) {
        for (const node of created) { if (!node.removed) { node.remove(); } }
        throw error;
    }
}
async function renderMasters(message) {
    if (['export-reskin', 'magic-source'].includes(message.type) && aiPendingMasters().length) {
        throw new Error('Áp dụng hoặc hủy xem thử AI trước khi xuất về folder.');
    }
    const manifest = requireActive();
    if (message.sessionId && manifest.sessionId !== message.sessionId) {
        throw new Error('Phiên nhập đang chọn đã thay đổi. Chọn lại asset rồi thử lại.');
    }
    const ids = new Set(message.assetIds || manifest.assets.map(asset => asset.id));
    const library = figma.currentPage.children.find(node => data(node, 'guiLibrary') === manifest.sessionId);
    const masters = library.findAll(node => node.type === 'COMPONENT' && data(node, 'guiAsset'));
    if ([...ids].some(id => !manifest.assets.some(asset => asset.id === id))) {
        throw new Error('Asset không thuộc phiên nhập đang mở.');
    }
    const entries = [];
    for (const asset of manifest.assets.filter(asset => ids.has(asset.id))) {
        const master = masters.find(node => data(node, 'guiAsset') === asset.id);
        if (!master || master.removed) { throw new Error('Không tìm thấy Assets gốc: ' + asset.path); }
        if (Math.abs(master.width - asset.width) > .01 || Math.abs(master.height - asset.height) > .01) {
            throw new Error(asset.path + ': cần giữ kích thước gốc ' + asset.width + '×' + asset.height + '.');
        }
        progress('Đang xuất asset ' + (entries.length + 1) + '/' + ids.size + ': ' + master.name);
        try {
            const bytes = await master.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 }, useAbsoluteBounds: true });
            entries.push({ assetId: asset.id, bytes: encode(bytes), nodeId: master.id });
        } catch (error) { throw new Error(asset.path + ': exportAsync thất bại — ' + error.message); }
    }
    if (!entries.length) { throw new Error('Chưa chọn asset để xuất.'); }
    post('assets-rendered', { operation: message.type, manifest, entries });
}
async function applyPreview(message) {
    const manifest = requireActive();
    if (message.sessionId !== manifest.sessionId) {
        throw new Error('Phản hồi xem trước thuộc phiên nhập khác. Kết nối lại rồi thử lại.');
    }
    let count = 0;
    for (const key of Object.keys(message.images || {})) {
        const hash = figma.createImage(decode(message.images[key])).hash;
        const nodes = figma.currentPage.findAll(node => data(node, 'guiSession') === manifest.sessionId
            && data(node, 'guiRender') === key && !data(node, 'guiLiveAsset'));
        for (const node of nodes) { node.fills = [{ type: 'IMAGE', imageHash: hash, scaleMode: 'FILL' }]; count++; }
    }
    post('preview-applied', { count });
}
async function exportScreen() {
    const manifest = requireActive();
    let wrapper = null;
    for (const selected of figma.currentPage.selection || []) {
        let node = selected;
        while (node && node.type !== 'PAGE' && node.type !== 'DOCUMENT') {
            if (data(node, 'guiScreen') && data(node, 'guiSession') === manifest.sessionId) { wrapper = node; break; }
            node = node.parent;
        }
        if (wrapper) { break; }
    }
    wrapper = wrapper || figma.currentPage.children.find(node => data(node, 'guiScreen')
        && data(node, 'guiSession') === manifest.sessionId);
    if (!wrapper || wrapper.removed) { throw new Error('Không tìm thấy frame màn. Chọn màn đã nhập trên trang này.'); }
    progress('Đang xuất PNG kiểm tra: ' + wrapper.name);
    const bytes = await wrapper.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: .5 } });
    post('screen-png', { bytes: Array.from(bytes) });
}
function mappedAsset(node) {
    const assetId = data(node, 'guiAssetReference') || data(node, 'guiLiveAsset') || data(node, 'guiSharedAsset')
        || data(node, 'guiAsset') || data(node, 'guiAssetCard');
    return assetId ? { assetId, sessionId: data(node, 'guiSession') } : null;
}
function selectAssetsFromCanvas() {
    if (aiPendingMasters().some(master => data(master, 'guiMagicJob'))) {
        throw new Error('Giữ hoặc hủy bản xem thử Magic trước khi chuyển sang thao tác này.');
    }
    const selection = figma.currentPage.selection || [];
    if (!selection.length) { throw new Error('Chọn sprite, component hoặc modal trên canvas trước.'); }
    const found = new Map();
    let unmatched = 0;
    function collect(node) {
        const match = mappedAsset(node);
        if (match) { found.set(match.sessionId + '/' + match.assetId, match); return 1; }
        let count = 0;
        for (const child of node.children || []) { count += collect(child); }
        return count;
    }
    for (const selected of selection) {
        let count = 0;
        let node = selected, match = null;
        while (node && node.type !== 'PAGE' && !match) { match = mappedAsset(node); node = node.parent; }
        if (match) { found.set(match.sessionId + '/' + match.assetId, match); }
        else { count = collect(selected); }
        if (!match && !count) { unmatched++; }
    }
    const sessions = new Set([...found.values()].map(match => match.sessionId));
    if (!found.size) { throw new Error('Selection không có sprite có mapping Unity. Chọn ảnh hoặc frame chứa ảnh.'); }
    if (sessions.size !== 1) {
        throw new Error('Selection thuộc nhiều phiên nhập. Chọn các element trong cùng một phiên để tránh xuất nhầm bản.');
    }
    const sessionId = [...sessions][0];
    const library = figma.currentPage.children.find(node => data(node, 'guiLibrary') === sessionId);
    if (!library) { throw new Error('Không tìm thấy Assets nguồn của selection.'); }
    const manifest = JSON.parse(data(library, 'guiManifest'));
    const assetIds = [...new Set([...found.values()].map(match => match.assetId))];
    if (assetIds.some(id => !manifest.assets.some(asset => asset.id === id))) {
        throw new Error('Mapping của selection không khớp thư viện nguồn.');
    }
    active = manifest;
    post('assets-selected', { manifest, assetIds, unmatched });
}
let thumbnailGeneration = 0;
async function assetThumbnails(message) {
    const generation = ++thumbnailGeneration;
    const library = figma.currentPage.children.find(node => data(node, 'guiLibrary') === message.sessionId);
    if (!library) { return; }
    const masters = library.findAll(node => node.type === 'COMPONENT' && data(node, 'guiAsset'));
    for (const master of masters) {
        if (generation !== thumbnailGeneration || library.removed) { return; }
        if (message.assetIds && !message.assetIds.includes(data(master, 'guiAsset'))) { continue; }
        try {
            const bytes = await master.exportAsync({ format: 'PNG', constraint: { type: 'SCALE',
                value: Math.min(1, 96 / Math.max(master.width, master.height)) }, useAbsoluteBounds: true });
            post('asset-thumbnail', { sessionId: message.sessionId, requestId: message.requestId,
                assetId: data(master, 'guiAsset'), bytes: encode(bytes) });
        } catch (error) {
            post('asset-thumbnail', { sessionId: message.sessionId, requestId: message.requestId,
                assetId: data(master, 'guiAsset'), error: error.message });
        }
    }
}
let aiTarget = null;
function aiRestore(master, key) {
    const value = data(master, key);
    if (!value) { return false; }
    const backup = JSON.parse(value);
    const overlay = master.children.find(child => child.id === backup.overlayId);
    if (overlay) { overlay.remove(); }
    for (const state of backup.states) {
        const child = master.children.find(node => node.id === state.id);
        if (child) { child.visible = state.visible; }
    }
    for (const saved of backup.renders || []) {
        const sprite = figma.currentPage.findAll(node => node.id === saved.id)[0];
        if (sprite) { sprite.fills = saved.fills; }
    }
    master.setPluginData(key, '');
    return true;
}
function aiPendingMasters() {
    return figma.currentPage.findAll(node => node.type === 'COMPONENT' && data(node, 'guiAiPending'));
}
function aiRevertPending() {
    for (const master of aiPendingMasters()) { aiRestore(master, 'guiAiPending'); }
}
async function aiSelectSource() {
    if (aiPendingMasters().some(master => data(master, 'guiMagicJob'))) {
        throw new Error('Giữ hoặc hủy bản xem thử Magic trước khi chuyển sang thao tác này.');
    }
    if ((figma.currentPage.selection || []).length !== 1) {
        throw new Error('Chọn đúng một asset nguồn hoặc sprite trong modal, rồi bấm Lấy từ selection.');
    }
    aiRevertPending();
    let node = figma.currentPage.selection[0], assetId = '', sessionId = '';
    while (node && node.type !== 'PAGE' && !assetId) {
        assetId = data(node, 'guiAssetReference') || data(node, 'guiLiveAsset') || data(node, 'guiSharedAsset')
            || data(node, 'guiAsset') || data(node, 'guiAssetCard');
        sessionId = data(node, 'guiSession');
        node = node.parent;
    }
    const library = figma.currentPage.children.find(item => data(item, 'guiLibrary') === sessionId);
    if (!library || !assetId) { throw new Error('Selection chưa có mapping Unity. Chọn một asset của tool.'); }
    const manifest = JSON.parse(data(library, 'guiManifest'));
    const asset = manifest.assets.find(item => item.id === assetId);
    const master = library.findAll(item => item.type === 'COMPONENT' && data(item, 'guiAsset') === assetId)[0];
    if (!asset || !master) { throw new Error('Không tìm thấy component nguồn của sprite.'); }
    if (master.width !== asset.width || master.height !== asset.height) {
        throw new Error('Component nguồn đã đổi kích thước. Khôi phục kích thước Unity trước khi dùng AI.');
    }
    const bytes = await master.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 },
        useAbsoluteBounds: true });
    active = manifest;
    const uses = figma.currentPage.findAll(item => data(item, 'guiSession') === sessionId
        && data(item, 'guiAssetReference') === assetId).length;
    aiTarget = { sessionId, assetId, masterId: master.id, path: asset.path, width: asset.width,
        height: asset.height, source: encode(bytes), uses };
    post('ai-source', { target: aiTarget, manifest, canUndo: !!data(master, 'guiAiUndo') });
}
function aiGetMaster(message) {
    if (!aiTarget || message.masterId !== aiTarget.masterId || message.sessionId !== aiTarget.sessionId) {
        throw new Error('Asset AI đã thay đổi. Lấy lại selection trước khi áp dụng.');
    }
    const master = figma.currentPage.findAll(node => node.id === aiTarget.masterId)[0];
    if (!master || master.type !== 'COMPONENT' || master.width !== aiTarget.width || master.height !== aiTarget.height) {
        throw new Error('Component nguồn đã bị xóa hoặc đổi kích thước.');
    }
    return master;
}
async function aiPreviewResult(message, notify = true) {
    if (notify && aiPendingMasters().some(master => data(master, 'guiMagicJob'))) {
        throw new Error('Giữ hoặc hủy xem thử Magic trước khi dùng AI từng asset.');
    }
    const master = aiGetMaster(message);
    const image = figma.createImage(decode(message.bytes));
    const size = await image.getSizeAsync();
    if (size.width !== aiTarget.width || size.height !== aiTarget.height) {
        throw new Error('Ảnh kết quả không khớp kích thước PNG Unity.');
    }
    aiRestore(master, 'guiAiPending');
    const bytes = await master.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 },
        useAbsoluteBounds: true });
    const sourceChanged = encode(bytes) !== aiTarget.source;
    const states = master.children.map(child => ({ id: child.id, visible: child.visible !== false }));
    const renders = figma.currentPage.findAll(node => data(node, 'guiSession') === aiTarget.sessionId
        && data(node, 'guiAssetReference') === aiTarget.assetId && !data(node, 'guiLiveAsset'))
        .map(node => ({ id: node.id, fills: JSON.parse(JSON.stringify(node.fills)) }));
    const overlay = figma.createRectangle();
    try {
        master.appendChild(overlay);
        overlay.name = 'AI reskin — PNG';
        overlay.resize(master.width, master.height);
        overlay.x = overlay.y = 0;
        overlay.constraints = { horizontal: 'STRETCH', vertical: 'STRETCH' };
        overlay.fills = [{ type: 'IMAGE', imageHash: image.hash, scaleMode: 'FILL' }];
        for (const state of states) { master.children.find(child => child.id === state.id).visible = false; }
        master.setPluginData('guiAiPending', JSON.stringify({ states, overlayId: overlay.id, renders, sourceChanged }));
    } catch (error) {
        overlay.remove();
        for (const state of states) { master.children.find(child => child.id === state.id).visible = state.visible; }
        throw error;
    }
    if (notify) { post('ai-previewed', { target: aiTarget, sourceChanged }); }
    return sourceChanged;
}
async function aiFinish(message) {
    if (aiPendingMasters().some(master => data(master, 'guiMagicJob'))) {
        throw new Error('Giữ hoặc hủy bản xem thử Magic trước khi chuyển sang thao tác này.');
    }
    const master = aiGetMaster(message);
    if (message.type === 'ai-apply') {
        const backup = data(master, 'guiAiPending');
        if (!backup) { throw new Error('Xem thử một phương án trước khi áp dụng.'); }
        master.setPluginData('guiAiUndo', backup);
        master.setPluginData('guiAiPending', '');
    } else if (message.type === 'ai-revert') { aiRestore(master, 'guiAiPending'); }
    else { aiRestore(master, 'guiAiPending'); aiRestore(master, 'guiAiUndo'); }
    aiTarget.source = encode(await master.exportAsync({ format: 'PNG', constraint: { type: 'SCALE', value: 1 },
        useAbsoluteBounds: true }));
    post('ai-finished', { operation: message.type, target: aiTarget, canUndo: !!data(master, 'guiAiUndo') });
}
function magicMasters(jobId, key) {
    return figma.currentPage.findAll(node => node.type === 'COMPONENT' && data(node, key) === jobId);
}
function magicSignature(master) {
    return JSON.stringify({ width: master.width, height: master.height, children: master.children.map(child => ({
        id: child.id, visible: child.visible, x: child.x, y: child.y, width: child.width, height: child.height,
        opacity: child.opacity, fills: child.fills })) });
}
function revertMagic(jobId) {
    const masters = magicMasters(jobId, 'guiMagicJob');
    for (const master of masters) { aiRestore(master, 'guiAiPending'); master.setPluginData('guiMagicJob', ''); }
    return masters.map(master => data(master, 'guiAsset'));
}
async function magicPreview(message) {
    const manifest = requireActive();
    if (manifest.sessionId !== message.sessionId) { throw new Error('Chọn lại đúng phiên của bộ Magic Reskin.'); }
    if (aiPendingMasters().some(master => data(master, 'guiMagicJob') !== message.jobId)) {
        throw new Error('Áp dụng hoặc hủy bản xem thử AI khác trước.');
    }
    if (!message.entries || !message.entries.length) { throw new Error('Chưa có ảnh Magic để xem thử.'); }
    const ids = new Set(message.entries.map(entry => entry.assetId));
    if (ids.size !== message.entries.length || [...ids].some(id => !manifest.assets.some(asset => asset.id === id))) {
        throw new Error('Bộ ảnh Magic không khớp mapping.');
    }
    const library = figma.currentPage.children.find(node => data(node, 'guiLibrary') === message.sessionId);
    const previousTarget = aiTarget;
    const changedAssetIds = [];
    revertMagic(message.jobId);
    try {
        for (const entry of message.entries) {
            const asset = manifest.assets.find(asset => asset.id === entry.assetId);
            const master = library.findAll(node => node.type === 'COMPONENT' && data(node, 'guiAsset') === asset.id)[0];
            if (!master) { throw new Error('Thiếu component nguồn: ' + asset.path); }
            aiTarget = { sessionId: message.sessionId, assetId: asset.id, masterId: master.id,
                width: asset.width, height: asset.height, source: entry.source };
            const changed = await aiPreviewResult(
                { masterId: master.id, sessionId: message.sessionId, bytes: entry.bytes }, false);
            if (changed) { changedAssetIds.push(asset.id); }
            master.setPluginData('guiMagicJob', message.jobId);
        }
    } catch (error) { revertMagic(message.jobId); throw error; }
    finally { aiTarget = previousTarget; }
    post('magic-previewed', { jobId: message.jobId, sessionId: message.sessionId,
        assetIds: [...ids], changedAssetIds });
}
function magicFinish(message) {
    let masters = magicMasters(message.jobId, message.type === 'magic-undo' ? 'guiMagicApplied' : 'guiMagicJob');
    if (!masters.length) { throw new Error('Không tìm thấy bản xem thử hoặc bản Magic đã áp dụng.'); }
    if (masters.some(master => data(master, 'guiSession') !== message.sessionId)) {
        throw new Error('Bộ Magic thuộc phiên nhập khác.');
    }
    if (message.type === 'magic-undo' && masters.some(master => data(master, 'guiMagicSignature') !== magicSignature(master))) {
        throw new Error('Artwork đã được chỉnh tiếp sau Magic. Chưa hoàn tác để tránh đè chỉnh sửa mới.');
    }
    if (message.type === 'magic-apply' && masters.some(master => !data(master, 'guiAiPending'))) {
        throw new Error('Bản xem thử Magic không còn nguyên vẹn. Hủy rồi xem thử lại.');
    }
    const ids = masters.map(master => data(master, 'guiAsset'));
    if (message.type === 'magic-revert') { revertMagic(message.jobId); }
    if (message.type === 'magic-apply') {
        for (const master of masters) {
            master.setPluginData('guiMagicUndo', data(master, 'guiAiPending'));
            master.setPluginData('guiAiPending', '');
            master.setPluginData('guiMagicJob', '');
            master.setPluginData('guiMagicApplied', message.jobId);
            master.setPluginData('guiMagicSignature', magicSignature(master));
        }
    }
    if (message.type === 'magic-undo') {
        for (const master of masters) {
            aiRestore(master, 'guiMagicUndo');
            master.setPluginData('guiMagicApplied', '');
            master.setPluginData('guiMagicSignature', '');
        }
    }
    post('magic-finished', { operation: message.type, jobId: message.jobId, sessionId: message.sessionId, assetIds: ids });
}
figma.ui.onmessage = async message => {
    if (!message) { return; }
    if (message.type === 'asset-thumbnails') { await assetThumbnails(message); return; }
    if (message.type === 'ready') {
        aiRevertPending();
        try {
            post('settings', { settings: await figma.clientStorage.getAsync(APP) || {} });
        } catch (error) {
            post('error', { text: 'Không đọc được cấu hình plugin: ' + error.message });
        }
        try { post('restored', { manifest: restoreActive() }); } catch (_) { /* No import on this page yet. */ }
        return;
    }
    if (message.type === 'save-settings') {
        try { await figma.clientStorage.setAsync(APP, message.settings); }
        catch (error) { post('error', { text: 'Không lưu được cấu hình plugin: ' + error.message }); }
        return;
    }
    if (running) { post('error', { text: 'Một thao tác đang chạy. Chờ hoàn tất rồi thử lại.' }); return; }
    running = true;
    try {
        if (message.type === 'magic-preview') { await magicPreview(message); }
        else if (['magic-apply', 'magic-revert', 'magic-undo'].includes(message.type)) { magicFinish(message); }
        else if (message.type === 'select-assets-from-canvas') { selectAssetsFromCanvas(); }
        else if (message.type === 'ai-source') { await aiSelectSource(); }
        else if (message.type === 'ai-preview') { await aiPreviewResult(message); }
        else if (['ai-apply', 'ai-revert', 'ai-undo'].includes(message.type)) { await aiFinish(message); }
        else if (message.type === 'import-scenes') { await importScenes(message.payload, message.mode); }
        else if (['export-reskin', 'sync-preview', 'magic-source'].includes(message.type)) { await renderMasters(message); }
        else if (message.type === 'apply-preview') { await applyPreview(message); }
        else if (message.type === 'export-screen') { await exportScreen(); }
        else if (message.type === 'focus-assets') {
            const manifest = requireActive();
            const library = figma.currentPage.children.find(node => data(node, 'guiLibrary') === manifest.sessionId);
            figma.currentPage.selection = [library];
            figma.viewport.scrollAndZoomIntoView([library]);
            post('done', { text: 'Chỉnh bên trong component Assets gốc; giữ nguyên kích thước component.' });
        } else if (message.type === 'export-mapping') {
            const manifest = requireActive();
            const screens = figma.currentPage.children.filter(node => data(node, 'guiScreen') && data(node, 'guiSession') === manifest.sessionId);
            const mapping = screens.flatMap(node => JSON.parse(data(node, 'unityMapping') || '[]'));
            post('mapping', { report: { manifest, mapping } });
        }
    } catch (error) { post('error', { operation: message.type, text: String(error.message || error) }); }
    finally { running = false; }
};

figma.on('close', aiRevertPending);
