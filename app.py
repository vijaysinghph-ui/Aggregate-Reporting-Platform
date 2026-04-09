import streamlit as st
from datetime import date
from openai import OpenAI

REPORT_TYPES = {
    "PADER": {
        "sections": [
            {
                "id": "cover_page",
                "title": "Cover Page",
                "purpose": "Capture title page details such as report title, product, strength, ANDA number, reporting period, company details, confidentiality statement, approval date, report status, and date of report."
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


def generate_ai_draft(section_title, section_purpose, source_data, comments, product_name, interval_start, interval_end):
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    if not source_data.strip():
        return "ERROR: Please enter source data before generating a draft."

    client = OpenAI(api_key=api_key)

    instructions = (
        "You are an expert pharmacovigilance medical writer. "
        "Draft only the requested report section in a concise, professional, regulatory style. "
        "Use only the source data provided. "
        "Do not invent facts, numbers, dates, tables, or conclusions. "
        "If information is missing, stay neutral and do not hallucinate. "
        "Return only the drafted section text."
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
        return response.output_text
    except Exception as e:
        return f"ERROR: {str(e)}"


st.title("Viginovix Aggregate Reporting Platform")
st.write("Prototype: AI-assisted aggregate report authoring and review")

st.header("Step 1: Select Report Type")

report_type = st.selectbox(
    "Choose Report Type",
    ["Select...", "PADER", "PBRER", "DSUR"]
)

if report_type == "PADER":
    st.success("PADER selected. Sections will load below.")

    st.header("Step 2: Report Setup")

    product_name = st.text_input("Product Name")
    interval_start = st.date_input("Reporting Interval Start Date", value=date.today())
    interval_end = st.date_input("Reporting Interval End Date", value=date.today())
    data_lock_point = st.date_input("Data Lock Point", value=date.today())
    region = st.selectbox("Region", ["US", "EU", "UK", "Global"])
    template_version = st.text_input("Template Version", value="v1.0")
    report_owner = st.text_input("Report Owner")

    st.subheader("Report Setup Summary")
    st.write(f"**Product Name:** {product_name}")
    st.write(f"**Interval Start:** {interval_start}")
    st.write(f"**Interval End:** {interval_end}")
    st.write(f"**Data Lock Point:** {data_lock_point}")
    st.write(f"**Region:** {region}")
    st.write(f"**Template Version:** {template_version}")
    st.write(f"**Report Owner:** {report_owner}")

    st.header("Step 3: PADER Sections")

    pader_sections = REPORT_TYPES["PADER"]["sections"]

    for section in pader_sections:
        with st.expander(section["title"]):
            st.write(f"**Purpose:** {section['purpose']}")

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

elif report_type in ["PBRER", "DSUR"]:
    st.info(f"{report_type} module coming soon.")
