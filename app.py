"""CBTI Assistant web API (FastAPI on Vercel).

User routes   : POST /api/ask, GET /api/check                (header X-Access-Code)
Admin routes  : /api/admin/*                                  (header X-Admin-Password)
"""
import hmac
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))

from fastapi import FastAPI, File, Header, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import config  # noqa: E402
import hf  # noqa: E402
import parse  # noqa: E402
import qa  # noqa: E402
from store import StoreError, get_store  # noqa: E402

app = FastAPI(title="CBTI Assistant")


# --------------------------------------------------------------------------- pages
# The pages live in the pages folder and are served by this app, so the site does not depend on static-file handling.

def _page(name):
    path = ROOT / "pages" / name
    if not path.exists():
        return HTMLResponse(f"<h1>Page file missing</h1><p>pages/{name} was not deployed. "
                            "Check that the pages folder is in the GitHub repository.</p>", status_code=500)
    return HTMLResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def home_page():
    return _page("index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return _page("admin.html")


@app.get("/api/ping")
def ping():
    """Public, no secrets: confirms the function is running and which parts were deployed."""
    return {"ok": True, "pages_deployed": [p.name for p in (ROOT / "pages").glob("*.html")],
            "catalogue_deployed": (ROOT / "data" / "catalogue.json").exists()}


# --------------------------------------------------------------------------- access control

def _same(given, expected):
    return hmac.compare_digest((given or "").encode(), (expected or "").encode())


def require_user(code):
    if config.ACCESS_CODE and not _same(code, config.ACCESS_CODE):
        time.sleep(1)  # slows down guessing
        raise HTTPException(401, "Incorrect access code.")


def require_admin(password):
    if not config.ADMIN_PASSWORD:
        raise HTTPException(503, "Admin is disabled: ADMIN_PASSWORD is not set.")
    if not _same(password, config.ADMIN_PASSWORD):
        time.sleep(1)
        raise HTTPException(401, "Incorrect admin password.")


def store_or_503():
    try:
        return get_store()
    except StoreError as error:
        raise HTTPException(503, str(error))


# --------------------------------------------------------------------------- user routes

class Question(BaseModel):
    question: str


@app.get("/api/check")
def check(x_access_code: str = Header(default="")):
    require_user(x_access_code)
    return {"ok": True}


@app.post("/api/ask")
def ask(body: Question, x_access_code: str = Header(default="")):
    require_user(x_access_code)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Please type a question.")
    if len(question) > 1000:
        raise HTTPException(400, "The question is too long (limit 1000 characters).")
    store_or_503()
    return qa.ask(question)


# --------------------------------------------------------------------------- admin routes

@app.get("/api/admin/check")
def admin_check(x_admin_password: str = Header(default="")):
    require_admin(x_admin_password)
    return {"ok": True}


@app.get("/api/admin/documents")
def list_documents(x_admin_password: str = Header(default="")):
    require_admin(x_admin_password)
    try:
        return {"documents": store_or_503().list_documents()}
    except StoreError as error:
        raise HTTPException(502, str(error))


@app.post("/api/admin/upload")
async def upload(file: UploadFile = File(...), x_admin_password: str = Header(default="")):
    require_admin(x_admin_password)
    filename = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(file.filename or "document").name).strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx"):
        raise HTTPException(400, "Only .pdf and .docx files are accepted.")
    content = await file.read()
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 4 MB. Split it into parts or compress it.")
    if not content:
        raise HTTPException(400, "The file is empty.")

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / filename
        path.write_bytes(content)
        try:
            catalogue = parse.load_catalogue()
            if suffix == ".pdf":
                title, kind, groups = parse.parse_pdf(path, parse.pillar_names(catalogue))
            else:
                title, kind, groups = parse.parse_docx(path)
        except Exception as error:  # damaged or unsupported file
            raise HTTPException(422, f"The file could not be read: {type(error).__name__}")
        related = parse.related_metrics(title, catalogue) if kind == "SOP" else []
        chunks = parse.make_chunks(filename, title, kind, groups, related)
    if not chunks:
        raise HTTPException(422, "No readable text was found. Scanned documents without a text layer are not supported.")
    try:
        store_or_503().add_document({"name": filename, "title": title, "doc_type": kind}, chunks)
    except StoreError as error:
        raise HTTPException(502, str(error))
    return {"name": filename, "title": title, "passages": len(chunks), "pending": len(chunks)}


class EmbedRequest(BaseModel):
    name: str
    batch: int = 24


@app.post("/api/admin/embed")
def embed_batch(body: EmbedRequest, x_admin_password: str = Header(default="")):
    """Embed the next batch of passages of one document. The page calls this until 'remaining' is 0."""
    require_admin(x_admin_password)
    store = store_or_503()
    try:
        rows = store.pending(body.name, max(1, min(body.batch, 32)))
        if rows:
            vectors = hf.embed([r["embed_text"] for r in rows])
            store.set_embeddings([(r["id"], v) for r, v in zip(rows, vectors)])
        return {"embedded": len(rows), "remaining": store.pending_count(body.name)}
    except (hf.HFError, StoreError) as error:
        raise HTTPException(502, str(error))


@app.delete("/api/admin/documents/{name}")
def delete_document(name: str, x_admin_password: str = Header(default="")):
    require_admin(x_admin_password)
    try:
        store_or_503().delete_document(name)
    except StoreError as error:
        raise HTTPException(502, str(error))
    return {"deleted": name}


@app.post("/api/admin/test")
def test_question(body: Question, x_admin_password: str = Header(default="")):
    """Retrieval only, with scores and without the threshold: used to choose MIN_SCORE."""
    require_admin(x_admin_password)
    store_or_503()
    try:
        passages = qa.retrieve(body.question.strip(), 8)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(502, f"Search failed: {error}")
    return {"threshold": config.MIN_SCORE, "passages": passages}


@app.get("/api/admin/health")
def health(x_admin_password: str = Header(default="")):
    require_admin(x_admin_password)
    report = {}
    try:
        report["database"] = f"ok ({len(get_store().list_documents())} documents, store: {get_store().name})"
    except Exception as error:  # noqa: BLE001
        report["database"] = f"FAILED: {error}"
    try:
        report["embeddings"] = f"ok ({len(hf.embed(['test'])[0])} dimensions, {config.EMBED_MODEL})"
    except Exception as error:  # noqa: BLE001
        report["embeddings"] = f"FAILED: {error}"
    try:
        hf.chat([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=5)
        report["answer_model"] = f"ok ({config.LLM_MODEL})"
    except Exception as error:  # noqa: BLE001
        report["answer_model"] = f"FAILED: {error}"
    report["settings"] = {"MIN_SCORE": config.MIN_SCORE, "TOP_K": config.TOP_K,
                          "access_code_set": bool(config.ACCESS_CODE), "admin_password_set": bool(config.ADMIN_PASSWORD)}
    return report
