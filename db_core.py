import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional until PostgreSQL is installed
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
DEFAULT_DB_PATH = RUNTIME_DIR / "citizen_power_line_bot.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"
DEFAULT_COMMUNITY_SLUG = "penghu-nanliao"
DEFAULT_PROGRESS_STAGES = ["規劃中", "申請中", "施工中", "併網測試", "正式運轉"]

__all__ = [
    "get_db_path",
    "get_database_engine",
    "ensure_db_directory",
    "get_connection",
    "run_schema",
    "get_database_metadata",
    "init_db",
]


class CursorProxy:
    def __init__(self, cursor=None, rows=None):
        self._cursor = cursor
        self._rows = rows

    def fetchone(self):
        if self._rows is not None:
            return self._rows[0] if self._rows else None
        return self._cursor.fetchone() if self._cursor else None

    def fetchall(self):
        if self._rows is not None:
            return list(self._rows)
        return self._cursor.fetchall() if self._cursor else []


class ConnectionProxy:
    def __init__(self, inner, engine):
        self._inner = inner
        self.engine = engine
        self._last_insert_id = None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        normalized = " ".join(sql.strip().split()).lower()
        if normalized.startswith("select last_insert_id()"):
            return CursorProxy(rows=[{"id": self._last_insert_id}])
        if self.engine == "sqlite":
            cursor = self._inner.execute(sql, params)
            if normalized.startswith("insert into"):
                self._last_insert_id = cursor.lastrowid
            return CursorProxy(cursor=cursor)
        return self._execute_postgres(sql, params, normalized)

    def executescript(self, script):
        if self.engine == "sqlite":
            self._inner.executescript(script)
            return None
        for statement in split_sql_statements(script):
            if statement.strip():
                self.execute(statement)
        return None

    def commit(self):
        self._inner.commit()

    def rollback(self):
        self._inner.rollback()

    def close(self):
        self._inner.close()

    def _execute_postgres(self, sql, params, normalized):
        pg_sql = convert_sql_for_postgres(sql)
        cursor = self._inner.cursor(row_factory=dict_row)
        if normalized.startswith("insert into") and " returning " not in normalized:
            pg_sql = f"{pg_sql.rstrip().rstrip(';')} RETURNING id"
            cursor.execute(pg_sql, params)
            inserted = cursor.fetchone()
            self._last_insert_id = inserted["id"] if inserted else None
            return CursorProxy(rows=[inserted] if inserted else [])
        cursor.execute(pg_sql, params)
        return CursorProxy(cursor=cursor)


def utc_now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def utc_today_iso():
    return datetime.utcnow().date().isoformat()


def get_database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def get_database_engine():
    return "postgres" if get_database_url() else "sqlite"


def get_db_path():
    raw_path = os.environ.get("DB_NAME", "").strip()
    return Path(raw_path) if raw_path else DEFAULT_DB_PATH


def ensure_db_directory():
    if get_database_engine() == "sqlite":
        get_db_path().parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    engine = get_database_engine()
    if engine == "postgres":
        if psycopg is None:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed. Add psycopg[binary] to requirements.")
        conn = psycopg.connect(get_database_url(), autocommit=False)
        return ConnectionProxy(conn, "postgres")

    ensure_db_directory()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return ConnectionProxy(conn, "sqlite")


def convert_sql_for_postgres(sql):
    return re.sub(r"\?", "%s", sql)


def split_sql_statements(script):
    statements = []
    current = []
    in_single = False
    in_double = False
    for char in script:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def convert_schema_for_postgres(schema_text):
    converted = schema_text.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    converted = converted.replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT CURRENT_TIMESTAMP::text")
    return converted


def run_schema(conn):
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    if conn.engine == "postgres":
        conn.executescript(convert_schema_for_postgres(schema_text))
    else:
        conn.executescript(schema_text)


def get_table_columns(conn, table_name):
    if conn.engine == "postgres":
        rows = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position ASC
            """,
            (table_name,),
        ).fetchall()
        return {row["name"] for row in rows}
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_progress_columns(conn):
    columns = get_table_columns(conn, "progress_items")
    if not columns:
        return
    if "line_user_id" not in columns:
        conn.execute("ALTER TABLE progress_items ADD COLUMN line_user_id TEXT NOT NULL DEFAULT ''")
    if "display_name" not in columns:
        conn.execute("ALTER TABLE progress_items ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE progress_items ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")


def ensure_faq_columns(conn):
    columns = get_table_columns(conn, "faq_items")
    if not columns:
        return
    if "category_id" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN category_id INTEGER")
    if "is_active" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "visibility_level" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN visibility_level TEXT NOT NULL DEFAULT 'public'")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")


def ensure_calculator_rule_columns(conn):
    columns = get_table_columns(conn, "calculator_rules")
    if not columns:
        return
    if "version" not in columns:
        conn.execute("ALTER TABLE calculator_rules ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    if "effective_from" not in columns:
        conn.execute("ALTER TABLE calculator_rules ADD COLUMN effective_from TEXT NOT NULL DEFAULT ''")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE calculator_rules ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")


def ensure_visibility_columns(conn):
    visibility_defaults = {
        "document_highlights": "public",
        "project_financial_rules": "restricted",
        "project_profit_distribution_rules": "restricted",
        "project_metrics": "restricted",
        "project_sites": "restricted",
    }
    for table_name, default_value in visibility_defaults.items():
        columns = get_table_columns(conn, table_name)
        if not columns:
            continue
        if "visibility_level" not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN visibility_level TEXT NOT NULL DEFAULT '{default_value}'")


def upsert_metadata(conn, meta_key, meta_value):
    conn.execute(
        """
        INSERT INTO app_metadata (meta_key, meta_value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(meta_key) DO UPDATE SET
            meta_value = excluded.meta_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (meta_key, meta_value),
    )


def ensure_app_metadata(conn):
    upsert_metadata(conn, "schema_name", "citizen_power_line_bot")
    upsert_metadata(conn, "schema_version", "2026-04-15-dual-engine")
    upsert_metadata(conn, "project_slug", DEFAULT_PROJECT_SLUG)
    if conn.engine == "postgres":
        upsert_metadata(conn, "db_path", "DATABASE_URL")
    else:
        upsert_metadata(conn, "db_path", str(get_db_path()))


