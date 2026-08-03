import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

GRID = 24.0
_cache = {}


def _p():
    return QPainterPath()


def _move(p, x, y):
    p.moveTo(x, y)
    return p


def _line(x1, y1, x2, y2):
    p = _p()
    p.moveTo(x1, y1)
    p.lineTo(x2, y2)
    return p


def _poly(pts, close=True):
    p = _p()
    p.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    if close:
        p.closeSubpath()
    return p


def _circle(cx, cy, r):
    p = _p()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def _rrect(x, y, w, h, r):
    p = _p()
    p.addRoundedRect(QRectF(x, y, w, h), r, r)
    return p


def _arc(cx, cy, r, start_deg, span_deg):
    p = _p()
    rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    p.arcMoveTo(rect, start_deg)
    p.arcTo(rect, start_deg, span_deg)
    return p


def _chevron(cx, cy, size, direction):
    dx, dy = {"left": (1, 0), "right": (-1, 0), "up": (0, 1), "down": (0, -1)}[direction]
    if dx:
        return _poly([(cx + dx * size * 0.5, cy - size), (cx - dx * size * 0.5, cy),
                      (cx + dx * size * 0.5, cy + size)], close=False)
    return _poly([(cx - size, cy + dy * size * 0.5), (cx, cy - dy * size * 0.5),
                  (cx + size, cy + dy * size * 0.5)], close=False)


def _star(cx, cy, outer, inner, points=5):
    p = _p()
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = -math.pi / 2 + i * math.pi / points
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        if i == 0:
            p.moveTo(x, y)
        else:
            p.lineTo(x, y)
    p.closeSubpath()
    return p


def _heart(cx, cy, w, h):
    p = _p()
    top = cy - h * 0.28
    p.moveTo(cx, cy + h * 0.5)
    p.cubicTo(cx - w * 0.98, cy - h * 0.06, cx - w * 0.62, top - h * 0.52, cx, top)
    p.cubicTo(cx + w * 0.62, top - h * 0.52, cx + w * 0.98, cy - h * 0.06, cx, cy + h * 0.5)
    p.closeSubpath()
    return p


def _speaker():
    return _poly([(3.5, 9.5), (7, 9.5), (11.5, 5.5), (11.5, 18.5), (7, 14.5), (3.5, 14.5)])


def _play():
    p = _p()
    p.moveTo(7.5, 5.2)
    p.lineTo(18.8, 11.4)
    p.quadTo(19.6, 12.0, 18.8, 12.6)
    p.lineTo(7.5, 18.8)
    p.quadTo(6.6, 19.2, 6.6, 18.2)
    p.lineTo(6.6, 5.8)
    p.quadTo(6.6, 4.8, 7.5, 5.2)
    p.closeSubpath()
    return [(p, "f")]


def _pause():
    return [(_rrect(7.0, 5.0, 3.6, 14.0, 1.6), "f"), (_rrect(13.4, 5.0, 3.6, 14.0, 1.6), "f")]


def _stop():
    return [(_rrect(6.2, 6.2, 11.6, 11.6, 2.6), "f")]


def _skip(flip):
    tri = _poly([(8.2, 5.4), (17.0, 11.4), (17.0, 12.6), (8.2, 18.6)])
    bar = _rrect(17.6, 5.4, 2.6, 13.2, 1.3)
    out = [(tri, "f"), (bar, "f")]
    if flip:
        out = [(_mirror(path), mode) for path, mode in out]
    return out


def _mirror(path):
    from PyQt6.QtGui import QTransform
    return QTransform().translate(GRID, 0).scale(-1, 1).map(path)


def _shuffle():
    a = _p()
    a.moveTo(3.0, 7.0)
    a.lineTo(6.4, 7.0)
    a.cubicTo(10.6, 7.0, 12.4, 17.0, 16.6, 17.0)
    a.lineTo(19.4, 17.0)
    b = _p()
    b.moveTo(3.0, 17.0)
    b.lineTo(6.4, 17.0)
    b.cubicTo(8.6, 17.0, 9.9, 14.2, 11.2, 11.6)
    c = _p()
    c.moveTo(14.0, 9.0)
    c.cubicTo(15.0, 7.6, 15.9, 7.0, 16.6, 7.0)
    c.lineTo(19.4, 7.0)
    return [(a, "s"), (b, "s"), (c, "s"),
            (_poly([(17.6, 4.8), (20.6, 7.0), (17.6, 9.2)]), "f"),
            (_poly([(17.6, 14.8), (20.6, 17.0), (17.6, 19.2)]), "f")]


