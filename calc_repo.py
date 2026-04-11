from db import get_connection

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"


def _rule_value(rule_map, key, fallback):
    entry = rule_map.get(key)
    return entry["value"] if entry else fallback


def get_project_summary(project_slug):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT p.id, p.name, p.slug, p.description, p.current_stage, p.status, c.name AS community_name
        FROM projects p
        INNER JOIN communities c ON c.id = p.community_id
        WHERE p.slug = ?
        LIMIT 1
        """,
        (project_slug,),
    ).fetchone()
    conn.close()
    return row


def get_project_financial_rules(project_slug):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT pfr.rule_name, pfr.rule_value, pfr.unit, pfr.note
        FROM project_financial_rules pfr
        INNER JOIN projects p ON p.id = pfr.project_id
        WHERE p.slug = ?
        ORDER BY pfr.rule_name ASC, pfr.version DESC, pfr.id DESC
        """,
        (project_slug,),
    ).fetchall()
    conn.close()

    rules = {}
    for row in rows:
        rules.setdefault(
            row["rule_name"],
            {
                "value": row["rule_value"],
                "unit": row["unit"],
                "note": row["note"],
            },
        )
    return rules


def get_project_profit_distribution(project_slug):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT ppdr.item_name, ppdr.ratio, ppdr.note
        FROM project_profit_distribution_rules ppdr
        INNER JOIN projects p ON p.id = ppdr.project_id
        WHERE p.slug = ?
        ORDER BY ppdr.display_order ASC, ppdr.id ASC
        """,
        (project_slug,),
    ).fetchall()
    conn.close()
    return rows


def get_project_metrics(project_slug):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT pm.metric_name, pm.metric_group, pm.metric_period, pm.metric_value, pm.unit, pm.note
        FROM project_metrics pm
        INNER JOIN projects p ON p.id = pm.project_id
        WHERE p.slug = ?
        ORDER BY pm.metric_group ASC, pm.metric_period ASC, pm.metric_name ASC
        """,
        (project_slug,),
    ).fetchall()
    conn.close()

    metrics = {}
    for row in rows:
        metrics[(row["metric_name"], row["metric_period"])] = row
        metrics.setdefault(row["metric_name"], row)
    return metrics


