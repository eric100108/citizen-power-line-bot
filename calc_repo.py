from math import floor

from db import get_connection

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"
PUBLIC_VISIBILITY = ("public",)
INTERNAL_VISIBILITY = ("public", "restricted", "internal")

SITE_PARAMETER_PRESETS = {
    "official_penghu_114": {
        "label": "官方參考",
        "source_label": "114 澎湖容量因數 + 115 屋頂型 FIT",
        "area_m2_per_kwp": 5.0,
        "annual_generation_per_kwp": 1249,
        "daily_generation_per_kwp": 3.42,
        "module_watt": 410,
        "module_area_m2": 1.95,
        "sell_price_per_kwh": 5.6279,
        "construction_unit_cost_per_kwp": 60000,
        "carbon_factor_kg_per_kwh": 0.474,
    },
    "nanliao_case": {
        "label": "南寮案例",
        "source_label": "南寮第二階段案例反推",
        "area_m2_per_kwp": 4.91,
        "annual_generation_per_kwp": 1263,
        "daily_generation_per_kwp": 3.46,
        "module_watt": 410,
        "module_area_m2": 1.95,
        "sell_price_per_kwh": 5.5,
        "construction_unit_cost_per_kwp": 60000,
        "carbon_factor_kg_per_kwh": 0.474,
    },
    "custom": {
        "label": "自訂參數",
        "source_label": "使用者自訂",
        "area_m2_per_kwp": 5.0,
        "annual_generation_per_kwp": 1249,
        "daily_generation_per_kwp": 3.42,
        "module_watt": 410,
        "module_area_m2": 1.95,
        "sell_price_per_kwh": 5.5,
        "construction_unit_cost_per_kwp": 60000,
        "carbon_factor_kg_per_kwh": 0.474,
    },
}

FIT_ROOFTOP_RATES = [
    {"capacity_min_kw": 1, "capacity_max_kw": 10, "rate_114_1": 5.7055, "rate_114_2": 5.6279, "rate_115": 5.6279},
    {"capacity_min_kw": 10, "capacity_max_kw": 20, "rate_114_1": 5.4561, "rate_114_2": 5.3819, "rate_115": 5.3819},
    {"capacity_min_kw": 20, "capacity_max_kw": 50, "rate_114_1": 4.2906, "rate_114_2": 4.2505, "rate_115": 4.2505},
    {"capacity_min_kw": 50, "capacity_max_kw": 100, "rate_114_1": 4.0853, "rate_114_2": 4.0459, "rate_115": 4.0459},
    {"capacity_min_kw": 100, "capacity_max_kw": 500, "rate_114_1": 3.7547, "rate_114_2": 3.7152, "rate_115": 3.7152},
    {"capacity_min_kw": 500, "capacity_max_kw": None, "rate_114_1": 3.6616, "rate_114_2": 3.6236, "rate_115": 3.6236},
]

OFFICIAL_SITE_ESTIMATE_NOTES = [
    "發電量預設採 114 年澎湖縣太陽光電容量因數：1,249 度/kW/年。",
    "收入預設採屋頂型太陽光電 FIT 級距費率；不再以南寮轉供情境價作為主模式。",
    "補助上限依公民電廠獎勵公式粗估：min(1,000 萬, 總設置經費 × 50%)。",
    "建置成本、模組瓦數與模組面積仍屬網站估算參數，正式申請需以當年度官方成本參數與設計資料確認。",
    "附表四至附表六的額外費率目前列為進階資料，尚未自動加計到 FIT 收入。",
]


def _fetch_site_parameter_presets():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                preset_code, label, source_label, area_m2_per_kwp,
                annual_generation_per_kwp, daily_generation_per_kwp, module_watt,
                module_area_m2, sell_price_per_kwh, construction_unit_cost_per_kwp,
                carbon_factor_kg_per_kwh
            FROM site_parameter_presets
            WHERE is_active = 1
            ORDER BY display_order ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        row["preset_code"]: {
            "label": row["label"],
            "source_label": row["source_label"],
            "area_m2_per_kwp": row["area_m2_per_kwp"],
            "annual_generation_per_kwp": row["annual_generation_per_kwp"],
            "daily_generation_per_kwp": row["daily_generation_per_kwp"],
            "module_watt": row["module_watt"],
            "module_area_m2": row["module_area_m2"],
            "sell_price_per_kwh": row["sell_price_per_kwh"],
            "construction_unit_cost_per_kwp": row["construction_unit_cost_per_kwp"],
            "carbon_factor_kg_per_kwh": row["carbon_factor_kg_per_kwh"],
        }
        for row in rows
    }


