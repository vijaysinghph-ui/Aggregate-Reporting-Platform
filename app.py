from datetime import date, datetime
import difflib

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
    export_audit_trail_to_word,
    export_report_to_word,
    generate_approval_page_text,
    generate_cover_page_text,
    generate_toc_text,
)
from services.storage import (
    create_report,
    create_version_snapshot,
    get_report,
    get_report_version,
    init_db,
    list_report_versions,
    list_reports,
    save_report,
)
from utils.file_extraction import extract_reference_text
from utils.table_analysis import (
    SECTION2_COLUMN_CANDIDATES,
    build_line_listing_backend_summary,
    build_section2_case_tables,
    read_uploaded_table,
    summarize_dataframe,
    suggest_section2_column_mapping,
)


st.set_page_config(
    page_title="Viginovix Aggregate Reporting Platform",
    layout="wide",
)

WORKFLOW_STATES = [
    "Author Draft",
    "Submitted for Review",
    "Reviewer Changes Requested",
    "Reviewer Approved",
    "Submitted for Approval",
    "Approver Changes Requested",
    "Approved",
]

PADER_VIEW_DASHBOARD = "Dashboard"
PADER_VIEW_EDITOR = "Create / Edit PADER"

DEMO_ROLES = ["Author", "Reviewer", "Approver", "Admin"]

DATE_FIELD_KEYS = {
    "approval_date",
    "interval_start",
    "interval_end",
    "data_lock_point",
    "report_date",
}

EDITABLE_WORKFLOW_STATES = {
    "Author Draft",
    "Reviewer Changes Requested",
    "Approver Changes Requested",
}

AUTHOR_QUEUE_STATUSES = {
    "Author Draft",
    "Reviewer Changes Requested",
    "Approver Changes Requested",
}

REVIEWER_QUEUE_STATUSES = {
    "Submitted for Review",
}

APPROVER_QUEUE_STATUSES = {
    "Submitted for Approval",
}


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


def get_secret_value(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except StreamlitSecretNotFoundError:
        return default


def initialize_workflow_state():
    st.session_state.setdefault("workflow_status", "Author Draft")
    st.session_state.setdefault("workflow_history", [])
    st.session_state.setdefault("review_comments", [])


def workflow_event(role: str, actor_name: str, action: str, comment: str):
    actor = actor_name.strip() if actor_name else role
    st.session_state["workflow_history"].append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "role": role,
            "actor": actor,
            "action": action,
            "comment": comment.strip(),
        }
    )


def set_workflow_status(status: str, role: str, actor_name: str, action: str, comment: str):
    st.session_state["workflow_status"] = status
    workflow_event(role, actor_name, action, comment)


def add_review_comment(role: str, actor_name: str, comment: str):
    if not comment.strip():
        return False

    actor = actor_name.strip() if actor_name else role
    st.session_state["review_comments"].append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "role": role,
            "actor": actor,
            "comment": comment.strip(),
        }
    )
    return True


def persist_current_report(
    context: dict,
    approval_context: dict,
    pader_sections: list[dict],
    title_override: str | None = None,
    version_type: str = "minor",
    actor_role: str = "System",
    actor_name: str = "",
    action: str = "Saved PADER",
) -> tuple[bool, str]:
    report_id = st.session_state.get("current_report_id")
    if not report_id:
        return False, "Create or load a PADER report before saving."

    title = (title_override or st.session_state.get("current_report_title", "")).strip()
    if not title:
        title = f"{context['product_name'] or 'PADER'} Report"

    drafts = get_drafts_for_sections(pader_sections)
    review_comments = st.session_state.get("review_comments", [])
    full_report_text = st.session_state.get("full_pader_report", "")
    workflow_status = st.session_state.get("workflow_status", "Author Draft")

    save_report(
        report_id=report_id,
        title=title,
        product_name=context["product_name"],
        assigned_reviewer=approval_context["reviewer_name"],
        assigned_approver=approval_context["approver_name"],
        context=context,
        approval_context=approval_context,
        drafts=drafts,
        review_comments=review_comments,
        full_report_text=full_report_text,
        workflow_status=workflow_status,
        workflow_history=st.session_state.get("workflow_history", []),
    )
    version_label = create_version_snapshot(
        report_id=report_id,
        version_type=version_type,
        actor_role=actor_role,
        actor_name=actor_name,
        action=action,
        workflow_status=workflow_status,
        context=context,
        approval_context=approval_context,
        drafts=drafts,
        review_comments=review_comments,
        full_report_text=full_report_text,
    )
    return True, f"Saved report #{report_id} as version {version_label}."


def is_report_editable() -> bool:
    return st.session_state.get("workflow_status", "Author Draft") in EDITABLE_WORKFLOW_STATES


def render_lock_banner(editable: bool):
    if editable:
        st.info("Report content is editable in the current workflow state.")
    else:
        st.warning(
            "Report content is locked for review or approval. "
            "Changes can be made only after a reviewer or approver requests changes."
        )


