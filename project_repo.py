from db import get_connection

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"


def get_project_overview(project_slug=DEFAULT_PROJECT_SLUG):
    conn = get_connection()

    project = conn.execute(
        """
        SELECT
            p.id,
            p.name,
            p.slug,
            p.description,
            p.current_stage,
            p.status,
            c.name AS community_name
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

    sites = conn.execute(
        """
        SELECT site_name, site_type, planned_capacity_kw, actual_capacity_kw,
               annual_generation_kwh, annual_revenue, status, note
        FROM project_sites
        WHERE project_id = ?
        ORDER BY id ASC
        """,
        (project["id"],),
    ).fetchall()

    metrics_rows = conn.execute(
        """
        SELECT metric_name, metric_group, metric_period, metric_value, unit, note
        FROM project_metrics
        WHERE project_id = ?
        ORDER BY metric_group ASC, metric_period ASC, metric_name ASC
        """,
        (project["id"],),
    ).fetchall()

    benefit_programs = conn.execute(
        """
        SELECT program_name, program_type, description, display_order
        FROM community_benefit_programs
        WHERE project_id = ? AND is_active = 1
        ORDER BY display_order ASC, id ASC
        """,
        (project["id"],),
    ).fetchall()

    financial_rows = conn.execute(
        """
        SELECT rule_name, rule_value, unit, note
        FROM project_financial_rules
        WHERE project_id = ?
        ORDER BY id ASC
        """,
        (project["id"],),
    ).fetchall()

    distribution_rows = conn.execute(
        """
        SELECT item_name, ratio, note
        FROM project_profit_distribution_rules
        WHERE project_id = ?
        ORDER BY display_order ASC, id ASC
        """,
        (project["id"],),
    ).fetchall()

    conn.close()

    metrics = {}
    metrics_by_group = {}
    for row in metrics_rows:
        metrics[row["metric_name"]] = row
        metrics_by_group.setdefault(row["metric_group"], []).append(row)

    financial_rules = {}
    for row in financial_rows:
        financial_rules[row["rule_name"]] = row

    return {
        "project": project,
        "milestones": milestones,
        "sites": sites,
        "metrics": metrics,
        "metrics_by_group": metrics_by_group,
        "benefit_programs": benefit_programs,
        "financial_rules": financial_rules,
        "distribution_rows": distribution_rows,
    }
