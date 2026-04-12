from datetime import datetime, timedelta

PROGRESS_STAGES = ["規劃中", "申請中", "施工中", "併網測試", "正式運轉"]
DEFAULT_PROGRESS_INTERVAL_DAYS = 14
STAGE_TO_STEP_CODE = {
    "規劃中": "survey",
    "申請中": "grant",
    "施工中": "construction-support",
    "併網測試": "grid-acceptance",
    "正式運轉": "operation-feedback",
}


def parse_progress_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def estimate_progress_interval_days(records_asc):
    if len(records_asc) < 2:
        return DEFAULT_PROGRESS_INTERVAL_DAYS

    deltas = []
    for previous, current in zip(records_asc, records_asc[1:]):
        previous_date = parse_progress_date(previous["updated_at"])
        current_date = parse_progress_date(current["updated_at"])
        delta_days = (current_date - previous_date).days
        if delta_days > 0:
            deltas.append(delta_days)

    if not deltas:
        return DEFAULT_PROGRESS_INTERVAL_DAYS

    return max(7, round(sum(deltas) / len(deltas)))


def build_predicted_progress(latest_record, records_asc):
    if latest_record is None or latest_record["stage"] not in PROGRESS_STAGES:
        return []

    current_index = PROGRESS_STAGES.index(latest_record["stage"])
    remaining_stages = PROGRESS_STAGES[current_index + 1:]
    if not remaining_stages:
        return []

    base_date = parse_progress_date(latest_record["updated_at"])
    interval_days = estimate_progress_interval_days(records_asc)

    predictions = []
    for offset, stage in enumerate(remaining_stages, start=1):
        predicted_date = base_date + timedelta(days=interval_days * offset)
        predictions.append({
            "stage": stage,
            "predicted_date": predicted_date.isoformat(),
            "days_after": interval_days * offset,
        })

    return predictions


def _row_to_dict(row):
    if row is None:
        return None
    return {key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row)


def build_sop_status(latest_record, service_steps):
    steps = [_row_to_dict(step) for step in service_steps]
    if not steps:
        return {
            "current_step": None,
            "completed_steps": [],
            "upcoming_steps": [],
            "completion_ratio": 0,
            "current_stage": latest_record["stage"] if latest_record else "",
        }

    step_index_by_code = {step["step_code"]: index for index, step in enumerate(steps)}

    current_index = 0
    if latest_record and latest_record["stage"] in STAGE_TO_STEP_CODE:
        mapped_code = STAGE_TO_STEP_CODE[latest_record["stage"]]
        current_index = step_index_by_code.get(mapped_code, 0)

    current_step = steps[current_index]
    completed_steps = steps[:current_index]
    upcoming_steps = steps[current_index + 1:]
    completion_ratio = round((current_index + 1) / len(steps), 4)

    return {
        "current_stage": latest_record["stage"] if latest_record else "尚未填報",
        "current_step": current_step,
        "completed_steps": completed_steps,
        "upcoming_steps": upcoming_steps,
        "completion_ratio": completion_ratio,
        "step_count": len(steps),
        "current_order": current_index + 1,
    }
