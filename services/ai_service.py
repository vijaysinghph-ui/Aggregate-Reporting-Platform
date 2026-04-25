from openai import OpenAI

from utils.text import safe_text


def get_openai_client(api_key: str | None):
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def generate_ai_draft(
    client,
    section_title: str,
    section_purpose: str,
    source_data: str,
    comments: str,
    product_name: str,
    interval_start,
    interval_end,
) -> str:
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
    client,
    report_context_text: str,
    previous_pader_text: str,
    label_text: str,
    report_status: str,
    report_status_other: str = "",
) -> str:
    if client is None:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    final_report_status = (
        report_status_other.strip()
        if report_status == "Other" and report_status_other
        else report_status
    )

    instructions = (
        "You are an expert pharmacovigilance medical writer drafting the Introduction section of a PADER. "
        "Use the current report context as authoritative for reporting interval and metadata. "
        "Use current label text as the primary source for current product truth when available. "
        "Use previous PADER text only as historical reference for stable wording and style. "
        "If a previous PADER is not available, generate the Introduction using report context and label only. "
        "If uploaded PDFs produce limited text, rely on the available extracted text and report context without guessing. "
        "Do not hallucinate product facts, regulatory details, or placeholders. "
        "Write gracefully even if some information is missing. "
        "Do not repeat the section title. "
        "Use the report status explicitly as follows: "
        "if report status is Annual, open with 'This annual Periodic Adverse Drug Experience Report (PADER)...'; "
        "if report status is Quarterly, open with 'This quarterly Periodic Adverse Drug Experience Report (PADER)...'; "
        "if report status is Other, use neutral wording such as 'This Periodic Adverse Drug Experience Report (PADER)...' "
        "unless the custom status clearly supports more specific phrasing. "
        "Return only the Introduction body text."
    )

    user_input = f"""
Current Report Context:
{report_context_text}

Report Status:
{final_report_status}

Previous PADER Reference Text:
{previous_pader_text}

Current Label Reference Text:
{label_text}
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


def generate_section2_draft(
    client,
    product_name: str,
    interval_start,
    interval_end,
    line_listing_summary: str,
) -> str:
    if client is None:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    if not safe_text(line_listing_summary).strip():
        return "ERROR: No line listing summary available."

    instructions = (
        "You are an expert pharmacovigilance physician writing the PADER section "
        "'Summary of Submitted 15-Day Alerts, New Adverse Drug Experiences and New Adverse Drug Experience Follow-up'. "
        "Use only the provided backend line listing summary. "
        "Do not invent counts, cases, dates, causality, listedness, seriousness, or conclusions. "
        "At the backend, align the output in a medically useful structure: "
        "first address 15-day alerts if identifiable; "
        "then emphasize medically important serious unlisted related cases if present; "
        "then describe other notable new adverse drug experiences and follow-up information if present; "
        "then end with a restrained concluding statement only if supported by the data. "
        "If fatal events are present, mention them in a neutral, regulatory way. "
        "If SOC patterns are present, you may group discussion accordingly. "
        "If causality information is present, use it carefully and only as reported. "
        "Maintain a cautious regulatory tone similar to real PADER narratives. "
        "Do not repeat the section title. "
        "Return only the section body text."
    )

    user_input = f"""
Product Name: {product_name}
Reporting Interval: {interval_start} to {interval_end}

Backend Line Listing Summary:
{line_listing_summary}
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


def generate_actions_taken_draft(
    client,
    regulatory_actions_summary: str,
    product_name: str,
    interval_start,
    interval_end,
) -> str:
    if client is None:
        return "ERROR: OPENAI_API_KEY not found in Streamlit secrets."

    if not safe_text(regulatory_actions_summary).strip():
        return (
            "No actions related to safety, labeling, or regulatory authority decisions "
            "were identified during the reporting interval."
        )

    instructions = (
        "You are an expert pharmacovigilance medical writer drafting the PADER section "
        "'Actions Taken Since Last Periodic Adverse Drug Experience Report'. "
        "Use only the uploaded regulatory actions summary. "
        "Do not invent actions, approvals, or authority decisions. "
        "If no meaningful actions are evident, state that no actions were identified during the reporting interval. "
        "Do not repeat the section title. "
        "Return only the section body text."
    )

    user_input = f"""
Product Name: {product_name}
Reporting Interval: {interval_start} to {interval_end}

Regulatory Actions Summary:
{regulatory_actions_summary}
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