def parse_saved_date(value):
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return date.today()


def apply_loaded_report(report: dict):
    for key, value in report["context"].items():
        st.session_state[key] = parse_saved_date(value) if key in DATE_FIELD_KEYS else value

    for key, value in report["approval_context"].items():
        st.session_state[key] = value

    for section_id, draft_text in report["drafts"].items():
        st.session_state[f"draft_{section_id}"] = draft_text

    st.session_state["full_pader_report"] = report.get("full_report_text", "")
    st.session_state["workflow_status"] = report.get("workflow_status", "Author Draft")
    st.session_state["workflow_history"] = report.get("workflow_history", [])
    st.session_state["review_comments"] = report.get("review_comments", [])


def load_report_into_session(report_id: int) -> bool:
    report = get_report(report_id)
    if not report:
        return False

    st.session_state["current_report_id"] = report_id
    st.session_state["current_report_title"] = report["title"]
    st.session_state["next_pader_view"] = PADER_VIEW_EDITOR
    apply_loaded_report(report)
    return True


def format_report_option(report: dict) -> str:
    product = report.get("product_name") or "No product"
    return f"#{report['id']} | {report['title']} | {product} | {report['workflow_status']}"


def normalize_name(value: str) -> str:
    return value.strip().lower()


def render_create_report_panel():
    st.header("Create New PADER")

    current_report_id = st.session_state.get("current_report_id")

    new_report_title = st.text_input(
        "New PADER Title",
        key="new_report_title",
        placeholder="Example: Product A Annual PADER 2026",
    )
    if st.button("Create New PADER"):
        title = new_report_title.strip() or f"PADER {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        report_id = create_report(title=title)
        st.session_state["current_report_id"] = report_id
        st.session_state["current_report_title"] = title
        st.session_state["workflow_status"] = "Author Draft"
        st.session_state["workflow_history"] = []
        st.session_state["review_comments"] = []
        st.success(f"Created report #{report_id}.")
        st.rerun()

    if current_report_id:
        st.caption(
            f"Active report: #{current_report_id} "
            f"{st.session_state.get('current_report_title', '')}"
        )


