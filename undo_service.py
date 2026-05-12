from collections import deque


class UndoStack:
    def __init__(self, maxlen=400):
        self._items = deque(maxlen=maxlen)

    def push(self, action, rows):
        snapshot = snapshot_rows(rows)
        if snapshot:
            self._items.append({"action": action, "rows": snapshot})

    def pop(self):
        if not self._items:
            return None
        return self._items.pop()

    def __bool__(self):
        return bool(self._items)


def snapshot_rows(rows):
    snapshot = []
    for row in rows:
        snapshot.append({
            "id": row["id"],
            "decision": row["_decision_var"].get() if "_decision_var" in row else row.get("decision", ""),
            "missing": bool(row.get("_missing", False)),
            "path": row.get("ruta", ""),
        })
    return snapshot
