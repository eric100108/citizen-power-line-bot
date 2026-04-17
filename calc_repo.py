from db import get_connection

DEFAULT_PROJECT_SLUG = "nanliao-citizen-power"
PUBLIC_VISIBILITY = ("public",)
INTERNAL_VISIBILITY = ("public", "restricted", "internal")


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
            "participation_summary": "這筆金額比較適合用來理解公民電廠參與方式、流程與風險，而不是直接對照個別案場的內部財務數字。",
            "next_step": "先查看案例與 SOP，判斷自己目前更接近哪一步。",
        }
    if ratio < 0.03:
        return {
            "participation_band": "評估參與",
            "participation_summary": "這個區間適合進一步確認你想扮演的角色，是場址提供、社區參與、還是投入更多討論與準備。",
            "next_step": "回到 SOP 對位頁，確認接下來要補哪一種資料。",
        }
    return {
        "participation_band": "準備決策",
        "participation_summary": "這個區間表示你可能已進入較具體的參與評估，但系統對外仍不會顯示南寮內部補助、分配與報酬資料。",
        "next_step": "建議直接進入 SOP 對位，並安排真人協助確認下一步。",
    }


def build_calculator_result(amount, project_slug=DEFAULT_PROJECT_SLUG):
    amount = max(amount, 0)
    fallback_settings = get_calculator_settings()
    project = get_project_summary(project_slug)
    rule_map = get_project_financial_rules_internal(project_slug)

    reference_project_budget = _rule_value(rule_map, "project_budget", fallback_settings["reference_project_budget"])
    resident_investment_ratio = _rule_value(rule_map, "resident_investment_ratio", 0.50)
    reference_resident_investment = max(reference_project_budget * resident_investment_ratio, 0)
    profile = _build_participation_profile(amount, reference_resident_investment)

    return {
        "amount": amount,
        "project_slug": project_slug,
        "project_name": project["name"] if project else "公民電廠案例",
        "community_name": project["community_name"] if project else "社區案例",
        "project_stage": project["current_stage"] if project else "規劃中",
        "project_status": project["status"] if project else "planning",
        "project_description": project["description"] if project else "這個頁面提供的是公開版參與判讀，不會直接揭露個別案場的敏感財務資訊。",
        "participation_band": profile["participation_band"],
        "participation_summary": profile["participation_summary"],
        "next_step": profile["next_step"],
        "public_notice": "頁面只提供公開版參與判讀。南寮的補助、分配、IRR 與內部財務模型仍保留在資料庫供系統比對，不直接對外顯示。",
        "public_guidance": [
            "先確認你想扮演的是理解、評估，還是準備決策的角色。",
            "再回到 SOP 對位頁，確認目前缺的是場址、補助、社區溝通，還是文件整理。",
            "若要進一步判斷，安排真人協助會比只看公開頁面更有效。",
        ],
    }
