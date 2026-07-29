"""
Weighted List Manager — Flask Backend
Serves the HTML frontend and provides a REST API backed by SQLite.
Run:  python app.py
Then open:  http://localhost:5000
"""

import sqlite3
import webbrowser
import threading
from datetime import datetime
from flask import Flask, g, jsonify, request, send_from_directory
import os

app = Flask(__name__, static_folder="static")
DB_PATH = os.path.join(os.path.dirname(__file__), "weighted_lists.db")


# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lists (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT    UNIQUE NOT NULL,
            created TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fields (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id  INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
            name     TEXT    NOT NULL,
            weight   REAL    NOT NULL DEFAULT 1.0,
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS items (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
            name    TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS item_values (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            field_id INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
            value    REAL,
            UNIQUE(item_id, field_id)
        );
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  SCORE CALCULATION
#  Score = sum(value_i * weight_i) / sum(active_weights) * 10
#  Fields with value=0 or NULL are excluded (weight not counted).
# ─────────────────────────────────────────────
def calculate_score(fields, values_dict):
    weighted_sum = 0.0
    total_weight = 0.0
    for f in fields:
        v = values_dict.get(f["id"])
        if v is None or v == 0:
            continue
        weighted_sum += v * f["weight"]
        total_weight += f["weight"]
    if total_weight == 0:
        return 0.0
    # Normalize: max possible = 10 * weight per field → divide by (10 * total_weight)
    score = (weighted_sum / (10.0 * total_weight)) * 10.0
    return round(score, 2)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  ROUTES — Static
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ─────────────────────────────────────────────
#  ROUTES — Lists
# ─────────────────────────────────────────────
@app.route("/api/lists", methods=["GET"])
def get_lists():
    db = get_db()
    lists = rows_to_list(db.execute("SELECT * FROM lists ORDER BY name").fetchall())
    return jsonify(lists)


@app.route("/api/lists", methods=["POST"])
def create_list():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO lists (name, created) VALUES (?, ?)",
            (name, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        db.commit()
        row = db.execute("SELECT * FROM lists WHERE name=?", (name,)).fetchone()
        return jsonify(row_to_dict(row)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f'List "{name}" already exists'}), 409


@app.route("/api/lists/<int:lid>", methods=["PUT"])
def rename_list(lid):
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    db = get_db()
    try:
        db.execute("UPDATE lists SET name=? WHERE id=?", (name, lid))
        db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Name already taken"}), 409


@app.route("/api/lists/<int:lid>", methods=["DELETE"])
def delete_list(lid):
    db = get_db()
    db.execute("DELETE FROM lists WHERE id=?", (lid,))
    db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
#  ROUTES — Fields
# ─────────────────────────────────────────────
@app.route("/api/lists/<int:lid>/fields", methods=["GET"])
def get_fields(lid):
    db = get_db()
    fields = rows_to_list(
        db.execute("SELECT * FROM fields WHERE list_id=? ORDER BY position, id", (lid,)).fetchall()
    )
    return jsonify(fields)


@app.route("/api/lists/<int:lid>/fields", methods=["POST"])
def add_field(lid):
    data = request.get_json()
    name = (data.get("name") or "").strip()
    try:
        weight = float(data.get("weight", 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid weight"}), 400
    if not name:
        return jsonify({"error": "Field name required"}), 400
    db = get_db()
    pos = db.execute(
        "SELECT COALESCE(MAX(position),0)+1 FROM fields WHERE list_id=?", (lid,)
    ).fetchone()[0]
    db.execute(
        "INSERT INTO fields (list_id, name, weight, position) VALUES (?,?,?,?)",
        (lid, name, weight, pos)
    )
    db.commit()
    fid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = db.execute("SELECT * FROM fields WHERE id=?", (fid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.route("/api/fields/<int:fid>", methods=["PUT"])
def update_field(fid):
    data = request.get_json()
    db = get_db()
    if "name" in data:
        name = data["name"].strip()
        if name:
            db.execute("UPDATE fields SET name=? WHERE id=?", (name, fid))
    if "weight" in data:
        try:
            w = float(data["weight"])
            db.execute("UPDATE fields SET weight=? WHERE id=?", (w, fid))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid weight"}), 400
    db.commit()
    row = db.execute("SELECT * FROM fields WHERE id=?", (fid,)).fetchone()
    return jsonify(row_to_dict(row))


@app.route("/api/lists/<int:lid>/fields/reorder", methods=["PUT"])
def reorder_fields(lid):
    data = request.get_json()
    order = data.get("order", [])   # list of field ids in new order
    db = get_db()
    for pos, fid in enumerate(order):
        db.execute("UPDATE fields SET position=? WHERE id=? AND list_id=?", (pos, fid, lid))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/fields/<int:fid>", methods=["DELETE"])
def delete_field(fid):
    db = get_db()
    db.execute("DELETE FROM fields WHERE id=?", (fid,))
    db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
#  ROUTES — Items
# ─────────────────────────────────────────────
@app.route("/api/lists/<int:lid>/items", methods=["GET"])
def get_items(lid):
    db = get_db()
    fields = db.execute(
        "SELECT * FROM fields WHERE list_id=? ORDER BY position, id", (lid,)
    ).fetchall()
    items = db.execute("SELECT * FROM items WHERE list_id=?", (lid,)).fetchall()

    result = []
    for item in items:
        vals_raw = db.execute(
            "SELECT field_id, value FROM item_values WHERE item_id=?", (item["id"],)
        ).fetchall()
        values = {r["field_id"]: r["value"] for r in vals_raw}
        score = calculate_score(fields, values)
        result.append({
            "id": item["id"],
            "name": item["name"],
            "values": {str(k): v for k, v in values.items()},
            "score": score,
        })
    return jsonify(result)


@app.route("/api/lists/<int:lid>/items", methods=["POST"])
def add_item(lid):
    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Item name required"}), 400
    values = data.get("values", {})

    db = get_db()
    db.execute("INSERT INTO items (list_id, name) VALUES (?,?)", (lid, name))
    db.commit()
    iid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for field_id_str, val in values.items():
        try:
            fid = int(field_id_str)
            v = float(val) if val not in (None, "", "N/A", "NA") else 0.0
        except (ValueError, TypeError):
            continue
        db.execute(
            "INSERT INTO item_values (item_id, field_id, value) VALUES (?,?,?) "
            "ON CONFLICT(item_id, field_id) DO UPDATE SET value=excluded.value",
            (iid, fid, v)
        )
    db.commit()

    fields = db.execute(
        "SELECT * FROM fields WHERE list_id=? ORDER BY position, id", (lid,)
    ).fetchall()
    vals_raw = db.execute("SELECT field_id, value FROM item_values WHERE item_id=?", (iid,)).fetchall()
    values_dict = {r["field_id"]: r["value"] for r in vals_raw}
    score = calculate_score(fields, values_dict)

    return jsonify({
        "id": iid, "name": name,
        "values": {str(k): v for k, v in values_dict.items()},
        "score": score
    }), 201


@app.route("/api/items/<int:iid>", methods=["PUT"])
def update_item(iid):
    data = request.get_json()
    db = get_db()

    item = db.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if not item:
        return jsonify({"error": "Not found"}), 404

    name = (data.get("name") or "").strip()
    if name:
        db.execute("UPDATE items SET name=? WHERE id=?", (name, iid))

    values = data.get("values", {})
    for field_id_str, val in values.items():
        try:
            fid = int(field_id_str)
            v = float(val) if val not in (None, "", "N/A", "NA") else 0.0
        except (ValueError, TypeError):
            continue
        db.execute(
            "INSERT INTO item_values (item_id, field_id, value) VALUES (?,?,?) "
            "ON CONFLICT(item_id, field_id) DO UPDATE SET value=excluded.value",
            (iid, fid, v)
        )
    db.commit()

    lid = item["list_id"]
    fields = db.execute(
        "SELECT * FROM fields WHERE list_id=? ORDER BY position, id", (lid,)
    ).fetchall()
    vals_raw = db.execute("SELECT field_id, value FROM item_values WHERE item_id=?", (iid,)).fetchall()
    values_dict = {r["field_id"]: r["value"] for r in vals_raw}
    score = calculate_score(fields, values_dict)

    return jsonify({
        "id": iid,
        "name": name or item["name"],
        "values": {str(k): v for k, v in values_dict.items()},
        "score": score
    })


@app.route("/api/items/<int:iid>", methods=["DELETE"])
def delete_item(iid):
    db = get_db()
    db.execute("DELETE FROM items WHERE id=?", (iid,))
    db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    def open_browser():
        import time; time.sleep(0.8)
        webbrowser.open("http://localhost:5000")
    threading.Thread(target=open_browser, daemon=True).start()
    print("\n  Weighted List Manager running at http://localhost:5000\n")
    app.run(debug=False, port=5000)