def _fetch_fit_rooftop_rates(tariff_year=115, period_label="full"):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT capacity_min_kw, capacity_max_kw, rate_per_kwh
            FROM fit_rooftop_rates
            WHERE tariff_year = ? AND period_label = ?
            ORDER BY capacity_min_kw ASC
            """,
            (tariff_year, period_label),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "capacity_min_kw": row["capacity_min_kw"],
            "capacity_max_kw": row["capacity_max_kw"],
            "rate_per_kwh": row["rate_per_kwh"],
        }
        for row in rows
    ]


def _rule_value(rule_map, key, fallback):
    entry = rule_map.get(key)
    return entry["value"] if entry else fallback


def _fetch_project_financial_rules(project_slug, visibility_levels):
    conn = get_connection()
    placeholders = ",".join("?" for _ in visibility_levels)
    rows = conn.execute(
        f"""
        SELECT pfr.rule_name, pfr.rule_value, pfr.unit, pfr.note, pfr.visibility_level
        FROM project_financial_rules pfr
        INNER JOIN projects p ON p.id = pfr.project_id
        WHERE p.slug = ? AND pfr.visibility_level IN ({placeholders})
        ORDER BY pfr.rule_name ASC, pfr.version DESC, pfr.id DESC
        """,
        (project_slug, *visibility_levels),
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
                "visibility_level": row["visibility_level"],
            },
        )
    return rules


def _fetch_distribution_rules(project_slug):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT pdr.item_name, pdr.ratio, pdr.display_order, pdr.note
        FROM project_profit_distribution_rules pdr
        INNER JOIN projects p ON p.id = pdr.project_id
        WHERE p.slug = ?
        ORDER BY pdr.display_order ASC, pdr.id ASC
        """,
        (project_slug,),
    ).fetchall()
    conn.close()
    return rows


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
    return _fetch_project_financial_rules(project_slug, PUBLIC_VISIBILITY)


def get_project_financial_rules_internal(project_slug):
    return _fetch_project_financial_rules(project_slug, INTERNAL_VISIBILITY)


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
        "reference_project_budget": settings.get("reference_project_budget", 5265000),
        "reference_resident_investment": settings.get("reference_resident_investment", 2632500),
        "area_m2_per_kwp": settings.get("area_m2_per_kwp", 5.0),
        "module_watt": settings.get("module_watt", 410),
        "annual_generation_per_kwp": settings.get("annual_generation_per_kwp", 1249),
        "construction_unit_cost_per_kwp": settings.get("construction_unit_cost_per_kwp", 60000),
        "degradation_rate": settings.get("degradation_rate", 0.01),
        "sell_price_per_kwh": settings.get("sell_price_per_kwh", 5.5),
    }


def _build_participation_profile(amount, reference_resident_investment):
    ratio = (amount / reference_resident_investment) if reference_resident_investment > 0 else 0
    if amount <= 0:
        return {
            "participation_band": "尚未輸入",
            "participation_summary": "先輸入想投入的金額，系統才會幫你判讀目前比較接近哪一種參與位置。",
            "next_step": "先輸入金額，再看是否要進一步對位 SOP。",
        }
    if ratio < 0.01:
        return {
            "participation_band": "初步了解",
            "participation_summary": "這筆金額比較適合用來理解公民電廠參與方式、流程與風險。",
            "next_step": "先查看案例與 SOP，判斷自己目前更接近哪一步。",
        }
    if ratio < 0.03:
        return {
            "participation_band": "評估參與",
            "participation_summary": "這個區間適合進一步確認你想扮演的角色，是場址提供、社區參與，還是投入更多討論與準備。",
            "next_step": "回到 SOP 對位頁，確認接下來要補哪一種資料。",
        }
    return {
        "participation_band": "準備決策",
        "participation_summary": "這個區間表示你可能已進入較具體的參與評估，可以安排真人協助確認場址、文件與參與方式。",
        "next_step": "建議直接進入 SOP 對位，並安排真人協助確認下一步。",
    }


