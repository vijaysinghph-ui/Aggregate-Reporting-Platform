REPORT_TYPES = {
    "PADER": {
        "sections": [
            {
                "id": "cover_page",
                "title": "Cover Page",
                "purpose": "Capture title page details such as report title, product, strength, NDA/ANDA number, reporting period, company details, confidentiality statement, approval date, report status, and date of report.",
            },
            {
                "id": "approval_page",
                "title": "Approval Page",
                "purpose": "Capture author, medical reviewer, reviewer, and approver details with signature/date placeholders.",
            },
            {
                "id": "table_of_contents",
                "title": "Table of Contents",
                "purpose": "Auto-generate the table of contents for the assembled report.",
            },
            {
                "id": "introduction",
                "title": "1. Introduction",
                "purpose": "Draft the Introduction using current report setup, previous PADER reference if available, and current label information if available.",
            },
            {
                "id": "summary_alerts_new_ades_followup",
                "title": "2. Summary of Submitted 15-Day Alerts, New Adverse Drug Experiences and New Adverse Drug Experience Follow-up",
                "purpose": "Draft the core safety summary using uploaded line listing data, with backend logic determining the best structure.",
            },
            {
                "id": "actions_taken",
                "title": "3. Actions Taken Since Last Periodic Adverse Drug Experience Report",
                "purpose": "Summarize product-specific regulatory actions, labeling changes, safety actions, and related authority actions during the reporting period.",
            },
            {
                "id": "conclusion",
                "title": "4. Conclusion",
                "purpose": "Provide the overall safety conclusion and state whether the product safety profile remains unchanged or if further action is planned.",
            },
        ]
    },
    "PBRER": {"sections": []},
    "DSUR": {"sections": []},
}

