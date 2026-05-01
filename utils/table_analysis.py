import re

import pandas as pd


SECTION2_COLUMN_CANDIDATES = {
    "case_id": {
        "label": "Case ID Number",
        "candidates": ["case id", "case number", "case no", "case_id"],
        "exclude_terms": [],
    },
    "event": {
        "label": "Adverse Drug Experiences / Event Term",
        "candidates": [
            "adverse drug experiences",
            "adverse event term",
            "event term",
            "preferred term",
            "reaction term",
            "reported event",
            "pt",
        ],
        "exclude_terms": ["date", "year", "onset", "receipt", "received"],
    },
    "date_submitted": {
        "label": "Date Submitted to FDA",
        "candidates": [
            "date submitted to fda",
            "date submitted",
            "submission date",
            "date received",
            "received date",
        ],
        "exclude_terms": [],
    },
    "report_type": {
        "label": "Report Type",
        "candidates": ["report type"],
        "exclude_terms": [],
    },
    "expedited": {
        "label": "15-Day Alert / Expedited Flag",
        "candidates": ["expedited status", "expedited", "15-day", "15 day", "alert"],
        "exclude_terms": [],
    },
    "followup": {
        "label": "Follow-up Flag",
        "candidates": ["follow-up", "follow up", "followup"],
        "exclude_terms": [],
    },
    "seriousness": {
        "label": "Seriousness",
        "candidates": ["seriousness", "serious"],
        "exclude_terms": [],
    },
    "listedness": {
        "label": "Listedness",
        "candidates": ["listedness", "listed/unlisted", "listedness status"],
        "exclude_terms": [],
    },
    "causality": {
        "label": "Causality / Relatedness",
        "candidates": ["causality", "relatedness", "causal association"],
        "exclude_terms": [],
    },
    "outcome": {
        "label": "Outcome",
        "candidates": ["outcome"],
        "exclude_terms": [],
    },
    "soc": {
        "label": "System Organ Class",
        "candidates": ["soc", "system organ class"],
        "exclude_terms": [],
    },
    "country": {
        "label": "Country",
        "candidates": ["country"],
        "exclude_terms": [],
    },
}


def read_uploaded_table(uploaded_file):
    if uploaded_file is None:
        return None, None
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file), None
        return pd.read_excel(uploaded_file), None
    except Exception as e:
        return None, str(e)


def detect_column(
    df: pd.DataFrame,
    candidates: list[str],
    exclude_terms: list[str] | None = None,
):
    cols = list(df.columns)
    lower_map = {str(c).strip().lower(): c for c in cols}
    exclude_terms = [term.strip().lower() for term in (exclude_terms or [])]

    def is_allowed(column_name: str) -> bool:
        normalized = str(column_name).strip().lower()
        return not any(term in normalized for term in exclude_terms)

    for cand in candidates:
        cand_l = cand.strip().lower()
        if cand_l in lower_map and is_allowed(lower_map[cand_l]):
            return lower_map[cand_l]

    for cand in candidates:
        cand_l = cand.strip().lower()
        for c in cols:
            if cand_l in str(c).strip().lower() and is_allowed(c):
                return c

    return None


def suggest_section2_column_mapping(df: pd.DataFrame) -> dict[str, str | None]:
    if df is None or df.empty:
        return {field: None for field in SECTION2_COLUMN_CANDIDATES}

    mapping = {}
    for field, definition in SECTION2_COLUMN_CANDIDATES.items():
        mapping[field] = detect_column(
            df,
            definition["candidates"],
            exclude_terms=definition.get("exclude_terms"),
        )
    return mapping


def summarize_dataframe(df: pd.DataFrame, max_rows: int = 10) -> str:
    if df is None or df.empty:
        return "No data available."

    lines = [
        f"Total rows: {len(df)}",
        f"Columns: {list(df.columns)}",
        "",
        "Sample rows:",
    ]
    preview = df.head(max_rows)
    for _, row in preview.iterrows():
        row_text = " | ".join([f"{col}: {row[col]}" for col in preview.columns[:8]])
        lines.append(f"- {row_text}")
    return "\n".join(lines)


def compact_text(value, max_chars: int = 220) -> str:
    if pd.isna(value):
        return ""

    text = str(value)
    text = text.replace("|", "/")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def normalize_event_text(value, max_chars: int = 180) -> str:
    text = compact_text(value, max_chars=1000)
    if not text:
        return ""

    bracketed_terms = re.findall(r"\[([^\]]+)\]", text)
    if bracketed_terms:
        cleaned_terms = []
        for term in bracketed_terms:
            cleaned = compact_text(term.replace("_", " "), max_chars=80).title()
            if cleaned and cleaned not in cleaned_terms:
                cleaned_terms.append(cleaned)
        if cleaned_terms:
            return compact_text("; ".join(cleaned_terms), max_chars=max_chars)

    return compact_text(text, max_chars=max_chars)