def _repeat(one=False):
    p = _p()
    p.moveTo(7.6, 6.6)
    p.lineTo(16.0, 6.6)
    p.arcTo(QRectF(13.0, 6.6, 6.4, 6.4), 90, -90)
    p.lineTo(19.4, 11.0)
    q = _p()
    q.moveTo(16.4, 17.4)
    q.lineTo(8.0, 17.4)
    q.arcTo(QRectF(4.6, 11.0, 6.4, 6.4), 270, -90)
    q.lineTo(4.6, 13.0)
    out = [(p, "s"), (q, "s"),
           (_poly([(9.4, 4.4), (9.4, 8.8), (6.4, 6.6)]), "f"),
           (_poly([(14.6, 15.2), (14.6, 19.6), (17.6, 17.4)]), "f")]
    if one:
        g = _p()
        g.moveTo(11.0, 10.6)
        g.lineTo(12.4, 9.6)
        g.lineTo(12.4, 14.6)
        out.append((g, "s"))
        out.append((_line(10.9, 14.6, 13.9, 14.6), "s"))
    return out


def _volume(level):
    out = [(_speaker(), "f")]
    if level <= 0:
        out.append((_line(15.0, 9.4, 20.4, 14.6), "s"))
        out.append((_line(20.4, 9.4, 15.0, 14.6), "s"))
        return out
    radii = [(2.6, 3.4), (5.2, 4.4), (7.8, 5.4)]
    for i in range(min(level, 3)):
        r, _w = radii[i]
        out.append((_arc(11.5, 12.0, r + 1.4, -52, 104), "s"))
    return out


def _equalizer():
    out = []
    for x, knob in ((6.5, 8.4), (12.0, 14.2), (17.5, 10.6)):
        out.append((_line(x, 4.4, x, 19.6), "s"))
        out.append((_rrect(x - 2.6, knob - 1.4, 5.2, 2.8, 1.4), "f"))
    return out


def _search():
    return [(_circle(10.6, 10.6, 5.6), "s"), (_line(14.8, 14.8, 20.0, 20.0), "s")]


def _folder(open_lid=False):
    p = _p()
    p.moveTo(3.2, 7.2)
    p.lineTo(3.2, 18.2)
    p.lineTo(20.8, 18.2)
    p.lineTo(20.8, 9.0)
    p.lineTo(11.6, 9.0)
    p.lineTo(9.6, 6.2)
    p.lineTo(3.2, 6.2)
    p.closeSubpath()
    out = [(p, "s")]
    if open_lid:
        out.append((_line(3.2, 11.4, 20.8, 11.4), "s"))
    return out


def _note():
    p = _p()
    p.moveTo(9.6, 16.4)
    p.lineTo(9.6, 5.4)
    p.lineTo(18.4, 3.6)
    p.lineTo(18.4, 14.6)
    return [(p, "s"), (_circle(7.2, 16.6, 2.5), "f"), (_circle(16.0, 14.8, 2.5), "f")]


def _plus():
    return [(_line(12, 5.2, 12, 18.8), "s"), (_line(5.2, 12, 18.8, 12), "s")]


def _minus():
    return [(_line(5.2, 12, 18.8, 12), "s")]


def _close():
    return [(_line(6.4, 6.4, 17.6, 17.6), "s"), (_line(17.6, 6.4, 6.4, 17.6), "s")]


def _check():
    return [(_poly([(5.4, 12.6), (10.0, 17.0), (18.6, 7.4)], close=False), "s")]


def _trash():
    return [(_line(4.4, 7.0, 19.6, 7.0), "s"),
            (_poly([(9.0, 7.0), (9.4, 4.6), (14.6, 4.6), (15.0, 7.0)], close=False), "s"),
            (_poly([(6.2, 7.0), (7.4, 19.6), (16.6, 19.6), (17.8, 7.0)], close=False), "s"),
            (_line(10.2, 10.4, 10.6, 16.4), "s"), (_line(13.8, 10.4, 13.4, 16.4), "s")]


def _heart_icon(filled):
    return [(_heart(12, 12.6, 9.2, 9.6), "f" if filled else "s")]


def _star_icon(filled):
    return [(_star(12, 12.2, 8.4, 3.7), "f" if filled else "s")]


def _list():
    out = []
    for y in (7.0, 12.0, 17.0):
        out.append((_circle(5.4, y, 1.3), "f"))
        out.append((_line(9.0, y, 19.4, y), "s"))
    return out


def _grid():
    out = []
    for x in (4.6, 13.2):
        for y in (4.6, 13.2):
            out.append((_rrect(x, y, 6.2, 6.2, 1.7), "s"))
    return out