def _sum_degraded_generation(first_year_generation_kwh, years, degradation_rate):
    total = 0
    rows = []
    for year in range(1, years + 1):
        factor = max(1 - (year - 1) * degradation_rate, 0)
        generation = first_year_generation_kwh * factor
        total += generation
        rows.append({"year": year, "generation_kwh": generation, "factor": factor})
    return total, rows


def _build_site_scale(capacity_kwp):
    if capacity_kwp < 10:
        return {
            "scale_label": "小型屋頂案場",
            "scale_summary": "適合先做為住家、店面或小型公共空間的初步評估。",
        }
    if capacity_kwp < 50:
        return {
            "scale_label": "中型社區案場",
            "scale_summary": "適合進一步確認結構、遮蔭、屋頂權屬與社區溝通條件。",
        }
    return {
        "scale_label": "大型示範案場",
        "scale_summary": "已具備較明確的專案規模，建議進入正式踏勘、併聯與財務模型評估。",
    }


def _get_fit_rate(capacity_kwp, rate_key="rate_115"):
    db_rates = _fetch_fit_rooftop_rates(115, "full")
    for row in db_rates:
        max_kw = row["capacity_max_kw"]
        if capacity_kwp >= row["capacity_min_kw"] and (max_kw is None or capacity_kwp < max_kw):
            return row["rate_per_kwh"], row

    for row in FIT_ROOFTOP_RATES:
        max_kw = row["capacity_max_kw"]
        if capacity_kwp >= row["capacity_min_kw"] and (max_kw is None or capacity_kwp < max_kw):
            return row[rate_key], row
    return FIT_ROOFTOP_RATES[0][rate_key], FIT_ROOFTOP_RATES[0]


def _format_capacity_tier(tier):
    min_kw = tier["capacity_min_kw"]
    max_kw = tier["capacity_max_kw"]
    if max_kw is None:
        return f"{min_kw:g} kW 以上"
    return f"{min_kw:g} kW 以上不及 {max_kw:g} kW"


def _build_site_parameters(
    parameter_mode,
    custom_area_m2_per_kwp=None,
    custom_annual_generation_per_kwp=None,
    custom_module_watt=None,
    custom_module_area_m2=None,
    custom_sell_price_per_kwh=None,
    custom_construction_unit_cost_per_kwp=None,
    custom_carbon_factor_kg_per_kwh=None,
):
    presets = _fetch_site_parameter_presets() or SITE_PARAMETER_PRESETS
    mode = parameter_mode if parameter_mode in presets else "official_penghu_114"
    params = dict(presets[mode])
    overrides = {
        "area_m2_per_kwp": custom_area_m2_per_kwp,
        "annual_generation_per_kwp": custom_annual_generation_per_kwp,
        "module_watt": custom_module_watt,
        "module_area_m2": custom_module_area_m2,
        "sell_price_per_kwh": custom_sell_price_per_kwh,
        "construction_unit_cost_per_kwp": custom_construction_unit_cost_per_kwp,
        "carbon_factor_kg_per_kwh": custom_carbon_factor_kg_per_kwh,
    }
    for key, value in overrides.items():
        if value is not None and value > 0:
            params[key] = value
    if custom_annual_generation_per_kwp is not None and custom_annual_generation_per_kwp > 0:
        params["daily_generation_per_kwp"] = params["annual_generation_per_kwp"] / 365
    return mode, params


