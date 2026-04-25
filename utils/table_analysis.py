import pandas as pd


def read_uploaded_table(uploaded_file):
    if uploaded_file is None:
        return None, None
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file), None
        return pd.read_excel(uploaded_file), None
    except Exception as e:
        return None, str(e)


def detect_column(df: pd.DataFrame, candidates: list[str]):
    cols = list(df.columns)
    lower_map = {str(c).strip().lower(): c for c in cols}

    for cand in candidates:
        cand_l = cand.strip().lower()
        if cand_l in lower_map:
            return lower_map[cand_l]

    for cand in candidates:
        cand_l = cand.strip().lower()
        for c in cols:
            if cand_l in str(c).strip().lower():
                return c

    return None


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


def table_value(row, column) -> str:
    if not column:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).replace("|", "/").strip()


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
            table_value(row, columns.get("seriousness")),
            table_value(row, columns.get("listedness")),
            table_value(row, columns.get("causality")),
            table_value(row, columns.get("outcome")),
        ]
        evaluation = "; ".join([part for part in evaluation_parts if part])
        values = [
            table_value(row, columns.get("case_id")),
            table_value(row, columns.get("event")),
            table_value(row, columns.get("date_submitted")),
            table_value(row, columns.get("report_type")),
            evaluation,
        ]
        lines.append("| " + " | ".join(values) + " |")

    if len(df) > max_rows:
        lines.append(f"\nTable truncated to first {max_rows} rows for draft export.")

    return "\n".join(lines)


def build_section2_case_tables(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""

    columns = {
        "case_id": detect_column(df, ["case id", "case number", "case no", "case_id"]),
        "event": detect_column(
            df, ["event term", "adverse drug experiences", "event", "pt", "preferred term"]
        ),
        "date_submitted": detect_column(
            df,
            [
                "date submitted to fda",
                "date submitted",
                "submission date",
                "date received",
                "received date",
            ],
        ),
        "report_type": detect_column(df, ["report type"]),
        "expedited": detect_column(df, ["expedited status", "expedited"]),
        "followup": detect_column(df, ["follow-up", "follow up"]),
        "seriousness": detect_column(df, ["seriousness", "serious"]),
        "listedness": detect_column(df, ["listedness", "listed/unlisted", "listedness status"]),
        "causality": detect_column(df, ["causality", "relatedness", "causal association"]),
        "outcome": detect_column(df, ["outcome"]),
    }

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


def build_line_listing_backend_summary(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No line listing data available."

    case_id_col = detect_column(df, ["case id", "case number", "case no", "case_id"])
    event_col = detect_column(
        df, ["event term", "adverse drug experiences", "event", "pt", "preferred term"]
    )
    soc_col = detect_column(df, ["soc", "system organ class"])
    seriousness_col = detect_column(df, ["seriousness", "serious"])
    listedness_col = detect_column(df, ["listedness", "listed/unlisted", "listedness status"])
    causality_col = detect_column(df, ["causality", "relatedness", "causal association"])
    report_type_col = detect_column(df, ["report type"])
    expedited_col = detect_column(df, ["expedited status", "expedited"])
    followup_col = detect_column(df, ["follow-up", "follow up"])
    outcome_col = detect_column(df, ["outcome"])
    country_col = detect_column(df, ["country"])

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