def _gear():
    out = [(_circle(12, 12, 3.2), "s")]
    ring = _p()
    for i in range(8):
        a = i * math.pi / 4
        x1 = 12 + 5.4 * math.cos(a)
        y1 = 12 + 5.4 * math.sin(a)
        x2 = 12 + 8.4 * math.cos(a)
        y2 = 12 + 8.4 * math.sin(a)
        ring.moveTo(x1, y1)
        ring.lineTo(x2, y2)
    out.append((ring, "s"))
    out.append((_circle(12, 12, 6.6), "s"))
    return out


def _sort():
    return [(_line(4.6, 7.0, 13.4, 7.0), "s"), (_line(4.6, 12.0, 11.0, 12.0), "s"),
            (_line(4.6, 17.0, 8.6, 17.0), "s"),
            (_line(17.2, 5.4, 17.2, 18.0), "s"),
            (_poly([(14.6, 15.4), (17.2, 19.0), (19.8, 15.4)]), "f")]


def _info():
    return [(_circle(12, 12, 8.4), "s"), (_circle(12, 7.9, 1.25), "f"),
            (_line(12, 11.2, 12, 16.6), "s")]


def _clock():
    return [(_circle(12, 12, 8.4), "s"),
            (_poly([(12, 7.2), (12, 12.2), (15.8, 14.2)], close=False), "s")]


def _timer():
    return [(_circle(12, 13.4, 7.4), "s"), (_line(9.4, 3.6, 14.6, 3.6), "s"),
            (_line(12, 3.6, 12, 6.0), "s"),
            (_poly([(12, 9.4), (12, 13.6), (15.2, 13.6)], close=False), "s")]


def _moon():
    p = _p()
    p.moveTo(19.0, 14.6)
    p.cubicTo(17.6, 15.3, 16.0, 15.6, 14.4, 15.2)
    p.cubicTo(10.4, 14.3, 8.2, 10.3, 9.6, 6.6)
    p.cubicTo(9.9, 5.8, 10.3, 5.1, 10.8, 4.5)
    p.cubicTo(6.4, 5.2, 3.6, 9.5, 4.7, 13.9)
    p.cubicTo(5.8, 18.3, 10.3, 20.9, 14.6, 19.6)
    p.cubicTo(16.6, 19.0, 18.2, 17.0, 19.0, 14.6)
    p.closeSubpath()
    return [(p, "f")]


def _sun():
    out = [(_circle(12, 12, 4.4), "f")]
    rays = _p()
    for i in range(8):
        a = i * math.pi / 4
        rays.moveTo(12 + 6.6 * math.cos(a), 12 + 6.6 * math.sin(a))
        rays.lineTo(12 + 9.2 * math.cos(a), 12 + 9.2 * math.sin(a))
    out.append((rays, "s"))
    return out


def _globe():
    out = [(_circle(12, 12, 8.4), "s"), (_line(3.6, 12, 20.4, 12), "s")]
    e = _p()
    e.addEllipse(QRectF(7.6, 3.6, 8.8, 16.8))
    out.append((e, "s"))
    return out


def _disc():
    return [(_circle(12, 12, 8.6), "s"), (_circle(12, 12, 3.0), "s"),
            (_circle(12, 12, 0.9), "f"),
            (_arc(12, 12, 6.0, 28, 96), "s"), (_arc(12, 12, 6.0, 208, 96), "s")]


def _wave():
    out = []
    heights = [3.0, 6.2, 9.4, 5.0, 8.2, 3.6, 6.8]
    for i, h in enumerate(heights):
        x = 4.2 + i * 2.7
        out.append((_line(x, 12 - h / 2, x, 12 + h / 2), "s"))
    return out


def _lyrics():
    out = [(_rrect(3.6, 4.6, 16.8, 14.8, 2.6), "s")]
    for i, (x0, x1) in enumerate(((6.8, 17.2), (6.8, 14.6), (6.8, 15.8))):
        y = 9.2 + i * 3.2
        out.append((_line(x0, y, x1, y), "s"))
    return out


def _queue():
    out = []
    for y in (6.6, 11.2):
        out.append((_line(4.0, y, 19.0, y), "s"))
    out.append((_line(4.0, 15.8, 12.4, 15.8), "s"))
    out.append((_line(16.4, 13.4, 16.4, 20.0), "s"))
    out.append((_line(13.1, 16.7, 19.7, 16.7), "s"))
    return out