def summarize_listedness(value) -> str:
    text = compact_text(value, max_chars=1000).lower()
    if not text:
        return ""

    has_unlisted = bool(re.search(r"\bunlisted\b", text))
    has_listed = bool(re.search(r"\blisted\b", text))
    has_unknown = bool(re.search(r"\bunknown\b", text))

    if has_unlisted and has_listed:
        return "Mixed listedness"
    if has_unlisted:
        return "Unlisted"
    if has_listed:
        return "Listed"
    if has_unknown:
        return "Unknown listedness"
    return compact_text(value, max_chars=80)


def summarize_seriousness(value) -> str:
    text = compact_text(value, max_chars=300).lower()
    if not text:
        return ""

    if "non-serious" in text or "non serious" in text:
        return "Non-serious"
    if re.search(r"\bserious\b", text) or text in {"yes", "y", "true", "1"}:
        return "Serious"
    if text in {"no", "n", "false", "0"}:
        return "Non-serious"
    return ""


def summarize_causality(value) -> str:
    text = compact_text(value, max_chars=500)
    lower_text = text.lower()
    if not text:
        return ""

    if "unlisted" in lower_text or "listed" in lower_text:
        return ""
    if "not related" in lower_text or "unrelated" in lower_text:
        return "Not related"
    if "related" in lower_text or "causal" in lower_text:
        return "Related"
    if "probable" in lower_text:
        return "Probable"
    if "possible" in lower_text:
        return "Possible"
    if len(text) > 80:
        return ""
    return text


def display_value(value: str, fallback: str = "Not available") -> str:
    return value if value else fallback


def table_value(row, column, max_chars: int = 220) -> str:
    if not column:
        return ""
    value = row.get(column, "")
    return compact_text(value, max_chars=max_chars)


