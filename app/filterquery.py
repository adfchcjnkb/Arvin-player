import re
import time

TEXT_COLUMNS = ("title", "artist", "album", "albumartist", "genre", "comment", "path")
NUMERIC_COLUMNS = {
    "year": "year",
    "track": "track_no",
    "rating": "rating",
    "playcount": "play_count",
    "skipcount": "skip_count",
    "bpm": "bpm",
    "length": "duration",
    "duration": "duration",
    "samplerate": "sample_rate",
    "bitrate": "bitrate",
}
DATE_COLUMNS = {"added": "added", "lastplayed": "last_played"}
BOOL_COLUMNS = {"favorite": "favorite", "loved": "favorite"}

ALIASES = {
    "artist": "artist",
    "albumartist": "albumartist",
    "album": "album",
    "title": "title",
    "genre": "genre",
    "comment": "comment",
    "path": "path",
    "file": "path",
}

_OPS = ("<=", ">=", "!=", "<>", "==", "=", "<", ">")
_TOKEN = re.compile(r'"[^"]*"|\S+')
_DURATION = re.compile(r"^(?:(\d+):)?(\d+):(\d{1,2})$")


class Node:
    def sql(self, params):
        raise NotImplementedError


class All(Node):
    def sql(self, params):
        return "1"


class And(Node):
    def __init__(self, kids):
        self.kids = kids

    def sql(self, params):
        parts = [k.sql(params) for k in self.kids]
        return "(" + " AND ".join(parts) + ")" if parts else "1"


class Or(Node):
    def __init__(self, kids):
        self.kids = kids

    def sql(self, params):
        parts = [k.sql(params) for k in self.kids]
        return "(" + " OR ".join(parts) + ")" if parts else "1"


class Not(Node):
    def __init__(self, kid):
        self.kid = kid

    def sql(self, params):
        return "NOT (" + self.kid.sql(params) + ")"


class Term(Node):
    def __init__(self, column, op, value):
        self.column = column
        self.op = op
        self.value = value

    def sql(self, params):
        params.append(self.value)
        return f"{self.column} {self.op} ?"


class AnyText(Node):
    def __init__(self, value):
        self.value = value

    def sql(self, params):
        parts = []
        for col in ("title", "artist", "album", "albumartist", "genre", "path"):
            params.append(f"%{self.value}%")
            parts.append(f"IFNULL({col},'') LIKE ? ESCAPE '\\'")
        return "(" + " OR ".join(parts) + ")"


def _parse_duration(text):
    m = _DURATION.match(text)
    if not m:
        return None
    h, mnt, sec = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(sec)


def _parse_relative_date(text):
    m = re.match(r"^(\d+)\s*(day|days|week|weeks|month|months|year|years)$", text, re.I)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower().rstrip("s")
    scale = {"day": 86400, "week": 604800, "month": 2592000, "year": 31536000}[unit]
    return time.time() - n * scale


def _escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_op(text):
    for op in _OPS:
        if text.startswith(op):
            return op, text[len(op):]
    return None, text


def _numeric_term(column, op, raw):
    value = _parse_duration(raw)
    if value is None:
        try:
            value = float(raw) if "." in raw else int(raw)
        except ValueError:
            return None
    return Term(column, "=" if op in ("==", None) else ("!=" if op == "<>" else op), value)


def _build_token(token):
    negate = False
    if token.startswith("-") and len(token) > 1:
        negate = True
        token = token[1:]

    node = None
    if ":" in token:
        name, _, rest = token.partition(":")
        key = name.strip().lower()
        rest = rest.strip().strip('"')
        op, raw = _split_op(rest)

        if key in BOOL_COLUMNS:
            truthy = raw.lower() not in ("0", "false", "no", "off")
            node = Term(BOOL_COLUMNS[key], "=", 1 if truthy else 0)
        elif key in NUMERIC_COLUMNS:
            node = _numeric_term(NUMERIC_COLUMNS[key], op, raw)
        elif key in DATE_COLUMNS:
            stamp = _parse_relative_date(raw)
            if stamp is not None:
                within = op in (None, "<", "<=", "=", "==")
                node = Term(DATE_COLUMNS[key], ">=" if within else "<=", stamp)
        elif key in ALIASES:
            col = ALIASES[key]
            if op in ("=", "=="):
                node = Term(f"LOWER(IFNULL({col},''))", "=", raw.lower())
            elif op in ("!=", "<>"):
                node = Term(f"LOWER(IFNULL({col},''))", "!=", raw.lower())
            else:
                node = _LikeTerm(col, raw)

    if node is None:
        node = AnyText(_escape_like(token.strip('"')))

    return Not(node) if negate else node


class _LikeTerm(Node):
    def __init__(self, column, value):
        self.column = column
        self.value = value

    def sql(self, params):
        params.append(f"%{_escape_like(self.value)}%")
        return f"IFNULL({self.column},'') LIKE ? ESCAPE '\\'"


def parse(text):
    text = (text or "").strip()
    if not text:
        return All()

    tokens = _TOKEN.findall(text)
    groups = [[]]
    pending_not = False

    for tok in tokens:
        upper = tok.upper()
        if upper == "OR":
            groups.append([])
            continue
        if upper == "AND":
            continue
        if upper == "NOT":
            pending_not = True
            continue
        node = _build_token(tok)
        if pending_not:
            node = Not(node)
            pending_not = False
        groups[-1].append(node)

    branches = [And(g) for g in groups if g]
    if not branches:
        return All()
    return branches[0] if len(branches) == 1 else Or(branches)


def to_sql(text):
    node = parse(text)
    params = []
    return node.sql(params), params


def help_lines():
    return [
        "artist:radiohead album:\"ok computer\"",
        "year:>=1990 genre:rock",
        "rating:>=4 playcount:>10",
        "length:>4:30 bpm:<100",
        "favorite:1 -genre:live",
        "added:<30days OR lastplayed:<7days",
        "beatles OR stones",
    ]