def _person():
    body = _p()
    body.moveTo(4.8, 20.0)
    body.cubicTo(4.8, 15.4, 8.0, 13.2, 12.0, 13.2)
    body.cubicTo(16.0, 13.2, 19.2, 15.4, 19.2, 20.0)
    return [(_circle(12, 8.0, 3.8), "s"), (body, "s")]


def _chart():
    out = [(_poly([(4.2, 19.4), (4.2, 4.6)], close=False), "s"),
           (_poly([(4.2, 19.4), (20.0, 19.4)], close=False), "s")]
    for x, h in ((7.6, 4.4), (11.4, 8.8), (15.2, 6.2), (18.2, 11.0)):
        out.append((_rrect(x - 1.35, 19.4 - h, 2.7, h, 1.0), "f"))
    return out


def _filter():
    return [(_poly([(3.8, 5.4), (20.2, 5.4), (13.9, 12.6), (13.9, 19.4),
                    (10.1, 17.2), (10.1, 12.6)], close=True), "s")]


def _edit():
    return [(_poly([(4.4, 19.6), (5.6, 15.4), (16.2, 4.8), (19.2, 7.8),
                    (8.6, 18.4)], close=True), "s"),
            (_line(14.2, 6.8, 17.2, 9.8), "s")]


def _save():
    return [(_poly([(4.6, 4.6), (16.4, 4.6), (19.4, 7.6), (19.4, 19.4), (4.6, 19.4)],
                   close=True), "s"),
            (_rrect(8.2, 4.6, 7.6, 5.0, 0.8), "s"),
            (_rrect(7.4, 13.0, 9.2, 6.4, 1.0), "s")]


def _import_icon():
    return [(_line(12, 3.8, 12, 14.2), "s"),
            (_poly([(8.4, 10.8), (12, 15.0), (15.6, 10.8)]), "f"),
            (_poly([(4.4, 15.0), (4.4, 19.6), (19.6, 19.6), (19.6, 15.0)], close=False), "s")]


def _export_icon():
    return [(_line(12, 15.0, 12, 4.6), "s"),
            (_poly([(8.4, 8.0), (12, 3.8), (15.6, 8.0)]), "f"),
            (_poly([(4.4, 15.0), (4.4, 19.6), (19.6, 19.6), (19.6, 15.0)], close=False), "s")]


def _mini():
    return [(_rrect(3.4, 5.0, 17.2, 14.0, 2.4), "s"),
            (_rrect(12.0, 12.2, 7.0, 5.4, 1.4), "f")]


def _expand():
    out = []
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        cx = 12 - sx * 6.6
        cy = 12 - sy * 6.6
        out.append((_poly([(cx + sx * 3.6, cy), (cx, cy), (cx, cy + sy * 3.6)], close=False), "s"))
    return out


def _dots():
    return [(_circle(12, 5.6, 1.7), "f"), (_circle(12, 12, 1.7), "f"),
            (_circle(12, 18.4, 1.7), "f")]


def _help():
    p = _p()
    p.moveTo(9.0, 9.4)
    p.cubicTo(9.0, 6.6, 15.2, 6.4, 15.2, 9.8)
    p.cubicTo(15.2, 12.2, 12.0, 12.4, 12.0, 15.2)
    return [(_circle(12, 12, 8.6), "s"), (p, "s"), (_circle(12, 18.2, 1.2), "f")]


def _cover():
    return [(_rrect(3.8, 3.8, 16.4, 16.4, 2.6), "s"),
            (_circle(9.0, 9.0, 1.9), "f"),
            (_poly([(3.8, 17.4), (9.8, 11.6), (14.0, 15.6), (16.6, 13.2), (20.2, 16.6)],
                   close=False), "s")]


def _headphones():
    return [(_arc(12, 12.4, 8.2, 0, 180), "s"),
            (_rrect(3.2, 12.0, 4.6, 7.6, 2.1), "f"),
            (_rrect(16.2, 12.0, 4.6, 7.6, 2.1), "f")]


def _speed():
    return [(_arc(12, 15.0, 7.8, 8, 164), "s"),
            (_poly([(11.0, 16.2), (16.8, 8.8), (13.4, 15.2)]), "f"),
            (_circle(12, 15.0, 1.7), "f")]


def _crossfade():
    a = _p()
    a.moveTo(3.6, 18.4)
    a.cubicTo(9.0, 18.4, 9.0, 6.2, 14.4, 6.2)
    a.lineTo(20.4, 6.2)
    b = _p()
    b.moveTo(3.6, 6.2)
    b.cubicTo(9.0, 6.2, 9.0, 18.4, 14.4, 18.4)
    b.lineTo(20.4, 18.4)
    return [(a, "s"), (b, "s")]


