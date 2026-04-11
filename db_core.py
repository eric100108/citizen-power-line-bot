import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR))) / "citizen-power-line-bot"
DEFAULT_DB_PATH = LOCAL_DATA_DIR / "citizen_power_line_bot.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
BUNDLED_DB_NAME = BASE_DIR / "app.db"

CHONGGUANG_COMMUNITY_ID = 1
NANLIAO_COMMUNITY_ID = 2

CHONGGUANG_PROJECT_ID = 1
NANLIAO_PROJECT_ID = 2

DOC_NANLIAO_EXEC_PLAN_ID = 1
DOC_NANLIAO_APPROVED_GRANT_ID = 2
DOC_NANLIAO_COMPANY_INTRO_20240916_ID = 3
DOC_CITIZEN_POWER_STAGE2_APPLY_ID = 4
DOC_NANLIAO_COMPANY_INTRO_20250623_ID = 5
DOC_CITIZEN_POWER_HISTORY_MODEL_ID = 6

__all__ = [
    "get_db_path",
    "ensure_db_directory",
    "get_connection",
    "run_schema",
    "init_db",
]


def utc_now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def utc_today_iso():
    return datetime.utcnow().date().isoformat()


def get_db_path():
    raw_path = os.environ.get("DB_NAME", "").strip()
    return Path(raw_path) if raw_path else DEFAULT_DB_PATH


def ensure_db_directory():
    get_db_path().parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    ensure_db_directory()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_schema(conn):
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def get_table_columns(conn, table_name):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_progress_columns(conn):
    columns = get_table_columns(conn, "progress_items")
    if "line_user_id" not in columns:
        conn.execute("ALTER TABLE progress_items ADD COLUMN line_user_id TEXT NOT NULL DEFAULT ''")
    if "display_name" not in columns:
        conn.execute("ALTER TABLE progress_items ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE progress_items ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")


def ensure_faq_columns(conn):
    columns = get_table_columns(conn, "faq_items")
    if "category_id" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN category_id INTEGER")
    if "is_active" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE faq_items ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")


