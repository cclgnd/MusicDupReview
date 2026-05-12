from collections import defaultdict


RULE_LABELS = {
    "longest_path": "Keep only longest path",
    "shortest_path": "Keep only shortest path",
    "largest": "Keep only largest file",
    "smallest": "Keep only smallest file",
    "newest": "Keep only newest modified",
    "oldest": "Keep only oldest modified",
    "exact_hash": "Trash exact hash duplicates only",
    "clear": "Clear group choices",
}


def apply_rule_to_groups(groups, rule):
    updates = []
    changed = 0
    for rows in groups:
        if rule == "exact_hash":
            changed += _mark_exact_hash_duplicates(rows, updates)
        elif rule == "clear":
            changed += _clear_group_decisions(rows, updates)
        else:
            changed += _apply_keep_one_rule(rows, rule, updates)
    return updates, changed


def rule_label(rule):
    return RULE_LABELS.get(rule, rule)


def overlap_file_count(groups):
    seen = set()
    overlap = set()
    for rows in groups:
        for row in rows:
            file_id = row.get("id")
            if file_id in seen:
                overlap.add(file_id)
            else:
                seen.add(file_id)
    return len(overlap)


def _apply_keep_one_rule(rows, rule, updates):
    if not rows:
        return 0

    key_funcs = {
        "longest_path": lambda r: (len(r.get("ruta") or ""), r.get("tamano") or 0),
        "shortest_path": lambda r: (-len(r.get("ruta") or ""), r.get("tamano") or 0),
        "largest": lambda r: (r.get("tamano") or 0, len(r.get("ruta") or "")),
        "smallest": lambda r: (-(r.get("tamano") or 0), -len(r.get("ruta") or "")),
        "newest": lambda r: (r.get("fecha_mod") or 0, r.get("tamano") or 0),
        "oldest": lambda r: (-(r.get("fecha_mod") or 0), r.get("tamano") or 0),
    }
    key_func = key_funcs.get(rule)
    if not key_func:
        return 0

    keeper = max(rows, key=key_func)
    for row in rows:
        updates.append((row["id"], "master" if row["id"] == keeper["id"] else "delete"))
    return len(rows)


def _mark_exact_hash_duplicates(rows, updates):
    by_hash = defaultdict(list)
    for row in rows:
        if row.get("md5"):
            by_hash[row["md5"]].append(row)

    changed = 0
    for hash_rows in by_hash.values():
        if len(hash_rows) < 2:
            continue
        keeper = max(hash_rows, key=lambda r: (r.get("tamano") or 0, len(r.get("ruta") or "")))
        for row in hash_rows:
            updates.append((row["id"], "master" if row["id"] == keeper["id"] else "delete"))
            changed += 1
    return changed


def _clear_group_decisions(rows, updates):
    changed = 0
    for row in rows:
        current = row.get("decision", "")
        if current:
            updates.append((row["id"], ""))
            changed += 1
    return changed