def render_all_reports_loader():
    reports = list_reports()
    current_report_id = st.session_state.get("current_report_id")

    st.subheader("All Saved PADERs")

    if not reports:
        st.info("No saved PADER reports yet.")
        return

    st.dataframe(
        [
            {
                "ID": report["id"],
                "Title": report["title"],
                "Product": report.get("product_name") or "",
                "Reviewer": report.get("assigned_reviewer") or "",
                "Approver": report.get("assigned_approver") or "",
                "Status": report["workflow_status"],
                "Updated": report["updated_at"],
            }
            for report in reports
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("View Version Snapshot")
    version_options = {
        (
            f"{version['version_label']} | {version['timestamp']} | "
            f"{version['actor_role']} | {version['action']}"
        ): version["id"]
        for version in versions
    }
    selected_version_label = st.selectbox(
        "Select Version",
        list(version_options.keys()),
        key="version_snapshot_select",
    )

    selected_version = get_report_version(version_options[selected_version_label])
    if not selected_version:
        st.error("Selected version could not be loaded.")
        return

    meta_col1, meta_col2, meta_col3 = st.columns(3)
    meta_col1.metric("Version", selected_version["version_label"])
    meta_col2.metric("Status", selected_version["workflow_status"])
    meta_col3.metric("Type", selected_version["version_type"])

    st.caption(
        f"{selected_version['timestamp']} | "
        f"{selected_version['actor_role']} | "
        f"{selected_version['actor_name']} | "
        f"{selected_version['action']}"
    )

    snapshot_comments = selected_version.get("review_comments", [])
    if snapshot_comments:
        st.write("Review Comments Captured in This Version")
        st.dataframe(snapshot_comments, use_container_width=True, hide_index=True)

    st.text_area(
        "Full PADER Text Captured in This Version",
        value=selected_version.get("full_report_text", ""),
        height=420,
        disabled=True,
        key=f"snapshot_text_{selected_version['id']}",
    )

    snapshot_docx = export_report_to_word(selected_version.get("full_report_text", ""))
    st.download_button(
        label="Download This Version as Word",
        data=snapshot_docx,
        file_name=f"PADER_Report_v{selected_version['version_label']}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"download_snapshot_{selected_version['id']}",
    )

    if len(versions) < 2:
        return

    st.subheader("Compare Versions")
    compare_options = {
        f"{version['version_label']} | {version['timestamp']} | {version['action']}": version["id"]
        for version in versions
    }
    compare_labels = list(compare_options.keys())

    compare_col1, compare_col2 = st.columns(2)
    with compare_col1:
        version_a_label = st.selectbox(
            "Version A",
            compare_labels,
            index=min(1, len(compare_labels) - 1),
            key="compare_version_a",
        )
    with compare_col2:
        version_b_label = st.selectbox(
            "Version B",
            compare_labels,
            index=0,
            key="compare_version_b",
        )

    version_a = get_report_version(compare_options[version_a_label])
    version_b = get_report_version(compare_options[version_b_label])
    if not version_a or not version_b:
        st.error("One of the selected versions could not be loaded.")
        return

    st.dataframe(
        [
            {
                "Side": "A",
                "Version": version_a["version_label"],
                "Timestamp": version_a["timestamp"],
                "Status": version_a["workflow_status"],
                "Actor": version_a["actor_name"],
                "Action": version_a["action"],
            },
            {
                "Side": "B",
                "Version": version_b["version_label"],
                "Timestamp": version_b["timestamp"],
                "Status": version_b["workflow_status"],
                "Actor": version_b["actor_name"],
                "Action": version_b["action"],
            },
        ],
        use_container_width=True,
        hide_index=True,
    )

    diff_lines = list(
        difflib.unified_diff(
            version_a.get("full_report_text", "").splitlines(),
            version_b.get("full_report_text", "").splitlines(),
            fromfile=f"Version {version_a['version_label']}",
            tofile=f"Version {version_b['version_label']}",
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines) if diff_lines else "No text differences found."
    st.code(diff_text, language="diff")

    report_options = {format_report_option(report): report["id"] for report in reports}
    labels = list(report_options.keys())
    default_index = 0
    if current_report_id:
        for idx, label in enumerate(labels):
            if report_options[label] == current_report_id:
                default_index = idx
                break

    selected_label = st.selectbox(
        "Load Existing PADER",
        labels,
        index=default_index,
        key="load_report_select",
    )
    if st.button("Load Selected PADER"):
        report_id = report_options[selected_label]
        if load_report_into_session(report_id):
            st.success(f"Loaded report #{report_id}.")
            st.rerun()


def render_queue_tab(
    reports: list[dict],
    statuses: set[str],
    select_key: str,
    button_key: str,
    empty_message: str,
    assigned_field: str | None = None,
    current_user_name: str = "",
):
    queued_reports = [
        report for report in reports if report["workflow_status"] in statuses
    ]
    if assigned_field and current_user_name.strip():
        current_name = normalize_name(current_user_name)
        queued_reports = [
            report
            for report in queued_reports
            if normalize_name(report.get(assigned_field) or "") == current_name
        ]

    if not queued_reports:
        st.info(empty_message)
        return

    st.dataframe(
        [
            {
                "ID": report["id"],
                "Title": report["title"],
                "Product": report.get("product_name") or "",
                "Reviewer": report.get("assigned_reviewer") or "",
                "Approver": report.get("assigned_approver") or "",
                "Status": report["workflow_status"],
                "Updated": report["updated_at"],
            }
            for report in queued_reports
        ],
        use_container_width=True,
        hide_index=True,
    )

    options = {format_report_option(report): report["id"] for report in queued_reports}
    selected = st.selectbox("Select PADER", list(options.keys()), key=select_key)
    if st.button("Open Selected PADER", key=button_key):
        report_id = options[selected]
        if load_report_into_session(report_id):
            st.success(f"Loaded report #{report_id}.")
            st.rerun()


def render_work_queues(role: str, current_user_name: str):
    st.header("Work Queues")

    reports = list_reports()

    if role == "Author":
        render_queue_tab(
            reports=reports,
            statuses=AUTHOR_QUEUE_STATUSES,
            select_key="author_queue_select",
            button_key="author_queue_open",
            empty_message="No author draft or change-request PADERs.",
        )
    elif role == "Reviewer":
        render_queue_tab(
            reports=reports,
            statuses=REVIEWER_QUEUE_STATUSES,
            select_key="reviewer_queue_select",
            button_key="reviewer_queue_open",
            empty_message="No PADERs are currently submitted to this reviewer.",
            assigned_field="assigned_reviewer",
            current_user_name=current_user_name,
        )
    elif role == "Approver":
        render_queue_tab(
            reports=reports,
            statuses=APPROVER_QUEUE_STATUSES,
            select_key="approver_queue_select",
            button_key="approver_queue_open",
            empty_message="No PADERs are currently submitted to this approver.",
            assigned_field="assigned_approver",
            current_user_name=current_user_name,
        )
    else:
        author_tab, reviewer_tab, approver_tab = st.tabs(
            ["Author Queue", "Reviewer Queue", "Approver Queue"]
        )

        with author_tab:
            render_queue_tab(
                reports=reports,
                statuses=AUTHOR_QUEUE_STATUSES,
                select_key="author_queue_select",
                button_key="author_queue_open",
                empty_message="No author draft or change-request PADERs.",
            )

        with reviewer_tab:
            render_queue_tab(
                reports=reports,
                statuses=REVIEWER_QUEUE_STATUSES,
                select_key="reviewer_queue_select",
                button_key="reviewer_queue_open",
                empty_message="No PADERs are currently submitted for review.",
            )

        with approver_tab:
            render_queue_tab(
                reports=reports,
                statuses=APPROVER_QUEUE_STATUSES,
                select_key="approver_queue_select",
                button_key="approver_queue_open",
                empty_message="No PADERs are currently submitted for approval.",
            )


def render_pader_dashboard(role: str, current_user_name: str):
    st.header("PADER Dashboard")
    user_label = current_user_name or "Not specified"
    st.caption(f"Current demo role: {role} | Current user: {user_label}")
    render_work_queues(role, current_user_name)

    if role == "Admin":
        st.divider()
        render_all_reports_loader()


def render_report_setup(editable: bool):
    st.header("Step 2: Report Setup")

    col1, col2 = st.columns(2)

    with col1:
        product_name = st.text_input("Product Name", key="product_name", disabled=not editable)
        nda_anda_number = st.text_input("NDA / ANDA Number", key="nda_anda_number", disabled=not editable)
        approval_date = st.date_input(
            "Approval Date",
            value=date.today(),
            key="approval_date",
            disabled=not editable,
        )
        company_name = st.text_input("Company Name", key="company_name", disabled=not editable)
        dosage_strength = st.text_input(
            "Dosage Form / Strength",
            key="dosage_strength",
            disabled=not editable,
        )
        company_address = st.text_area(
            "Company Address",
            height=100,
            key="company_address",
            disabled=not editable,
        )

    with col2:
        interval_start = st.date_input(
            "Reporting Interval Start Date",
            value=date.today(),
            key="interval_start",
            disabled=not editable,
        )
        interval_end = st.date_input(
            "Reporting Interval End Date",
            value=date.today(),
            key="interval_end",
            disabled=not editable,
        )
        data_lock_point = st.date_input(
            "Data Lock Point",
            value=date.today(),
            key="data_lock_point",
            disabled=not editable,
        )
        region = st.selectbox("Region", ["US", "EU", "UK", "Global"], key="region", disabled=not editable)
        template_version = st.text_input(
            "Template Version",
            value="v1.0",
            key="template_version",
            disabled=not editable,
        )
        report_owner = st.text_input("Report Owner", key="report_owner", disabled=not editable)
        report_status = st.selectbox(
            "Report Status",
            ["Annual", "Quarterly", "Other"],
            key="report_status",
            disabled=not editable,
        )

    report_status_other = ""
    if report_status == "Other":
        report_status_other = st.text_input(
            "If Other, specify Report Status",
            key="report_status_other",
            disabled=not editable,
        )

    report_date = st.date_input(
        "Date of Report",
        value=date.today(),
        key="report_date",
        disabled=not editable,
    )
    confidentiality_statement = st.text_area(
        "Confidentiality Statement",
        value=(
            "This document is a confidential communication. Acceptance of this document "
            "constitutes an agreement by the recipient that no unpublished information "
            "contained herein will be published or disclosed without prior written approval."
        ),
        height=100,
        key="confidentiality_statement",
        disabled=not editable,
    )

    return {
        "product_name": product_name,
        "nda_anda_number": nda_anda_number,
        "approval_date": approval_date,
        "company_name": company_name,
        "dosage_strength": dosage_strength,
        "company_address": company_address,
        "interval_start": interval_start,
        "interval_end": interval_end,
        "data_lock_point": data_lock_point,
        "region": region,
        "template_version": template_version,
        "report_owner": report_owner,
        "report_status": report_status,
        "report_status_other": report_status_other,
        "report_date": report_date,
        "confidentiality_statement": confidentiality_statement,
    }


def render_approval_workflow(editable: bool):
    st.header("Approval Workflow Details")

    a1, a2 = st.columns(2)
    with a1:
        author_name = st.text_input("Author Name", key="author_name", disabled=not editable)
        author_designation = st.text_input(
            "Author Designation",
            key="author_designation",
            disabled=not editable,
        )
        medical_reviewer_name = st.text_input(
            "Medical Reviewer Name",
            key="medical_reviewer_name",
            disabled=not editable,
        )
        medical_reviewer_designation = st.text_input(
            "Medical Reviewer Designation",
            key="medical_reviewer_designation",
            disabled=not editable,
        )
    with a2:
        reviewer_name = st.text_input("Reviewer Name", key="reviewer_name", disabled=not editable)
        reviewer_designation = st.text_input(
            "Reviewer Designation",
            key="reviewer_designation",
            disabled=not editable,
        )
        approver_name = st.text_input("Approver Name", key="approver_name", disabled=not editable)
        approver_designation = st.text_input(
            "Approver Designation",
            key="approver_designation",
            disabled=not editable,
        )

    return {
        "author_name": author_name,
        "author_designation": author_designation,
        "medical_reviewer_name": medical_reviewer_name,
        "medical_reviewer_designation": medical_reviewer_designation,
        "reviewer_name": reviewer_name,
        "reviewer_designation": reviewer_designation,
        "approver_name": approver_name,
        "approver_designation": approver_designation,
    }


def render_review_comments_panel(
    role: str,
    current_user_name: str,
    context: dict,
    approval_context: dict,
    pader_sections: list[dict],
):
    st.subheader("Review Comments")

    status = st.session_state["workflow_status"]
    can_comment = (
        status == "Submitted for Review" and role in ["Reviewer", "Admin"]
    ) or (
        status == "Submitted for Approval" and role in ["Approver", "Admin"]
    )

    comment_role = role
    if role == "Admin":
        if status == "Submitted for Review":
            comment_role = "Reviewer"
        elif status == "Submitted for Approval":
            comment_role = "Approver"

    default_actor = current_user_name
    if not default_actor and comment_role == "Reviewer":
        default_actor = approval_context["reviewer_name"]
    if not default_actor and comment_role == "Approver":
        default_actor = approval_context["approver_name"]

    new_comment = st.text_area(
        "Add Review Comment",
        key="review_comment_text",
        height=100,
        disabled=not can_comment,
        placeholder="Add full-PADER review feedback here.",
    )

    if st.button("Add Review Comment", disabled=not can_comment):
        if add_review_comment(comment_role, default_actor, new_comment):
            ok, message = persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="minor",
                actor_role=comment_role,
                actor_name=default_actor,
                action="Added review comment",
            )
            if ok:
                st.success("Review comment saved.")
            else:
                st.error(message)
            st.rerun()
        else:
            st.error("Enter a review comment before saving.")

    comments = st.session_state.get("review_comments", [])
    if comments:
        st.dataframe(comments, use_container_width=True, hide_index=True)
    else:
        st.info("No review comments have been added yet.")


def render_workflow_tracker(
    role: str,
    current_user_name: str,
    context: dict,
    approval_context: dict,
    pader_sections: list[dict],
):
    initialize_workflow_state()

    st.header("Step 5: Author / Reviewer / Approver Workflow")

    status = st.session_state["workflow_status"]
    try:
        status_index = WORKFLOW_STATES.index(status)
    except ValueError:
        status_index = 0

    st.progress((status_index + 1) / len(WORKFLOW_STATES))

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Status", status)
    c2.metric("Reviewer", approval_context["reviewer_name"] or "Not assigned")
    c3.metric("Approver", approval_context["approver_name"] or "Not assigned")

    render_review_comments_panel(
        role=role,
        current_user_name=current_user_name,
        context=context,
        approval_context=approval_context,
        pader_sections=pader_sections,
    )

    comments = st.text_area(
        "Workflow Comments",
        key="workflow_comments",
        height=100,
        placeholder="Add review notes, requested changes, or approval comments.",
    )

    author_col, reviewer_col, approver_col = st.columns(3)

    with author_col:
        st.subheader("Author")
        can_submit = status in [
            "Author Draft",
            "Reviewer Changes Requested",
            "Approver Changes Requested",
        ]
        if can_submit and not st.session_state.get("current_report_id"):
            st.caption("Create or load a PADER report before submitting.")
        if can_submit and not st.session_state.get("full_pader_report", "").strip():
            st.caption("Assemble the full PADER before submitting.")
        if st.button("Submit to Reviewer", disabled=not can_submit):
            if not st.session_state.get("current_report_id"):
                st.error("Create or load a PADER report before submitting to reviewer.")
                return
            if not st.session_state.get("full_pader_report", "").strip():
                st.error("Assemble the full PADER report before submitting to reviewer.")
                return
            set_workflow_status(
                status="Submitted for Review",
                role="Author",
                actor_name=approval_context["author_name"],
                action="Submitted report to reviewer",
                comment=comments,
            )
            ok, message = persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="minor",
                actor_role="Author",
                actor_name=approval_context["author_name"],
                action="Submitted report to reviewer",
            )
            if not ok:
                st.error(message)
                return
            st.success("Submitted to reviewer and saved the locked review snapshot.")
            st.rerun()

    with reviewer_col:
        st.subheader("Reviewer")
        can_review = status == "Submitted for Review"
        if st.button("Request Author Changes", disabled=not can_review):
            set_workflow_status(
                status="Reviewer Changes Requested",
                role="Reviewer",
                actor_name=approval_context["reviewer_name"],
                action="Requested author changes",
                comment=comments,
            )
            persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="minor",
                actor_role="Reviewer",
                actor_name=approval_context["reviewer_name"],
                action="Requested author changes",
            )
            st.rerun()
        if st.button("Reviewer Approve", disabled=not can_review):
            set_workflow_status(
                status="Reviewer Approved",
                role="Reviewer",
                actor_name=approval_context["reviewer_name"],
                action="Reviewer approved report",
                comment=comments,
            )
            persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="minor",
                actor_role="Reviewer",
                actor_name=approval_context["reviewer_name"],
                action="Reviewer approved report",
            )
            st.rerun()
        if st.button("Submit to Approver", disabled=status != "Reviewer Approved"):
            set_workflow_status(
                status="Submitted for Approval",
                role="Reviewer",
                actor_name=approval_context["reviewer_name"],
                action="Submitted report to approver",
                comment=comments,
            )
            persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="minor",
                actor_role="Reviewer",
                actor_name=approval_context["reviewer_name"],
                action="Submitted report to approver",
            )
            st.rerun()

    with approver_col:
        st.subheader("Approver")
        can_approve = status == "Submitted for Approval"
        if st.button("Request Reviewer Changes", disabled=not can_approve):
            set_workflow_status(
                status="Approver Changes Requested",
                role="Approver",
                actor_name=approval_context["approver_name"],
                action="Requested reviewer changes",
                comment=comments,
            )
            persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="minor",
                actor_role="Approver",
                actor_name=approval_context["approver_name"],
                action="Requested reviewer changes",
            )
            st.rerun()
        if st.button("Final Approve", disabled=not can_approve):
            set_workflow_status(
                status="Approved",
                role="Approver",
                actor_name=approval_context["approver_name"],
                action="Final approved report",
                comment=comments,
            )
            persist_current_report(
                context,
                approval_context,
                pader_sections,
                version_type="major",
                actor_role="Approver",
                actor_name=approval_context["approver_name"],
                action="Final approved report",
            )
            st.rerun()

    if st.session_state["workflow_history"]:
        st.subheader("Workflow History")
        st.dataframe(
            st.session_state["workflow_history"],
            use_container_width=True,
            hide_index=True,
        )