def build_site_estimate_result(
    site_ping=30,
    usable_ratio=0.85,
    project_slug=DEFAULT_PROJECT_SLUG,
    years=20,
    carbon_factor_kg_per_kwh=None,
    tree_absorption_kg_per_year=12,
    parameter_mode="official_penghu_114",
    area_input_type="gross_area",
    degradation_method="compound",
    sales_mode="fit",
    custom_area_m2_per_kwp=None,
    custom_annual_generation_per_kwp=None,
    custom_module_watt=None,
    custom_module_area_m2=None,
    custom_sell_price_per_kwh=None,
    custom_construction_unit_cost_per_kwp=None,
):
    site_ping = max(site_ping, 0)
    usable_ratio = min(max(usable_ratio, 0), 1)
    years = max(int(years), 1)
    tree_absorption_kg_per_year = max(tree_absorption_kg_per_year, 1)
    area_input_type = area_input_type if area_input_type in {"gross_area", "usable_area"} else "gross_area"
    degradation_method = degradation_method if degradation_method in {"compound", "linear", "none"} else "compound"
    sales_mode = sales_mode if sales_mode in {"fit", "wheeling_transfer", "self_use"} else "fit"

    fallback_settings = get_calculator_settings()
    rule_map = get_project_financial_rules_internal(project_slug)
    resolved_mode, params = _build_site_parameters(
        parameter_mode,
        custom_area_m2_per_kwp=custom_area_m2_per_kwp,
        custom_annual_generation_per_kwp=custom_annual_generation_per_kwp,
        custom_module_watt=custom_module_watt,
        custom_module_area_m2=custom_module_area_m2,
        custom_sell_price_per_kwh=custom_sell_price_per_kwh,
        custom_construction_unit_cost_per_kwp=custom_construction_unit_cost_per_kwp,
        custom_carbon_factor_kg_per_kwh=carbon_factor_kg_per_kwh,
    )

    area_m2_per_kwp = params.get("area_m2_per_kwp") or fallback_settings["area_m2_per_kwp"]
    module_watt = params.get("module_watt") or fallback_settings["module_watt"]
    module_area_m2 = params.get("module_area_m2") or 1.95
    annual_generation_per_kwp = params.get("annual_generation_per_kwp") or fallback_settings["annual_generation_per_kwp"]
    daily_generation_per_kwp = params.get("daily_generation_per_kwp") or annual_generation_per_kwp / 365
    construction_unit_cost_per_kwp = params.get("construction_unit_cost_per_kwp") or fallback_settings["construction_unit_cost_per_kwp"]
    degradation_rate = _rule_value(rule_map, "degradation_rate", fallback_settings["degradation_rate"])
    carbon_factor_kg_per_kwh = max(params.get("carbon_factor_kg_per_kwh", 0.474), 0)

    usable_ping = site_ping if area_input_type == "usable_area" else site_ping * usable_ratio
    site_area_m2 = site_ping * 3.3058
    usable_area_m2 = usable_ping * 3.3058
    capacity_kwp = (usable_area_m2 / area_m2_per_kwp) if area_m2_per_kwp > 0 else 0
    panel_count = round((capacity_kwp * 1000) / module_watt) if module_watt > 0 else 0
    module_total_area_m2 = panel_count * module_area_m2
    daily_generation_kwh = capacity_kwp * daily_generation_per_kwp
    first_year_generation_kwh = capacity_kwp * annual_generation_per_kwp
    if degradation_method == "none":
        lifetime_generation_kwh = first_year_generation_kwh * years
        yearly_generation_rows = [
            {"year": year, "generation_kwh": first_year_generation_kwh, "factor": 1}
            for year in range(1, years + 1)
        ]
    elif degradation_method == "linear":
        lifetime_generation_kwh, yearly_generation_rows = _sum_degraded_generation(first_year_generation_kwh, years, degradation_rate)
    else:
        lifetime_generation_kwh = 0
        yearly_generation_rows = []
        for year in range(1, years + 1):
            factor = (1 - degradation_rate) ** (year - 1)
            generation = first_year_generation_kwh * factor
            lifetime_generation_kwh += generation
            yearly_generation_rows.append({"year": year, "generation_kwh": generation, "factor": factor})
    year_20_generation_kwh = yearly_generation_rows[-1]["generation_kwh"] if yearly_generation_rows else 0
    construction_cost = capacity_kwp * construction_unit_cost_per_kwp
    fit_rate, fit_tier = _get_fit_rate(capacity_kwp, "rate_115")
    if custom_sell_price_per_kwh is not None and custom_sell_price_per_kwh > 0:
        sell_price_per_kwh = custom_sell_price_per_kwh
    elif sales_mode == "fit":
        sell_price_per_kwh = fit_rate
    else:
        sell_price_per_kwh = params.get("sell_price_per_kwh", fallback_settings["sell_price_per_kwh"])
    first_year_revenue = first_year_generation_kwh * sell_price_per_kwh
    lifetime_revenue = lifetime_generation_kwh * sell_price_per_kwh
    reward_max = min(10000000, construction_cost * 0.5)
    minimum_community_investment = construction_cost * 0.2
    annual_carbon_reduction_kg = first_year_generation_kwh * carbon_factor_kg_per_kwh
    lifetime_carbon_reduction_kg = lifetime_generation_kwh * carbon_factor_kg_per_kwh
    tree_equivalent = annual_carbon_reduction_kg / tree_absorption_kg_per_year
    scale = _build_site_scale(capacity_kwp)

    return {
        "project_slug": project_slug,
        "parameter_mode": resolved_mode,
        "parameter_label": params["label"],
        "parameter_source_label": params["source_label"],
        "parameter_presets": SITE_PARAMETER_PRESETS,
        "fit_rooftop_rates": FIT_ROOFTOP_RATES,
        "area_input_type": area_input_type,
        "degradation_method": degradation_method,
        "sales_mode": sales_mode,
        "site_ping": site_ping,
        "usable_ratio": usable_ratio,
        "usable_ping": usable_ping,
        "site_area_m2": site_area_m2,
        "usable_area_m2": usable_area_m2,
        "capacity_kwp": capacity_kwp,
        "panel_count": panel_count,
        "module_watt": module_watt,
        "module_area_m2": module_area_m2,
        "module_total_area_m2": module_total_area_m2,
        "area_m2_per_kwp": area_m2_per_kwp,
        "daily_generation_per_kwp": daily_generation_per_kwp,
        "annual_generation_per_kwp": annual_generation_per_kwp,
        "degradation_rate": degradation_rate,
        "construction_unit_cost_per_kwp": construction_unit_cost_per_kwp,
        "sell_price_per_kwh": sell_price_per_kwh,
        "fit_rate": fit_rate,
        "fit_tier": fit_tier,
        "fit_tier_label": _format_capacity_tier(fit_tier),
        "official_notes": OFFICIAL_SITE_ESTIMATE_NOTES,
        "daily_generation_kwh": daily_generation_kwh,
        "first_year_generation_kwh": first_year_generation_kwh,
        "year_20_generation_kwh": year_20_generation_kwh,
        "lifetime_generation_kwh": lifetime_generation_kwh,
        "construction_cost": construction_cost,
        "reward_max": reward_max,
        "minimum_community_investment": minimum_community_investment,
        "eligible_capacity": capacity_kwp >= 10,
        "required_participant_count": 15,
        "first_year_revenue": first_year_revenue,
        "lifetime_revenue": lifetime_revenue,
        "years": years,
        "carbon_factor_kg_per_kwh": carbon_factor_kg_per_kwh,
        "annual_carbon_reduction_kg": annual_carbon_reduction_kg,
        "lifetime_carbon_reduction_kg": lifetime_carbon_reduction_kg,
        "tree_absorption_kg_per_year": tree_absorption_kg_per_year,
        "tree_equivalent": tree_equivalent,
        "yearly_generation_rows": yearly_generation_rows,
        **scale,
    }


