"""JobShield Ingestion Engine: Web URL Scraper & Document Text Extractor.

Supports:
1. Live Web URL extraction (Careers portals, job boards, HTML pages) with SSRF guardrails.
2. Document text extraction (PDF via pypdf, Word .docx via python-docx & pure zipfile fallback, and plain text).
"""
import io
import re
import ipaddress
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

# SSRF Protection: Deny private, loopback, link-local, and reserved IP ranges
DENIED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def is_safe_url(url: str) -> tuple[bool, str | None]:
    """Validate that a URL is well-formed, uses HTTP(S), and does not resolve to private IPs."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            return False, "Only http:// and https:// URLs are supported."
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "Invalid URL: missing domain hostname."
        if hostname in DENIED_HOSTS or hostname.endswith(".local") or hostname.endswith(".internal"):
            return False, "Restricted address: internal and localhost domains are not allowed."
        
        # Check if hostname is an IP literal
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False, "Restricted IP: private network addresses cannot be scanned."
        except ValueError:
            pass  # Standard domain name, proceed
        
        return True, None
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"


def fetch_job_from_url(url: str, timeout_seconds: float = 8.0) -> dict:
    """Fetch and extract clean job posting text and metadata from a live web URL.
    
    Returns a dict with:
      - success (bool)
      - text (str)
      - title (str)
      - url (str)
      - error (str | None)
    """
    clean_url = url.strip()
    safe, err = is_safe_url(clean_url)
    if not safe:
        return {"success": False, "text": "", "title": "", "url": clean_url, "error": err}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout_seconds, verify=False) as client:
            resp = client.get(clean_url, headers=headers)
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "text": "",
                    "title": "",
                    "url": clean_url,
                    "error": f"Server returned HTTP status {resp.status_code} ({resp.reason_phrase}).",
                }
            html = resp.text
    except httpx.TimeoutException:
        return {
            "success": False,
            "text": "",
            "title": "",
            "url": clean_url,
            "error": f"Connection timed out while fetching {clean_url}.",
        }
    except Exception as e:
        return {
            "success": False,
            "text": "",
            "title": "",
            "url": clean_url,
            "error": f"Failed to retrieve URL: {str(e)}",
        }

    # Parse and extract text using BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        page_title = ""
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()

        # Remove irrelevant noise elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "svg"]):
            element.decompose()

        # Check for focused job content containers first
        content_container = None
        selectors = [
            'div[class*="job-description"]',
            'div[class*="jobDescription"]',
            'div[class*="job_description"]',
            'div[class*="posting-requirements"]',
            'div[class*="job-details"]',
            'div[id*="job-description"]',
            'div[id*="jobDescription"]',
            'article',
            'main',
            '[role="main"]',
        ]
        for sel in selectors:
            match = soup.select_one(sel)
            if match and len(match.get_text(strip=True)) > 150:
                content_container = match
                break

        target = content_container if content_container else (soup.body if soup.body else soup)
        
        # Convert tags to text preserving newlines
        lines = []
        for p in target.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "div"]):
            txt = p.get_text(separator=" ", strip=True)
            if txt and len(txt) > 2:
                # Avoid duplicate nested text lines
                if not lines or lines[-1] != txt:
                    lines.append(txt)

        if not lines:
            raw_text = target.get_text(separator="\n", strip=True)
        else:
            raw_text = "\n".join(lines)

        # Clean excess blank lines
        clean_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

        if len(clean_text) < 40:
            return {
                "success": False,
                "text": clean_text,
                "title": page_title,
                "url": clean_url,
                "error": "The webpage loaded, but could not find enough readable job description text.",
            }

        return {
            "success": True,
            "text": clean_text,
            "title": page_title,
            "url": clean_url,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "text": "",
            "title": "",
            "url": clean_url,
            "error": f"Error parsing HTML content: {str(e)}",
        }


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract readable text from PDF bytes using pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages):
            page_content = page.extract_text()
            if page_content:
                pages_text.append(page_content.strip())
        return "\n\n".join(pages_text).strip()
    except Exception as e:
        raise ValueError(f"Failed to parse PDF document: {e}")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract readable text from DOCX bytes using python-docx with pure-python zipfile fallback."""
    # Attempt 1: python-docx
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_txt:
                    paragraphs.append(row_txt)
        if paragraphs:
            return "\n\n".join(paragraphs).strip()
    except Exception:
        pass

    # Attempt 2: Pure standard library zipfile fallback (requires NO external dependencies)
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Find all w:t text nodes
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text_nodes = [node.text for node in tree.findall(".//w:t", namespaces) if node.text]
            return " ".join(text_nodes).strip()
    except Exception as e:
        raise ValueError(f"Failed to parse Word (.docx) document: {e}")


def extract_text_from_document(file_bytes: bytes, filename: str) -> dict:
    """Extract plain text from uploaded files (.pdf, .docx, .doc, .txt).
    
    Returns a dict with:
      - success (bool)
      - text (str)
      - filename (str)
      - char_count (int)
      - error (str | None)
    """
    fn_lower = filename.lower()
    try:
        if fn_lower.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif fn_lower.endswith(".docx") or fn_lower.endswith(".doc"):
            text = extract_text_from_docx(file_bytes)
        elif fn_lower.endswith(".txt") or fn_lower.endswith(".text") or fn_lower.endswith(".md"):
            # Plain text with encoding detection fallback
            for encoding in ["utf-8", "utf-16", "latin-1", "cp1252"]:
                try:
                    text = file_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = file_bytes.decode("utf-8", errors="replace")
        else:
            return {
                "success": False,
                "text": "",
                "filename": filename,
                "char_count": 0,
                "error": f"Unsupported file format '{filename}'. Please upload a PDF, Word (.docx), or plain text file.",
            }

        clean_text = text.strip()
        if len(clean_text) < 30:
            return {
                "success": False,
                "text": clean_text,
                "filename": filename,
                "char_count": len(clean_text),
                "error": f"Document '{filename}' appears empty or has less than 30 readable characters.",
            }

        return {
            "success": True,
            "text": clean_text,
            "filename": filename,
            "char_count": len(clean_text),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "text": "",
            "filename": filename,
            "char_count": 0,
            "error": str(e),
        }