def render_cover_page(context: dict, editable: bool):
    if st.button("Generate Cover Page", key="btn_cover_page", disabled=not editable):
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

    st.text_area(
        "Draft Output for Cover Page",
        key="draft_cover_page",
        height=280,
        disabled=not editable,
    )


def render_approval_page(context: dict, approval_context: dict, editable: bool):
    if st.button("Generate Approval Page", key="btn_approval_page", disabled=not editable):
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

    st.text_area(
        "Draft Output for Approval Page",
        key="draft_approval_page",
        height=320,
        disabled=not editable,
    )


def render_table_of_contents(pader_sections: list[dict], editable: bool):
    if st.button("Generate Table of Contents", key="btn_table_of_contents", disabled=not editable):
        st.session_state["draft_table_of_contents"] = generate_toc_text(pader_sections)

    st.text_area(
        "Draft Output for Table of Contents",
        key="draft_table_of_contents",
        height=220,
        disabled=not editable,
    )


def render_introduction(context: dict, client, editable: bool):
    previous_pader_file = st.file_uploader(
        "Upload Previous PADER (optional)",
        type=["pdf", "docx", "txt"],
        key="previous_pader_upload",
        disabled=not editable,
    )

    label_file = st.file_uploader(
        "Upload Current Label",
        type=["pdf", "docx", "txt"],
        key="label_upload",
        disabled=not editable,
    )

    if st.button("Generate Introduction", key="btn_introduction", disabled=not editable):
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

    st.text_area(
        "Draft Output for 1. Introduction",
        key="draft_introduction",
        height=260,
        disabled=not editable,
    )