def build_calculator_result(amount, project_slug=DEFAULT_PROJECT_SLUG, roof_ping=30):
    amount = max(amount, 0)
    fallback_settings = get_calculator_settings()
    project = get_project_summary(project_slug)
    rule_map = get_project_financial_rules_internal(project_slug)
    distribution_rows = _fetch_distribution_rules(project_slug)

    reference_project_budget = _rule_value(rule_map, "project_budget", fallback_settings["reference_project_budget"])
    resident_investment_ratio = _rule_value(rule_map, "resident_investment_ratio", 0.50)
    reference_resident_investment = max(
        _rule_value(rule_map, "reference_resident_investment", reference_project_budget * resident_investment_ratio),
        0,
    )
    reference_irr = _rule_value(rule_map, "reference_irr", 0.0878)
    shareholder_dividend_rate = _rule_value(rule_map, "shareholder_dividend_rate", 0.50)
    annual_net_income = _rule_value(rule_map, "annual_net_income", 304754)
    ownership_ratio = (amount / reference_resident_investment) if reference_resident_investment > 0 else 0
    annual_dividend_pool = annual_net_income * shareholder_dividend_rate
    annual_dividend_share = annual_dividend_pool * ownership_ratio
    annual_reference_return = amount * reference_irr
    project_years = int(_rule_value(rule_map, "project_years", 20))
    estimated_20y_reference_return = annual_reference_return * project_years
    payback_years = (amount / annual_reference_return) if annual_reference_return > 0 else None
    profile = _build_participation_profile(amount, reference_resident_investment)
    site_estimate = build_site_estimate_result(roof_ping, 1, project_slug, project_years)

    return {
        "amount": amount,
        "project_slug": project_slug,
        "project_name": project["name"] if project else "公民電廠案例",
        "community_name": project["community_name"] if project else "社區案例",
        "project_stage": project["current_stage"] if project else "規劃中",
        "project_status": project["status"] if project else "planning",
        "project_description": project["description"] if project else "這個頁面提供的是參與判讀與屋頂容量快速估算。",
        "participation_band": profile["participation_band"],
        "participation_summary": profile["participation_summary"],
        "next_step": profile["next_step"],
        "reference_project_budget": reference_project_budget,
        "resident_investment_ratio": resident_investment_ratio,
        "reference_resident_investment": reference_resident_investment,
        "reference_irr": reference_irr,
        "annual_reference_return": annual_reference_return,
        "annual_dividend_pool": annual_dividend_pool,
        "annual_dividend_share": annual_dividend_share,
        "ownership_ratio": ownership_ratio,
        "estimated_20y_reference_return": estimated_20y_reference_return,
        "payback_years": payback_years,
        "sell_price_per_kwh": site_estimate["sell_price_per_kwh"],
        "sell_price_min_per_kwh": _rule_value(rule_map, "sell_price_min_per_kwh", 5.0),
        "sell_price_max_per_kwh": _rule_value(rule_map, "sell_price_max_per_kwh", 7.0),
        "degradation_rate": site_estimate["degradation_rate"],
        "annual_generation_kwh": _rule_value(rule_map, "annual_generation_kwh", 112635),
        "average_annual_income": _rule_value(rule_map, "average_annual_income", 619494),
        "actual_built_capacity_kw": _rule_value(rule_map, "actual_built_capacity_kw", 62.335),
        "actual_annual_generation_kwh": _rule_value(rule_map, "actual_annual_generation_kwh", 78723),
        "actual_annual_revenue_twd": _rule_value(rule_map, "actual_annual_revenue_twd", 393615),
        "government_subsidy_ratio": _rule_value(rule_map, "government_subsidy_ratio", 0.50),
        "government_subsidy": _rule_value(rule_map, "government_subsidy", 2632500),
        "project_years": project_years,
        "total_20y_net_income": _rule_value(rule_map, "total_20y_net_income", 5516039),
        "target_capacity_kw": _rule_value(rule_map, "target_capacity_kw", 300),
        "target_site_count": int(_rule_value(rule_map, "target_site_count", 15)),
        "distribution_rows": distribution_rows,
        "public_notice": "試算結果是基於南寮 2026 統整版參數的初步估算，不等於正式設計、合約或投資承諾。",
        "public_guidance": [
            "先用屋頂坪數估容量與片數。",
            "再用投入金額判斷自己目前比較接近理解、評估，還是準備決策。",
            "如果要進入正式推動，仍需真人確認場址、結構、文件與合約。",
        ],
        "roof_ping": site_estimate["site_ping"],
        "roof_capacity_kwp": site_estimate["capacity_kwp"],
        "panel_count": site_estimate["panel_count"],
        "first_year_generation_kwh": site_estimate["first_year_generation_kwh"],
        "year_20_generation_kwh": site_estimate["year_20_generation_kwh"],
        "estimated_construction_cost": site_estimate["construction_cost"],
        "first_year_revenue": site_estimate["first_year_revenue"],
        "area_m2_per_kwp": site_estimate["area_m2_per_kwp"],
        "module_watt": site_estimate["module_watt"],
        "annual_generation_per_kwp": site_estimate["annual_generation_per_kwp"],
        "construction_unit_cost_per_kwp": site_estimate["construction_unit_cost_per_kwp"],
    }
