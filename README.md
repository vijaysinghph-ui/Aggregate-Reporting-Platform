# Viginovix Aggregate Reporting Platform

Streamlit prototype for creating, reviewing, approving, versioning, and exporting PADER reports.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app runs at `http://localhost:8501`.

## Streamlit Cloud Deployment

Since GitHub and Streamlit are already connected:

1. Push this project to the connected GitHub repository.
2. In Streamlit Cloud, choose that repository.
3. Set the main file path to:

```text
app.py
```

4. Add the OpenAI key in Streamlit Cloud app settings under `Secrets`:

```toml
OPENAI_API_KEY = "your_api_key_here"
```

5. Deploy or reboot the app.

## Important Demo Notes

- Do not commit `.streamlit/secrets.toml`; secrets belong in Streamlit Cloud settings.
- Do not commit `data/pader_platform.db`; it contains local demo records.
- The current app uses SQLite for prototype persistence. Streamlit Cloud can reset local files when the app restarts, so a client demo that needs durable shared work queues should move persistence to a hosted database such as Postgres or Supabase.

## Current Workflow

- Author creates and edits a PADER draft.
- Author submits the complete PADER for review.
- Reviewer gives full-document comments and either requests changes or approves.
- Author submits approved review output for final approval.
- Approver requests changes or approves the PADER.
- Version history and audit trail are maintained for saves, workflow actions, comments, and approvals.
