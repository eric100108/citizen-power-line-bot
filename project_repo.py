from db import get_connection

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"
PUBLIC_HIGHLIGHT_TYPES = {"knowledge", "engagement", "ecosystem"}
PUBLIC_VISIBILITY = ("public",)
INTERNAL_VISIBILITY = ("public", "restricted", "internal")
PUBLIC_RULE_SUMMARY = [
    {
        "label": "適用辦法",
        "value": "合作社及社區公開募集設置再生能源公民電廠示範獎勵辦法",
        "detail": "南寮案例頁依公開募集型公民電廠辦法整理公開資訊。",
    },
    {
        "label": "獎勵階段",
        "value": "實質設置階段",
        "detail": "頁面只呈現該階段應公開理解的流程、文件與參與原則。",
    },
    {
        "label": "獎勵上限",
        "value": "每案上限新臺幣 1,000 萬元，且不得超過總設置經費 50%",
        "detail": "前台不揭露南寮實際補助金額與內部財務數字，只呈現辦法規則。",
    },
    {
        "label": "公開募集原則",
        "value": "由團體發起，公開召集社區居民、社區團體或其他個人共同參與",
        "detail": "頁面保留的是參與方式與治理原則，不公開個別投資名單。",
    },
    {
        "label": "社區投資參與原則",
        "value": "居民或社區團體具投資意向之總額，至少占規劃總設置經費 20%",
        "detail": "前台只說明參與門檻，不公開南寮個別分配與投資比例。",
    },
    {
        "label": "補助限制",
        "value": "不得就相同補助項目重複申請政府補助",
        "detail": "公開頁面只保留法規限制，敏感申請資料維持在資料庫。",
    },
]

PUBLIC_HIGHLIGHT_CONTENT = {
    "knowledge": "公開版只保留制度理解、社區治理與流程設計等知識，細部財務模型與內部文件不在網站揭露。",
    "engagement": "公開版重點放在社區如何溝通、公開募集與建立共識，不公開個別參與名單與投資安排。",
    "ecosystem": "公開版只描述地方協作與營運回饋方向，不揭露個別收益分配與私密協作細節。",
}


def _fetch_rows(conn, sql, params, visibility_levels):
    placeholders = ",".join("?" for _ in visibility_levels)
    sql = sql.replace("__VISIBILITY_FILTER__", f"visibility_level IN ({placeholders})")
    return conn.execute(sql, (*params, *visibility_levels)).fetchall()


def _sanitize_sites(rows):
    sanitized = []
    for index, row in enumerate(rows, start=1):
        sanitized.append(
            {
                "site_name": f"示範場域 {index}",
                "site_type": row["site_type"],
                "status": row["status"],
                "note": "僅公開場域類型與推進狀態，細部位置、容量與營運數字不在前台顯示。",
            }
        )
    return sanitized


def _sanitize_document_highlights(rows):
    sanitized = []
    for row in rows:
        highlight_type = row["highlight_type"]
        if highlight_type not in PUBLIC_HIGHLIGHT_TYPES:
            continue
        sanitized.append(
            {
                "highlight_type": highlight_type,
                "title": row["title"],
                "content": PUBLIC_HIGHLIGHT_CONTENT.get(highlight_type, "公開版文件摘要僅保留可對外展示的知識內容。"),
                "reference_page": row["reference_page"],
                "display_order": row["display_order"],
                "source_title": row["source_title"],
            }
        )
    return sanitized


def _get_project_overview(project_slug, visibility_levels):
    conn = get_connection()
    project = conn.execute(
        """
        SELECT p.id, p.name, p.slug, p.description, p.current_stage, p.status, c.name AS community_name
        FROM projects p
        INNER JOIN communities c ON c.id = p.community_id
        WHERE p.slug = ?
        LIMIT 1
        """,
        (project_slug,),
    ).fetchone()
    if not project:
        conn.close()
        return None

    milestones = conn.execute(
        """
        SELECT title, stage_group, planned_period, status, display_order, note
        FROM project_milestones
        WHERE project_id = ?
        ORDER BY display_order ASC, id ASC
        """,
        (project["id"],),
    ).fetchall()

    sites = _fetch_rows(
        conn,
        """
        SELECT site_name, site_type, planned_capacity_kw, actual_capacity_kw,
               annual_generation_kwh, annual_revenue, status, note, visibility_level
        FROM project_sites
        WHERE project_id = ? AND __VISIBILITY_FILTER__
        ORDER BY id ASC
        """,
        (project["id"],),
        visibility_levels,
    )

    benefit_programs = conn.execute(
        """
        SELECT program_name, program_type, description, display_order
        FROM community_benefit_programs
        WHERE project_id = ? AND is_active = 1
        ORDER BY display_order ASC, id ASC
        """,
        (project["id"],),
    ).fetchall()

    service_steps = conn.execute(
        """
        SELECT step_code, title, stage_group, audience, summary, recommended_action, display_order
        FROM service_journey_steps
        WHERE project_id = ?
        ORDER BY display_order ASC, id ASC
        """,
        (project["id"],),
    ).fetchall()

    document_highlights = _fetch_rows(
        conn,
        """
        SELECT dh.highlight_type, dh.title, dh.content, dh.reference_page, dh.display_order, sd.title AS source_title, dh.visibility_level
        FROM document_highlights dh
        INNER JOIN source_documents sd ON sd.id = dh.source_document_id
        WHERE __VISIBILITY_FILTER__
        ORDER BY dh.display_order ASC, dh.id ASC
        """,
        tuple(),
        visibility_levels,
    )
    conn.close()

    if visibility_levels == PUBLIC_VISIBILITY:
        sites_payload = _sanitize_sites(sites)
        highlights_payload = _sanitize_document_highlights(document_highlights)
    else:
        sites_payload = sites
        highlights_payload = document_highlights

    return {
        "project": project,
        "milestones": milestones,
        "sites": sites_payload,
        "benefit_programs": benefit_programs,
        "financial_rules": {},
        "distribution_rows": [],
        "service_steps": service_steps,
        "document_highlights": highlights_payload,
        "regulation_summary": PUBLIC_RULE_SUMMARY,
    }


def get_project_overview(project_slug=DEFAULT_PROJECT_SLUG):
    return _get_project_overview(project_slug, PUBLIC_VISIBILITY)


def get_project_overview_internal(project_slug=DEFAULT_PROJECT_SLUG):
    return _get_project_overview(project_slug, INTERNAL_VISIBILITY)