def get_section2_mapping_from_state(df) -> dict[str, str | None]:
    column_lookup = {str(column): column for column in df.columns}
    mapping = {}
    for field in SECTION2_COLUMN_CANDIDATES:
        selected = st.session_state.get(f"section2_mapping_{field}", "Not mapped")
        mapping[field] = column_lookup.get(selected)
    return mapping


def render_section2_column_mapping(df, editable: bool) -> dict[str, str | None]:
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
            st.selectbox(
                definition["label"],
                options,
                key=key,
                disabled=not editable,
            )

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


def render_section_2(context: dict, client, editable: bool):
    uploaded_file = st.file_uploader(
        "Upload PADER Line Listing or Source File",
        type=["xlsx", "csv", "pdf", "docx", "txt"],
        key="line_listing_upload",
        disabled=not editable,
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
                section2_mapping = render_section2_column_mapping(df, editable)
        else:
            source_text = extract_uploaded_source_text(uploaded_file, "Section 2 source file")
            st.session_state["line_listing_df"] = None
            st.session_state["line_listing_source_text"] = source_text

    if st.button("Generate Section 2", key="btn_summary_alerts_new_ades_followup", disabled=not editable):
        df = st.session_state.get("line_listing_df", None)
        source_text = st.session_state.get("line_listing_source_text", "")
        if df is None and not source_text:
            st.error("Please upload a line listing or source PDF/DOCX/TXT file first.")
        else:
            with st.spinner("Generating Section 2..."):
                if df is not None:
                    section2_mapping = section2_mapping or get_section2_mapping_from_state(df)
                backend_summary = (
                    build_line_listing_backend_summary(df, section2_mapping)
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
                    build_section2_case_tables(df, section2_mapping)
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
        disabled=not editable,
    )


def render_actions_taken(context: dict, client, editable: bool):
    st.caption(
        "Upload the current-period regulatory actions source as Excel/CSV or as a searchable "
        "PDF/DOCX/TXT file."
    )
    regulatory_actions_file = st.file_uploader(
        "Upload Regulatory Actions File for Section 3",
        type=["xlsx", "csv", "pdf", "docx", "txt"],
        key="regulatory_actions_upload",
        disabled=not editable,
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

    if st.button("Generate Section 3", key="btn_actions_taken", disabled=not editable):
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
        disabled=not editable,
    )


def render_conclusion(context: dict, client, editable: bool):
    comments = st.text_area(
        "Comments / Drafting Instructions for 4. Conclusion",
        key="comment_conclusion",
        height=120,
        disabled=not editable,
        placeholder=(
            "Example: No new safety concerns were identified during the reporting period; "
            "the benefit-risk profile remains unchanged."
        ),
    )

    if st.button("Generate Draft for 4. Conclusion", key="btn_conclusion", disabled=not editable):
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

    st.text_area(
        "Draft Output for 4. Conclusion",
        key="draft_conclusion",
        height=220,
        disabled=not editable,
    )


def render_standard_ai_section(section: dict, context: dict, client, editable: bool):
    source_file = st.file_uploader(
        f"Upload Source File for {section['title']} (optional)",
        type=["pdf", "docx", "txt"],
        key=f"source_file_{section['id']}",
        disabled=not editable,
    )

    uploaded_source_text = extract_uploaded_source_text(
        source_file,
        f"Source file for {section['title']}",
    )

    source_data = st.text_area(
        f"Source Data for {section['title']}",
        key=f"source_{section['id']}",
        height=180,
        disabled=not editable,
    )

    comments = st.text_area(
        f"Comments / Drafting Instructions for {section['title']}",
        key=f"comment_{section['id']}",
        height=100,
        disabled=not editable,
    )

    if st.button(
        f"Generate Draft for {section['title']}",
        key=f"btn_{section['id']}",
        disabled=not editable,
    ):
        with st.spinner("Generating AI draft..."):
            combined_source_data = source_data
            if uploaded_source_text:
                combined_source_data = (
                    f"{source_data}\n\nUploaded source file text:\n{uploaded_source_text[:12000]}"
                    if source_data
                    else uploaded_source_text[:12000]
                )
            st.session_state[f"draft_{section['id']}"] = generate_ai_draft(
                client=client,
                section_title=section["title"],
                section_purpose=section["purpose"],
                source_data=combined_source_data,
                comments=comments,
                product_name=context["product_name"],
                interval_start=context["interval_start"],
                interval_end=context["interval_end"],
            )

    st.text_area(
        f"Draft Output for {section['title']}",
        key=f"draft_{section['id']}",
        height=220,
        disabled=not editable,
    )


def render_pader_sections(context: dict, approval_context: dict, client, editable: bool):
    st.header("Step 3: PADER Sections")

    pader_sections = REPORT_TYPES["PADER"]["sections"]

    for section in pader_sections:
        with st.expander(section["title"]):
            st.write(f"**Purpose:** {section['purpose']}")

            if section["id"] == "cover_page":
                render_cover_page(context, editable)
            elif section["id"] == "approval_page":
                render_approval_page(context, approval_context, editable)
            elif section["id"] == "table_of_contents":
                render_table_of_contents(pader_sections, editable)
            elif section["id"] == "introduction":
                render_introduction(context, client, editable)
            elif section["id"] == "summary_alerts_new_ades_followup":
                render_section_2(context, client, editable)
            elif section["id"] == "actions_taken":
                render_actions_taken(context, client, editable)
            elif section["id"] == "conclusion":
                render_conclusion(context, client, editable)
            else:
                render_standard_ai_section(section, context, client, editable)

    return pader_sections


def render_assembly_and_export(context: dict, pader_sections: list[dict], editable: bool):
    st.header("Step 4: Generate Full PADER Report")
    st.caption(
        "Generate a complete draft from the current section outputs. "
        "Authors can still edit and regenerate while the report is in an editable workflow state."
    )

    if st.button("Generate / Refresh Full PADER Report", disabled=not editable):
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
        disabled=not editable,
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


def render_export():
    st.header("Step 6: Export")

    full_report_text = st.session_state.get("full_pader_report", "")
    workflow_status = st.session_state.get("workflow_status", "Author Draft")

    if not full_report_text:
        st.info("Assemble the full report first to enable Word export.")
    elif workflow_status != "Approved":
        st.info("Final approval is required before Word export is enabled.")
    else:
        docx_bytes = export_report_to_word(full_report_text)
        st.download_button(
            label="Download Full PADER Report as Word",
            data=docx_bytes,
            file_name="PADER_Report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def render_save_report(
    role: str,
    current_user_name: str,
    context: dict,
    approval_context: dict,
    pader_sections: list[dict],
):
    st.header("Step 7: Save")

    report_id = st.session_state.get("current_report_id")
    st.session_state.setdefault("current_report_title", "")
    report_title = st.text_input("Report Title", key="current_report_title")

    if not report_id:
        st.info("Create or load a PADER report before saving.")
        return

    if st.button("Save Current PADER"):
        title = report_title.strip() or f"{context['product_name'] or 'PADER'} Report"
        ok, message = persist_current_report(
            context,
            approval_context,
            pader_sections,
            title_override=title,
            version_type="minor",
            actor_role=role,
            actor_name=current_user_name,
            action="Saved current PADER",
        )
        if ok:
            st.success(message)
        else:
            st.error(message)


def render_version_history():
    st.header("Step 8: Version History & Audit Trail")

    report_id = st.session_state.get("current_report_id")
    if not report_id:
        st.info("Create or load a PADER report to view version history.")
        return

    versions = list_report_versions(report_id)
    if not versions:
        st.info("No saved versions yet. Save or submit the PADER to create version 0.1.")
        return

    st.dataframe(
        [
            {
                "Version": version["version_label"],
                "Type": version["version_type"],
                "Timestamp": version["timestamp"],
                "Role": version["actor_role"],
                "Actor": version["actor_name"],
                "Action": version["action"],
                "Status": version["workflow_status"],
            }
            for version in versions
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_audit_trail_export(context: dict, approval_context: dict):
    st.header("Step 9: Audit Trail Export")

    report_id = st.session_state.get("current_report_id")
    if not report_id:
        st.info("Create or load a PADER report before exporting the audit trail.")
        return

    versions = list_report_versions(report_id)
    audit_docx = export_audit_trail_to_word(
        report_title=st.session_state.get("current_report_title", ""),
        context=context,
        approval_context=approval_context,
        workflow_status=st.session_state.get("workflow_status", "Author Draft"),
        workflow_history=st.session_state.get("workflow_history", []),
        review_comments=st.session_state.get("review_comments", []),
        versions=versions,
    )
    st.download_button(
        label="Download Audit Trail as Word",
        data=audit_docx,
        file_name="PADER_Audit_Trail.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def render_pader_app():
    init_db()

    st.subheader("PADER Workspace")
    role = st.selectbox("Demo Role", DEMO_ROLES, key="demo_role")
    current_user_name = st.text_input(
        "Current User Name",
        key="current_user_name",
        placeholder="Must match assigned reviewer or approver name for filtered queues",
    )

    available_views = [PADER_VIEW_DASHBOARD]
    if role in ["Author", "Admin"] or st.session_state.get("current_report_id"):
        available_views.append(PADER_VIEW_EDITOR)

    next_view = st.session_state.pop("next_pader_view", None)
    if next_view in available_views:
        st.session_state["pader_view"] = next_view

    if st.session_state.get("pader_view") not in available_views:
        st.session_state["pader_view"] = PADER_VIEW_DASHBOARD

    selected_view = st.radio(
        "View",
        available_views,
        horizontal=True,
        key="pader_view",
    )

    if selected_view == PADER_VIEW_DASHBOARD:
        render_pader_dashboard(role, current_user_name)
        return

    if role in ["Author", "Admin"]:
        render_create_report_panel()
    else:
        active_title = st.session_state.get("current_report_title", "")
        if active_title:
            st.caption(f"Reviewing active PADER: {active_title}")

    editable = is_report_editable()
    render_lock_banner(editable)
    context = render_report_setup(editable)
    approval_context = render_approval_workflow(editable)
    client = get_openai_client(get_secret_value("OPENAI_API_KEY"))
    pader_sections = render_pader_sections(context, approval_context, client, editable)
    render_assembly_and_export(context, pader_sections, editable)
    render_workflow_tracker(role, current_user_name, context, approval_context, pader_sections)
    render_export()
    render_save_report(role, current_user_name, context, approval_context, pader_sections)
    render_version_history()
    render_audit_trail_export(context, approval_context)


def main():
    st.title("Viginovix Aggregate Reporting Platform")
    st.write("Prototype: AI-assisted aggregate report authoring and review")

    st.header("Step 1: Select Report Type")

    report_type = st.selectbox("Choose Report Type", ["Select...", "PADER", "PBRER", "DSUR"])

    if report_type == "PADER":
        render_pader_app()
    elif report_type in ["PBRER", "DSUR"]:
        st.info(f"{report_type} module coming soon.")


if __name__ == "__main__":
    main()
