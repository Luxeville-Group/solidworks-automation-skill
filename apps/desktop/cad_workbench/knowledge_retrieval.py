"""@brief Local-first CAD Studio RAG retrieval with an optional cloud knowledge connector."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
TOKEN_PATTERN = re.compile(r"[^\W\d_][\w+.#/-]*", re.UNICODE)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """@brief Prevent cloud RAG requests from redirecting authorization headers to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


@dataclass(frozen=True)
class KnowledgeChunk:
    """@brief A traceable knowledge retrieval result."""

    source: str
    title: str
    text: str
    score: float
    sha256: str
    provider: str = "local"


def default_knowledge_roots() -> list[Path]:
    """@brief Return built-in mechanical knowledge roots."""
    return [
        REPO_ROOT / "SKILL.md",
        REPO_ROOT / "references",
        REPO_ROOT / "subskills",
    ]


def _iter_documents(roots: Iterable[Path]) -> Iterable[Path]:
    """@brief Enumerate supported text files in knowledge roots."""
    seen: set[Path] = set()
    for root in roots:
        root = Path(root).expanduser().resolve()
        candidates = [root] if root.is_file() else root.rglob("*") if root.is_dir() else []
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield resolved


def _document_text(path: Path, max_bytes: int = 2 * 1024 * 1024) -> str:
    """@brief Read knowledge documents safely and reject excessively large inputs."""
    if path.stat().st_size > max_bytes:
        return ""
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if path.suffix.lower() == ".json":
        try:
            value = json.dumps(json.loads(value), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return ""
    return value.strip()


def _chunks(text: str, max_chars: int = 1400, overlap: int = 180) -> Iterable[str]:
    """@brief Split knowledge documents by paragraph with a small context overlap."""
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            yield current
            current = f"{current[-overlap:]}\n\n{paragraph}".strip()
        else:
            for start in range(0, len(paragraph), max_chars - overlap):
                yield paragraph[start : start + max_chars]
            current = ""
    if current:
        yield current


def _tokens(text: str) -> list[str]:
    """@brief Extract Turkish and English engineering search terms while retaining Unicode letters."""
    normalized = text.replace("İ", "i").casefold().replace("ı", "i")
    return TOKEN_PATTERN.findall(normalized)



def _title(path: Path, text: str) -> str:
    """@brief Derive a result title from its Markdown heading or filename."""
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            return line.lstrip("# ").strip()[:120]
    return path.stem.replace("_", " ")[:120]


def retrieve_local_knowledge(query: str, roots: Iterable[Path] | None = None, top_k: int = 6) -> list[KnowledgeChunk]:
    """@brief Run lightweight BM25-style retrieval over local Skill knowledge."""
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []

    documents: list[tuple[Path, str, str, list[str]]] = []
    document_frequency: dict[str, int] = {}
    for path in _iter_documents(roots or default_knowledge_roots()):
        text = _document_text(path)
        if not text:
            continue
        for chunk in _chunks(text):
            tokens = _tokens(chunk)
            documents.append((path, _title(path, chunk), chunk, tokens))
            for token in query_tokens.intersection(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1

    count = max(1, len(documents))
    ranked: list[KnowledgeChunk] = []
    for path, title, text, tokens in documents:
        token_counts = {token: tokens.count(token) for token in query_tokens if token in tokens}
        if not token_counts:
            continue
        score = 0.0
        for token, frequency in token_counts.items():
            inverse_frequency = math.log(1 + count / (1 + document_frequency.get(token, 0)))
            score += (1 + math.log(frequency)) * inverse_frequency
        normalized = score / math.sqrt(max(1, len(tokens)))
        ranked.append(
            KnowledgeChunk(
                source=str(path),
                title=title,
                text=text,
                score=round(normalized, 6),
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.source, item.sha256))
    return ranked[: max(1, min(int(top_k), 12))]


def retrieve_cloud_knowledge(query: str, config: dict[str, Any], timeout_seconds: float = 8.0) -> list[KnowledgeChunk]:
    """@brief Call the explicitly configured  HTTPS RAG  service; read tokens from environment variables only."""
    endpoint = str(config.get("endpoint") or "").strip()
    parsed_endpoint = urllib.parse.urlsplit(endpoint)
    if (
        parsed_endpoint.scheme.lower() != "https"
        or not parsed_endpoint.hostname
        or parsed_endpoint.username is not None
        or parsed_endpoint.password is not None
        or parsed_endpoint.fragment
    ):
        raise ValueError("Bulut bilgi tabanı endpoint Şunu kullanmalısınız:  HTTPS")
    token_env = str(config.get("tokenEnv") or "CAD_STUDIO_RAG_TOKEN")
    if token_env != "CAD_STUDIO_RAG_TOKEN":
        raise ValueError("Bulut bilgi tabanı token bilgisini yalnızca CAD_STUDIO_RAG_TOKEN değişkeninden okuyabilir")
    token = os.environ.get(token_env, "")
    if not token:
        raise RuntimeError(f"Bulut bilgi tabanı için ortam değişkeni eksik {token_env}")
    payload = json.dumps(
        {
            "query": query,
            "namespace": str(config.get("namespace") or "cad-studio"),
            "topK": max(1, min(int(config.get("topK") or 6), 12)),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_NoRedirectHandler())
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Bulut bilgi tabanı araması başarısız: {exc}") from exc
    items = raw.get("chunks") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("Bulut bilgi tabanı yanıtında chunks dizisi eksik")
    chunks: list[KnowledgeChunk] = []
    for item in items:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        text = str(item["text"]).strip()[:4000]
        chunks.append(
            KnowledgeChunk(
                source=str(item.get("source") or endpoint),
                title=str(item.get("title") or "Bulut bilgisi")[:120],
                text=text,
                score=float(item.get("score") or 0.0),
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                provider="cloud",
            )
        )
    return chunks


def build_job_knowledge_context(job: dict[str, Any]) -> dict[str, Any]:
    """@brief Build auditable RAG context from the objective for injection into the Codex prompt."""
    query = "\n".join(
        str(value)
        for value in (job.get("objective"), job.get("detail"), job.get("expectedOutput"), job.get("prompt"))
        if value
    )
    ui_config = job.get("uiConfig") if isinstance(job.get("uiConfig"), dict) else {}
    knowledge_config = ui_config.get("knowledgeBase") if isinstance(ui_config.get("knowledgeBase"), dict) else {}
    roots = default_knowledge_roots()
    for raw_path in knowledge_config.get("localRoots", []) if isinstance(knowledge_config.get("localRoots"), list) else []:
        path = Path(str(raw_path)).expanduser()
        if path.exists():
            roots.append(path)
    chunks = retrieve_local_knowledge(query, roots=roots, top_k=int(knowledge_config.get("topK") or 6))
    warnings: list[str] = []
    if knowledge_config.get("cloudEnabled") is True:
        capabilities = job.get("capabilities") if isinstance(job.get("capabilities"), list) else []
        if "external_network" not in capabilities:
            warnings.append("Bulut bilgi tabanı kullanılmadı: görev belirtmiyor:  external_network  capability.")
        elif not job.get("approvedAt"):
            warnings.append("Bulut bilgi tabanı kullanılmadı: dış ağ erişimi henüz onaylanmadı.")
        else:
            try:
                chunks.extend(retrieve_cloud_knowledge(query, knowledge_config))
            except (ValueError, RuntimeError) as exc:
                warnings.append(str(exc))
    chunks.sort(key=lambda item: (-item.score, item.provider, item.source))
    limited: list[KnowledgeChunk] = []
    seen: set[tuple[str, str]] = set()
    remaining_chars = 12_000
    for item in chunks:
        key = (item.source, item.sha256)
        if key in seen or remaining_chars <= 0 or len(limited) >= 12:
            continue
        seen.add(key)
        text = item.text[:remaining_chars]
        if not text:
            continue
        limited.append(
            KnowledgeChunk(
                source=item.source,
                title=item.title,
                text=text,
                score=item.score,
                sha256=item.sha256,
                provider=item.provider,
            )
        )
        remaining_chars -= len(text)
    return {
        "querySha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "providers": sorted(set(item.provider for item in limited)),
        "chunks": [asdict(item) for item in limited],
        "warnings": warnings,
    }
