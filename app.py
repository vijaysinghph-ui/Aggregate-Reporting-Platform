import io
import streamlit as st
import pandas as pd
from datetime import date
from openai import OpenAI
from docx import Document

# =========================================================
# App Config
# =========================================================
st.set_page_config(
    page_title="Viginovix Aggregate Reporting Platform",
    layout="wide"
)

# =========================================================
# Constants
# =========================================================
REPORT_TYPES = {
    "PADER": {
        "sections": [
            {
                "id": "cover_page",
                "title": "Cover Page",
                "purpose": "Capture title page details such as report title, product, strength, NDA/ANDA number, reporting period, company details, confidentiality statement, approval date, report status, and date of report."
            },
            {
                "id": "approval_page",
                "title": "Approval Page",
                "purpose": "Capture author, medical reviewer, reviewer, and approver details with signature/date placeholders."
            },
            {
                "id": "table_of_contents",
                "title": "Table of Contents",
                "purpose": "Auto-generate the table of contents for the assembled report."
            },
            {
                "id": "introduction",
                "title": "1. Introduction",
                "purpose": "Summarize the reporting interval, product, report scope, sources of safety data, dosage forms/strengths, and any duplication disclaimer."
            },
            {
                "id": "summary_alerts_new_ades_followup",
                "title": "2. Summary of Submitted 15-Day Alerts, New Adverse Drug Experiences and New Adverse Drug Experience Follow-up",
                "purpose": "Summarize 15-day alerts, non-expedited new adverse drug experiences, follow-up reports, case tables, and overall safety interpretation."
            },
            {
                "id": "actions_taken",
                "title": "3. Actions Taken Since Last Periodic Adverse Drug Experience Report",
                "purpose": "Capture any safety-related actions, labeling changes, and references to current prescribing information or appendices."
            },
            {
                "id": "conclusion",
                "title": "4. Conclusion",
                "purpose": "Provide the overall safety conclusion and state whether the product safety profile remains unchanged or if further action is planned."
            }
        ]
    },
    "PBRER": {"sections": []},
    "DSUR": {"sections": []}
}

# =========================================================
# Helpers
# =========================================================
def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def safe_text(value) -> str:
    return "" if value is None else str(value)


def generate_ai_draft(
    section_title: str,
    section_purpose: str,
    source_data: str,
    comments: str,
    product_name: str,
    interval_start,
    interval_end,
) -> str:
    client = get_openai_client()
    if client is None:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    if not safe_text(source_data).strip():
        return "ERROR: Please provide source data before generating a draft."

    instructions = (
        "You are an expert pharmacovigilance medical writer. "
        "Draft only the requested report section in a concise, professional, regulatory style. "
        "Use only the source data provided. "
        "Do not invent facts, numbers, dates, tables, or conclusions. "
        "If information is missing, stay neutral and do not hallucinate. "
        "Do not repeat the section heading if it is already provided outside the body text. "
        "Return only the drafted section body text."
    )

    user_input = f"""
Report Type: PADER
Section Title: {section_title}
Section Purpose: {section_purpose}

Report Context:
Product Name: {product_name}
Reporting Interval Start: {interval_start}
Reporting Interval End: {interval_end}

Source Data:
{source_data}

Drafting Instructions:
{comments}
"""

    try:
        response = client.responses.create(
            model="gpt-5.4",
            instructions=instructions,
            input=user_input,
        )
        return response.output_text.strip()
    except Exception as e:
        return f"ERROR: {str(e)}"


def generate_introduction_draft(
    product_name: str,
    interval_start,
    interval_end,
    section_purpose: str,
    previous_intro_text: str,
    current_change_notes: str,
    instructions_text: str,
    report_context_text: str
) -> str:
    client = get_openai_client()
    if client is None:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    instructions = (
        "You are an expert pharmacovigilance medical writer drafting the Introduction section of a PADER. "
        "Use previous PADER introduction text only as reference, not as unquestioned truth. "
        "Always prioritize current report context and explicit user updates. "
        "Refresh the wording for the current reporting interval. "
        "Do not copy outdated statements if current change notes indicate updates. "
        "Do not invent facts. "
        "Do not repeat the section title. "
        "Return only the section body text."
    )

    user_input = f"""
Report Type: PADER
Section Title: 1. Introduction
Section Purpose: {section_purpose}

Current Report Context:
{report_context_text}

Current Reporting Interval:
Start: {interval_start}
End: {interval_end}

Reference Text from Previous PADER Introduction:
{previous_intro_text}

What Changed for Current Report:
{current_change_notes}

Drafting Instructions:
{instructions_text}
"""

    try:
        response = client.responses.create(
            model="gpt-5.4",
            instructions=instructions,
            input=user_input,
        )
        return response.output_text.strip()
    except Exception as e:
        return f"ERROR: {str(e)}"


