import zipfile
import xml.etree.ElementTree as ET

from pypdf import PdfReader


def extract_text_from_pdf(uploaded_file) -> str:
    """
    Extract text from searchable PDFs.
    If the PDF is scanned/image-only, output may be poor or empty.
    """
    try:
        uploaded_file.seek(0)
        reader = PdfReader(uploaded_file)
        texts = []

        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                texts.append(page_text)

        return "\n".join(texts).strip()
    except Exception:
        return ""


def extract_text_from_docx(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as z:
            xml_content = z.read("word/document.xml")
        root = ET.fromstring(xml_content)
        texts = []
        for node in root.iter():
            if node.tag.endswith("}t") and node.text:
                texts.append(node.text)
        return "\n".join(texts).strip()
    except Exception:
        return ""


def extract_text_from_txt(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
        return uploaded_file.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_reference_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""

    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        return extract_text_from_pdf(uploaded_file)

    if filename.endswith(".docx"):
        return extract_text_from_docx(uploaded_file)

    if filename.endswith(".txt"):
        return extract_text_from_txt(uploaded_file)

    return ""