def get_database_metadata():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT meta_key, meta_value, updated_at
        FROM app_metadata
        ORDER BY meta_key ASC
        """
    ).fetchall()
    conn.close()
    return rows


def upsert_community(conn, slug, name, description):
    conn.execute(
        """
        INSERT INTO communities (name, slug, description, is_active)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(slug) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            is_active = 1
        """,
        (name, slug, description),
    )
    return conn.execute("SELECT id FROM communities WHERE slug = ?", (slug,)).fetchone()["id"]


def upsert_project(conn, community_id, slug, name, description, current_stage, status):
    conn.execute(
        """
        INSERT INTO projects (community_id, name, slug, description, current_stage, status)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            community_id = excluded.community_id,
            name = excluded.name,
            description = excluded.description,
            current_stage = excluded.current_stage,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        (community_id, name, slug, description, current_stage, status),
    )
    return conn.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()["id"]


def upsert_source_document(conn, slug, title, file_name, version_label, published_date, note):
    conn.execute(
        """
        INSERT INTO source_documents (title, slug, file_name, version_label, source_type, published_date, note)
        VALUES (?, ?, ?, ?, 'pdf', ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            title = excluded.title,
            file_name = excluded.file_name,
            version_label = excluded.version_label,
            published_date = excluded.published_date,
            note = excluded.note
        """,
        (title, slug, file_name, version_label, published_date, note),
    )
    return conn.execute("SELECT id FROM source_documents WHERE slug = ?", (slug,)).fetchone()["id"]