def read_uploaded_table(uploaded_file):
    if uploaded_file is None:
        return None

    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        return pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return None


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


def summarize_line_listing(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No line listing data available."

    case_id_col = detect_column(df, ["case id", "case_id", "case number", "case no"])
    event_col = detect_column(df, ["event term", "adverse drug experiences", "event", "pt", "preferred term"])
    report_type_col = detect_column(df, ["report type"])
    seriousness_col = detect_column(df, ["seriousness", "serious"])
    expedited_col = detect_column(df, ["expedited status", "expedited"])
    followup_col = detect_column(df, ["follow-up", "follow up"])
    country_col = detect_column(df, ["country"])
    submission_date_col = detect_column(df, ["submission date", "date submitted to food and drug administration", "date submitted"])

    summary_lines = []
    summary_lines.append(f"Total number of line listing rows: {len(df)}")

    summary_lines.append("Detected columns:")
    summary_lines.append(f"- Case ID: {case_id_col}")
    summary_lines.append(f"- Event Term: {event_col}")
    summary_lines.append(f"- Report Type: {report_type_col}")
    summary_lines.append(f"- Seriousness: {seriousness_col}")
    summary_lines.append(f"- Expedited Status: {expedited_col}")
    summary_lines.append(f"- Follow-up: {followup_col}")
    summary_lines.append(f"- Country: {country_col}")
    summary_lines.append(f"- Submission Date: {submission_date_col}")

    expedited_count = None
    if expedited_col:
        expedited_count = df[df[expedited_col].astype(str).str.lower().isin(["yes", "y", "true", "1", "expedited"])].shape[0]
    elif report_type_col:
        expedited_count = df[df[report_type_col].astype(str).str.lower().str.contains("15|alert|expedited", na=False)].shape[0]

    followup_count = None
    if followup_col:
        followup_count = df[df[followup_col].astype(str).str.lower().isin(["yes", "y", "true", "1", "follow-up", "follow up"])].shape[0]
    elif report_type_col:
        followup_count = df[df[report_type_col].astype(str).str.lower().str.contains("follow", na=False)].shape[0]

    serious_count = None
    if seriousness_col:
        serious_count = df[df[seriousness_col].astype(str).str.lower().str.contains("serious|yes|y|true", na=False)].shape[0]

    non_expedited_count = None
    if expedited_count is not None:
        non_expedited_count = len(df) - expedited_count

    summary_lines.append("")
    summary_lines.append("Computed case summary:")
    summary_lines.append(f"- Total cases: {len(df)}")
    summary_lines.append(f"- Expedited / 15-day alert cases: {expedited_count if expedited_count is not None else 'Not determined'}")
    summary_lines.append(f"- Non-expedited cases: {non_expedited_count if non_expedited_count is not None else 'Not determined'}")
    summary_lines.append(f"- Follow-up cases: {followup_count if followup_count is not None else 'Not determined'}")
    summary_lines.append(f"- Serious cases: {serious_count if serious_count is not None else 'Not determined'}")

    if country_col:
        summary_lines.append("")
        summary_lines.append("Country distribution:")
        country_counts = df[country_col].astype(str).value_counts(dropna=False).head(10)
        for idx, val in country_counts.items():
            summary_lines.append(f"- {idx}: {val}")

    if event_col:
        summary_lines.append("")
        summary_lines.append("Most frequent event terms:")
        event_counts = df[event_col].astype(str).value_counts(dropna=False).head(10)
        for idx, val in event_counts.items():
            summary_lines.append(f"- {idx}: {val}")

    if case_id_col and event_col:
        summary_lines.append("")
        summary_lines.append("Sample case rows:")
        sample_df = df[[case_id_col, event_col]].head(5)
        for _, row in sample_df.iterrows():
            summary_lines.append(f"- Case ID {row[case_id_col]} | Event: {row[event_col]}")

    return "\n".join(summary_lines)


def generate_section2_draft(
    section_title: str,
    section_purpose: str,
    line_listing_summary: str,
    medical_notes: str,
    product_name: str,
    interval_start,
    interval_end
) -> str:
    client = get_openai_client()
    if client is None:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    if not safe_text(line_listing_summary).strip():
        return "ERROR: No line listing summary available."

    instructions = (
        "You are an expert pharmacovigilance medical writer drafting the PADER section "
        "'Summary of Submitted 15-Day Alerts, New Adverse Drug Experiences and New Adverse Drug Experience Follow-up'. "
        "Use only the uploaded line listing summary and user medical/regulatory notes. "
        "Do not invent counts, dates, case IDs, or conclusions. "
        "Keep 15-day alerts, new adverse drug experiences, and follow-up information clearly separated when possible. "
        "Use a formal, concise, regulatory tone. "
        "Do not repeat the section title. "
        "Return only the section body text."
    )

    user_input = f"""
Report Type: PADER
Section Title: {section_title}
Section Purpose: {section_purpose}

Current Report Context:
Product Name: {product_name}
Reporting Interval Start: {interval_start}
Reporting Interval End: {interval_end}

Structured Line Listing Summary:
{line_listing_summary}

Medical / Regulatory Notes:
{medical_notes}
"""

    try:
        response = client.responses.create(
            model="gpt-5.4",
            instructions=instructions,
            input=user_input,
        )
        return response.output_text.strip()
    except Exception as e:
        return f"ERROR: {str(e)}"


def generate_cover_page_text(
    product_name: str,
    dosage_strength: str,
    nda_anda_number: str,
    company_name: str,
    interval_start,
    interval_end,
    approval_date,
    report_status: str,
    report_date,
    confidentiality_statement: str,
    company_address: str
) -> str:
    lines = [
        "ANNUAL ADVERSE DRUG EXPERIENCE REPORT",
        f"({interval_start} to {interval_end})",
        f"{product_name}, {dosage_strength}; NDA/ANDA No. {nda_anda_number}",
        "",
        f"{company_name}",
        company_address,
        "",
        "Periodic Adverse Drug Experience Report",
        "A report for the United States Food and Drug Administration",
        "",
        f"Approval Date: {approval_date}",
        f"Review Period: {interval_start} to {interval_end}",
        f"Report Status: {report_status}",
        f"Date of Report: {report_date}",
        "",
        confidentiality_statement
    ]
    return "\n".join(lines)


def generate_approval_page_text(
    product_name: str,
    interval_start,
    interval_end,
    author_name: str,
    author_designation: str,
    medical_reviewer_name: str,
    medical_reviewer_designation: str,
    reviewer_name: str,
    reviewer_designation: str,
    approver_name: str,
    approver_designation: str,
    company_name: str
) -> str:
    lines = [
        f"Product: {product_name}",
        f"Reporting Interval: {interval_start} to {interval_end}",
        "",
        "Author:",
        f"Name: {author_name}",
        f"Designation: {author_designation}",
        f"For: {company_name}",
        "Signature: ____________________",
        "Date: ____________________",
        "",
        "Medical Reviewer:",
        f"Name: {medical_reviewer_name}",
        f"Designation: {medical_reviewer_designation}",
        f"For: {company_name}",
        "Signature: ____________________",
        "Date: ____________________",
        "",
        "Reviewed by:",
        f"Name: {reviewer_name}",
        f"Designation: {reviewer_designation}",
        f"For: {company_name}",
        "Signature: ____________________",
        "Date: ____________________",
        "",
        "Approved by:",
        f"Name: {approver_name}",
        f"Designation: {approver_designation}",
        f"For: {company_name}",
        "Signature: ____________________",
        "Date: ____________________",
    ]
    return "\n".join(lines)


def generate_toc_text(sections: list[dict]) -> str:
    toc_lines = []
    for section in sections:
        if section["id"] == "cover_page":
            continue
        toc_lines.append(section["title"])
    return "\n".join(toc_lines)


def assemble_full_report(
    product_name: str,
    interval_start,
    interval_end,
    report_owner: str,
    sections: list[dict]
) -> str:
    report_parts = []

    report_parts.append("ANNUAL ADVERSE DRUG EXPERIENCE REPORT")
    report_parts.append(f"Product: {product_name}")
    report_parts.append(f"Review Period: {interval_start} to {interval_end}")
    report_parts.append(f"Report Owner: {report_owner}")
    report_parts.append("\n" + "=" * 80 + "\n")

    for section in sections:
        section_title = section["title"]
        draft_key = f"draft_{section['id']}"
        section_text = safe_text(st.session_state.get(draft_key, "")).strip()

        if not section_text:
            section_text = "[No draft available for this section yet.]"

        report_parts.append(section_title)
        report_parts.append(section_text)
        report_parts.append("\n" + "-" * 80 + "\n")

    return "\n".join(report_parts)


def export_report_to_word(full_report_text: str) -> bytes:
    doc = Document()
    lines = full_report_text.splitlines()

    for line in lines:
        stripped = line.strip()

        if not stripped:
            doc.add_paragraph("")
        elif stripped == "ANNUAL ADVERSE DRUG EXPERIENCE REPORT":
            doc.add_heading(stripped, level=0)
        elif stripped in [
            "Cover Page",
            "Approval Page",
            "Table of Contents",
            "1. Introduction",
            "2. Summary of Submitted 15-Day Alerts, New Adverse Drug Experiences and New Adverse Drug Experience Follow-up",
            "3. Actions Taken Since Last Periodic Adverse Drug Experience Report",
            "4. Conclusion",
        ]:
            doc.add_heading(stripped, level=1)
        else:
            doc.add_paragraph(line)

    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()

# =========================================================
# Main UI
# =========================================================
st.title("Viginovix Aggregate Reporting Platform")
st.write("Prototype: AI-assisted aggregate report authoring and review")

st.header("Step 1: Select Report Type")

report_type = st.selectbox(
    "Choose Report Type",
    ["Select...", "PADER", "PBRER", "DSUR"]
)

if report_type == "PADER":
    st.success("PADER selected. Sections will load below.")

    # -----------------------------------------------------
    # Step 2: Report Setup
    # -----------------------------------------------------
    st.header("Step 2: Report Setup")

    col1, col2 = st.columns(2)

    with col1:
        product_name = st.text_input("Product Name")
        nda_anda_number = st.text_input("NDA / ANDA Number")
        approval_date = st.date_input("Approval Date", value=date.today())
        company_name = st.text_input("Company Name")
        dosage_strength = st.text_input("Dosage Form / Strength")
        company_address = st.text_area("Company Address", height=100)

    with col2:
        interval_start = st.date_input("Reporting Interval Start Date", value=date.today())
        interval_end = st.date_input("Reporting Interval End Date", value=date.today())
        data_lock_point = st.date_input("Data Lock Point", value=date.today())
        region = st.selectbox("Region", ["US", "EU", "UK", "Global"])
        template_version = st.text_input("Template Version", value="v1.0")
        report_owner = st.text_input("Report Owner")
        report_status = st.selectbox("Report Status", ["Annual", "Quarterly"])

    report_date = st.date_input("Date of Report", value=date.today())
    confidentiality_statement = st.text_area(
        "Confidentiality Statement",
        value="This document is a confidential communication. Acceptance of this document constitutes an agreement by the recipient that no unpublished information contained herein will be published or disclosed without prior written approval.",
        height=100
    )

    st.subheader("Report Setup Summary")
    st.write(f"**Product Name:** {product_name}")
    st.write(f"**NDA / ANDA Number:** {nda_anda_number}")
    st.write(f"**Approval Date:** {approval_date}")
    st.write(f"**Company Name:** {company_name}")
    st.write(f"**Dosage Form / Strength:** {dosage_strength}")
    st.write(f"**Interval Start:** {interval_start}")
    st.write(f"**Interval End:** {interval_end}")
    st.write(f"**Data Lock Point:** {data_lock_point}")
    st.write(f"**Region:** {region}")
    st.write(f"**Template Version:** {template_version}")
    st.write(f"**Report Owner:** {report_owner}")
    st.write(f"**Report Status:** {report_status}")
    st.write(f"**Date of Report:** {report_date}")

    # -----------------------------------------------------
    # Approval workflow fields
    # -----------------------------------------------------
    st.header("Approval Workflow Details")

    a1, a2 = st.columns(2)
    with a1:
        author_name = st.text_input("Author Name")
        author_designation = st.text_input("Author Designation")
        medical_reviewer_name = st.text_input("Medical Reviewer Name")
        medical_reviewer_designation = st.text_input("Medical Reviewer Designation")
    with a2:
        reviewer_name = st.text_input("Reviewer Name")
        reviewer_designation = st.text_input("Reviewer Designation")
        approver_name = st.text_input("Approver Name")
        approver_designation = st.text_input("Approver Designation")

    # -----------------------------------------------------
    # Step 3: PADER Sections
    # -----------------------------------------------------
    st.header("Step 3: PADER Sections")

    pader_sections = REPORT_TYPES["PADER"]["sections"]

    for section in pader_sections:
        with st.expander(section["title"]):
            st.write(f"**Purpose:** {section['purpose']}")

            # Cover Page
            if section["id"] == "cover_page":
                if st.button("Generate Cover Page", key="btn_cover_page"):
                    st.session_state["draft_cover_page"] = generate_cover_page_text(
                        product_name=product_name,
                        dosage_strength=dosage_strength,
                        nda_anda_number=nda_anda_number,
                        company_name=company_name,
                        interval_start=interval_start,
                        interval_end=interval_end,
                        approval_date=approval_date,
                        report_status=report_status,
                        report_date=report_date,
                        confidentiality_statement=confidentiality_statement,
                        company_address=company_address
                    )

                st.text_area(
                    "Draft Output for Cover Page",
                    key="draft_cover_page",
                    height=280
                )

            # Approval Page
            elif section["id"] == "approval_page":
                if st.button("Generate Approval Page", key="btn_approval_page"):
                    st.session_state["draft_approval_page"] = generate_approval_page_text(
                        product_name=product_name,
                        interval_start=interval_start,
                        interval_end=interval_end,
                        author_name=author_name,
                        author_designation=author_designation,
                        medical_reviewer_name=medical_reviewer_name,
                        medical_reviewer_designation=medical_reviewer_designation,
                        reviewer_name=reviewer_name,
                        reviewer_designation=reviewer_designation,
                        approver_name=approver_name,
                        approver_designation=approver_designation,
                        company_name=company_name
                    )

                st.text_area(
                    "Draft Output for Approval Page",
                    key="draft_approval_page",
                    height=320
                )

            # TOC
            elif section["id"] == "table_of_contents":
                if st.button("Generate Table of Contents", key="btn_table_of_contents"):
                    st.session_state["draft_table_of_contents"] = generate_toc_text(pader_sections)

                st.text_area(
                    "Draft Output for Table of Contents",
                    key="draft_table_of_contents",
                    height=220
                )

            # Introduction
            elif section["id"] == "introduction":
                st.subheader("Current Report Context")

                intro_context = f"""
Product Name: {product_name}
NDA / ANDA Number: {nda_anda_number}
Approval Date: {approval_date}
Company Name: {company_name}
Dosage Form / Strength: {dosage_strength}
Reporting Interval Start: {interval_start}
Reporting Interval End: {interval_end}
Region: {region}
Report Status: {report_status}
"""

                st.text_area(
                    "Current Report Context (editable reference)",
                    value=intro_context,
                    key="intro_report_context",
                    height=180
                )

                st.subheader("Upload Previous PADER (optional)")
                st.file_uploader(
                    "Upload Previous PADER (PDF or DOCX) - placeholder for future extraction workflow",
                    type=["pdf", "docx"],
                    key="previous_pader_upload"
                )

                st.subheader("Extracted Prior Introduction / Reference Text")
                previous_intro_text = st.text_area(
                    "Paste extracted or reference text from previous PADER Introduction",
                    key="previous_intro_text",
                    height=220
                )

                st.subheader("What Changed for Current Report?")
                current_change_notes = st.text_area(
                    "Describe what changed from the previous PADER",
                    key="intro_change_notes",
                    height=120
                )

                st.subheader("Drafting Instructions")
                intro_comments = st.text_area(
                    "Instructions for drafting the Introduction",
                    key="comment_introduction",
                    height=120
                )

                if st.button("Generate Draft for 1. Introduction", key="btn_introduction"):
                    with st.spinner("Generating AI draft for Introduction..."):
                        draft_text = generate_introduction_draft(
                            product_name=product_name,
                            interval_start=interval_start,
                            interval_end=interval_end,
                            section_purpose=section["purpose"],
                            previous_intro_text=previous_intro_text,
                            current_change_notes=current_change_notes,
                            instructions_text=intro_comments,
                            report_context_text=st.session_state.get("intro_report_context", intro_context)
                        )
                        st.session_state["draft_introduction"] = draft_text

                st.text_area(
                    "Draft Output for 1. Introduction",
                    key="draft_introduction",
                    height=260
                )

            # Section 2
            elif section["id"] == "summary_alerts_new_ades_followup":
                st.subheader("Upload PADER Line Listing")

                uploaded_file = st.file_uploader(
                    "Upload PADER Line Listing (Excel or CSV)",
                    type=["xlsx", "csv"],
                    key="line_listing_upload"
                )

                if uploaded_file is not None:
                    df = read_uploaded_table(uploaded_file)
                    if df is not None:
                        st.session_state["line_listing_df"] = df
                        st.success("Line listing uploaded successfully.")

                df = st.session_state.get("line_listing_df", None)

                st.subheader("Expected Columns")
                st.write(
                    "- Case ID\n"
                    "- Event Term\n"
                    "- Receipt Date\n"
                    "- Submission Date\n"
                    "- Report Type\n"
                    "- Seriousness\n"
                    "- Expedited Status\n"
                    "- Follow-up\n"
                    "- Country\n"
                    "- Case Evaluation"
                )

                if df is not None:
                    st.subheader("Preview of Uploaded Line Listing")
                    st.dataframe(df.head(10), use_container_width=True)

                    st.subheader("Auto-Generated Case Summary")
                    summary_text = summarize_line_listing(df)
                    st.text_area(
                        "Line Listing Summary Used for Drafting",
                        value=summary_text,
                        key="line_listing_summary",
                        height=300
                    )

                st.subheader("Medical / Regulatory Notes")
                medical_notes = st.text_area(
                    "Enter interpretation notes or drafting guidance",
                    key="section2_medical_notes",
                    height=120
                )

                if st.button(
                    "Generate Draft for 2. Summary of Submitted 15-Day Alerts, New Adverse Drug Experiences and New Adverse Drug Experience Follow-up",
                    key="btn_summary_alerts_new_ades_followup"
                ):
                    df = st.session_state.get("line_listing_df", None)
                    if df is None:
                        st.error("Please upload a line listing file first.")
                    else:
                        with st.spinner("Generating AI draft for Section 2..."):
                            summary_text = st.session_state.get("line_listing_summary", summarize_line_listing(df))
                            draft_text = generate_section2_draft(
                                section_title=section["title"],
                                section_purpose=section["purpose"],
                                line_listing_summary=summary_text,
                                medical_notes=medical_notes,
                                product_name=product_name,
                                interval_start=interval_start,
                                interval_end=interval_end
                            )
                            st.session_state["draft_summary_alerts_new_ades_followup"] = draft_text

                st.text_area(
                    "Draft Output for Section 2",
                    key="draft_summary_alerts_new_ades_followup",
                    height=260
                )

            # Remaining standard sections
            else:
                source_data = st.text_area(
                    f"Source Data for {section['title']}",
                    key=f"source_{section['id']}",
                    height=180
                )

                comments = st.text_area(
                    f"Comments / Drafting Instructions for {section['title']}",
                    key=f"comment_{section['id']}",
                    height=100
                )

                if st.button(f"Generate Draft for {section['title']}", key=f"btn_{section['id']}"):
                    with st.spinner("Generating AI draft..."):
                        draft_text = generate_ai_draft(
                            section_title=section["title"],
                            section_purpose=section["purpose"],
                            source_data=source_data,
                            comments=comments,
                            product_name=product_name,
                            interval_start=interval_start,
                            interval_end=interval_end
                        )
                        st.session_state[f"draft_{section['id']}"] = draft_text

                st.text_area(
                    f"Draft Output for {section['title']}",
                    key=f"draft_{section['id']}",
                    height=220
                )

    # -----------------------------------------------------
    # Step 4: Assemble Full Report
    # -----------------------------------------------------
    st.header("Step 4: Assemble Full Report")

    if st.button("Assemble Full PADER Report"):
        full_report = assemble_full_report(
            product_name=product_name,
            interval_start=interval_start,
            interval_end=interval_end,
            report_owner=report_owner,
            sections=pader_sections
        )
        st.session_state["full_pader_report"] = full_report

    st.text_area(
        "Full PADER Report Output",
        key="full_pader_report",
        height=600
    )

    # -----------------------------------------------------
    # Step 5: Export
    # -----------------------------------------------------
    st.header("Step 5: Export")

    full_report_text = st.session_state.get("full_pader_report", "")
    if full_report_text:
        docx_bytes = export_report_to_word(full_report_text)
        st.download_button(
            label="Download Full PADER Report as Word",
            data=docx_bytes,
            file_name="PADER_Report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        st.info("Assemble the full report first to enable Word export.")

elif report_type in ["PBRER", "DSUR"]:
    st.info(f"{report_type} module coming soon.")
