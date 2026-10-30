"""Small prefab-based catalog previews, without Unity or import-session side effects."""
import base64
import io
from PIL import Image, ImageChops, ImageDraw, ImageFont
from unity_source import render_sprite


def rgba(value):
    return tuple(round(max(0, min(1, value.get(key, 1))) * 255) for key in ('r', 'g', 'b', 'a'))


def preview_scene(scene, registry):
    scale = min(220 / max(1, scene['width']), 260 / max(1, scene['height']))
    size = (max(1, round(scene['width'] * scale)), max(1, round(scene['height'] * scale)))
    rendered = {}

    def draw(node, origin_x=0, origin_y=0):
        x = origin_x + round(node.get('x', 0) * scale)
        y = origin_y + round(node.get('y', 0) * scale)
        width = min(1024, max(1, round(node.get('w', 1) * scale)))
        height = min(1024, max(1, round(node.get('h', 1) * scale)))
        layer = Image.new('RGBA', size)
        color = node.get('color')
        if color and node.get('type') != 'TEXT':
            ImageDraw.Draw(layer).rectangle((x, y, x + width, y + height), fill=rgba(color))
        if node.get('type') == 'IMAGE' and node.get('imageKey') in registry.renders:
            key = node['imageKey']
            if key not in rendered:
                recipe = registry.renders[key]
                raw = base64.b64decode(registry.assets[recipe['assetId']]['bytes'])
                rendered[key] = Image.open(io.BytesIO(render_sprite(raw, recipe))).convert('RGBA')
            image = rendered[key].resize((width, height), Image.Resampling.LANCZOS)
            if node.get('opacity', 1) != 1:
                alpha = image.getchannel('A').point(lambda value: round(value * node['opacity']))
                image.putalpha(alpha)
            if node.get('rotation'):
                image = image.rotate(-node['rotation'], resample=Image.Resampling.BICUBIC, expand=True)
            layer.alpha_composite(image, (x + (width - image.width) // 2, y + (height - image.height) // 2))
        if node.get('type') == 'TEXT':
            text = str(node.get('text', ''))
            if node.get('uppercase'):
                text = text.upper()
            try:
                font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', max(1, round(node.get('fontSize', 20) * scale)))
            except OSError:
                font = ImageFont.load_default()
            if node.get('textLayout', {}).get('wrap', True):
                lines = []
                measure = ImageDraw.Draw(layer)
                for paragraph in text[:500].split('\n'):
                    current = ''
                    for word in paragraph.split(' '):
                        candidate = (current + ' ' + word).strip()
                        if current and measure.textlength(candidate, font=font) > width:
                            lines.append(current)
                            current = word
                        else:
                            current = candidate
                    lines.append(current)
                text = '\n'.join(lines)
            ImageDraw.Draw(layer).multiline_text((x + width / 2, y), text[:500], font=font,
                                                fill=rgba(color or {}), anchor='ma', align='center', spacing=0)
        for child in node.get('children', []):
            layer.alpha_composite(draw(child, x, y))
        if node.get('clip'):
            mask = Image.new('L', size)
            ImageDraw.Draw(mask).rectangle((x, y, x + width - 1, y + height - 1), fill=255)
            layer.putalpha(ImageChops.multiply(layer.getchannel('A'), mask))
        return layer

    canvas = draw(scene['root'])
    bounds = canvas.getbbox()
    if bounds:
        canvas = canvas.crop(bounds)
    canvas.thumbnail((160, 180), Image.Resampling.LANCZOS)
    result = io.BytesIO()
    canvas.save(result, format='PNG')
    return base64.b64encode(result.getvalue()).decode()