def _bluetooth():
    p = _p()
    p.moveTo(8.4, 8.0)
    p.lineTo(15.6, 15.4)
    p.lineTo(12.0, 19.2)
    p.lineTo(12.0, 4.8)
    p.lineTo(15.6, 8.6)
    p.lineTo(8.4, 16.0)
    return [(p, "s")]


def _speaker_box():
    return [(_rrect(6.0, 3.4, 12.0, 17.2, 2.4), "s"),
            (_circle(12, 14.6, 3.4), "s"),
            (_circle(12, 7.4, 1.5), "f")]


def _usb():
    return [(_line(12, 20.0, 12, 5.6), "s"),
            (_poly([(9.6, 7.6), (12, 3.4), (14.4, 7.6)]), "f"),
            (_line(12, 13.4, 7.8, 10.6), "s"),
            (_rrect(6.2, 8.4, 3.2, 3.2, 0.8), "f"),
            (_line(12, 16.2, 16.2, 13.4), "s"),
            (_circle(16.8, 12.6, 1.7), "f")]


def _monitor():
    return [(_rrect(3.2, 4.6, 17.6, 11.8, 2.0), "s"),
            (_line(8.6, 20.0, 15.4, 20.0), "s"),
            (_line(12, 16.4, 12, 20.0), "s")]


BUILDERS = {
    "play": _play,
    "bluetooth": _bluetooth,
    "speaker": _speaker_box,
    "usb": _usb,
    "monitor": _monitor,
    "pause": _pause,
    "stop": _stop,
    "next": lambda: _skip(False),
    "prev": lambda: _skip(True),
    "shuffle": _shuffle,
    "repeat": lambda: _repeat(False),
    "repeat_one": lambda: _repeat(True),
    "volume_mute": lambda: _volume(0),
    "volume_low": lambda: _volume(1),
    "volume_mid": lambda: _volume(2),
    "volume_high": lambda: _volume(3),
    "equalizer": _equalizer,
    "search": _search,
    "folder": lambda: _folder(False),
    "folder_open": lambda: _folder(True),
    "note": _note,
    "plus": _plus,
    "minus": _minus,
    "close": _close,
    "check": _check,
    "trash": _trash,
    "heart": lambda: _heart_icon(False),
    "heart_filled": lambda: _heart_icon(True),
    "star": lambda: _star_icon(False),
    "star_filled": lambda: _star_icon(True),
    "list": _list,
    "grid": _grid,
    "gear": _gear,
    "sort": _sort,
    "info": _info,
    "clock": _clock,
    "timer": _timer,
    "moon": _moon,
    "sun": _sun,
    "globe": _globe,
    "disc": _disc,
    "wave": _wave,
    "lyrics": _lyrics,
    "queue": _queue,
    "person": _person,
    "chart": _chart,
    "filter": _filter,
    "edit": _edit,
    "save": _save,
    "import": _import_icon,
    "export": _export_icon,
    "mini": _mini,
    "expand": _expand,
    "dots": _dots,
    "help": _help,
    "cover": _cover,
    "headphones": _headphones,
    "speed": _speed,
    "crossfade": _crossfade,
    "chevron_left": lambda: [(_chevron(12, 12, 4.2, "left"), "s")],
    "chevron_right": lambda: [(_chevron(12, 12, 4.2, "right"), "s")],
    "chevron_up": lambda: [(_chevron(12, 12, 4.2, "up"), "s")],
    "chevron_down": lambda: [(_chevron(12, 12, 4.2, "down"), "s")],
}


def names():
    return sorted(BUILDERS)


def paint(painter: QPainter, name: str, rect: QRectF, color, width=2.0):
    builder = BUILDERS.get(name)
    if builder is None:
        return
    col = QColor(color)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(rect.x(), rect.y())
    scale = min(rect.width(), rect.height()) / GRID
    painter.scale(scale, scale)

    pen = QPen(col)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    for path, mode in builder():
        if mode == "f":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(col)
            painter.drawPath(path)
        else:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
    painter.restore()


def pixmap(name: str, size: int, color, width=2.0, dpr=1.0) -> QPixmap:
    key = (name, size, QColor(color).name(QColor.NameFormat.HexArgb), round(width, 2), round(dpr, 2))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    paint(painter, name, QRectF(0, 0, size, size), color, width)
    painter.end()
    _cache[key] = px
    return px


def icon(name: str, size: int = 24, color="#ffffff", width=2.0) -> QIcon:
    ic = QIcon()
    for factor in (1.0, 2.0):
        ic.addPixmap(pixmap(name, size, color, width, factor))
    return ic


def clear_cache():
    _cache.clear()
