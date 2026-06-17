"""Flask application entry point for the ML Experiment Tracking platform.

Routes
------
Page routes (HTML):
    GET  /                         -> dashboard.html
    GET  /experiment/<id>          -> detail.html
    GET  /compare                  -> compare.html

API routes (JSON):
    GET  /api/experiments                 -> list with ?project= and ?search=
    GET  /api/experiment/<id>             -> one experiment + its epoch_metrics
    GET  /api/compare?ids=1,2             -> two experiments side by side
    PATCH /api/experiment/<id>/notes      -> update the notes field

Error handling
--------------
    404                  -> renders `404.html`
    500 (unhandled)      -> JSON `{"error": "..."}` (since this is an API-first app)
    All API routes catch sqlite3.Error and return a 500 with a stable JSON shape.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import traceback
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template, request

from database import get_db, init_db


log = logging.getLogger("ml_tracker")


# --------------------------------------------------------------------------- #
# Serialization helpers                                                        #
# --------------------------------------------------------------------------- #
def _parse_json_field(value: Optional[str]) -> Optional[Any]:
    """Parse a JSON-text column. Return None when empty or malformed."""
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        # Defensive: never let a corrupted JSON cell blow up an API response.
        return None


def _experiment_to_dict(row: sqlite3.Row,
                        epoch_metrics: Optional[List[Dict[str, Any]]] = None
                        ) -> Dict[str, Any]:
    """Shape a SQLite row into the JSON representation promised in the spec."""
    return {
        "id":         row["id"],
        "name":       row["name"],
        "project":    row["project"],
        "tags":       row["tags"],
        "params":     _parse_json_field(row["params"]),
        "metrics":    _parse_json_field(row["metrics"]),
        "notes":      row["notes"],
        "status":     row["status"],
        "created_at": row["created_at"],
        "end_time":   row["end_time"] if "end_time" in row.keys() else None,
        "epoch_metrics": epoch_metrics or [],
    }


def _fetch_epoch_metrics(experiment_id: int) -> List[Dict[str, Any]]:
    """Return epoch metrics for a single experiment, ordered for plotting."""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT metric_name, value, step
              FROM epoch_metrics
             WHERE experiment_id = ?
             ORDER BY metric_name, step
            """,
            (experiment_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _parse_id_list(raw: Optional[str]) -> List[int]:
    """Parse a comma-separated `ids` query string into a clean int list."""
    if not raw:
        return []
    ids: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    # Deduplicate while preserving order.
    seen: set[int] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


# --------------------------------------------------------------------------- #
# DB-call wrapper                                                              #
# --------------------------------------------------------------------------- #
def _with_db(fn):
    """Run a DB-touching callable and convert sqlite3 errors into JSON 500s.

    The API endpoints are JSON-first, so the front-end always gets a stable
    shape on failure instead of an HTML stack trace. Page routes get the
    default Flask 500 handler.
    """
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except sqlite3.Error as exc:
            log.error("Database error in %s: %s", fn.__name__, exc)
            return jsonify({
                "error": "database error",
                "detail": str(exc),
                "endpoint": fn.__name__,
            }), 500
        except (KeyError, TypeError, ValueError) as exc:
            log.error("Bad request in %s: %s", fn.__name__, exc)
            return jsonify({
                "error": "bad request",
                "detail": str(exc),
                "endpoint": fn.__name__,
            }), 400
    wrapper.__name__ = fn.__name__
    return wrapper


# --------------------------------------------------------------------------- #
# Application factory                                                          #
# --------------------------------------------------------------------------- #
def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__)

    # Ensure the database schema exists on startup.
    init_db()

    # ------------------------------------------------------------------ #
    # Page routes (HTML)                                                  #
    # ------------------------------------------------------------------ #
    @app.route("/")
    def index():
        """Render the dashboard with the latest experiments."""
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY datetime(created_at) DESC, id DESC"
            ).fetchall()
            experiments = [_experiment_to_dict(r) for r in rows]
        finally:
            conn.close()
        return render_template("dashboard.html", experiments=experiments)

    @app.route("/experiment/<int:experiment_id>")
    def experiment_detail(experiment_id: int):
        """Render the detail page for a single experiment."""
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            # 404 is friendlier than rendering an empty detail page.
            return render_template("detail.html", experiment=None,
                                   not_found=True), 404

        experiment = _experiment_to_dict(row, _fetch_epoch_metrics(experiment_id))
        return render_template("detail.html", experiment=experiment,
                               not_found=False)

    @app.route("/compare")
    def compare_page():
        """Render the compare page. Selection happens client-side."""
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT id, name, project, status, created_at "
                "FROM experiments ORDER BY datetime(created_at) DESC, id DESC"
            ).fetchall()
        finally:
            conn.close()
        return render_template("compare.html",
                               experiments=[dict(r) for r in rows])

    # ------------------------------------------------------------------ #
    # API routes (JSON)                                                   #
    # ------------------------------------------------------------------ #
    @app.route("/api/experiments")
    @_with_db
    def api_experiments():
        """List experiments with optional `project` and `search` filters."""
        project = (request.args.get("project") or "").strip()
        search  = (request.args.get("search")  or "").strip()

        sql = "SELECT * FROM experiments WHERE 1=1"
        params: List[Any] = []

        if project:
            sql += " AND project = ?"
            params.append(project)

        if search:
            # Case-insensitive substring match across name, project, and tags.
            sql += (
                " AND (LOWER(name)    LIKE ?"
                "  OR LOWER(COALESCE(project, '')) LIKE ?"
                "  OR LOWER(COALESCE(tags,    '')) LIKE ?)"
            )
            like = f"%{search.lower()}%"
            params.extend([like, like, like])

        sql += " ORDER BY datetime(created_at) DESC, id DESC"

        conn = get_db()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return jsonify([_experiment_to_dict(r) for r in rows])

    @app.route("/api/experiment/<int:experiment_id>")
    @_with_db
    def api_experiment(experiment_id: int):
        """Return a single experiment plus all of its epoch metrics."""
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            return jsonify({"error": "experiment not found",
                            "id": experiment_id}), 404

        return jsonify(_experiment_to_dict(
            row, _fetch_epoch_metrics(experiment_id)
        ))

    @app.route("/api/compare")
    @_with_db
    def api_compare():
        """Return two (or more) experiments side by side for comparison."""
        ids = _parse_id_list(request.args.get("ids"))
        if len(ids) < 2:
            return jsonify({
                "error": "Provide at least two ids via ?ids=1,2",
                "ids_received": ids,
            }), 400

        placeholders = ",".join("?" for _ in ids)
        conn = get_db()
        try:
            rows = conn.execute(
                f"SELECT * FROM experiments WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        finally:
            conn.close()

        # Preserve the order requested by the caller for predictable display.
        by_id = {r["id"]: r for r in rows}
        ordered = [by_id[i] for i in ids if i in by_id]

        return jsonify({
            "requested_ids": ids,
            "missing_ids":   [i for i in ids if i not in by_id],
            "experiments":   [_experiment_to_dict(
                                  r, _fetch_epoch_metrics(r["id"])
                              ) for r in ordered],
        })

    @app.route("/api/experiment/<int:experiment_id>/notes",
               methods=["PATCH"])
    @_with_db
    def api_update_notes(experiment_id: int):
        """Update the `notes` field for an experiment."""
        payload = request.get_json(silent=True)
        if payload is None or "notes" not in payload:
            return jsonify({
                "error": "Body must be JSON with a 'notes' field",
            }), 400

        notes = payload["notes"]
        if not isinstance(notes, str):
            return jsonify({"error": "'notes' must be a string"}), 400

        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT id FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
            if existing is None:
                return jsonify({
                    "error": "experiment not found",
                    "id": experiment_id,
                }), 404

            conn.execute(
                "UPDATE experiments SET notes = ? WHERE id = ?",
                (notes, experiment_id),
            )
            conn.commit()

            updated = conn.execute(
                "SELECT * FROM experiments WHERE id = ?",
                (experiment_id,),
            ).fetchone()
        finally:
            conn.close()

        return jsonify(_experiment_to_dict(updated,
                                           _fetch_epoch_metrics(experiment_id)))

    # ------------------------------------------------------------------ #
    # Error handlers                                                       #
    # ------------------------------------------------------------------ #
    @app.errorhandler(404)
    def not_found(_e):
        # Distinguish API 404s (JSON) from page 404s (HTML).
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "not found",
                "path":  request.path,
            }), 404
        return render_template("404.html", path=request.path), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return jsonify({
            "error":  "method not allowed",
            "method": request.method,
            "path":   request.path,
        }), 405

    @app.errorhandler(500)
    def internal_error(e):
        log.error("Unhandled 500 on %s %s: %s", request.method, request.path, e)
        log.error(traceback.format_exc())
        if request.path.startswith("/api/"):
            return jsonify({
                "error":  "internal server error",
                "detail": str(e),
            }), 500
        # For page routes, re-raise so Flask's debug page (or a future
        # custom 500.html) can render.
        raise e

    return app


if __name__ == "__main__":
    # Surface Python warnings + our own logs in dev.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = create_app()
    # Run on localhost only; debug is convenient for local experimentation.
    app.run(host="127.0.0.1", port=5000, debug=True)