def ensure_calculator_rule_columns(conn):
    columns = get_table_columns(conn, "calculator_rules")
    if "version" not in columns:
        conn.execute("ALTER TABLE calculator_rules ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    if "effective_from" not in columns:
        conn.execute("ALTER TABLE calculator_rules ADD COLUMN effective_from TEXT NOT NULL DEFAULT ''")
    if "created_at" not in columns:
        conn.execute("ALTER TABLE calculator_rules ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")


def upsert_community(conn, community_id, name, slug, description=""):
    conn.execute(
        """
        INSERT OR IGNORE INTO communities (id, name, slug, description, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (community_id, name, slug, description),
    )
    conn.execute(
        """
        UPDATE communities
        SET name = ?, slug = ?, description = ?, is_active = 1
        WHERE id = ?
        """,
        (name, slug, description, community_id),
    )


def upsert_project(conn, project_id, community_id, name, slug, description="", current_stage="", status="planning"):
    conn.execute(
        """
        INSERT OR IGNORE INTO projects (
            id, community_id, name, slug, description, current_stage, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, community_id, name, slug, description, current_stage, status),
    )
    conn.execute(
        """
        UPDATE projects
        SET community_id = ?, name = ?, slug = ?, description = ?, current_stage = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (community_id, name, slug, description, current_stage, status, project_id),
    )


def upsert_source_document(
    conn,
    document_id,
    title,
    slug,
    file_name="",
    version_label="",
    source_type="pdf",
    published_date="",
    note="",
):
    conn.execute(
        """
        INSERT OR IGNORE INTO source_documents (
            id, title, slug, file_name, version_label, source_type, published_date, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (document_id, title, slug, file_name, version_label, source_type, published_date, note),
    )
    conn.execute(
        """
        UPDATE source_documents
        SET title = ?, slug = ?, file_name = ?, version_label = ?, source_type = ?, published_date = ?, note = ?
        WHERE id = ?
        """,
        (title, slug, file_name, version_label, source_type, published_date, note, document_id),
    )


def upsert_faq_category(conn, category_id, name, slug):
    conn.execute(
        """
        INSERT OR IGNORE INTO faq_categories (id, name, slug)
        VALUES (?, ?, ?)
        """,
        (category_id, name, slug),
    )
    conn.execute(
        """
        UPDATE faq_categories
        SET name = ?, slug = ?
        WHERE id = ?
        """,
        (name, slug, category_id),
    )


def ensure_calculator_rule(conn, rule_name, value):
    row = conn.execute(
        "SELECT id FROM calculator_rules WHERE rule_name = ? LIMIT 1",
        (rule_name,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE calculator_rules
            SET value = ?, version = 1, effective_from = ?
            WHERE id = ?
            """,
            (value, utc_today_iso(), row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO calculator_rules (rule_name, value, version, effective_from, created_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (rule_name, value, utc_today_iso(), utc_now_iso()),
    )


def ensure_project_financial_rule(conn, project_id, source_document_id, rule_name, rule_value, unit="", note="", version=1):
    row = conn.execute(
        """
        SELECT id
        FROM project_financial_rules
        WHERE project_id = ? AND rule_name = ? AND version = ?
        LIMIT 1
        """,
        (project_id, rule_name, version),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_financial_rules
            SET source_document_id = ?, rule_value = ?, unit = ?, note = ?, effective_from = ?
            WHERE id = ?
            """,
            (source_document_id, rule_value, unit, note, utc_today_iso(), row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO project_financial_rules (
            project_id, source_document_id, rule_name, rule_value, unit, note, version, effective_from
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, rule_name, rule_value, unit, note, version, utc_today_iso()),
    )


def ensure_profit_distribution_rule(conn, project_id, source_document_id, item_name, ratio, display_order, note=""):
    row = conn.execute(
        """
        SELECT id
        FROM project_profit_distribution_rules
        WHERE project_id = ? AND item_name = ?
        LIMIT 1
        """,
        (project_id, item_name),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_profit_distribution_rules
            SET source_document_id = ?, ratio = ?, display_order = ?, note = ?
            WHERE id = ?
            """,
            (source_document_id, ratio, display_order, note, row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO project_profit_distribution_rules (
            project_id, source_document_id, item_name, ratio, display_order, note
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, item_name, ratio, display_order, note),
    )


def ensure_investment_intent(conn, project_id, source_document_id, intent_code, amount, note="", investor_name=""):
    row = conn.execute(
        """
        SELECT id
        FROM investment_intents
        WHERE project_id = ? AND intent_code = ?
        LIMIT 1
        """,
        (project_id, intent_code),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE investment_intents
            SET source_document_id = ?, investor_name = ?, amount = ?, note = ?
            WHERE id = ?
            """,
            (source_document_id, investor_name, amount, note, row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO investment_intents (
            project_id, source_document_id, intent_code, investor_name, amount, note
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, intent_code, investor_name, amount, note),
    )


def ensure_project_site(
    conn,
    project_id,
    source_document_id,
    site_name,
    site_type="rooftop",
    planned_capacity_kw=0,
    actual_capacity_kw=0,
    annual_generation_kwh=0,
    annual_revenue=0,
    status="planned",
    note="",
):
    row = conn.execute(
        """
        SELECT id
        FROM project_sites
        WHERE project_id = ? AND site_name = ?
        LIMIT 1
        """,
        (project_id, site_name),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_sites
            SET source_document_id = ?, site_type = ?, planned_capacity_kw = ?, actual_capacity_kw = ?,
                annual_generation_kwh = ?, annual_revenue = ?, status = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                source_document_id,
                site_type,
                planned_capacity_kw,
                actual_capacity_kw,
                annual_generation_kwh,
                annual_revenue,
                status,
                note,
                row["id"],
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO project_sites (
            project_id, source_document_id, site_name, site_type, planned_capacity_kw, actual_capacity_kw,
            annual_generation_kwh, annual_revenue, status, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            source_document_id,
            site_name,
            site_type,
            planned_capacity_kw,
            actual_capacity_kw,
            annual_generation_kwh,
            annual_revenue,
            status,
            note,
        ),
    )


def ensure_project_milestone(
    conn,
    project_id,
    source_document_id,
    milestone_code,
    title,
    stage_group="",
    planned_period="",
    status="planned",
    display_order=0,
    note="",
):
    row = conn.execute(
        """
        SELECT id
        FROM project_milestones
        WHERE project_id = ? AND milestone_code = ?
        LIMIT 1
        """,
        (project_id, milestone_code),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_milestones
            SET source_document_id = ?, title = ?, stage_group = ?, planned_period = ?, status = ?,
                display_order = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, title, stage_group, planned_period, status, display_order, note, row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO project_milestones (
            project_id, source_document_id, milestone_code, title, stage_group, planned_period, status, display_order, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, milestone_code, title, stage_group, planned_period, status, display_order, note),
    )


def ensure_project_metric(
    conn,
    project_id,
    source_document_id,
    metric_name,
    metric_group,
    metric_period,
    metric_value,
    unit="",
    note="",
):
    row = conn.execute(
        """
        SELECT id
        FROM project_metrics
        WHERE project_id = ? AND metric_name = ? AND metric_group = ? AND metric_period = ?
        LIMIT 1
        """,
        (project_id, metric_name, metric_group, metric_period),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE project_metrics
            SET source_document_id = ?, metric_value = ?, unit = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, metric_value, unit, note, row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO project_metrics (
            project_id, source_document_id, metric_name, metric_group, metric_period, metric_value, unit, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, metric_name, metric_group, metric_period, metric_value, unit, note),
    )


def ensure_community_benefit_program(
    conn,
    project_id,
    source_document_id,
    program_name,
    program_type,
    description,
    display_order=0,
    is_active=1,
):
    row = conn.execute(
        """
        SELECT id
        FROM community_benefit_programs
        WHERE project_id = ? AND program_name = ?
        LIMIT 1
        """,
        (project_id, program_name),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE community_benefit_programs
            SET source_document_id = ?, program_type = ?, description = ?, display_order = ?,
                is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (source_document_id, program_type, description, display_order, is_active, row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO community_benefit_programs (
            project_id, source_document_id, program_name, program_type, description, display_order, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, source_document_id, program_name, program_type, description, display_order, is_active),
    )


def seed_legacy_data(conn):
    legacy_rules = [
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
    ]
    for rule_name, value in legacy_rules:
        ensure_calculator_rule(conn, rule_name, value)

    if conn.execute("SELECT COUNT(*) FROM faq_items").fetchone()[0] == 0:
        faq_rows = [
            (
                "regulation",
                "如何加入公民電廠？",
                "可以先了解案場說明、投資門檻與社區規則，再由社區或公司提供實際參與方式。",
            ),
            (
                "investment",
                "投資試算的數字怎麼來？",
                "目前依南寮公民電廠方案書中的建置成本、售電價格、年發電量與 IRR 參考值進行估算。",
            ),
            (
                "project-progress",
                "案場進度會顯示哪些階段？",
                "起案初期通常會經過增資、併網審查、試運轉、驗收交接與正式運維等階段。",
            ),
        ]
        for category_slug, question, answer in faq_rows:
            conn.execute(
                """
                INSERT INTO faq_items (category_id, question, answer, is_active, created_at, updated_at)
                VALUES (
                    (SELECT id FROM faq_categories WHERE slug = ? LIMIT 1),
                    ?, ?, 1, ?, ?
                )
                """,
                (category_slug, question, answer, utc_now_iso(), utc_now_iso()),
            )

    if conn.execute("SELECT COUNT(*) FROM progress_items").fetchone()[0] == 0:
        conn.execute(
            """
            INSERT INTO progress_items (stage, updated_at, line_user_id, display_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("規劃中", "2026-04-10", "", "系統預設", utc_now_iso()),
        )


def seed_product_tables(conn):
    upsert_community(
        conn,
        CHONGGUANG_COMMUNITY_ID,
        "重光社區",
        "penghu-chongguang",
        "系統原型與示範功能使用的社區。",
    )
    upsert_community(
        conn,
        NANLIAO_COMMUNITY_ID,
        "南寮社區",
        "penghu-nanliao",
        "南寮公民電廠研究、起案與示範場域。",
    )

    upsert_project(
        conn,
        CHONGGUANG_PROJECT_ID,
        CHONGGUANG_COMMUNITY_ID,
        "重光社區示範案",
        "chongguang-demo",
        "目前系統功能與頁面流程的示範案。",
        "規劃中",
        "planning",
    )
    upsert_project(
        conn,
        NANLIAO_PROJECT_ID,
        NANLIAO_COMMUNITY_ID,
        "南寮公民電廠",
        "nanliao-citizen-power",
        "南寮社區公民電廠的規劃、增資、併網與營運資料。",
        "正式運維",
        "active",
    )

    source_documents = [
        (
            DOC_NANLIAO_EXEC_PLAN_ID,
            "111年度澎湖南寮社區公開募集設置再生能源公民電廠示範獎勵計畫執行方案書",
            "nanliao-exec-plan-20231108",
            "nanliao_exec_plan_20231108.pdf",
            "2023-11-08 修正版",
            "pdf",
            "2023-11-08",
            "南寮公民電廠起案與財務模型的主要執行方案。",
        ),
        (
            DOC_NANLIAO_APPROVED_GRANT_ID,
            "111年社區公開募集設置再生能源公民電廠示範獎勵申請（澎湖南寮）核定版",
            "nanliao-grant-approved-20220610",
            "nanliao_grant_approved_20220610.pdf",
            "2022-06-10 核定版",
            "pdf",
            "2022-06-10",
            "南寮社區早期目標容量、潛力點與查核點資料來源。",
        ),
        (
            DOC_NANLIAO_COMPANY_INTRO_20240916_ID,
            "1130916 南寮公民電廠公司介紹",
            "nanliao-company-intro-20240916",
            "nanliao_company_intro_20240916.pdf",
            "2024-09-16",
            "pdf",
            "2024-09-16",
            "南寮公民電廠公司介紹與社區參與說明。",
        ),
        (
            DOC_CITIZEN_POWER_STAGE2_APPLY_ID,
            "1131017 公民電廠示範獎勵辦法計畫第二階段獎勵申請",
            "citizen-power-stage2-apply-20241017",
            "citizen_power_stage2_apply_20241017.pdf",
            "2024-10-17",
            "pdf",
            "2024-10-17",
            "第二階段增資、併網、驗收與正式運維的時程依據。",
        ),
        (
            DOC_NANLIAO_COMPANY_INTRO_20250623_ID,
            "20250623 南寮公民電廠簡介",
            "nanliao-company-intro-20250623",
            "nanliao_company_intro_20250623.pdf",
            "2025-06-23",
            "pdf",
            "2025-06-23",
            "南寮公民電廠實際建置場景、年發電量與年收益摘要。",
        ),
        (
            DOC_CITIZEN_POWER_HISTORY_MODEL_ID,
            "公民電廠發展歷程與創新推動模式",
            "citizen-power-history-model",
            "citizen_power_history_model.pdf",
            "研究整理版",
            "pdf",
            "",
            "作為公民電廠模式與制度演進的背景參考文件。",
        ),
    ]
    for args in source_documents:
        upsert_source_document(conn, *args)

    faq_categories = [
        (1, "法規與申請", "regulation"),
        (2, "投資與收益", "investment"),
        (3, "案場進度", "project-progress"),
        (4, "韌性與社區回饋", "resilience"),
    ]
    for args in faq_categories:
        upsert_faq_category(conn, *args)

    financial_rules = [
        ("installed_capacity_kw", 87.75, "kW", "南寮方案書中的規劃建置容量", DOC_NANLIAO_EXEC_PLAN_ID),
        ("project_budget", 5265000, "TWD", "規劃總設備經費", DOC_NANLIAO_EXEC_PLAN_ID),
        ("price_per_kw", 60000, "TWD/kW", "單瓩建置成本參考值", DOC_NANLIAO_EXEC_PLAN_ID),
        ("sell_price_per_kwh", 5.5, "TWD/kWh", "財務模型採用的綠電轉供售價", DOC_NANLIAO_EXEC_PLAN_ID),
        ("sell_price_min_per_kwh", 5, "TWD/kWh", "文件中的售電價格區間下限", DOC_NANLIAO_EXEC_PLAN_ID),
        ("sell_price_max_per_kwh", 7, "TWD/kWh", "文件中的售電價格區間上限", DOC_NANLIAO_EXEC_PLAN_ID),
        ("annual_generation_kwh", 112635, "kWh", "年平均發電量", DOC_NANLIAO_EXEC_PLAN_ID),
        ("degradation_rate", 0.01, "ratio", "模組年衰退率", DOC_NANLIAO_EXEC_PLAN_ID),
        ("project_years", 20, "year", "方案財務模型觀察年期", DOC_NANLIAO_EXEC_PLAN_ID),
        ("average_annual_income", 619494, "TWD", "年平均售電收入", DOC_NANLIAO_EXEC_PLAN_ID),
        ("annual_net_income", 304754, "TWD", "可供股東與社區分配的年淨收益估算", DOC_NANLIAO_EXEC_PLAN_ID),
        ("total_20y_income", 12389873, "TWD", "20 年總收入", DOC_NANLIAO_EXEC_PLAN_ID),
        ("total_20y_net_income", 5516039, "TWD", "20 年總淨收益", DOC_NANLIAO_EXEC_PLAN_ID),
        ("reference_irr", 0.0878, "ratio", "20 年平均內部報酬率 IRR", DOC_NANLIAO_EXEC_PLAN_ID),
        ("government_subsidy", 2632500, "TWD", "中央補助金額", DOC_NANLIAO_EXEC_PLAN_ID),
        ("government_subsidy_ratio", 0.50, "ratio", "設備補助比例", DOC_NANLIAO_EXEC_PLAN_ID),
        ("resident_investment_ratio", 0.50, "ratio", "社區居民投資比例", DOC_NANLIAO_EXEC_PLAN_ID),
        ("target_capacity_kw", 300, "kW", "早期擴大量體目標", DOC_NANLIAO_APPROVED_GRANT_ID),
        ("target_site_count", 15, "site", "早期規劃的潛力屋頂點數", DOC_NANLIAO_APPROVED_GRANT_ID),
        ("target_annual_generation_kwh", 513095, "kWh", "300kW 目標容量的年發電量估算", DOC_NANLIAO_EXEC_PLAN_ID),
    ]
    for rule_name, rule_value, unit, note, source_document_id in financial_rules:
        ensure_project_financial_rule(
            conn,
            NANLIAO_PROJECT_ID,
            source_document_id,
            rule_name,
            rule_value,
            unit,
            note,
        )

    profit_rules = [
        ("股東紅利", 0.50, 1, "年度淨收益分配給股東的比例"),
        ("運維與行政", 0.35, 2, "系統運維與公司行政開銷"),
        ("案場租金", 0.10, 3, "案場租金與場地使用成本"),
        ("社區回饋", 0.05, 4, "綠能收益回饋社區的比例"),
    ]
    for item_name, ratio, display_order, note in profit_rules:
        ensure_profit_distribution_rule(
            conn,
            NANLIAO_PROJECT_ID,
            DOC_NANLIAO_EXEC_PLAN_ID,
            item_name,
            ratio,
            display_order,
            note,
        )

    nanliao_intents = [
        ("A01", 1100000),
        ("A02", 1000000),
        ("A03", 400000),
        ("A04", 100000),
        ("A05", 50000),
        ("A06", 50000),
        ("A07", 400000),
        ("A08", 540000),
        ("A09", 100000),
        ("A10", 100000),
        ("A11", 100000),
        ("A12", 50000),
        ("B01", 100000),
        ("B02", 100000),
        ("B03", 400000),
        ("B04", 100000),
        ("C01", 525000),
        ("C02", 50000),
    ]
    for intent_code, amount in nanliao_intents:
        ensure_investment_intent(
            conn,
            NANLIAO_PROJECT_ID,
            DOC_NANLIAO_EXEC_PLAN_ID,
            intent_code,
            amount,
            note="南寮執行方案書中的投資意向金額整理",
        )

    project_sites = [
        ("南寮屋頂場景 1", 27.3, "已建置場景，455W 模組 60 片"),
        ("南寮屋頂場景 2", 11.83, "已建置場景，455W 模組 26 片"),
        ("南寮屋頂場景 3", 23.205, "已建置場景，455W 模組 51 片"),
    ]
    for site_name, actual_capacity_kw, note in project_sites:
        ensure_project_site(
            conn,
            NANLIAO_PROJECT_ID,
            DOC_NANLIAO_COMPANY_INTRO_20250623_ID,
            site_name,
            site_type="rooftop",
            actual_capacity_kw=actual_capacity_kw,
            status="operating",
            note=note,
        )

    milestones = [
        (
            "capacity-and-budget-confirmation",
            "確認案場容量、工程預算與規劃時程",
            "治理與募資",
            "第二階段啟動",
            "completed",
            10,
            "先確認容量、預算與時程，再送董事會定案。",
        ),
        (
            "capital-increase",
            "公司增資與股東名冊建立",
            "治理與募資",
            "第二階段啟動",
            "completed",
            20,
            "建立增資股東名冊、確認增資基準日並召開股東臨時會。",
        ),
        (
            "grid-review",
            "併網審查與台電同意作業",
            "工程與審查",
            "工程建置期",
            "completed",
            30,
            "完成併網申請與相關審查文件。",
        ),
        (
            "trial-run-and-registration",
            "併網試運轉與設備登記",
            "工程與審查",
            "工程建置期",
            "completed",
            40,
            "辦理試運轉、計價電表安裝與能源局設備登記。",
        ),
        (
            "acceptance-and-handover",
            "設備驗收與技術交接",
            "工程與交接",
            "工程完工期",
            "completed",
            50,
            "工程團隊與公民電廠公司進行驗收與技術交接。",
        ),
        (
            "green-power-transfer",
            "綠電轉供作業",
            "營運",
            "正式運維期",
            "active",
            60,
            "進入綠電轉供與正式營運流程。",
        ),
        (
            "system-operations",
            "系統運維與效益分析",
            "營運",
            "正式運維期",
            "active",
            70,
            "前兩年由原工程團隊提供保固與帶領，後續逐步建立在地運維能力。",
        ),
    ]
    for milestone_code, title, stage_group, planned_period, status, display_order, note in milestones:
        ensure_project_milestone(
            conn,
            NANLIAO_PROJECT_ID,
            DOC_CITIZEN_POWER_STAGE2_APPLY_ID,
            milestone_code,
            title,
            stage_group,
            planned_period,
            status,
            display_order,
            note,
        )

    metrics = [
        ("planned_capacity_kw", "planning", "2023-plan", 87.75, "kW", "方案書規劃容量"),
        ("project_budget_twd", "planning", "2023-plan", 5265000, "TWD", "規劃總設備經費"),
        ("reference_irr", "planning", "2023-plan", 0.0878, "ratio", "20 年平均 IRR"),
        ("annual_generation_kwh", "planning", "2023-plan", 112635, "kWh", "規劃年發電量"),
        ("annual_revenue_twd", "planning", "2023-plan", 619494, "TWD", "規劃年收入"),
        ("total_20y_revenue_twd", "planning", "2023-plan", 12389873, "TWD", "規劃 20 年總收入"),
        ("total_20y_net_income_twd", "planning", "2023-plan", 5516039, "TWD", "規劃 20 年總淨收益"),
        ("resident_investor_count", "participation", "2024-survey", 16, "person", "預估社區居民參與投資人數"),
        ("total_investor_count", "participation", "2024-survey", 18, "person", "總投資人數"),
        ("valid_survey_response_count", "participation", "2024-survey", 55, "response", "有效問卷份數"),
        ("awareness_ratio", "participation", "2024-survey", 0.64, "ratio", "知道社區正在籌建公民電廠的比例"),
        ("investment_willingness_ratio", "participation", "2024-survey", 0.27, "ratio", "願意出資成為股東的比例"),
        ("target_capacity_kw", "target", "2022-grant", 300, "kW", "早期規劃總容量目標"),
        ("target_site_count", "target", "2022-grant", 15, "site", "早期潛力屋頂數目標"),
        ("target_survey_count", "target", "2022-grant", 50, "response", "早期居民問卷數目標"),
        ("actual_built_capacity_kw", "operation", "2025-summary", 62.335, "kW", "2025 簡介中的已建置容量"),
        ("actual_annual_generation_kwh", "operation", "2025-summary", 78723, "kWh", "2025 簡介中的年發電量"),
        ("actual_annual_revenue_twd", "operation", "2025-summary", 393615, "TWD", "2025 簡介中的年收益"),
    ]
    for metric_name, metric_group, metric_period, metric_value, unit, note in metrics:
        source_document_id = DOC_NANLIAO_COMPANY_INTRO_20250623_ID if metric_group == "operation" else DOC_NANLIAO_EXEC_PLAN_ID
        if metric_period == "2022-grant":
            source_document_id = DOC_NANLIAO_APPROVED_GRANT_ID
        ensure_project_metric(
            conn,
            NANLIAO_PROJECT_ID,
            source_document_id,
            metric_name,
            metric_group,
            metric_period,
            metric_value,
            unit,
            note,
        )

    community_programs = [
        (
            "綠色能源教育宣導",
            "education",
            "向下扎根推動再生能源教育與社區能源知識普及。",
            10,
        ),
        (
            "社區老人健康講座與契作",
            "health",
            "結合健康講座與農場收成安排老人有薪契作，讓高齡者持續參與社區經濟。",
            20,
        ),
        (
            "低碳有機耕種輔導",
            "agriculture",
            "輔導社區發展低碳有機農業，讓綠能收益回到在地生活。",
            30,
        ),
        (
            "青年與新住民回流機會",
            "community",
            "吸引文創與再生能源設備運維相關人才投入社區，帶動地方工作機會。",
            40,
        ),
        (
            "在地研究與經驗擴散",
            "research",
            "支持在地研究與公民電廠經驗整理，協助模式擴散到其他社區。",
            50,
        ),
    ]
    for program_name, program_type, description, display_order in community_programs:
        ensure_community_benefit_program(
            conn,
            NANLIAO_PROJECT_ID,
            DOC_NANLIAO_COMPANY_INTRO_20240916_ID,
            program_name,
            program_type,
            description,
            display_order,
        )


def copy_bundled_db_if_needed():
    db_path = get_db_path()
    if not db_path.exists() and BUNDLED_DB_NAME.exists():
        ensure_db_directory()
        shutil.copyfile(BUNDLED_DB_NAME, db_path)


def init_db():
    copy_bundled_db_if_needed()
    conn = get_connection()
    run_schema(conn)
    ensure_progress_columns(conn)
    ensure_faq_columns(conn)
    ensure_calculator_rule_columns(conn)
    seed_product_tables(conn)
    seed_legacy_data(conn)
    conn.commit()
    conn.close()
