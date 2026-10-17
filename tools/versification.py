"""Сопоставление еврейских стихов (WLC) с синодальными через нумерацию KJV.

Таблицы JSword задают правила вида  ИСХОДНЫЙ=KJV  (стих или диапазон, «!a/!b» — часть стиха,
«?…» — стиха нет в KJV). Стихи, не упомянутые в правилах, совпадают с KJV по номеру.
"""
import re
from collections import defaultdict

REF = re.compile(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)(?:!(\w))?$")


def parse_ref(s):
    m = REF.match(s.strip())
    if not m:
        raise ValueError(f"не разобрана ссылка: {s}")
    return m.group(1), int(m.group(2)), int(m.group(3)), bool(m.group(4))


def expand(side, lengths=None, count=None):
    """Список (книга, глава, стих, часть_стиха). lengths — длины глав этой системы, если известны."""
    if "-" not in side:
        return [parse_ref(side)]
    a, b = side.split("-")
    b1, c1, v1, p1 = parse_ref(a)
    b2, c2, v2, p2 = parse_ref(b)
    if b1 != b2:
        raise ValueError(f"диапазон через книги: {side}")
    out = []
    if c1 == c2:
        out = [(b1, c1, v, False) for v in range(v1, v2 + 1)]
    else:
        if lengths and all((b1, c) in lengths for c in range(c1, c2)):
            ends = {c: lengths[(b1, c)] for c in range(c1, c2)}
        elif c2 == c1 + 1 and count:
            # Конец главы находится из длины парного диапазона. Если парная сторона — один стих,
            # диапазон начинается с последнего стиха главы.
            ends = {c1: max(count - v2 + v1 - 1, v1)}
        else:
            raise ValueError(f"нельзя развернуть диапазон {side}")
        for c in range(c1, c2 + 1):
            start = v1 if c == c1 else 1
            end = ends[c] if c < c2 else v2
            out += [(b1, c, v, False) for v in range(start, end + 1)]
    if out:
        out[0] = out[0][:3] + (p1,)
        out[-1] = out[-1][:3] + (p2 or out[-1][3],)
    return out


# Местные поправки к таблице Synodal.properties, проверенные по тексту модуля getBible.
# Перекрывают правила JSword для тех же синодальных стихов.
SYNODAL_CORRECTIONS = [
    "Ps.12.6=Ps.13.5-Ps.13.6",         # в JSword опечатка: «Ps.13.5-Ps.12.6»
    "Lev.14.55=Lev.14.55-Lev.14.56",   # синодальный 14:55 содержит текст 14:55–56 еврейского и KJV
    "Lev.14.56=Lev.14.57",
    "Ps.114.8=Ps.116.8-Ps.116.9",      # в модуле стих 114:9 слит с 114:8
]


def load_rules(path, lengths, errors, corrections=()):
    """Возвращает словарь: (книга, глава, стих) исходной системы → множество ((книга, глава, стих) KJV, частично).
    Строки, которые нельзя однозначно разобрать, пропускаются и попадают в errors."""
    rules = defaultdict(set)
    fixed = set()
    for line in list(path.read_text("utf-8").splitlines()) + [f"{c}  " for c in corrections]:
        is_fix = line.endswith("  ")
        line = line.strip()
        if not line or line.startswith(("#", "!")) or "=" not in line:
            continue
        left, right = (x.strip() for x in line.split("="))
        if right.startswith("?"):
            for b, c, v, _ in expand(left, lengths):
                rules[(b, c, v)]  # стиха нет в KJV: явно пустое соответствие
            continue
        try:
            lhs = expand(left, lengths)
            rhs = expand(right, None, count=len(lhs))
        except ValueError as e:
            errors.append(f"{path.name}: {line} — {e}")
            continue
        if len(lhs) == len(rhs):
            pairs = zip(lhs, rhs)
        else:
            pairs = [(l, r) for l in lhs for r in rhs]
        multi = len(lhs) != len(rhs)
        for (b, c, v, lp), (rb, rc, rv, rp) in pairs:
            if is_fix and (b, c, v) not in fixed:
                rules[(b, c, v)] = set()
                fixed.add((b, c, v))
            rules[(b, c, v)].add(((rb, rc, rv), lp or rp or multi))
    return rules


def to_kjv(ref, rules):
    if ref in rules:
        return rules[ref]
    return {(ref, False)}


def compose(heb_verses, heb_rules, syn_verses, syn_rules):
    """Для каждого еврейского стиха — список (синодальный стих, точное ли совпадение)."""
    syn_by_kjv = defaultdict(set)
    syn_targets = {}
    for s in syn_verses:
        targets = to_kjv(s, syn_rules)
        syn_targets[s] = targets
        for k, partial in targets:
            syn_by_kjv[k].add((s, partial))
    result, heb_by_syn = {}, defaultdict(set)
    for h in heb_verses:
        found = {}
        h_partial = False
        for k, partial in to_kjv(h, heb_rules):
            h_partial |= partial
            for s, sp in syn_by_kjv.get(k, ()):
                found[s] = found.get(s, False) or partial or sp
        result[h] = found
        for s in found:
            heb_by_syn[s].add(h)
    out = {}
    for h, found in result.items():
        out[h] = [(s, not p and len(found) == 1 and len(heb_by_syn[s]) == 1) for s, p in sorted(found.items())]
    unmatched_syn = [s for s in syn_verses if not heb_by_syn.get(s)]
    return out, unmatched_syn