def upsert_document_highlight(conn, source_document_id, highlight_type, title, content, reference_page, display_order, visibility_level="public"):

    row = conn.execute(
        "SELECT id FROM document_highlights WHERE source_document_id = ? AND title = ? LIMIT 1",
        (source_document_id, title),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE document_highlights
            SET highlight_type = ?, content = ?, visibility_level = ?, reference_page = ?, display_order = ?
            WHERE id = ?
            """,
            (highlight_type, content, visibility_level, reference_page, display_order, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO document_highlights (source_document_id, highlight_type, title, content, visibility_level, reference_page, display_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (source_document_id, highlight_type, title, content, visibility_level, reference_page, display_order),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]

def upsert_faq_category(conn, slug, name):
    conn.execute(
        """
        INSERT INTO faq_categories (name, slug)
        VALUES (?, ?)
        ON CONFLICT(slug) DO UPDATE SET name = excluded.name
        """,
        (name, slug),
    )
    return conn.execute("SELECT id FROM faq_categories WHERE slug = ?", (slug,)).fetchone()["id"]


def upsert_faq_item(conn, category_id, question, answer, visibility_level="public"):

    row = conn.execute(
        "SELECT id FROM faq_items WHERE question = ? LIMIT 1",
        (question,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE faq_items
            SET category_id = ?, answer = ?, visibility_level = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (category_id, answer, visibility_level, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO faq_items (category_id, question, answer, visibility_level, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (category_id, question, answer, visibility_level, utc_now_iso(), utc_now_iso()),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def ensure_calculator_rule(conn, rule_name, value):
    row = conn.execute("SELECT id FROM calculator_rules WHERE rule_name = ? LIMIT 1", (rule_name,)).fetchone()
    if row:
        conn.execute(
            "UPDATE calculator_rules SET value = ?, version = 1, effective_from = ? WHERE id = ?",
            (value, utc_today_iso(), row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO calculator_rules (rule_name, value, version, effective_from, created_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (rule_name, value, utc_today_iso(), utc_now_iso()),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_project_financial_rule(conn, project_id, source_document_id, rule_name, rule_value, unit="", note="", version=1, visibility_level="restricted"):

    row = conn.execute(
        "SELECT id FROM project_financial_rules WHERE project_id = ? AND rule_name = ? AND version = ? LIMIT 1",
        (project_id, rule_name, version),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_financial_rules
            SET source_document_id = ?, rule_value = ?, unit = ?, note = ?, visibility_level = ?, effective_from = ?
            WHERE id = ?
            """,
            (source_document_id, rule_value, unit, note, visibility_level, utc_today_iso(), row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO project_financial_rules (
            project_id, source_document_id, rule_name, rule_value, unit, note, visibility_level, version, effective_from
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, rule_name, rule_value, unit, note, visibility_level, version, utc_today_iso()),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_profit_distribution_rule(conn, project_id, source_document_id, item_name, ratio, display_order, note="", visibility_level="restricted"):

    row = conn.execute(
        "SELECT id FROM project_profit_distribution_rules WHERE project_id = ? AND item_name = ? LIMIT 1",
        (project_id, item_name),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_profit_distribution_rules
            SET source_document_id = ?, ratio = ?, display_order = ?, note = ?, visibility_level = ?
            WHERE id = ?
            """,
            (source_document_id, ratio, display_order, note, visibility_level, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO project_profit_distribution_rules (project_id, source_document_id, item_name, ratio, display_order, note, visibility_level)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, item_name, ratio, display_order, note, visibility_level),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_project_metric(conn, project_id, source_document_id, metric_name, metric_group, metric_period, metric_value, unit="", note="", visibility_level="restricted"):

    row = conn.execute(
        """
        SELECT id FROM project_metrics
        WHERE project_id = ? AND metric_name = ? AND metric_group = ? AND metric_period = ?
        LIMIT 1
        """,
        (project_id, metric_name, metric_group, metric_period),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_metrics
            SET source_document_id = ?, metric_value = ?, unit = ?, note = ?, visibility_level = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, metric_value, unit, note, visibility_level, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO project_metrics (project_id, source_document_id, metric_name, metric_group, metric_period, metric_value, unit, note, visibility_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, metric_name, metric_group, metric_period, metric_value, unit, note, visibility_level),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_project_site(conn, project_id, source_document_id, site_name, site_type, planned_capacity_kw, actual_capacity_kw, annual_generation_kwh, annual_revenue, status, note="", visibility_level="restricted"):

    row = conn.execute(
        "SELECT id FROM project_sites WHERE project_id = ? AND site_name = ? LIMIT 1",
        (project_id, site_name),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_sites
            SET source_document_id = ?, site_type = ?, planned_capacity_kw = ?, actual_capacity_kw = ?,
                annual_generation_kwh = ?, annual_revenue = ?, status = ?, note = ?, visibility_level = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, site_type, planned_capacity_kw, actual_capacity_kw, annual_generation_kwh, annual_revenue, status, note, visibility_level, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO project_sites (
            project_id, source_document_id, site_name, site_type, planned_capacity_kw, actual_capacity_kw,
            annual_generation_kwh, annual_revenue, status, note, visibility_level
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, site_name, site_type, planned_capacity_kw, actual_capacity_kw, annual_generation_kwh, annual_revenue, status, note, visibility_level),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]

def upsert_project_milestone(conn, project_id, source_document_id, milestone_code, title, stage_group, planned_period, status, display_order, note=""):
    row = conn.execute(
        "SELECT id FROM project_milestones WHERE project_id = ? AND milestone_code = ? LIMIT 1",
        (project_id, milestone_code),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_milestones
            SET source_document_id = ?, title = ?, stage_group = ?, planned_period = ?, status = ?, display_order = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, title, stage_group, planned_period, status, display_order, note, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO project_milestones (project_id, source_document_id, milestone_code, title, stage_group, planned_period, status, display_order, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, milestone_code, title, stage_group, planned_period, status, display_order, note),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_service_journey_step(conn, project_id, source_document_id, step_code, title, stage_group, audience, summary, recommended_action, display_order):
    row = conn.execute(
        "SELECT id FROM service_journey_steps WHERE project_id = ? AND step_code = ? LIMIT 1",
        (project_id, step_code),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE service_journey_steps
            SET source_document_id = ?, title = ?, stage_group = ?, audience = ?, summary = ?, recommended_action = ?, display_order = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, title, stage_group, audience, summary, recommended_action, display_order, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO service_journey_steps (
            project_id, source_document_id, step_code, title, stage_group, audience, summary, recommended_action, display_order
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, step_code, title, stage_group, audience, summary, recommended_action, display_order),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_community_benefit_program(conn, project_id, source_document_id, program_name, program_type, description, display_order, is_active=1):
    row = conn.execute(
        "SELECT id FROM community_benefit_programs WHERE project_id = ? AND program_name = ? LIMIT 1",
        (project_id, program_name),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE community_benefit_programs
            SET source_document_id = ?, program_type = ?, description = ?, display_order = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, program_type, description, display_order, is_active, row["id"]),
        )
        return row["id"]

    conn.execute(
        """
        INSERT INTO community_benefit_programs (project_id, source_document_id, program_name, program_type, description, display_order, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, program_name, program_type, description, display_order, is_active),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_project_progress_seed(conn, project_id, stage, updated_at, note=""):
    row = conn.execute(
        "SELECT id FROM project_progress WHERE project_id = ? AND stage = ? AND updated_at = ? AND user_id IS NULL LIMIT 1",
        (project_id, stage, updated_at),
    ).fetchone()
    if row:
        conn.execute("UPDATE project_progress SET note = ? WHERE id = ?", (note, row["id"]))
        return row["id"]

    conn.execute(
        """
        INSERT INTO project_progress (project_id, user_id, stage, updated_at, note, is_predicted)
        VALUES (?, NULL, ?, ?, ?, 0)
        """,
        (project_id, stage, updated_at, note),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def upsert_progress_item_seed(conn, stage, updated_at, display_name):
    row = conn.execute(
        "SELECT id FROM progress_items WHERE stage = ? AND updated_at = ? AND display_name = ? LIMIT 1",
        (stage, updated_at, display_name),
    ).fetchone()
    if row:
        return row["id"]

    conn.execute(
        """
        INSERT INTO progress_items (stage, updated_at, line_user_id, display_name, created_at)
        VALUES (?, ?, '', ?, ?)
        """,
        (stage, updated_at, display_name, utc_now_iso()),
    )
    return conn.execute("SELECT last_insert_id() AS id").fetchone()["id"]


def seed_base_data(conn):
    community_id = upsert_community(
        conn,
        DEFAULT_COMMUNITY_SLUG,
        "澎湖南寮社區",
        "以澎湖南寮為核心的社區型公民電廠示範場域，結合居民參與、屋頂光電與地方回饋。",
    )
    project_id = upsert_project(
        conn,
        community_id,
        DEFAULT_PROJECT_SLUG,
        "南寮公民電廠",
        "以南寮社區為核心的陪伴式公民電廠建造服務示範案，從社區溝通、補助申請、場址盤點到營運回饋，協助地方完成共創能源轉型。",
        "正式運轉",
        "active",
    )

    doc_history = upsert_source_document(
        conn,
        "citizen-power-history-model",
        "公民電廠制度與發展背景整理",
        "citizen_power_history_model.txt",
        "2021-term-paper",
        "2021-02-01",
        "整理公民電廠制度脈絡、FIT、PPA、REC 與社區能源治理背景，作為服務設計與 FAQ 的知識底稿。",
    )
    doc_exec_plan = upsert_source_document(
        conn,
        "nanliao-exec-plan-20231108",
        "南寮公民電廠執行規劃書",
        "nanliao_exec_plan_20231108.pdf",
        "2023-11-08",
        "2023-11-08",
        "作為專案規劃、財務模型、問卷與里程碑設計的主要參考來源。",
    )
    doc_grant = upsert_source_document(
        conn,
        "nanliao-grant-approved-20220610",
        "南寮公民電廠補助核定文件",
        "nanliao_grant_approved_20220610.pdf",
        "2022-06-10",
        "2022-06-10",
        "作為核定目標容量、補助金額與申請期程的參考來源。",
    )
    doc_company = upsert_source_document(
        conn,
        "nanliao-company-intro-20250623",
        "南寮公民電廠營運摘要",
        "nanliao_company_intro_20250623.pdf",
        "2025-06-23",
        "2025-06-23",
        "作為已建置容量、分場景資料與營運成果的參考來源。",
    )

    doc_final_report = upsert_source_document(
        conn,
        "report-nanliao-solar-final-2026",
        "澎湖南寮公民電廠 2026 年最終統整版",
        "report_nanliao_solar_final_2026.pdf",
        "NP-FINAL-2026",
        "2026-04-18",
        "整合南寮案容量換算、模組片數、發電量、衰減、財務分配與環境效益參數，作為試算與 FAQ 的最新版依據。",
    )

    highlight_rows = [
        (doc_final_report, "calculator", "官方預設試算口徑", "網站預設以可用面積為輸入口徑，採 5.0 m2/kW、410W/片、1.95 m2/片、1,249 度/kW/年與 0.474 kgCO2e/度作為官方預設粗估。", "handbook", 90),
        (doc_final_report, "calculator", "南寮案例試算口徑", "南寮案例模式採 4.91 m2/kW、3.46 度/kW/日、1,263 度/kW/年、5.5 元/度與 60,000 元/kW；這是案例情境值，不是全台通用標準。", "handbook", 100),
        (doc_final_report, "environment", "南寮日照環境參數", "NASA 氣象資料顯示南寮區域全天空表面短波下行輻射度為 4.6872 kWh/m2/day。", "p.1", 110),
        (doc_final_report, "finance", "2026 財務模型參數", "建置單價 60,000 元/kWp、綠電轉供電價 5.5 元/度，收益分配以股東紅利 50%、維運行政 35%、租金 10%、社區回饋 5% 為基準。", "p.2", 120),
        (doc_final_report, "ecosystem", "環境效益", "屋頂型太陽能板建置後可降低房舍內部溫度約 2 至 3 度，並對應 SDGs 潔淨能源、永續城鄉與氣候行動。", "p.2", 130),
        (doc_history, "knowledge", "公民電廠核心概念", "公民電廠強調由在地居民、社區組織與公共部門共同參與，讓能源收益、決策與學習留在地方。", "p.1-p.2", 10),
        (doc_history, "knowledge", "制度工具", "整理 FIT、PPA、REC 等制度工具，可作為募集、售電與營運溝通時的基礎知識。", "p.1-p.3", 20),
        (doc_grant, "grant", "補助核定目標", "補助文件可辨識出本案以 300kW 及 15 個場址為目標，並核列 2,632,500 元補助。", "p.4", 30),
        (doc_exec_plan, "planning", "執行規劃重點", "執行規劃書整理出 87.75kW 規劃容量、5,265,000 元預算、20 年 IRR 8.78% 與居民參與設計。", "p.3-p.4", 40),
        (doc_exec_plan, "engagement", "陪伴流程重點", "文件呈現出陪伴式推進流程，包括社區說明、場址盤點、申請補助、投資溝通、施工與驗收。", "schedule", 50),
        (doc_company, "operation", "實際建置成果", "2025 年營運摘要可辨識三個場景 27.3kW、11.83kW、23.205kW，合計已建置 62.335kW。", "p.15-p.17", 60),
        (doc_company, "operation", "營運效益", "營運摘要揭露年發電量約 78,723 度、年營收約 393,615 元，可作為示範案營運成果。", "p.18", 70),
        (doc_company, "ecosystem", "地方協力模式", "摘要指出政府、學校與社區共同參與，符合社區擁有與公共回饋的公民電廠模式。", "p.3-p.5", 80),
    ]
    for row in highlight_rows:
        upsert_document_highlight(conn, *row)

    faq_categories = {
        "regulation": "政策與制度",
        "investment": "投資參與",
        "project-progress": "案場進度",
        "service-model": "陪伴服務",
        "site-planning": "場址與規劃",
        "finance": "財務與回饋",
    }
    category_ids = {slug: upsert_faq_category(conn, slug, name) for slug, name in faq_categories.items()}

    faq_rows = [
        ("regulation", "什麼是公民電廠？", "公民電廠是由在地居民、社區或地方組織共同參與投資與治理的再生能源案場，目標是不只發電，也把收益、決策與學習留在地方。"),
        ("service-model", "什麼叫陪伴式公民電廠建造服務？", "陪伴式服務不是只交付設備，而是一路協助社區完成說明會、場址盤點、補助申請、財務試算、居民募集、施工驗收到營運回饋。"),
        ("site-planning", "系統會先幫社區做哪些前期工作？", "前期會先整理社區需求、盤點可用屋頂與用電情境、確認是否適合做屋頂型光電，再把可行性評估轉成執行與募集方案。"),
        ("site-planning", "如果社區還沒有確定場址，也可以先開始嗎？", "可以。陪伴式推進不一定要等場址完全確認才開始，通常可以先做社區需求盤點、核心窗口建立、可用建物清單整理與補助方向判讀，再逐步收斂場址。"),
        ("site-planning", "屋頂適不適合做公民電廠，要先看什麼？", "第一步先看 4 件事：屋頂是否可合法使用、日照與遮蔽情況、結構條件是否安全、以及後續維運與併網是否可行。南寮的做法也是先盤點建物資料、照片與用電情境，再進一步估容量。"),
        ("site-planning", "屋頂提供者可以怎麼參與公民電廠？", "可以。屋頂提供者不一定要自己出資，也可以用場址合作的方式參與。實務上會先確認建物條件、屋頂使用權、租金或回饋方式，以及後續施工與維運配合事項。"),
        ("finance", "南寮案的規劃規模大概是多少？", "依執行規劃書整理，本案規劃容量約 87.75kW，專案總預算約 5,265,000 元，並以 20 年期與 8.78% 參考 IRR 建立財務模型。"),
        ("finance", "我不知道該不該做公民電廠，先怎麼判斷？", "可以先從 4 個問題判斷：1. 社區或場址是否有明確需求，2. 是否有可盤點的屋頂或合作空間，3. 是否有核心推動者，4. 是否願意花時間做溝通與行政。只要前兩步還不明確，也可以先從案例、場址與補助方向開始理解，不必一次做完決定。"),
        ("finance", "補助沒有申請到，案子還能做嗎？", "可以，但要重新評估財務結構。若沒有補助，通常要重算居民募集金額、投資門檻、收益分配與案場規模，有些案子會改成分期推進或先做較小規模示範。"),
        ("finance", "公民電廠最大的風險通常是什麼？", "常見風險不是只有發電設備，還包括場址條件不穩定、居民溝通不足、補助或行政時程延誤、財務模型不易理解，以及施工與驗收節點沒有被持續追蹤。這也是陪伴式服務存在的原因。"),
        ("finance", "這個案子有補助嗎？", "有。南寮案目前整理到的是政府補助，不是民間企業補助；補助核定文件可辨識出政府補助約 2,632,500 元，約占專案預算的一半。若你要找類似資源，第一步先看中央或地方政府的能源、經發、社區營造相關計畫，再確認申請窗口、截止日期、附件清單與補助對象。民間企業或基金會通常比較偏 ESG 合作、公益支持或示範案資源，不能先假設一定有固定補助。"),
        ("finance", "公民電廠補助通常要去哪裡找？", "以目前南寮資料可推論，公民電廠補助優先看政府機關，而不是先找民間企業。實務上建議先查中央部會與地方政府的能源、經發、社區營造、地方創生或永續相關計畫，並同步確認承辦窗口、申請資格、期程與需要的附件。"),
        ("finance", "公民電廠補助是政府的還是民間的？", "南寮案目前可辨識的是政府補助。對多數社區型公民電廠來說，早期資源通常先從政府計畫找起；民間企業或基金會比較像合作資源、公益贊助或 ESG 專案，不一定是標準化補助。"),
        ("finance", "申請補助前要先準備什麼？", "建議至少先準備 4 類資料：1. 社區或組織基本資料，2. 可用場址與現況說明，3. 初步容量、預算與期程，4. 為什麼要做這個案子的公益或地方效益。這些資料先整理好，後續不論對政府窗口或合作單位都比較容易對接。"),
        ("investment", "居民要怎麼參與投資？", "系統會先用試算頁協助理解投入金額、社區持股占比與股利池，再依實際募集規則安排說明、登記與後續參與。"),
        ("investment", "投資收益會怎麼分配？", "目前示範資料採股東股利 50%、營運維護 35%、場址租金 10%、社區回饋 5% 的分配架構，方便居民理解收益如何回到案場與地方。"),
        ("investment", "公民電廠有機會賺錢嗎？", "有機會，但不能只用賺不賺錢來判斷。通常要一起看補助、案場條件、售電模式、維運成本與社區回饋安排。南寮示範案則是用試算與收益分配架構，幫居民先理解投入與回報。"),
        ("investment", "如果我不想投資，只想支持社區，也能參與嗎？", "可以。公民電廠不只有投資角色，也可以透過參與說明會、提供場址資訊、協助居民溝通、支持社區回饋安排等方式參與。"),
        ("investment", "社區回饋通常會怎麼安排？", "南寮示範資料目前採社區回饋 5% 的架構，概念上是把部分收益回到地方公共需求，例如教育推廣、公共空間改善或社區活動支持，讓案場不只是發電，也能回到地方治理。"),
        ("service-model", "第一次找真人協助前，要先準備什麼？", "建議先準備社區名稱、目前卡住的步驟、可用場址概況、是否想申請補助，以及你最在意的問題。這樣後續比較容易快速判斷目前對應南寮 SOP 的哪一步。"),
        ("service-model", "我們社區有誰可以一起推動公民電廠？", "通常至少要先有 3 種角色：願意持續協調的核心推動者、能提供或協助盤點場址的人、以及願意一起參與說明與決策的居民或合作夥伴。不是一開始就要全部到位，但需要先找到第一批同行者。"),
        ("service-model", "可以先看案例再決定要不要做嗎？", "可以，而且很建議。先看像南寮這樣的案例，可以幫你理解它怎麼從社區啟動、場址盤點、補助申請一路走到正式運轉，再決定自己目前最適合先走哪一步。"),
        ("project-progress", "從開始到正式運轉，大概要經過哪些階段？", "以南寮案例來看，通常會經過社區啟動、場址踏勘、補助與行政文件、財務設計、居民溝通募集、施工協調、併網驗收，最後才進入正式運轉與社區回饋。"),
        ("project-progress", "南寮案現在進行到哪裡？", "目前系統整理為正式運轉階段，並已建置三處場景共 62.335kW，可從專案總覽與進度頁查看里程碑與進度紀錄。"),
        ("project-progress", "目前已經做出哪些成果？", "營運摘要可辨識已建置 27.3kW、11.83kW、23.205kW 三處屋頂場景，合計年發電量約 78,723 度、年營收約 393,615 元。"),
        ("service-model", "為什麼系統要把文件整理進資料庫？", "因為陪伴式服務需要把規劃書、補助核定、營運摘要與制度背景整合成可查詢的專案知識，讓 FAQ、試算、案場總覽與陪伴流程說法一致。"),
    ]
    faq_rows.extend([
        ("site-planning", "屋頂坪數要怎麼換算成太陽光電容量？", "預設請使用可用面積估算：容量 kW = 可用面積 m2 / 5.0。若使用者輸入的是總屋頂面積，系統會先乘上可用率；南寮案例模式則可切換為 4.91 m2/kW。"),
        ("site-planning", "系統怎麼估算需要幾片太陽能板？", "網站預設以 410W/片、1.95 m2/片估算，片數 = round(容量 × 1000 / 410)。這是網站假設值，正式設計仍要依實際模組規格與現場排布調整。"),
        ("finance", "南寮的發電量試算用什麼基準？", "官方預設採 114 年澎湖平均 1,249 度/kW/年；南寮案例模式採 1,263 度/kW/年。長期試算可切換複利衰退或線性衰退，避免把不同 1% 衰退算法混在一起。"),
        ("finance", "南寮 2026 版收益分配怎麼看？", "2026 統整版採用股東紅利 50%、維運行政 35%、場址租金 10%、社區回饋 5% 作為財務模型基準。前台只用來說明模型邏輯，實際案場仍需依合約與治理規則確認。"),
        ("service-model", "南寮報告中的環境效益可以怎麼轉成服務說法？", "可以轉成陪伴式服務裡的非財務價值：屋頂太陽能板可能降低房舍內部溫度約 2 至 3 度，並對應潔淨能源、永續城鄉與氣候行動等永續目標。"),
    ])

    for category_slug, question, answer in faq_rows:
        upsert_faq_item(conn, category_ids[category_slug], question, answer)

    calculator_rules = [
        ("annual_return_rate", 0.08),
        ("operation_cost_rate", 0.35),
        ("project_years", 20),
        ("degradation_rate", 0.01),
        ("reference_irr", 0.0878),
        ("sell_price_per_kwh", 5.5),
        ("annual_generation_kwh", 112635),
        ("annual_net_income", 304754),
        ("shareholder_dividend_rate", 0.50),
        ("site_rent_rate", 0.10),
        ("community_return_rate", 0.05),
        ("reference_project_budget", 5265000),
        ("reference_resident_investment", 2632500),
        ("area_m2_per_kwp", 5.0),
        ("nanliao_case_area_m2_per_kwp", 4.91),
        ("module_watt", 410),
        ("module_area_m2", 1.95),
        ("annual_generation_per_kwp", 1249),
        ("nanliao_case_annual_generation_per_kwp", 1263),
        ("daily_generation_per_kwp", 3.42),
        ("nanliao_case_daily_generation_per_kwp", 3.46),
        ("construction_unit_cost_per_kwp", 60000),
        ("carbon_factor_kg_per_kwh", 0.474),
        ("nanliao_solar_irradiation_kwh_m2_day", 4.6872),
        ("roof_temperature_reduction_min_c", 2),
        ("roof_temperature_reduction_max_c", 3),
    ]
    for rule_name, value in calculator_rules:
        ensure_calculator_rule(conn, rule_name, value)

    financial_rules = [
        ("installed_capacity_kw", 87.75, "kW", "第一階段規劃容量", doc_exec_plan),
        ("project_budget", 5265000, "TWD", "專案總預算", doc_exec_plan),
        ("sell_price_per_kwh", 5.5, "TWD/kWh", "試算採用參考售電單價", doc_exec_plan),
        ("sell_price_min_per_kwh", 5.0, "TWD/kWh", "試算售電單價下限", doc_exec_plan),
        ("sell_price_max_per_kwh", 7.0, "TWD/kWh", "試算售電單價上限", doc_exec_plan),
        ("annual_generation_kwh", 112635, "kWh", "規劃年發電量", doc_exec_plan),
        ("annual_net_income", 304754, "TWD", "規劃年淨收益", doc_exec_plan),
        ("shareholder_dividend_rate", 0.50, "ratio", "股東股利分配比率", doc_exec_plan),
        ("operation_cost_rate", 0.35, "ratio", "營運成本比率", doc_exec_plan),
        ("site_rent_rate", 0.10, "ratio", "場址租金比率", doc_exec_plan),
        ("community_return_rate", 0.05, "ratio", "社區回饋比率", doc_exec_plan),
        ("project_years", 20, "year", "專案年期", doc_exec_plan),
        ("degradation_rate", 0.01, "ratio", "年衰減率", doc_exec_plan),
        ("reference_irr", 0.0878, "ratio", "參考 IRR", doc_exec_plan),
        ("government_subsidy", 2632500, "TWD", "政府補助金額", doc_grant),
        ("government_subsidy_ratio", 0.50, "ratio", "政府補助占比", doc_grant),
        ("resident_investment_ratio", 0.50, "ratio", "居民投資占比", doc_exec_plan),
        ("reference_resident_investment", 2632500, "TWD", "居民募集總額", doc_exec_plan),
        ("area_m2_per_kwp", 5.0, "m2/kW", "南寮第一階段初估係數，作為網站官方預設口徑", doc_final_report),
        ("nanliao_case_area_m2_per_kwp", 4.91, "m2/kW", "南寮第二階段 5 戶案場反推係數，僅作案例模式", doc_final_report),
        ("module_watt", 410, "W", "網站預設單片模組瓦數，可由管理端調整", doc_final_report),
        ("module_area_m2", 1.95, "m2/panel", "網站預設單片模組面積，可由管理端調整", doc_final_report),
        ("annual_generation_per_kwp", 1249, "kWh/kW/year", "114 年澎湖官方平均年發電係數", doc_final_report),
        ("nanliao_case_annual_generation_per_kwp", 1263, "kWh/kW/year", "南寮案例年發電係數，僅作案例模式", doc_final_report),
        ("daily_generation_per_kwp", 3.42, "kWh/kW/day", "114 年澎湖官方平均日發電係數", doc_final_report),
        ("nanliao_case_daily_generation_per_kwp", 3.46, "kWh/kW/day", "南寮案例日發電係數", doc_final_report),
        ("construction_unit_cost_per_kwp", 60000, "TWD/kWp", "2026 統整版建置單價基準", doc_final_report),
        ("carbon_factor_kg_per_kwh", 0.474, "kgCO2e/kWh", "113 年度官方電力排碳係數，作為 location-based 粗估預設", doc_final_report),
        ("nanliao_solar_irradiation_kwh_m2_day", 4.6872, "kWh/m2/day", "2026 統整版 NASA 南寮日照環境參數", doc_final_report),
        ("roof_temperature_reduction_min_c", 2, "C", "屋頂太陽能板可能降低室內溫度下限", doc_final_report),
        ("roof_temperature_reduction_max_c", 3, "C", "屋頂太陽能板可能降低室內溫度上限", doc_final_report),
        ("average_annual_income", 619494, "TWD", "規劃平均年收入", doc_exec_plan),
        ("total_20y_income", 12389873, "TWD", "規劃 20 年總收入", doc_exec_plan),
        ("total_20y_net_income", 5516039, "TWD", "規劃 20 年淨收益", doc_exec_plan),
        ("target_capacity_kw", 300, "kW", "補助核定目標容量", doc_grant),
        ("target_site_count", 15, "site", "補助核定目標場址數", doc_grant),
    ]
    for rule_name, rule_value, unit, note, source_document_id in financial_rules:
        upsert_project_financial_rule(conn, project_id, source_document_id, rule_name, rule_value, unit, note)

    distribution_rules = [
        ("股東股利分配", 0.50, 1, "作為投資人股利分配池", doc_exec_plan),
        ("營運與維護", 0.35, 2, "設備維運、保險與行政成本", doc_exec_plan),
        ("場址租金", 0.10, 3, "回饋提供屋頂或場址的合作方", doc_exec_plan),
        ("社區回饋", 0.05, 4, "支持地方活動與公共需求", doc_exec_plan),
    ]
    distribution_rules.extend([
        ("股東紅利", 0.50, 11, "2026 統整版年度收益分配核心，用於吸引公民參與。", doc_final_report),
        ("維運行政", 0.35, 12, "2026 統整版維持電廠長期穩定運作的必要開銷。", doc_final_report),
        ("場址租金", 0.10, 13, "2026 統整版場址使用與合作回饋基準。", doc_final_report),
        ("社區回饋金", 0.05, 14, "2026 統整版社區回饋金，可用於長者供餐、有機耕種與教育宣導。", doc_final_report),
    ])

    for item_name, ratio, display_order, note, source_document_id in distribution_rules:
        upsert_profit_distribution_rule(conn, project_id, source_document_id, item_name, ratio, display_order, note)

    metrics = [
        ("capacity_area_factor_m2_per_kwp", "technical", "official-penghu-114", 5.0, "m2/kW", "南寮第一階段初估係數，作為網站官方預設", doc_final_report),
        ("nanliao_case_area_factor_m2_per_kwp", "technical", "nanliao-case", 4.91, "m2/kW", "南寮第二階段案例反推係數", doc_final_report),
        ("module_watt", "technical", "site-default", 410, "W", "網站預設單片模組瓦數", doc_final_report),
        ("module_area_m2", "technical", "site-default", 1.95, "m2/panel", "網站預設單片模組面積", doc_final_report),
        ("annual_generation_per_kwp", "technical", "official-penghu-114", 1249, "kWh/kW/year", "114 年澎湖官方平均年發電係數", doc_final_report),
        ("nanliao_case_annual_generation_per_kwp", "technical", "nanliao-case", 1263, "kWh/kW/year", "南寮案例年發電係數", doc_final_report),
        ("daily_generation_per_kwp", "technical", "official-penghu-114", 3.42, "kWh/kW/day", "114 年澎湖官方平均日發電係數", doc_final_report),
        ("nanliao_case_daily_generation_per_kwp", "technical", "nanliao-case", 3.46, "kWh/kW/day", "南寮案例日發電係數", doc_final_report),
        ("construction_unit_cost_per_kwp", "finance", "2026-final", 60000, "TWD/kWp", "2026 統整版建置單價", doc_final_report),
        ("carbon_factor_kg_per_kwh", "environment", "official-113", 0.474, "kgCO2e/kWh", "113 年度官方電力排碳係數", doc_final_report),
        ("nanliao_solar_irradiation", "environment", "2026-final", 4.6872, "kWh/m2/day", "NASA 南寮全天空表面短波下行輻射度", doc_final_report),
        ("penghu_pv_capacity_mw", "regional-context", "2024-11", 68.47, "MW", "澎湖光電容量", doc_final_report),
        ("penghu_wind_capacity_mw", "regional-context", "2024-11", 19.2, "MW", "澎湖風電容量", doc_final_report),
        ("penghu_pv_generation_share", "regional-context", "2025-Q1", 0.3225, "ratio", "澎湖光電發電占比", doc_final_report),
        ("roof_temperature_reduction_min_c", "environment", "2026-final", 2, "C", "屋頂光電降溫效益下限", doc_final_report),
        ("roof_temperature_reduction_max_c", "environment", "2026-final", 3, "C", "屋頂光電降溫效益上限", doc_final_report),
        ("planned_capacity_kw", "planning", "2023-plan", 87.75, "kW", "執行規劃容量", doc_exec_plan),
        ("project_budget_twd", "planning", "2023-plan", 5265000, "TWD", "專案總預算", doc_exec_plan),
        ("reference_irr", "planning", "2023-plan", 0.0878, "ratio", "規劃 IRR", doc_exec_plan),
        ("resident_investor_count", "participation", "2024-survey", 16, "person", "居民投資意願人數", doc_exec_plan),
        ("valid_survey_response_count", "participation", "2024-survey", 55, "response", "有效問卷數", doc_exec_plan),
        ("target_capacity_kw", "target", "2022-grant", 300, "kW", "補助核定目標容量", doc_grant),
        ("target_site_count", "target", "2022-grant", 15, "site", "補助核定目標場址數", doc_grant),
        ("actual_built_capacity_kw", "operation", "2025-summary", 62.335, "kW", "已建置容量", doc_company),
        ("actual_annual_generation_kwh", "operation", "2025-summary", 78723, "kWh", "實際年發電量", doc_company),
        ("actual_annual_revenue_twd", "operation", "2025-summary", 393615, "TWD", "實際年營收", doc_company),
        ("scene_count", "operation", "2025-summary", 3, "site", "已公開場景數", doc_company),
        ("penghu_renewable_capacity_mw", "regional-context", "2024-11", 87.6, "MW", "簡報中揭露的澎湖整體再生能源容量背景", doc_company),
    ]
    for metric_name, metric_group, metric_period, metric_value, unit, note, source_document_id in metrics:
        upsert_project_metric(conn, project_id, source_document_id, metric_name, metric_group, metric_period, metric_value, unit, note)

    sites = [
        ("南寮場景一", "rooftop", 27.30, 27.30, 34400, 172000, "operating", "營運摘要 p.15，455W 模組 60 片。", doc_company),
        ("南寮場景二", "rooftop", 11.83, 11.83, 14900, 74500, "operating", "營運摘要 p.16，455W 模組 26 片。", doc_company),
        ("南寮場景三", "rooftop", 23.205, 23.205, 29423, 147115, "operating", "營運摘要 p.17，455W 模組 51 片。", doc_company),
    ]
    for site_name, site_type, planned_capacity_kw, actual_capacity_kw, annual_generation_kwh, annual_revenue, status, note, source_document_id in sites:
        upsert_project_site(conn, project_id, source_document_id, site_name, site_type, planned_capacity_kw, actual_capacity_kw, annual_generation_kwh, annual_revenue, status, note)

    milestones = [
        ("community-start", "啟動社區說明與議題對焦", "規劃", "2021 Q4 - 2022 Q2", "completed", 10, "依補助申請時程與簡報內容整理，先完成社區對話與方向聚焦。", doc_grant),
        ("grant-approved", "取得補助核定", "申請", "2022-06", "completed", 20, "補助核定文件可辨識補助核定與目標容量、場址數。", doc_grant),
        ("execution-plan", "完成執行規劃與財務模型", "規劃", "2023-11", "completed", 30, "整理容量、預算、IRR、問卷與投資參與設計。", doc_exec_plan),
        ("site-engagement", "進行場址盤點與居民溝通", "籌備", "2023 Q4 - 2024 Q2", "completed", 40, "依執行規劃書排程，逐步確認場址與居民參與。", doc_exec_plan),
        ("construction", "完成主要場址施工", "施工", "2024 Q2 - 2024 Q4", "completed", 50, "完成三處屋頂型光電示範場景建置。", doc_company),
        ("grid-test", "完成併網測試與驗收", "驗收", "2024 Q4 - 2025 Q1", "completed", 60, "完成系統驗收與營運前測試。", doc_company),
        ("operation", "進入正式運轉與社區回饋", "營運", "2025 - now", "active", 70, "進入穩定營運，開始以營運數據支持後續複製與回饋。", doc_company),
    ]
    for milestone_code, title, stage_group, planned_period, status, display_order, note, source_document_id in milestones:
        upsert_project_milestone(conn, project_id, source_document_id, milestone_code, title, stage_group, planned_period, status, display_order, note)

    service_steps = [
        ("discover", "社區啟動與需求盤點", "前期啟動", "community", "先確認社區為什麼要做公民電廠，盤點地方需求、可能合作對象與能源議題。", "安排說明會、建立核心窗口，整理地方期待與疑慮。", 10, doc_history),
        ("survey", "場址踏勘與屋頂條件評估", "場址規劃", "site-owner", "依執行規劃書與南寮案例經驗，先做屋頂條件、法規限制與容量初估。", "蒐集建物資料、用電情境與照片，建立可行場址名單。", 20, doc_exec_plan),
        ("grant", "補助與行政文件準備", "申請準備", "community", "把計畫內容整理成補助所需文件，並對齊目標容量、預算與執行期程。", "確認申請窗口、截止日期、附件清單與預算拆分。", 30, doc_grant),
        ("finance-design", "財務模型與投資架構設計", "財務設計", "investor", "用容量、預算、補助比與收益分配規則，建立居民容易理解的試算模型。", "先確認募集對象、投入門檻、股利池與社區回饋比例。", 40, doc_exec_plan),
        ("resident-engagement", "居民溝通與參與募集", "社區溝通", "resident", "把專業資訊轉成居民聽得懂的問答、風險提醒與參與流程。", "安排說明、FAQ、試算頁與登記機制，降低參與門檻。", 50, doc_exec_plan),
        ("construction-support", "施工協調與進度追蹤", "施工執行", "community", "施工階段持續協調場址、設備、施工節點與回報節奏。", "建立里程碑、拍照記錄與定期更新機制。", 60, doc_company),
        ("grid-acceptance", "併網驗收與上線準備", "驗收上線", "community", "在系統完成後整理驗收、併網測試與上線前文件。", "確認驗收清單、併網結果與營運資料交接。", 70, doc_company),
        ("operation-feedback", "營運揭露與社區回饋", "長期營運", "community", "營運後持續更新發電、收益與回饋，讓案場變成可複製的地方經驗。", "固定揭露年發電量、收益、回饋用途與下一步擴點計畫。", 80, doc_company),
    ]
    for step_code, title, stage_group, audience, summary, recommended_action, display_order, source_document_id in service_steps:
        upsert_service_journey_step(conn, project_id, source_document_id, step_code, title, stage_group, audience, summary, recommended_action, display_order)

    programs = [
        ("能源教育推廣", "education", "把南寮案整理成社區能源教育內容，讓居民理解再生能源、公民參與與地方治理的連結。", 10, doc_history),
        ("社區公共回饋", "community", "以部分收益支持地方活動、公共空間改善與社區共同需求，形成看得見的地方回饋。", 20, doc_exec_plan),
        ("場址合作回饋", "site-partnership", "透過場址租金或合作回饋，讓提供屋頂與場域的合作夥伴能持續參與。", 30, doc_exec_plan),
        ("在地示範複製", "development", "把三處場景與營運成果整理成可複製模型，支持更多社區推進公民電廠。", 40, doc_company),
    ]
    programs.extend([
        ("屋頂降溫效益", "environment", "2026 統整版指出屋頂太陽能板建置後可降低房舍內部溫度約 2 至 3 度，可作為居民溝通時的非財務效益。", 50, doc_final_report),
        ("永續教育素材", "education", "把南寮案連結到 SDGs 潔淨能源、永續城鄉與氣候行動，作為社區教育與對外說明素材。", 60, doc_final_report),
    ])

    for program_name, program_type, description, display_order, source_document_id in programs:
        upsert_community_benefit_program(conn, project_id, source_document_id, program_name, program_type, description, display_order)

    if conn.execute("SELECT COUNT(*) FROM project_progress WHERE project_id = ?", (project_id,)).fetchone()[0] == 0:
        progress_rows = [
            ("規劃中", "2023-11-08", "完成執行規劃書整理並建立專案財務模型"),
            ("申請中", "2024-03-15", "完成補助與場址確認所需文件彙整"),
            ("施工中", "2024-08-20", "三處示範場景陸續進場施工"),
            ("併網測試", "2025-01-15", "完成併網測試與驗收前確認"),
            ("正式運轉", "2025-06-23", "依營運摘要整理為正式運轉階段"),
        ]
        for stage, updated_at, note in progress_rows:
            upsert_project_progress_seed(conn, project_id, stage, updated_at, note)

    if conn.execute("SELECT COUNT(*) FROM progress_items").fetchone()[0] == 0:
        progress_items = [
            ("規劃中", "2023-11-08", "系統預設資料"),
            ("申請中", "2024-03-15", "系統預設資料"),
            ("施工中", "2024-08-20", "系統預設資料"),
            ("併網測試", "2025-01-15", "系統預設資料"),
            ("正式運轉", "2025-06-23", "系統預設資料"),
        ]
        for stage, updated_at, display_name in progress_items:
            upsert_progress_item_seed(conn, stage, updated_at, display_name)


def init_db():
    conn = get_connection()
    run_schema(conn)
    ensure_app_metadata(conn)
    ensure_progress_columns(conn)
    ensure_faq_columns(conn)
    ensure_calculator_rule_columns(conn)
    ensure_visibility_columns(conn)
    seed_base_data(conn)
    conn.commit()
    conn.close()


