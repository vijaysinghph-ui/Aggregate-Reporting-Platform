from datetime import date

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from config.report_types import REPORT_TYPES
from services.ai_service import (
    generate_actions_taken_draft,
    generate_ai_draft,
    generate_introduction_draft,
    generate_section2_draft,
    get_openai_client,
)
from services.report_builder import (
    assemble_full_report,
    export_report_to_word,
    generate_approval_page_text,
    generate_cover_page_text,
    generate_toc_text,
)
from utils.file_extraction import extract_reference_text
from utils.table_analysis import (
    build_line_listing_backend_summary,
    build_section2_case_tables,
    read_uploaded_table,
    summarize_dataframe,
)


st.set_page_config(
    page_title="Viginovix Aggregate Reporting Platform",
    layout="wide",
)

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


def get_secret_value(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except StreamlitSecretNotFoundError:
        return default


def get_drafts_for_sections(sections: list[dict]) -> dict[str, str]:
    return {
        section["id"]: st.session_state.get(f"draft_{section['id']}", "")
        for section in sections
    }


def read_table_or_show_error(uploaded_file):
    df, error = read_uploaded_table(uploaded_file)
    if error:
        st.error(f"Error reading file: {error}")
    return df


def detect_uploaded_column(df, candidates: list[str], exclude_terms: list[str] | None = None):
    column_lookup = {str(column).strip().lower(): column for column in df.columns}
    exclude_terms = [term.strip().lower() for term in (exclude_terms or [])]

    def is_allowed(column_name) -> bool:
        normalized = str(column_name).strip().lower()
        return not any(term in normalized for term in exclude_terms)

    for candidate in candidates:
        normalized_candidate = candidate.strip().lower()
        if normalized_candidate in column_lookup and is_allowed(column_lookup[normalized_candidate]):
            return column_lookup[normalized_candidate]

    for candidate in candidates:
        normalized_candidate = candidate.strip().lower()
        for column in df.columns:
            if normalized_candidate in str(column).strip().lower() and is_allowed(column):
                return column

    return None


def suggest_section2_column_mapping(df) -> dict[str, object | None]:
    return {
        field: detect_uploaded_column(
            df,
            definition["candidates"],
            exclude_terms=definition.get("exclude_terms"),
        )
        for field, definition in SECTION2_COLUMN_CANDIDATES.items()
    }


def build_section2_summary(df, mapping: dict[str, object | None]) -> str:
    try:
        return build_line_listing_backend_summary(df, mapping)
    except TypeError:
        return build_line_listing_backend_summary(df)


def build_section2_tables(df, mapping: dict[str, object | None]) -> str:
    try:
        return build_section2_case_tables(df, mapping)
    except TypeError:
        return build_section2_case_tables(df)


def extract_uploaded_source_text(uploaded_file, label: str) -> str:
    if uploaded_file is None:
        return ""

    extracted_text = extract_reference_text(uploaded_file)
    if extracted_text:
        st.success(f"{label} uploaded and text extracted successfully.")
        with st.expander(f"Preview extracted text from {uploaded_file.name}"):
            st.text_area(
                "Extracted Text Preview",
                value=extracted_text[:4000],
                height=220,
                disabled=True,
                key=f"preview_{label}_{uploaded_file.name}",
            )
    else:
        st.warning(
            f"No extractable text was found in {uploaded_file.name}. "
            "If this is a scanned PDF, OCR will be needed before the AI can read it."
        )
    return extracted_text


def render_report_setup():
    st.header("Step 2: Report Setup")

    col1, col2 = st.columns(2)
    with col1:
        product_name = st.text_input("Product Name", key="product_name")
        nda_anda_number = st.text_input("NDA / ANDA Number", key="nda_anda_number")
        approval_date = st.date_input("Approval Date", value=date.today(), key="approval_date")
        dosage_strength = st.text_input("Dosage Form / Strength", key="dosage_strength")
        company_name = st.text_input("Company Name", key="company_name")
        company_address = st.text_area("Company Address", key="company_address", height=90)
    with col2:
        interval_start = st.date_input("Reporting Interval Start", value=date.today(), key="interval_start")
        interval_end = st.date_input("Reporting Interval End", value=date.today(), key="interval_end")
        data_lock_point = st.date_input("Data Lock Point", value=date.today(), key="data_lock_point")
        report_date = st.date_input("Date of Report", value=date.today(), key="report_date")
        region = st.selectbox("Region", ["US", "EU", "Global", "Other"], key="region")
        report_status = st.selectbox("Report Status", ["Annual", "Quarterly", "Other"], key="report_status")
        report_status_other = ""
        if report_status == "Other":
            report_status_other = st.text_input("Other Report Status", key="report_status_other")

    report_owner = st.text_input("Report Owner", key="report_owner")
    confidentiality_statement = st.text_area(
        "Confidentiality Statement",
        key="confidentiality_statement",
        value=(
            "This document is confidential and intended solely for regulatory review. "
            "It should not be copied or distributed without authorization."
        ),
        height=90,
    )

    st.subheader("Document Signatories")
    s1, s2 = st.columns(2)
    with s1:
        author_name = st.text_input("Author Name", key="author_name")
        author_designation = st.text_input("Author Designation", key="author_designation")
        medical_reviewer_name = st.text_input("Medical Reviewer Name", key="medical_reviewer_name")
        medical_reviewer_designation = st.text_input(
            "Medical Reviewer Designation",
            key="medical_reviewer_designation",
        )
    with s2:
        reviewer_name = st.text_input("Reviewer Name", key="reviewer_name")
        reviewer_designation = st.text_input("Reviewer Designation", key="reviewer_designation")
        approver_name = st.text_input("Approver Name", key="approver_name")
        approver_designation = st.text_input("Approver Designation", key="approver_designation")

    context = {
        "product_name": product_name,
        "nda_anda_number": nda_anda_number,
        "approval_date": approval_date,
        "dosage_strength": dosage_strength,
        "company_name": company_name,
        "company_address": company_address,
        "interval_start": interval_start,
        "interval_end": interval_end,
        "data_lock_point": data_lock_point,
        "report_date": report_date,
        "region": region,
        "report_status": report_status,
        "report_status_other": report_status_other,
        "report_owner": report_owner,
        "confidentiality_statement": confidentiality_statement,
    }
    approval_context = {
        "author_name": author_name,
        "author_designation": author_designation,
        "medical_reviewer_name": medical_reviewer_name,
        "medical_reviewer_designation": medical_reviewer_designation,
        "reviewer_name": reviewer_name,
        "reviewer_designation": reviewer_designation,
        "approver_name": approver_name,
        "approver_designation": approver_designation,
    }
    return context, approval_context


def render_cover_page(context: dict):
    if st.button("Generate Cover Page", key="btn_cover_page"):
        st.session_state["draft_cover_page"] = generate_cover_page_text(
            product_name=context["product_name"],
            dosage_strength=context["dosage_strength"],
            nda_anda_number=context["nda_anda_number"],
            company_name=context["company_name"],
            interval_start=context["interval_start"],
            interval_end=context["interval_end"],
            approval_date=context["approval_date"],
            report_status=context["report_status"],
            report_status_other=context["report_status_other"],
            report_date=context["report_date"],
            confidentiality_statement=context["confidentiality_statement"],
            company_address=context["company_address"],
        )

    st.text_area("Draft Output for Cover Page", key="draft_cover_page", height=280)


def render_approval_page(context: dict, approval_context: dict):
    if st.button("Generate Approval Page", key="btn_approval_page"):
        st.session_state["draft_approval_page"] = generate_approval_page_text(
            product_name=context["product_name"],
            interval_start=context["interval_start"],
            interval_end=context["interval_end"],
            author_name=approval_context["author_name"],
            author_designation=approval_context["author_designation"],
            medical_reviewer_name=approval_context["medical_reviewer_name"],
            medical_reviewer_designation=approval_context["medical_reviewer_designation"],
            reviewer_name=approval_context["reviewer_name"],
            reviewer_designation=approval_context["reviewer_designation"],
            approver_name=approval_context["approver_name"],
            approver_designation=approval_context["approver_designation"],
            company_name=context["company_name"],
        )

    st.text_area("Draft Output for Approval Page", key="draft_approval_page", height=320)


def render_table_of_contents(pader_sections: list[dict]):
    if st.button("Generate Table of Contents", key="btn_table_of_contents"):
        st.session_state["draft_table_of_contents"] = generate_toc_text(pader_sections)

    st.text_area("Draft Output for Table of Contents", key="draft_table_of_contents", height=220)


def render_introduction(context: dict, client):
    previous_pader_file = st.file_uploader(
        "Upload Previous PADER (optional)",
        type=["pdf", "docx", "txt"],
        key="previous_pader_upload",
    )
    label_file = st.file_uploader(
        "Upload Current Label / RSI",
        type=["pdf", "docx", "txt"],
        key="label_upload",
    )

    if st.button("Generate Introduction", key="btn_introduction"):
        with st.spinner("Generating Introduction..."):
            previous_pader_text = extract_reference_text(previous_pader_file)
            label_text = extract_reference_text(label_file)
            report_context_text = f"""
Product Name: {context["product_name"]}
NDA / ANDA Number: {context["nda_anda_number"]}
Approval Date: {context["approval_date"]}
Company Name: {context["company_name"]}
Dosage Form / Strength: {context["dosage_strength"]}
Reporting Interval Start: {context["interval_start"]}
Reporting Interval End: {context["interval_end"]}
Region: {context["region"]}
Report Status: {context["report_status_other"] if context["report_status"] == "Other" and context["report_status_other"] else context["report_status"]}
"""
            if not previous_pader_text and not label_text:
                st.warning(
                    "No extractable text was found from the uploaded files. "
                    "If these are scanned PDFs, this prototype may not extract them reliably."
                )
            st.session_state["draft_introduction"] = generate_introduction_draft(
                client=client,
                report_context_text=report_context_text,
                previous_pader_text=previous_pader_text,
                label_text=label_text,
                report_status=context["report_status"],
                report_status_other=context["report_status_other"],
            )

    st.text_area("Draft Output for 1. Introduction", key="draft_introduction", height=260)


def get_section2_mapping_from_state(df) -> dict[str, object | None]:
    column_lookup = {str(column): column for column in df.columns}
    mapping = {}
    for field in SECTION2_COLUMN_CANDIDATES:
        selected = st.session_state.get(f"section2_mapping_{field}", "Not mapped")
        mapping[field] = column_lookup.get(selected)
    return mapping


def render_section2_column_mapping(df) -> dict[str, object | None]:
    st.subheader("Column Mapping")
    st.caption(
        "Confirm how the uploaded line listing columns map to the PADER Section 2 fields. "
        "Auto-detected values can be corrected before generation."
    )

    defaults = suggest_section2_column_mapping(df)
    options = ["Not mapped"] + [str(column) for column in df.columns]
    fields = list(SECTION2_COLUMN_CANDIDATES.items())
    columns = st.columns(2)

    for index, (field, definition) in enumerate(fields):
        key = f"section2_mapping_{field}"
        default_column = defaults.get(field)
        default_value = str(default_column) if str(default_column) in options else "Not mapped"
        if st.session_state.get(key) not in options:
            st.session_state[key] = default_value
        with columns[index % 2]:
            st.selectbox(definition["label"], options, key=key)

    mapping = get_section2_mapping_from_state(df)
    missing_core_fields = [
        SECTION2_COLUMN_CANDIDATES[field]["label"]
        for field in ["case_id", "event"]
        if not mapping.get(field)
    ]
    if missing_core_fields:
        st.warning(
            "Please map these core fields for a better Section 2 table: "
            + ", ".join(missing_core_fields)
        )
    return mapping


def render_section_2(context: dict, client):
    uploaded_file = st.file_uploader(
        "Upload PADER Line Listing or Source File",
        type=["xlsx", "csv", "pdf", "docx", "txt"],
        key="line_listing_upload",
    )

    section2_mapping = None
    if uploaded_file is not None:
        filename = uploaded_file.name.lower()
        if filename.endswith((".xlsx", ".csv")):
            df = read_table_or_show_error(uploaded_file)
            if df is not None:
                st.session_state["line_listing_df"] = df
                st.session_state["line_listing_source_text"] = ""
                mapping_signature = (
                    f"{uploaded_file.name}:{len(df)}:"
                    + "|".join([str(column) for column in df.columns])
                )
                if st.session_state.get("line_listing_mapping_signature") != mapping_signature:
                    for field in SECTION2_COLUMN_CANDIDATES:
                        st.session_state.pop(f"section2_mapping_{field}", None)
                    st.session_state["line_listing_mapping_signature"] = mapping_signature
                st.success("Line listing uploaded successfully.")
                st.dataframe(df.head(10), use_container_width=True)
                section2_mapping = render_section2_column_mapping(df)
        else:
            source_text = extract_uploaded_source_text(uploaded_file, "Section 2 source file")
            st.session_state["line_listing_df"] = None
            st.session_state["line_listing_source_text"] = source_text

    if st.button("Generate Section 2", key="btn_summary_alerts_new_ades_followup"):
        df = st.session_state.get("line_listing_df", None)
        source_text = st.session_state.get("line_listing_source_text", "")
        if df is None and not source_text:
            st.error("Please upload a line listing or source PDF/DOCX/TXT file first.")
        else:
            with st.spinner("Generating Section 2..."):
                if df is not None:
                    section2_mapping = section2_mapping or get_section2_mapping_from_state(df)
                backend_summary = (
                    build_section2_summary(df, section2_mapping)
                    if df is not None
                    else source_text[:12000]
                )
                draft_text = generate_section2_draft(
                    client=client,
                    product_name=context["product_name"],
                    interval_start=context["interval_start"],
                    interval_end=context["interval_end"],
                    line_listing_summary=backend_summary,
                )
                case_tables = (
                    build_section2_tables(df, section2_mapping)
                    if df is not None
                    else ""
                )
                if case_tables:
                    draft_text = f"{draft_text}\n\n{case_tables}"
                st.session_state["draft_summary_alerts_new_ades_followup"] = draft_text

    st.text_area(
        "Draft Output for Section 2",
        key="draft_summary_alerts_new_ades_followup",
        height=320,
    )


def render_actions_taken(context: dict, client):
    st.caption(
        "Upload the current-period regulatory actions source as Excel/CSV or as a searchable "
        "PDF/DOCX/TXT file."
    )
    regulatory_actions_file = st.file_uploader(
        "Upload Regulatory Actions File for Section 3",
        type=["xlsx", "csv", "pdf", "docx", "txt"],
        key="regulatory_actions_upload",
    )

    if regulatory_actions_file is not None:
        filename = regulatory_actions_file.name.lower()
        if filename.endswith((".xlsx", ".csv")):
            reg_df = read_table_or_show_error(regulatory_actions_file)
            if reg_df is not None:
                st.session_state["regulatory_actions_df"] = reg_df
                st.session_state["regulatory_actions_source_text"] = ""
                st.success("Regulatory actions file uploaded successfully.")
                st.dataframe(reg_df.head(10), use_container_width=True)
        else:
            source_text = extract_uploaded_source_text(
                regulatory_actions_file,
                "Regulatory actions source file",
            )
            st.session_state["regulatory_actions_df"] = None
            st.session_state["regulatory_actions_source_text"] = source_text

    if st.button("Generate Section 3", key="btn_actions_taken"):
        reg_df = st.session_state.get("regulatory_actions_df", None)
        source_text = st.session_state.get("regulatory_actions_source_text", "")
        if reg_df is None and not source_text:
            draft_text = (
                "No actions related to safety, labeling, or regulatory authority decisions "
                "were identified during the reporting interval."
            )
        else:
            reg_summary = (
                summarize_dataframe(reg_df, max_rows=8)
                if reg_df is not None
                else source_text[:12000]
            )
            draft_text = generate_actions_taken_draft(
                client=client,
                regulatory_actions_summary=reg_summary,
                product_name=context["product_name"],
                interval_start=context["interval_start"],
                interval_end=context["interval_end"],
            )
        st.session_state["draft_actions_taken"] = draft_text

    st.text_area(
        "Draft Output for 3. Actions Taken Since Last Periodic Adverse Drug Experience Report",
        key="draft_actions_taken",
        height=260,
    )


def render_conclusion(context: dict, client):
    comments = st.text_area(
        "Comments / Drafting Instructions for 4. Conclusion",
        key="comment_conclusion",
        height=120,
        placeholder=(
            "Example: No new safety concerns were identified during the reporting period; "
            "the benefit-risk profile remains unchanged."
        ),
    )

    if st.button("Generate Draft for 4. Conclusion", key="btn_conclusion"):
        with st.spinner("Generating Conclusion..."):
            conclusion_context = f"""
Product Name: {context["product_name"]}
Reporting Interval Start: {context["interval_start"]}
Reporting Interval End: {context["interval_end"]}
"""
            st.session_state["draft_conclusion"] = generate_ai_draft(
                client=client,
                section_title="4. Conclusion",
                section_purpose=(
                    "Provide the overall safety conclusion and state whether the product "
                    "safety profile remains unchanged or if further action is planned."
                ),
                source_data=conclusion_context,
                comments=comments,
                product_name=context["product_name"],
                interval_start=context["interval_start"],
                interval_end=context["interval_end"],
            )

    st.text_area("Draft Output for 4. Conclusion", key="draft_conclusion", height=220)


def render_pader_sections(context: dict, approval_context: dict, client):
    st.header("Step 3: PADER Sections")
    pader_sections = REPORT_TYPES["PADER"]["sections"]

    for section in pader_sections:
        with st.expander(section["title"]):
            st.write(f"**Purpose:** {section['purpose']}")
            if section["id"] == "cover_page":
                render_cover_page(context)
            elif section["id"] == "approval_page":
                render_approval_page(context, approval_context)
            elif section["id"] == "table_of_contents":
                render_table_of_contents(pader_sections)
            elif section["id"] == "introduction":
                render_introduction(context, client)
            elif section["id"] == "summary_alerts_new_ades_followup":
                render_section_2(context, client)
            elif section["id"] == "actions_taken":
                render_actions_taken(context, client)
            elif section["id"] == "conclusion":
                render_conclusion(context, client)

    return pader_sections


def render_assembly_and_export(context: dict, pader_sections: list[dict]):
    st.header("Step 4: Generate Full PADER Report")
    st.caption(
        "Generate a complete draft from the current section outputs. "
        "Authors can edit section text above and refresh the full draft."
    )

    if st.button("Generate / Refresh Full PADER Report"):
        st.session_state["full_pader_report"] = assemble_full_report(
            product_name=context["product_name"],
            interval_start=context["interval_start"],
            interval_end=context["interval_end"],
            report_owner=context["report_owner"],
            sections=pader_sections,
            drafts=get_drafts_for_sections(pader_sections),
        )
        st.success("Full PADER report draft generated.")

    st.text_area(
        "Full PADER Report Output",
        key="full_pader_report",
        height=600,
    )

    full_report_text = st.session_state.get("full_pader_report", "")
    if full_report_text:
        draft_docx = export_report_to_word(full_report_text)
        st.download_button(
            label="Download Draft PADER Report as Word",
            data=draft_docx,
            file_name="Draft_PADER_Report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        st.info("Generate the full PADER report to preview and download the draft.")


def render_pader_app():
    context, approval_context = render_report_setup()
    client = get_openai_client(get_secret_value("OPENAI_API_KEY"))
    pader_sections = render_pader_sections(context, approval_context, client)
    render_assembly_and_export(context, pader_sections)


def main():
    st.title("Viginovix Aggregate Reporting Platform")
    st.write("Prototype: AI-assisted PADER authoring and Word draft generation")

    st.header("Step 1: Select Report Type")
    report_type = st.selectbox("Choose Report Type", ["Select...", "PADER", "PBRER", "DSUR"])

    if report_type == "PADER":
        render_pader_app()
    elif report_type in ["PBRER", "DSUR"]:
        st.info(f"{report_type} module coming soon.")


if __name__ == "__main__":
    main()
