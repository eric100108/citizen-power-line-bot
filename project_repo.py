from db import get_connection

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"
PUBLIC_HIGHLIGHT_TYPES = {"knowledge", "engagement", "ecosystem"}
PUBLIC_VISIBILITY = ("public",)
INTERNAL_VISIBILITY = ("public", "restricted", "internal")
PUBLIC_RULE_SUMMARY = [
    {
        "label": "適用辦法",
        "value": "合作社及社區公開募集設置再生能源公民電廠示範獎勵辦法",
        "detail": "確認案件是否符合公民電廠示範獎勵的基本方向。",
    },
    {
        "label": "獎勵階段",
        "value": "實質設置階段",
        "detail": "重點在容量門檻、設置期程、社區參與與執行文件。",
    },
    {
        "label": "獎勵上限",
        "value": "每案上限新臺幣 1,000 萬元，且不得超過總設置經費 50%",
        "detail": "起案前可先用此規則估算補助上限，再依年度資料確認。",
    },
    {
        "label": "公開募集原則",
        "value": "由團體發起，公開召集社區居民、社區團體或其他個人共同參與",
        "detail": "需要有清楚的發起團體、參與方式與社區溝通安排。",
    },
    {
        "label": "社區投資參與原則",
        "value": "居民或社區團體具投資意向之總額，至少占規劃總設置經費 20%",
        "detail": "起案時需確認社區參與意願與資金規劃是否達標。",
    },
    {
        "label": "補助限制",
        "value": "不得就相同補助項目重複申請政府補助",
        "detail": "申請前需檢查是否已使用其他補助來源。",
    },
]

PUBLIC_HIGHLIGHT_CONTENT = {
    "knowledge": "制度重點、社區治理與推動流程。",
    "engagement": "社區溝通、公開募集與共識建立。",
    "ecosystem": "地方協作、營運回饋與後續擴點。",
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
                "note": "提供場域類型與推進狀態，作為場址盤點參考。",
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
                "content": PUBLIC_HIGHLIGHT_CONTENT.get(highlight_type, "專案方向與文件重點。"),
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