def markdown_case_table(df: pd.DataFrame, columns: dict[str, str], max_rows: int = 25) -> str:
    headers = [
        "Case ID Number",
        "Adverse Drug Experiences",
        "Date Submitted to FDA",
        "Report Type",
        "ADE Evaluation",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for _, row in df.head(max_rows).iterrows():
        evaluation_parts = [
            summarize_seriousness(row.get(columns.get("seriousness"), ""))
            if columns.get("seriousness")
            else "",
            summarize_listedness(row.get(columns.get("listedness"), ""))
            if columns.get("listedness")
            else "",
            summarize_causality(row.get(columns.get("causality"), ""))
            if columns.get("causality")
            else "",
            table_value(row, columns.get("outcome"), max_chars=60),
        ]
        evaluation = "; ".join([part for part in evaluation_parts if part])
        values = [
            display_value(table_value(row, columns.get("case_id"), max_chars=40)),
            display_value(normalize_event_text(row.get(columns.get("event"), ""))),
            display_value(table_value(row, columns.get("date_submitted"), max_chars=40)),
            display_value(table_value(row, columns.get("report_type"), max_chars=60)),
            display_value(compact_text(evaluation, max_chars=160)),
        ]
        lines.append("| " + " | ".join(values) + " |")

    if len(df) > max_rows:
        lines.append(f"\nTable truncated to first {max_rows} rows for draft export.")

    return "\n".join(lines)


def normalize_column_mapping(
    df: pd.DataFrame,
    columns: dict[str, str | None] | None,
) -> dict[str, str | None]:
    if columns is None:
        return suggest_section2_column_mapping(df)

    valid_columns = set(df.columns)
    return {
        field: columns.get(field) if columns.get(field) in valid_columns else None
        for field in SECTION2_COLUMN_CANDIDATES
    }


def build_section2_case_tables(
    df: pd.DataFrame,
    columns: dict[str, str | None] | None = None,
) -> str:
    if df is None or df.empty:
        return ""

    columns = normalize_column_mapping(df, columns)

    expedited_mask = pd.Series(False, index=df.index)
    if columns["expedited"]:
        expedited_mask = df[columns["expedited"]].astype(str).str.lower().isin(
            ["yes", "y", "true", "1", "expedited"]
        )
    elif columns["report_type"]:
        expedited_mask = (
            df[columns["report_type"]]
            .astype(str)
            .str.lower()
            .str.contains("15|alert|expedited", na=False)
        )

    followup_mask = pd.Series(False, index=df.index)
    if columns["followup"]:
        followup_mask = df[columns["followup"]].astype(str).str.lower().isin(
            ["yes", "y", "true", "1", "follow-up", "follow up"]
        )
    elif columns["report_type"]:
        followup_mask = (
            df[columns["report_type"]]
            .astype(str)
            .str.lower()
            .str.contains("follow", na=False)
        )

    expedited_df = df[expedited_mask]
    followup_df = df[followup_mask]
    new_ade_df = df[~expedited_mask & ~followup_mask]

    sections = [
        ("15-Day Alert Case Table", expedited_df),
        ("New Adverse Drug Experience Case Table", new_ade_df),
        ("Follow-up Report Case Table", followup_df),
    ]

    lines = ["", "Section 2 Case Tables"]
    for title, table_df in sections:
        lines.extend(["", title])
        if table_df.empty:
            lines.append("No cases identified for this table.")
        else:
            lines.append(markdown_case_table(table_df, columns))

    return "\n".join(lines).strip()


def build_line_listing_backend_summary(
    df: pd.DataFrame,
    columns: dict[str, str | None] | None = None,
) -> str:
    if df is None or df.empty:
        return "No line listing data available."

    columns = normalize_column_mapping(df, columns)
    case_id_col = columns.get("case_id")
    event_col = columns.get("event")
    soc_col = columns.get("soc")
    seriousness_col = columns.get("seriousness")
    listedness_col = columns.get("listedness")
    causality_col = columns.get("causality")
    report_type_col = columns.get("report_type")
    expedited_col = columns.get("expedited")
    followup_col = columns.get("followup")
    outcome_col = columns.get("outcome")
    country_col = columns.get("country")

    lines = [
        f"Total number of cases: {len(df)}",
        "Detected columns:",
        f"- Case ID: {case_id_col}",
        f"- Event Term: {event_col}",
        f"- SOC: {soc_col}",
        f"- Seriousness: {seriousness_col}",
        f"- Listedness: {listedness_col}",
        f"- Causality: {causality_col}",
        f"- Report Type: {report_type_col}",
        f"- Expedited Status: {expedited_col}",
        f"- Follow-up: {followup_col}",
        f"- Outcome: {outcome_col}",
        f"- Country: {country_col}",
    ]

    expedited_df = None
    if expedited_col:
        expedited_df = df[
            df[expedited_col]
            .astype(str)
            .str.lower()
            .isin(["yes", "y", "true", "1", "expedited"])
        ]
    elif report_type_col:
        expedited_df = df[
            df[report_type_col]
            .astype(str)
            .str.lower()
            .str.contains("15|alert|expedited", na=False)
        ]

    followup_df = None
    if followup_col:
        followup_df = df[
            df[followup_col]
            .astype(str)
            .str.lower()
            .isin(["yes", "y", "true", "1", "follow-up", "follow up"])
        ]
    elif report_type_col:
        followup_df = df[
            df[report_type_col].astype(str).str.lower().str.contains("follow", na=False)
        ]

    serious_df = None
    if seriousness_col:
        serious_df = df[
            df[seriousness_col]
            .astype(str)
            .str.lower()
            .str.contains("serious|yes|y|true", na=False)
        ]

    unlisted_df = None
    if listedness_col:
        unlisted_df = df[
            df[listedness_col].astype(str).str.lower().str.contains("unlisted", na=False)
        ]

    related_df = None
    if causality_col:
        related_df = df[
            df[causality_col]
            .astype(str)
            .str.lower()
            .str.contains("related|causal", na=False)
        ]

    sur_df = df.copy()
    if seriousness_col:
        sur_df = sur_df[
            sur_df[seriousness_col]
            .astype(str)
            .str.lower()
            .str.contains("serious|yes|y|true", na=False)
        ]
    if listedness_col:
        sur_df = sur_df[
            sur_df[listedness_col].astype(str).str.lower().str.contains("unlisted", na=False)
        ]
    if causality_col:
        sur_df = sur_df[
            sur_df[causality_col]
            .astype(str)
            .str.lower()
            .str.contains("related|causal", na=False)
        ]

    lines.extend(
        [
            "",
            "Core classification summary:",
            f"- Expedited / 15-day alert cases: {len(expedited_df) if expedited_df is not None else 'Not determined'}",
            f"- Follow-up cases: {len(followup_df) if followup_df is not None else 'Not determined'}",
            f"- Serious cases: {len(serious_df) if serious_df is not None else 'Not determined'}",
            f"- Unlisted cases: {len(unlisted_df) if unlisted_df is not None else 'Not determined'}",
            f"- Related cases: {len(related_df) if related_df is not None else 'Not determined'}",
            f"- Serious unlisted related cases: {len(sur_df)}",
        ]
    )

    if outcome_col:
        fatal_df = df[
            df[outcome_col]
            .astype(str)
            .str.lower()
            .str.contains("fatal|death|died", na=False)
        ]
        lines.append(f"- Fatal cases: {len(fatal_df)}")

    if soc_col:
        lines.append("")
        lines.append("Top SOC distribution:")
        soc_counts = df[soc_col].astype(str).value_counts(dropna=False).head(10)
        for idx, val in soc_counts.items():
            lines.append(f"- {idx}: {val}")

    if event_col:
        lines.append("")
        lines.append("Top event terms:")
        event_counts = df[event_col].astype(str).value_counts(dropna=False).head(10)
        for idx, val in event_counts.items():
            lines.append(f"- {idx}: {val}")

    if len(sur_df) > 0:
        lines.append("")
        lines.append("Serious unlisted related case examples:")
        cols_to_show = [
            c
            for c in [case_id_col, event_col, soc_col, causality_col, listedness_col, outcome_col]
            if c
        ]
        sample_sur = sur_df[cols_to_show].head(8) if cols_to_show else sur_df.head(5)
        for _, row in sample_sur.iterrows():
            row_text = " | ".join([f"{col}: {row[col]}" for col in sample_sur.columns])
            lines.append(f"- {row_text}")

    return "\n".join(lines)