def get_calculator_settings():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT rule_name, value
        FROM calculator_rules
        ORDER BY version DESC, effective_from DESC, id DESC
        """
    ).fetchall()
    conn.close()

    settings = {}
    for row in rows:
        settings.setdefault(row["rule_name"], row["value"])

    return {
        "reference_irr": settings.get("reference_irr", 0.0878),
        "sell_price_per_kwh": settings.get("sell_price_per_kwh", 5.5),
        "annual_generation_kwh": settings.get("annual_generation_kwh", 112635),
        "annual_net_income": settings.get("annual_net_income", 304754),
        "shareholder_dividend_rate": settings.get("shareholder_dividend_rate", 0.50),
        "operation_cost_rate": settings.get("operation_cost_rate", 0.35),
        "site_rent_rate": settings.get("site_rent_rate", 0.10),
        "community_return_rate": settings.get("community_return_rate", 0.05),
        "project_years": int(settings.get("project_years", 20)),
        "degradation_rate": settings.get("degradation_rate", 0.01),
        "reference_project_budget": settings.get("reference_project_budget", 5265000),
        "reference_resident_investment": settings.get("reference_resident_investment", 2632500),
    }


def build_calculator_result(amount, project_slug=DEFAULT_PROJECT_SLUG):
    amount = max(amount, 0)
    fallback_settings = get_calculator_settings()
    project = get_project_summary(project_slug)
    rule_map = get_project_financial_rules(project_slug)
    metrics = get_project_metrics(project_slug)
    distribution_rows = get_project_profit_distribution(project_slug)

    reference_project_budget = _rule_value(
        rule_map,
        "project_budget",
        fallback_settings["reference_project_budget"],
    )
    resident_investment_ratio = _rule_value(rule_map, "resident_investment_ratio", 0.50)
    reference_resident_investment = max(reference_project_budget * resident_investment_ratio, 0)
    shareholder_dividend_rate = _rule_value(
        rule_map,
        "shareholder_dividend_rate",
        fallback_settings["shareholder_dividend_rate"],
    )

    for row in distribution_rows:
        if row["item_name"] == "股東紅利":
            shareholder_dividend_rate = row["ratio"]
            break

    settings = {
        "reference_irr": _rule_value(rule_map, "reference_irr", fallback_settings["reference_irr"]),
        "sell_price_per_kwh": _rule_value(rule_map, "sell_price_per_kwh", fallback_settings["sell_price_per_kwh"]),
        "sell_price_min_per_kwh": _rule_value(rule_map, "sell_price_min_per_kwh", 5.0),
        "sell_price_max_per_kwh": _rule_value(rule_map, "sell_price_max_per_kwh", 7.0),
        "annual_generation_kwh": _rule_value(rule_map, "annual_generation_kwh", fallback_settings["annual_generation_kwh"]),
        "annual_net_income": _rule_value(rule_map, "annual_net_income", fallback_settings["annual_net_income"]),
        "shareholder_dividend_rate": shareholder_dividend_rate,
        "operation_cost_rate": _rule_value(rule_map, "operation_cost_rate", fallback_settings["operation_cost_rate"]),
        "site_rent_rate": _rule_value(rule_map, "site_rent_rate", fallback_settings["site_rent_rate"]),
        "community_return_rate": _rule_value(rule_map, "community_return_rate", fallback_settings["community_return_rate"]),
        "project_years": int(_rule_value(rule_map, "project_years", fallback_settings["project_years"])),
        "degradation_rate": _rule_value(rule_map, "degradation_rate", fallback_settings["degradation_rate"]),
        "reference_project_budget": reference_project_budget,
        "reference_resident_investment": reference_resident_investment,
        "installed_capacity_kw": _rule_value(rule_map, "installed_capacity_kw", 0),
        "target_capacity_kw": _rule_value(rule_map, "target_capacity_kw", 0),
        "target_site_count": int(_rule_value(rule_map, "target_site_count", 0)),
        "average_annual_income": _rule_value(rule_map, "average_annual_income", 0),
        "total_20y_income": _rule_value(rule_map, "total_20y_income", 0),
        "total_20y_net_income": _rule_value(rule_map, "total_20y_net_income", 0),
        "government_subsidy": _rule_value(rule_map, "government_subsidy", 0),
        "government_subsidy_ratio": _rule_value(rule_map, "government_subsidy_ratio", 0),
        "resident_investment_ratio": resident_investment_ratio,
    }

    annual_reference_return = amount * settings["reference_irr"]
    estimated_20y_reference_return = annual_reference_return * settings["project_years"]
    annual_dividend_pool = settings["annual_net_income"] * settings["shareholder_dividend_rate"]
    ownership_ratio = (amount / reference_resident_investment) if reference_resident_investment > 0 else 0
    annual_dividend_share = annual_dividend_pool * ownership_ratio
    payback_years = (amount / annual_dividend_share) if annual_dividend_share > 0 else None

    actual_capacity_row = metrics.get("actual_built_capacity_kw")
    actual_generation_row = metrics.get("actual_annual_generation_kwh")
    actual_revenue_row = metrics.get("actual_annual_revenue_twd")

    return {
        "amount": amount,
        "project_slug": project_slug,
        "project_name": project["name"] if project else "公民電廠案場",
        "community_name": project["community_name"] if project else "社區",
        "project_stage": project["current_stage"] if project else "",
        "project_status": project["status"] if project else "planning",
        "project_description": project["description"] if project else "",
        "distribution_rows": distribution_rows,
        "actual_built_capacity_kw": actual_capacity_row["metric_value"] if actual_capacity_row else 0,
        "actual_annual_generation_kwh": actual_generation_row["metric_value"] if actual_generation_row else 0,
        "actual_annual_revenue_twd": actual_revenue_row["metric_value"] if actual_revenue_row else 0,
        "annual_reference_return": annual_reference_return,
        "estimated_20y_reference_return": estimated_20y_reference_return,
        "annual_dividend_pool": annual_dividend_pool,
        "ownership_ratio": ownership_ratio,
        "annual_dividend_share": annual_dividend_share,
        "payback_years": payback_years,
        **settings,
    }
