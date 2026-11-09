import glob as _glob
import hashlib
import os
import sys
import re
import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Optional
from pathlib import Path
from datetime import datetime

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

# --- Pipeline configuration ----------------------------------------------
# Everything niche-specific (brand, categories, suggestion keywords, style rules) lives in a
# YAML file so the same receiver, Graft and MCP tools can serve any blog. These built-in
# defaults equal receiver/config/wayzyy.yaml; a user file only needs the keys it changes.
_DEFAULT_CONFIG = {
    "brand": {
        "name": "Wayzyy",
        "description": "Goa vacation rental & travel marketplace",
        "topic_keyword": "Goa",
        "fallback_research_prompt": "Topic: {topic}. Write a comprehensive guide for {brand}'s audience based on your knowledge.",
    },
    "categories": {
        "default": "Guide",
        "rules": [
            {"name": "Beaches", "keywords": ["beach"]},
            {"name": "Stays & Villas", "keywords": ["rental", "villa"]},
            {"name": "Food & Cafes", "keywords": ["food", "cafe"]},
            {"name": "Seasonal", "keywords": ["monsoon"]},
        ],
    },
    "suggestion": {
        "tiers": [
            ["villa", "vacation rental", "airbnb alternative", "where to stay"],
            ["best beaches", "hidden beaches", "south goa", "north goa", "itinerary", "workation"],
            ["things to do", "travel guide", "family", "budget", "monsoon", "restaurants", "cafe", "nightlife"],
        ],
    },
    "style": {
        "banned_words": [
            "delve", "tapestry", "nestled", "picture-perfect", "hidden gem", "breathtaking", "vibrant",
            "moreover", "furthermore", "in conclusion", "leverage", "utilize", "optimal", "seamlessly", "must-visit",
        ],
        "banned_openers": ["are you planning", "looking for", "if you're planning"],
        "attribution_keyword": "pexels",
        "publish_threshold": 85,
    },
    # Used only when a Superlinked SIE server is reachable (SIE_URL); otherwise ignored.
    "semantic": {
        # What an on-brand article is about. Empty means "<brand name>: <brand description>".
        "brand_profile": "Travel guide for tourists visiting Goa: where to stay, villas, beaches, food, things to do",
        # Suggest skips topics less similar than this to the brand profile.
        "min_relevance": 0.25,
        # Suggest skips topics at least this similar to an existing draft's title.
        "covered_threshold": 0.75,
        # Points added to a suggestion score per unit of relevance (relevance 0.4 -> +12).
        "relevance_weight": 30,
        # Related reads link to published posts listed in the site's blogPosts.ts. Empty means
        # <site_repo_path from the writer's config.yaml>/src/lib/blogPosts.ts.
        "site_posts_file": "",
        # A draft's text must be at least this similar to a post's title and description.
        "link_min_similarity": 0.6,
        # A draft title at least this similar to another title is flagged as a near-duplicate.
        "duplicate_threshold": 0.85,
        # Site URL of a post.
        "link_template": "/blog/{slug}",
    },
}


def _str_list(value, where: str) -> list:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"Config error: {where} must be a list of strings.")
    return value


def _load_config(path) -> dict:
    """Merge a YAML config over the built-in defaults and validate its shape."""
    import copy

    config = copy.deepcopy(_DEFAULT_CONFIG)
    if path:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"PIPELINE_CONFIG points to a missing file: {path}")
        if yaml is None:
            raise RuntimeError("PyYAML is required to read PIPELINE_CONFIG: pip install pyyaml")
        user = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(user, dict):
            raise ValueError(f"Config error: {path} must contain a mapping at the top level.")
        for section in ("brand", "categories", "suggestion", "style", "semantic"):
            if section in user:
                if not isinstance(user[section], dict):
                    raise ValueError(f"Config error: '{section}' must be a mapping.")
                config[section].update(user[section])
        if user.get("data_dir"):
            config["data_dir"] = str((path.parent / str(user["data_dir"])).resolve())
        config["_path"] = str(path)

    for rule in config["categories"]["rules"]:
        if not isinstance(rule, dict) or "name" not in rule:
            raise ValueError("Config error: each category rule needs a 'name' and a 'keywords' list.")
        _str_list(rule.get("keywords", []), f"categories.rules[{rule['name']}].keywords")
    for i, tier in enumerate(config["suggestion"]["tiers"]):
        _str_list(tier, f"suggestion.tiers[{i}]")
    _str_list(config["style"]["banned_words"], "style.banned_words")
    _str_list(config["style"]["banned_openers"], "style.banned_openers")
    sem = config["semantic"]
    for key in ("brand_profile", "site_posts_file"):
        if not isinstance(sem.get(key), str):
            raise ValueError(f"Config error: semantic.{key} must be a string.")
    if not isinstance(sem.get("link_template"), str) or "{slug}" not in sem["link_template"]:
        raise ValueError("Config error: semantic.link_template must be a string containing {slug}.")
    for key in ("min_relevance", "covered_threshold", "relevance_weight", "link_min_similarity", "duplicate_threshold"):
        if isinstance(sem.get(key), bool) or not isinstance(sem.get(key), (int, float)):
            raise ValueError(f"Config error: semantic.{key} must be a number.")
    return config


# The Graftcode gateway runs this module from a temp copy, so scripts/run_gateway.sh passes the
# config path explicitly. Unset means "use the built-in defaults".
CONFIG = _load_config(os.environ.get("PIPELINE_CONFIG"))

# Paths are configurable through environment variables so the receiver runs on
# any machine. Defaults assume the standard Wayzyy checkout under ~/Documents.
_DEFAULT_ROOT = Path.home() / "Documents" / "wayzyy-site"
WAYZYY_WRITER_DIR = Path(os.environ.get("WAYZYY_WRITER_DIR", _DEFAULT_ROOT / "article-writer"))
CHRONICALLY_ONLINE_DIR = Path(os.environ.get("WAYZYY_SCANNER_DIR", _DEFAULT_ROOT / "24-7-chronically-online"))

# Demo mode: when the real article-writer pipeline is not present, the receiver
# serves bundled sample data so anyone can run and explore the Graftcode
# integration without API keys or the private pipeline.
# The Graftcode gateway runs the module from a temp copy, so __file__ is not
# reliable there; scripts/run_gateway.sh passes WAYZYY_SAMPLE_DIR explicitly.
SAMPLE_DIR = Path(os.environ.get("WAYZYY_SAMPLE_DIR") or CONFIG.get("data_dir") or Path(__file__).resolve().parent.parent / "sample_data")
WRITER_AVAILABLE = (WAYZYY_WRITER_DIR / "agent").is_dir()
SCANNER_AVAILABLE = (CHRONICALLY_ONLINE_DIR / "main.py").is_file()
DRAFTS_DIR = Path(os.environ.get("WAYZYY_DRAFTS_DIR", (WAYZYY_WRITER_DIR / "drafts") if WRITER_AVAILABLE else (SAMPLE_DIR / "drafts")))
REVIEW_DIR = Path(os.environ.get("WAYZYY_REVIEW_DIR", (CHRONICALLY_ONLINE_DIR / "review") if SCANNER_AVAILABLE else (SAMPLE_DIR / "review")))

# The receiver is normally started by Graftcode, not by the article-writer
# process. Load the writer's environment here so the receiver reports and uses
# the same provider configuration as the real pipeline.
try:
    from dotenv import load_dotenv
    load_dotenv(WAYZYY_WRITER_DIR / ".env", override=False)
except ImportError:
    pass


# --- Typed contract -------------------------------------------------------
# Only str / int / float / bool / simple classes / list[T], which is the
# portable baseline for Graftcode grafts. Dates are ISO strings.

@dataclass
class QueueStats:
    pending_topics_count: int
    completed_drafts_count: int


@dataclass
class Providers:
    primary_llm: str
    research_engine: str
    media_engine: str


@dataclass
class PipelineStatus:
    status: str
    runtime: str
    transport: str
    active_brand: str
    queue_stats: QueueStats
    providers: Providers
    timestamp: str


@dataclass
class Topic:
    id: str
    title: str
    filename: str
    category: str
    sources_count: int
    snippet: str
    # Filled only when Superlinked SIE is reachable: similarity to the brand profile,
    # and the existing draft that already covers this topic (if any).
    relevance: Optional[float] = None
    on_brand: Optional[bool] = None
    covered_by: str = ""


@dataclass
class TopicSource:
    platform: str
    title: str
    url: str


@dataclass
class ArticleResult:
    status: str
    filename: str
    title: str
    word_count: int
    saved_to: str
    preview_snippet: str
    style_flags: list[str]


@dataclass
class DraftSummary:
    filename: str
    title: str
    word_count: int
    size_bytes: int
    updated_at: str


@dataclass
class DraftContent:
    filename: str
    content: str
    word_count: int


@dataclass
class SaveResult:
    status: str
    filename: str
    size_bytes: int
    word_count: int


@dataclass
class StyleAudit:
    filename: str
    brand_score: int
    verdict: str
    ai_cliches_found: list[str]
    passive_instances: int
    passed_checks: list[str]
    recommendations: list[str]


@dataclass
class ScanResult:
    status: str
    message: str
    output: str
    pending_topics_count: int


@dataclass
class ArticleSuggestion:
    topic: str
    rationale: str
    score: int
    matched_signals: list[str]
    sources_count: int
    relevance: Optional[float] = None
    engine: str = "keyword"
    skipped_off_brand: int = 0
    skipped_covered: int = 0


@dataclass
class RelatedLink:
    slug: str
    title: str
    url: str
    score: float
    # Already listed in this draft's "Related reads" section.
    included: bool


@dataclass
class NearDuplicate:
    title: str
    # "site" for a published post (ref is its URL) or "draft" (ref is the filename).
    kind: str
    ref: str
    score: float


@dataclass
class RelatedLinksResult:
    filename: str
    engine: str
    # URL of this draft's own published copy, when its title matches a live post.
    published_as: str
    links: list[RelatedLink]
    near_duplicates: list[NearDuplicate]
    message: str


@dataclass
class SimilarArticle:
    filename: str
    title: str
    score: float
    engine: str


@dataclass
class PullRequestResult:
    status: str
    branch: str
    target_repo: str
    target_branch: str
    pr_title: str
    commit_hash: str
    pr_url: str
    files_modified: list[str]
    message: str


SIE_URL = os.environ.get("SIE_URL", "")
SIE_MODEL = os.environ.get("SIE_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


def _embed_with_sie(texts: list) -> list:
    """Embed texts through a self-hosted Superlinked SIE server (optional)."""
    from sie_sdk import SIEClient
    from sie_sdk.types import Item

    # Fail fast when the server is down; allow time for a model's first-call download.
    client = SIEClient(SIE_URL, connect_timeout_s=3, timeout_s=120)
    results = client.encode(SIE_MODEL, [Item(text=t) for t in texts], wait_for_capacity=False)
    return [[float(v) for v in r["dense"]] for r in results]


# Embeddings keyed by "model|sha1 of the text": a draft, topic or query is embedded once,
# and an edited draft is re-embedded because its text changed. With SIE_CACHE_FILE set
# (scripts/run_gateway.sh sets it), the cache is kept on disk and survives restarts.
_EMBED_CACHE: dict = {}
SIE_CACHE_FILE = os.environ.get("SIE_CACHE_FILE", "")
_disk_cache_loaded = False


def _read_disk_cache() -> dict:
    try:
        data = json.loads(Path(SIE_CACHE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_disk_cache(new: dict) -> None:
    """Merge new vectors into the cache file (other gateway processes share it)."""
    try:
        path = Path(SIE_CACHE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = {**_read_disk_cache(), **{k: [round(x, 6) for x in v] for k, v in new.items()}}
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(merged), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[sie] could not write {SIE_CACHE_FILE}: {exc}", file=sys.stderr, flush=True)


def _embed_cached(texts: list) -> list:
    global _disk_cache_loaded
    if SIE_CACHE_FILE and not _disk_cache_loaded:
        _EMBED_CACHE.update({k: v for k, v in _read_disk_cache().items() if k not in _EMBED_CACHE})
        _disk_cache_loaded = True
    keys = [f"{SIE_MODEL}|{hashlib.sha1(t.encode('utf-8')).hexdigest()}" for t in texts]
    missing = list(dict.fromkeys(k for k in keys if k not in _EMBED_CACHE))
    if missing:
        text_of = dict(zip(keys, texts))
        new = dict(zip(missing, _embed_with_sie([text_of[k] for k in missing])))
        _EMBED_CACHE.update(new)
        if SIE_CACHE_FILE:
            _save_disk_cache(new)
    return [_EMBED_CACHE[k] for k in keys]


def _embed_drafts_and_query(query: str, files: list, texts: list) -> tuple:
    vectors = _embed_cached([query] + texts)
    return vectors[0], vectors[1:]


def _draft_title(path: Path, text: str) -> str:
    """Front-matter `title:` or the first `# ` heading, else the filename."""
    for line in text.splitlines()[:5]:
        if line.startswith("title:"):
            return line.replace("title:", "").strip().strip('"').strip("'")
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").title()


def _log_sie_fallback(exc: Exception) -> None:
    """SIE is optional, so failures fall back to keywords; say why in the gateway log."""
    print(f"[sie] {SIE_URL} unavailable, using keywords: {type(exc).__name__}: {exc}"[:500], file=sys.stderr, flush=True)


def _draft_named_for(topic: dict, files: list) -> str:
    """The draft whose filename contains the topic's slug, or "" (no embeddings needed)."""
    slugs = {_slug(topic["title"])}
    if "_" in topic["filename"]:
        slugs.add(_slug(topic["filename"].split("_", 1)[1].rsplit(".", 1)[0]))
    for f in files:
        if any(slug and slug in f.stem.lower() for slug in slugs):
            return f.name
    return ""


RELATED_HEADING = "## Related reads"


def _split_related(text: str) -> tuple:
    """Splits a draft into (body, existing "Related reads" section or "")."""
    m = re.search(rf"^{re.escape(RELATED_HEADING)}\s*$", text, re.MULTILINE)
    if not m:
        return text, ""
    rest = text[m.start():]
    nxt = re.search(r"^#{1,2} ", rest[len(RELATED_HEADING):], re.MULTILINE)
    end = m.start() + len(RELATED_HEADING) + nxt.start() if nxt else len(text)
    return text[: m.start()] + text[end:], text[m.start():end]


def _site_posts_path():
    configured = CONFIG["semantic"]["site_posts_file"].strip()
    if configured:
        return Path(configured).expanduser()
    writer_cfg = WAYZYY_WRITER_DIR / "config.yaml"
    if yaml is None or not writer_cfg.is_file():
        return None
    try:
        repo = (yaml.safe_load(writer_cfg.read_text(encoding="utf-8")) or {}).get("site_repo_path")
    except Exception:
        return None
    return Path(repo).expanduser() / "src" / "lib" / "blogPosts.ts" if repo else None


_POST_RE = re.compile(
    r'slug:\s*"([^"]+)",\s*title:\s*"((?:[^"\\]|\\.)*)",\s*description:\s*"((?:[^"\\]|\\.)*)"', re.S)


def _site_posts() -> list:
    """Published posts as (slug, title, description), read from the site's blogPosts.ts."""
    path = _site_posts_path()
    if not path or not path.is_file():
        return []
    return [(slug, title.replace('\\"', '"'), desc.replace('\\"', '"'))
            for slug, title, desc in _POST_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))]


def _post_url(slug: str) -> str:
    return CONFIG["semantic"]["link_template"].format(slug=slug)


# Titles this similar are the same article (a draft and its published copy).
_SAME_TITLE = 0.97


def _publisher_slug(title: str) -> str:
    """The site publisher's base slug: the title before ':', without '(2026)'. It may
    append a word when the slug is taken, so a published copy's slug starts with this."""
    core = re.sub(r"\(\d{4}\)", "", title.split(":")[0]).strip()
    return re.sub(r"[^a-z0-9]+", "-", core.lower()).strip("-")


def _is_published_copy(draft_title: str, post_slug: str) -> bool:
    base = _publisher_slug(draft_title)
    # Too short a base ("goa") would match most posts, so only use specific ones.
    return base.count("-") >= 2 and (post_slug == base or post_slug.startswith(base + "-"))


def _brand_profile() -> str:
    profile = CONFIG["semantic"]["brand_profile"].strip()
    return profile or f"{CONFIG['brand']['name']}: {CONFIG['brand']['description']}"


def _topic_signals(topics: list, files: list, texts: list):
    """
    With SIE reachable, returns for each topic (relevance to the brand profile,
    closest draft filename, similarity to that draft's title). Returns None when SIE
    is not configured or unreachable, so callers keep their keyword-only behaviour.

    Coverage compares the topic with draft *titles*: a short topic is loosely similar
    to every long article on the same destination, so whole-text scores over-match.
    """
    if not SIE_URL or not topics:
        return None
    titles = [_draft_title(f, t) for f, t in zip(files, texts)]
    try:
        vectors = _embed_cached([_brand_profile()] + [t["title"] for t in topics] + titles)
    except Exception as exc:
        _log_sie_fallback(exc)
        return None
    profile, topic_vecs, draft_vecs = vectors[0], vectors[1:1 + len(topics)], vectors[1 + len(topics):]
    signals = []
    for v in topic_vecs:
        relevance = _cosine(profile, v)
        best_file, best_score = "", 0.0
        for f, d in zip(files, draft_vecs):
            score = _cosine(v, d)
            if score > best_score:
                best_file, best_score = f.name, score
        signals.append((round(relevance, 3), best_file, round(best_score, 3)))
    return signals


def _to_json(result) -> str:
    """Serialize typed results to JSON for the wire.

    Typed dataclass returns reach Node callers as opaque handles in the alpha
    Graftcode SDK, so the public surface returns JSON strings while the
    dataclasses above stay as the internal schema.
    """
    if isinstance(result, list):
        return json.dumps([asdict(r) for r in result])
    return json.dumps(asdict(result))


def _writer_imports():
    """Import the production article pipeline lazily after its path is ready."""
    writer_root = str(WAYZYY_WRITER_DIR)
    if writer_root not in sys.path:
        sys.path.insert(0, writer_root)
    from agent.planner import generate_outline
    from agent.researcher import run_research
    from agent.style_checker import check_article
    from agent.writer import parse_outline, write_full_article
    return generate_outline, run_research, check_article, parse_outline, write_full_article


def _topic_snippet(content: str) -> str:
    """One-line summary for a queue entry: front-matter facts, else the first prose line."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match:
        meta = dict(
            (k.strip(), v.strip())
            for k, _, v in (line.partition(":") for line in match.group(1).splitlines())
            if v.strip()
        )
        parts = []
        if meta.get("platforms"):
            parts.append(f"Seen on: {meta['platforms']}")
        if meta.get("classification"):
            parts.append(f"Type: {meta['classification'].replace('_', ' ')}")
        if parts:
            return " · ".join(parts)
        content = content[match.end():]
    prose = next((l.strip() for l in content.splitlines() if l.strip() and not l.startswith(("#", ">", "-"))), "")
    return prose[:180]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _title_from_filename(stem: str) -> str:
    """Readable title from a queue filename such as 2026-01-05_quiet-beaches."""
    return re.sub(r"^\d{4}-\d{2}-\d{2}_?", "", stem).replace("-", " ").replace("_", " ").strip().title()


def _strip_front_matter(text: str) -> str:
    match = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
    return text[match.end():] if match else text


def _validated_name(filename) -> str:
    """Accept only a plain file name: no directories, no absolute paths, no traversal."""
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Draft filename is required.")
    name = filename.strip()
    if "\x00" in name or "/" in name or "\\" in name or name in (".", "..") or name != Path(name).name:
        raise ValueError(f"Invalid draft filename {filename!r}: only a plain file name is allowed.")
    return name


def _inside_drafts(path: Path) -> Path:
    """Resolve symlinks and require the real location to be inside the drafts folder."""
    root = DRAFTS_DIR.resolve()
    resolved = path.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError("Draft path resolves outside the drafts folder.")
    return resolved


def _find_draft(filename: str, exact_only: bool = False) -> Path:
    """Resolve an existing draft by exact name, falling back to a partial name match.

    A partial name must match exactly one draft, so a vague name never picks an arbitrary
    file. Every candidate is checked after symlink resolution, so neither a crafted name
    nor a symlink planted in the drafts folder can reach a file outside it.
    """
    name = _validated_name(filename)
    exact = DRAFTS_DIR / name
    if exact.is_file():
        return _inside_drafts(exact)
    if exact_only:
        raise ValueError(f"Draft '{filename}' not found (an exact file name is required).")
    matches = []
    for match in sorted(DRAFTS_DIR.glob(f"*{_glob.escape(name)}*")):
        if not match.is_file():
            continue
        try:
            matches.append(_inside_drafts(match))
        except ValueError:
            continue  # a symlink pointing outside is never a match
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches[:5])
        raise ValueError(f"Draft name '{filename}' is ambiguous; it matches: {names}")
    if matches:
        return matches[0]
    raise ValueError(f"Draft '{filename}' not found.")


def _draft_write_path(filename: str) -> Path:
    """Path a draft may be written to: a plain *.md name that stays inside the drafts folder."""
    name = _validated_name(filename)
    if not name.lower().endswith(".md"):
        raise ValueError("Draft filenames must end in .md.")
    return _inside_drafts(DRAFTS_DIR / name)


def _new_draft_path(topic: str) -> Path:
    """A fresh draft path for a topic. Never reuses an existing file, so edits are not overwritten.

    Topics with no Latin letters or digits (for example Hindi) get a short hash instead of
    an empty slug, so different topics do not collide.
    """
    slug = _slug(topic) or "topic-" + hashlib.sha1(topic.encode("utf-8")).hexdigest()[:8]
    base = f"{datetime.now().strftime('%Y-%m-%d')}_{slug}"
    path, n = _draft_write_path(f"{base}.md"), 2
    while path.exists():
        path, n = _draft_write_path(f"{base}-{n}.md"), n + 1
    return path


class ArticlePipelineService:
    """
    Graftcode Receiver Service:
    Exposes the Wayzyy Autonomous Content Engine methods to:
    1. Next.js / TypeScript front-end callers (via auto-generated strongly typed Graft).
    2. Claude Desktop / Cursor agents (via auto-exposed MCP tool calling).
    """

    def get_pipeline_status(self) -> str:
        """
        Returns real-time pipeline status, model providers, and queue counts.
        """
        pending_count = len(list(REVIEW_DIR.glob("*.md"))) if REVIEW_DIR.exists() else 0
        drafts_count = len(list(DRAFTS_DIR.glob("*.md"))) if DRAFTS_DIR.exists() else 0

        # Check API key configuration
        has_kimi = bool(os.environ.get("KIMI_API_KEY"))
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_groq = bool(os.environ.get("GROQ_API_KEY"))
        has_firecrawl = bool(os.environ.get("FIRECRAWL_API_KEY"))
        has_pexels = bool(os.environ.get("PEXELS_API_KEY"))

        if has_openai:
            primary_llm = f"OpenAI {os.environ.get('OPENAI_MODEL', 'gpt-5.5')} (primary; Groq fallback)"
        elif has_kimi:
            primary_llm = "Kimi Moonshot (primary; Groq fallback)"
        elif has_groq:
            primary_llm = "Groq LLaMA 3.3 70B (active; Kimi unavailable)"
        else:
            primary_llm = "Not configured"
        if not WRITER_AVAILABLE:
            primary_llm = "Demo mode (article-writer pipeline not attached)"

        return _to_json(PipelineStatus(
            status="online (demo mode)" if not WRITER_AVAILABLE else "online",
            runtime=f"Python {sys.version_info.major}.{sys.version_info.minor} (Native Graftcode Receiver)",
            transport="Hypertube / Binary RPC + WebSocket + MCP",
            active_brand=f"{CONFIG['brand']['name']} ({CONFIG['brand']['description']})",
            queue_stats=QueueStats(
                pending_topics_count=pending_count,
                completed_drafts_count=drafts_count,
            ),
            providers=Providers(
                primary_llm=primary_llm,
                research_engine="Firecrawl Web Search" if has_firecrawl else "Not configured (limited context)",
                media_engine="Pexels License API" if has_pexels else "Local placeholder (Pexels unavailable)",
            ),
            timestamp=datetime.now().isoformat(),
        ))

    def list_pending_topics(self) -> str:
        """
        Retrieves pending topics in the review queue with metadata and source counts.
        With Superlinked SIE reachable, each topic also gets a brand-relevance score and
        the existing draft that already covers it, if any.
        """
        topics = self._load_topics()[:12]
        files, texts = self._draft_corpus()
        signals = _topic_signals([asdict(t) for t in topics], files, texts)
        if signals:
            threshold = CONFIG["semantic"]["covered_threshold"]
            for t, (relevance, draft, draft_score) in zip(topics, signals):
                t.relevance = relevance
                t.on_brand = relevance >= CONFIG["semantic"]["min_relevance"]
                t.covered_by = draft if draft_score >= threshold else ""
        for t in topics:
            t.covered_by = t.covered_by or _draft_named_for(asdict(t), files)
        return _to_json(topics)

    def _load_topics(self) -> list:
        """All pending topics (private helper: Graftcode does not apply Python default args)."""
        topics = []
        if REVIEW_DIR.exists():
            for f in sorted(REVIEW_DIR.glob("*.md"), reverse=True):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    title = _title_from_filename(f.stem)
                    # extract sources count
                    sources_count = len(re.findall(r"^- \[([^\]]+)\]", content, re.MULTILINE))
                    keyword = re.search(r"^keyword:\s*(.+)$", content, re.MULTILINE)
                    if keyword:
                        title = keyword.group(1).strip().strip('"').strip("'")
                    # extract category
                    category = CONFIG["categories"]["default"]
                    for rule in CONFIG["categories"]["rules"]:
                        if any(k.lower() in title.lower() for k in rule.get("keywords", [])):
                            category = rule["name"]
                            break

                    topics.append(Topic(
                        id=f.name,
                        title=title,
                        filename=f.name,
                        category=category,
                        sources_count=sources_count,
                        snippet=_topic_snippet(content),
                    ))
                except Exception:
                    continue

        return topics

    def get_topic_sources(self, topic: str) -> str:
        """
        Retrieves verified sources, headlines, and platform URLs for a specific topic.
        """
        if not (topic or "").strip():
            raise ValueError("Topic cannot be empty.")
        sources = []
        if REVIEW_DIR.exists():
            for fname in REVIEW_DIR.glob("*.md"):
                content = fname.read_text(encoding="utf-8", errors="ignore")
                if topic.lower() in fname.name.lower() or topic.lower() in content.lower():
                    for m in re.finditer(r"^- \[([^\]]+)\] \[([^\]]+)\]\(([^)]*)\)", content, re.MULTILINE):
                        platform, title, url = m.groups()
                        sources.append(TopicSource(platform=platform, title=title, url=url))

        return _to_json(sources)

    def write_article(self, topic: str, skip_research: bool = False, extra_research: str = "") -> str:
        """
        Executes the full generation pipeline for an article:
        Topic Analysis -> Research Synthesis -> Tone Formatting -> Image Attribution -> Draft Output.
        """
        clean_topic = topic.strip()
        if not clean_topic:
            raise ValueError("Topic cannot be empty.")

        if not WRITER_AVAILABLE:
            return self._write_demo_article(clean_topic)

        generate_outline, run_research, check_article, parse_outline, write_full_article = _writer_imports()
        research_brief = ""
        if skip_research:
            research_brief = CONFIG["brand"]["fallback_research_prompt"].format(topic=clean_topic, brand=CONFIG["brand"]["name"])
        else:
            research_result = run_research(clean_topic)
            research_brief = research_result["brief"]
        if (extra_research or "").strip():
            research_brief += (
                "\n\nADDITIONAL RESEARCH PROVIDED BY THE USER (treat as authoritative):\n"
                + (extra_research or "").strip()
            )

        outline = generate_outline(clean_topic, research_brief)
        parsed = parse_outline(outline)
        parsed["title"] = parsed.get("title") or clean_topic
        parsed["primary_keyword"] = parsed.get("primary_keyword") or clean_topic
        article_content = write_full_article(parsed, research_brief)
        style_result = check_article(article_content)
        article_content = style_result["article"]

        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        target_path = _new_draft_path(clean_topic)
        filename = target_path.name
        target_path.write_text(article_content, encoding="utf-8")

        return _to_json(ArticleResult(
            status="completed",
            filename=filename,
            title=str(parsed["title"]),
            word_count=len(article_content.split()),
            saved_to=str(target_path),
            preview_snippet=article_content[:250],
            style_flags=[str(flag) for flag in style_result.get("flags", [])],
        ))

    def _write_demo_article(self, topic: str) -> str:
        """Demo mode: write a clearly-labelled placeholder draft (no LLM, no API keys)."""
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        body = (
            f"# {topic}\n\n"
            "> Demo-mode placeholder. Attach the real article-writer pipeline "
            "(set WAYZYY_WRITER_DIR) to generate a researched article.\n\n"
            f"This draft was created by `write_article(\"{topic}\")` over Graftcode.\n"
        )
        target_path = _new_draft_path(topic)
        target_path.write_text(body, encoding="utf-8")
        return _to_json(ArticleResult(
            status="completed (demo)",
            filename=target_path.name,
            title=topic,
            word_count=len(body.split()),
            saved_to=str(target_path),
            preview_snippet=body[:250],
            style_flags=["demo-mode"],
        ))

    def list_drafts(self) -> str:
        """
        Lists all generated drafts with file size, modified date, and word count.
        """
        drafts = []
        if DRAFTS_DIR.exists():
            for f in sorted(DRAFTS_DIR.glob("*.md"), reverse=True):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    title = f.stem.replace("-", " ").title()
                    for line in lines[:5]:
                        if line.startswith("title:"):
                            title = line.replace("title:", "").strip().strip('"').strip("'")
                            break
                        elif line.startswith("# "):
                            title = line.replace("# ", "").strip()
                            break

                    drafts.append(DraftSummary(
                        filename=f.name,
                        title=title,
                        word_count=len(content.split()),
                        size_bytes=f.stat().st_size,
                        updated_at=datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d, %Y %H:%M"),
                    ))
                except Exception:
                    continue

        return _to_json(drafts)

    def get_draft(self, filename: str) -> str:
        """
        Returns the raw markdown content of a draft.
        """
        file_path = _find_draft(filename)
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return _to_json(DraftContent(
            filename=file_path.name,
            content=content,
            word_count=len(content.split()),
        ))

    def save_draft(self, filename: str, content: str) -> str:
        """
        Saves updated markdown content back to the draft file.
        """
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = _draft_write_path(filename)
        file_path.write_text(content, encoding="utf-8")
        return _to_json(SaveResult(
            status="success",
            filename=file_path.name,
            size_bytes=file_path.stat().st_size,
            word_count=len(content.split()),
        ))

    def run_style_check(self, filename: str) -> str:
        """
        Heuristic style audit of a draft (a few rule-based checks, not a full style guide):
        Checks for AI clichés, banned openers, passive-voice density and basic structure.
        """
        file_path = _find_draft(filename)

        text = file_path.read_text(encoding="utf-8", errors="ignore").lower()

        style = CONFIG["style"]
        found_cliches = [w for w in style["banned_words"] if re.search(rf"\b{re.escape(w.lower())}\b", text)]

        # Check passive voice occurrences
        passive_matches = len(re.findall(r"\b(is|are|was|were|been)\s+\w+ed\b", text))

        body = _strip_front_matter(text)
        first_line = next((l for l in body.splitlines() if l.strip() and not l.startswith(("#", ">"))), "")
        passed_checks = []
        if not first_line.startswith(tuple(o.lower() for o in style["banned_openers"])):
            passed_checks.append("No banned generic opener")
        if re.search(r"^## ", text, re.MULTILINE):
            passed_checks.append("Has an H2 section structure")
        topic_keyword = CONFIG["brand"]["topic_keyword"]
        if topic_keyword and topic_keyword.lower() in text:
            passed_checks.append(f"Mentions the topic keyword ('{topic_keyword}')")
        attribution = style["attribution_keyword"]
        if attribution and attribution.lower() in text:
            passed_checks.append(f"Includes {attribution.title()} attribution")
        if not found_cliches:
            passed_checks.append("No banned AI clichés")

        # Score calculation
        deductions = len(found_cliches) * 4 + min(passive_matches, 5) * 2
        score = max(60, 100 - deductions)

        return _to_json(StyleAudit(
            filename=file_path.name,
            brand_score=score,
            verdict="Ready for Publication" if score >= style["publish_threshold"] else "Needs Minor Polish",
            ai_cliches_found=found_cliches,
            passive_instances=passive_matches,
            passed_checks=passed_checks,
            recommendations=[f"Replace cliché '{w}' with a specific detail." for w in found_cliches[:3]],
        ))

    def run_scanner(self) -> str:
        """
        Runs the real trend scanner (`main.py --scan` in the scanner project) and
        reports the resulting queue size. In demo mode it reports that nothing ran.
        """
        if not SCANNER_AVAILABLE:
            return _to_json(ScanResult(
                status="skipped (demo mode)",
                message="Scanner project not found. Set WAYZYY_SCANNER_DIR to enable real scans.",
                output="",
                pending_topics_count=len(list(REVIEW_DIR.glob("*.md"))) if REVIEW_DIR.exists() else 0,
            ))
        result = subprocess.run(
            [sys.executable, "main.py", "--scan"],
            cwd=CHRONICALLY_ONLINE_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Scanner failed: {result.stderr[-1000:]}")
        return _to_json(ScanResult(
            status="success",
            message="Scanner finished.",
            output=result.stdout[-2000:],
            pending_topics_count=len(list(REVIEW_DIR.glob("*.md"))) if REVIEW_DIR.exists() else 0,
        ))

    def suggest_next_article(self) -> str:
        """
        Ranks the pending topics by business relevance (keyword tiers) and the
        number of real trend sources, and returns the best one to write next.

        With Superlinked SIE reachable it also skips off-brand topics and topics an
        existing draft already covers (by meaning, not filename), and adds the topic's
        similarity to the brand profile to its score. Thresholds live in `semantic:`.
        """
        topics = [asdict(t) for t in self._load_topics()]
        if not topics:
            raise ValueError("No pending topics in the queue. Run the scanner first.")

        # The review queue is not pruned when an article is written, so skip topics
        # that already have a draft (matched on the topic slug inside the draft filename).
        files, texts = self._draft_corpus()
        topics = [t for t in topics if not _draft_named_for(t, files)]
        if not topics:
            raise ValueError("Every pending topic already has a draft. Run the scanner for new topics.")

        sem = CONFIG["semantic"]
        signals = _topic_signals(topics, files, texts)
        skipped_off_brand = skipped_covered = 0
        if signals:
            kept = []
            for t, (relevance, draft, draft_score) in zip(topics, signals):
                if draft_score >= sem["covered_threshold"]:
                    skipped_covered += 1
                elif relevance < sem["min_relevance"]:
                    skipped_off_brand += 1
                else:
                    kept.append({**t, "relevance": relevance})
            if not kept:
                raise ValueError(
                    f"No on-brand, uncovered topics left ({skipped_off_brand} off-brand, "
                    f"{skipped_covered} already covered by a draft). Run the scanner, or lower "
                    "semantic.min_relevance in the pipeline config."
                )
            topics = kept

        tiers = CONFIG["suggestion"]["tiers"]
        best = None
        for t in topics:
            title = t["title"].lower()
            matched, tier_score = [], 0
            for i, words in enumerate(tiers):
                hits = [w for w in words if w.lower() in title]
                if hits:
                    matched += hits
                    tier_score = max(tier_score, (len(tiers) - i) * 10)
            score = tier_score + t["sources_count"]
            if signals:
                score += round(t["relevance"] * sem["relevance_weight"])
            if best is None or score > best[0]:
                best = (score, t, matched)
        score, t, matched = best

        rationale = (
            f"Highest-scoring pending topic: {t['sources_count']} trend sources"
            + (f"; matches business signals: {', '.join(matched)}" if matched else "; no business-keyword match")
        )
        if signals:
            rationale += (
                f"; brand relevance {t['relevance']:.2f} (Superlinked SIE). Skipped "
                f"{skipped_off_brand} off-brand and {skipped_covered} already-covered topics"
            )
        return _to_json(ArticleSuggestion(
            topic=t["title"],
            rationale=rationale + ".",
            score=score,
            matched_signals=matched,
            sources_count=t["sources_count"],
            relevance=t["relevance"] if signals else None,
            engine=f"keyword + sie:{SIE_MODEL}" if signals else "keyword",
            skipped_off_brand=skipped_off_brand,
            skipped_covered=skipped_covered,
        ))

    def find_similar_articles(self, query: str, limit: int = 3) -> str:
        """
        Finds existing drafts closest in meaning to a topic or question, so a new
        article can reuse the blog's own wording and avoid duplicates.

        Uses embeddings from a self-hosted Superlinked SIE server when SIE_URL is set
        and reachable; otherwise falls back to keyword overlap (no extra service needed).
        """
        limit = self._check_similar_args(query, limit)
        files, texts = self._draft_corpus()
        results, _, _ = self._rank_similar(query, limit, files, texts, use_sie=True)
        return _to_json(results)

    def compare_search_engines(self, query: str, limit: int = 3) -> str:
        """
        Runs the same query through keyword overlap and through Superlinked SIE
        embeddings, side by side, with the time each engine took. Used by the
        dashboard to show what semantic search adds over plain keyword matching.
        """
        limit = self._check_similar_args(query, limit)
        files, texts = self._draft_corpus()
        keyword, k_engine, k_ms = self._rank_similar(query, limit, files, texts, use_sie=False)
        out = {
            "query": query,
            "drafts_searched": len(files),
            "keyword": {"engine": k_engine, "ms": k_ms, "results": [asdict(r) for r in keyword]},
            "sie": {"engine": f"sie:{SIE_MODEL}", "ms": 0, "available": False, "results": [], "message": ""},
        }
        if not SIE_URL:
            out["sie"]["message"] = "SIE_URL is not set. Start sie-server and restart with SIE_URL=http://localhost:8090."
        elif files:
            semantic, s_engine, s_ms = self._rank_similar(query, limit, files, texts, use_sie=True)
            if s_engine.startswith("sie:"):
                out["sie"].update(available=True, ms=s_ms, results=[asdict(r) for r in semantic])
            else:
                out["sie"]["message"] = f"SIE server at {SIE_URL} is not reachable."
        return json.dumps(out)

    @staticmethod
    def _check_similar_args(query: str, limit) -> int:
        if not (query or "").strip():
            raise ValueError("query must not be empty")
        return int(limit) if limit else 3  # Graftcode does not apply Python default args

    @staticmethod
    def _draft_corpus():
        files = sorted(DRAFTS_DIR.glob("*.md")) if DRAFTS_DIR.exists() else []
        return files, [f.read_text(encoding="utf-8", errors="ignore") for f in files]

    @staticmethod
    def _rank_similar(query: str, limit: int, files: list, texts: list, use_sie: bool):
        """Returns (results, engine used, milliseconds)."""
        if not files:
            return [], "keyword-overlap", 0
        t0 = time.perf_counter()
        engine, scores = "keyword-overlap", None
        if use_sie and SIE_URL:
            try:
                q_vec, doc_vecs = _embed_drafts_and_query(query, files, texts)
                scores = [_cosine(q_vec, v) for v in doc_vecs]
                engine = f"sie:{SIE_MODEL}"
            except Exception as exc:
                _log_sie_fallback(exc)
                scores = None  # SIE missing or unreachable: use the fallback
        if scores is None:
            q = _tokens(query)
            scores = [len(q & _tokens(t)) / (len(q) or 1) for t in texts]
        ms = round((time.perf_counter() - t0) * 1000)

        ranked = sorted(zip(files, texts, scores), key=lambda x: x[2], reverse=True)[: max(1, limit)]
        results = []
        for f, text, score in ranked:
            results.append(SimilarArticle(filename=f.name, title=_draft_title(f, text), score=round(score, 3), engine=engine))
        return results, engine, ms

    def suggest_related_links(self, filename: str, limit: int = 3) -> str:
        """
        Suggests published posts (from the site's blogPosts.ts) to link from this draft
        as "Related reads", with their real URLs, and flags near-duplicate titles among
        posts and drafts. Uses Superlinked SIE embeddings when reachable (off-brand
        drafts get no suggestions); otherwise falls back to shared-word overlap.
        Nothing is written: see insert_related_links.
        """
        source = _find_draft(filename)
        limit = int(limit) if limit else 3  # Graftcode does not apply Python default args
        sem = CONFIG["semantic"]
        text = source.read_text(encoding="utf-8", errors="ignore")
        body, related = _split_related(text)
        title = _draft_title(source, text)
        posts = _site_posts()
        files, texts = self._draft_corpus()
        others = [(f, _draft_title(f, t)) for f, t in zip(files, texts) if f.resolve() != source.resolve()]
        if not posts:
            path = _site_posts_path()
            return _to_json(RelatedLinksResult(
                filename=source.name, engine="none", published_as="", links=[], near_duplicates=[],
                message=f"No published posts found ({path or 'set semantic.site_posts_file'}), so there is nothing to link to.",
            ))

        post_texts = [f"{t}. {d}" for _, t, d in posts]
        engine, on_brand, link_scores, title_scores, draft_title_scores = "keyword-overlap", None, None, None, None
        if SIE_URL:
            try:
                n = len(posts)
                v = _embed_cached([body, title, _brand_profile()] + post_texts + [t for _, t, _ in posts] + [t for _, t in others])
                b, tv, profile = v[0], v[1], v[2]
                link_scores = [_cosine(b, x) for x in v[3:3 + n]]
                title_scores = [_cosine(tv, x) for x in v[3 + n:3 + 2 * n]]
                draft_title_scores = [_cosine(tv, x) for x in v[3 + 2 * n:]]
                on_brand = _cosine(profile, tv) >= sem["min_relevance"]
                engine = f"sie:{SIE_MODEL}"
            except Exception as exc:
                _log_sie_fallback(exc)
        if link_scores is None:
            words, norm = _tokens(body), title.strip().lower()
            link_scores = [len(words & _tokens(p)) / (len(_tokens(p)) or 1) for p in post_texts]
            title_scores = [1.0 if t.strip().lower() == norm else 0.0 for _, t, _ in posts]
            draft_title_scores = [1.0 if t.strip().lower() == norm else 0.0 for _, t in others]

        same = [j for j, sc in enumerate(title_scores)
                if sc >= _SAME_TITLE or _is_published_copy(title, posts[j][0])]
        own = max(same, key=lambda j: link_scores[j]) if same else None
        duplicates = [
            NearDuplicate(title=posts[j][1], kind="site", ref=_post_url(posts[j][0]), score=round(title_scores[j], 3))
            for j in sorted(range(len(posts)), key=lambda j: -title_scores[j])
            if j != own and title_scores[j] >= sem["duplicate_threshold"]
        ] + [
            NearDuplicate(title=t, kind="draft", ref=f.name, score=round(sc, 3))
            for (f, t), sc in zip(others, draft_title_scores) if sc >= sem["duplicate_threshold"]
        ]

        candidates = [
            j for j in sorted(range(len(posts)), key=lambda j: -link_scores[j])
            if j != own and title_scores[j] < sem["duplicate_threshold"] and f"]({_post_url(posts[j][0])})" not in body
        ]
        message = ""
        if on_brand is False:
            links, message = [], "This draft looks off-brand, so no related reads are suggested for it."
        else:
            floor = sem["link_min_similarity"] if on_brand is not None else 0.0
            links = [
                RelatedLink(slug=posts[j][0], title=posts[j][1], url=_post_url(posts[j][0]),
                            score=round(link_scores[j], 3), included=f"]({_post_url(posts[j][0])})" in related)
                for j in candidates if link_scores[j] > floor
            ][:limit]
            if on_brand is None:
                message = "Keyword overlap only: start Superlinked SIE (SIE_URL) for meaning-based suggestions."
            elif not links:
                message = f"No published post is similar enough (link_min_similarity {sem['link_min_similarity']})."
        return _to_json(RelatedLinksResult(
            filename=source.name, engine=engine, published_as=_post_url(posts[own][0]) if own is not None else "",
            links=links, near_duplicates=duplicates, message=message,
        ))

    def insert_related_links(self, filename: str, slugs: str) -> str:
        """
        Writes a "## Related reads" section linking to the given published posts
        (comma-separated slugs, usually from suggest_related_links), replacing any
        existing one. An empty list removes the section. Returns the saved draft's details.
        """
        source = _find_draft(filename, exact_only=True)
        posts = {slug: title for slug, title, _ in _site_posts()}
        lines = []
        for slug in [x.strip() for x in (slugs or "").split(",") if x.strip()]:
            if slug not in posts:
                raise ValueError(f"No published post with slug '{slug}'.")
            lines.append(f"[{posts[slug]}]({_post_url(slug)})")
        body, _ = _split_related(source.read_text(encoding="utf-8", errors="ignore"))
        body = body.rstrip() + "\n"
        if lines:
            # One link per paragraph: the site publisher turns each line into a <p>.
            body += f"\n{RELATED_HEADING}\n\n" + "\n\n".join(lines) + "\n"
        return self.save_draft(source.name, body)

    def push_to_github(self, filename: str) -> str:
        """
        Publishes the draft through the production publisher, pushes a new branch,
        and creates a real GitHub pull request when GITHUB_TOKEN/GH_TOKEN is set.
        """
        if not WRITER_AVAILABLE:
            raise RuntimeError("push_to_github needs the real article-writer pipeline (set WAYZYY_WRITER_DIR).")
        if str(WAYZYY_WRITER_DIR) not in sys.path:
            sys.path.insert(0, str(WAYZYY_WRITER_DIR))
        from agent.site_publisher import publish_draft

        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN/GH_TOKEN is not configured. The publisher will not push a branch "
                "until GitHub PR authorization is available."
            )

        site_dir = os.environ.get("WAYZYY_SITE_DIR")
        if not site_dir:
            raise RuntimeError("WAYZYY_SITE_DIR is not set. Point it at your local checkout of the site repo.")

        # Publishing is irreversible, so it needs the exact draft file name.
        file_path = _find_draft(filename, exact_only=True)

        result = publish_draft(str(file_path), dry_run=False)
        branch_name = f"add-blog-{result['slug']}"
        remote = subprocess.check_output(
            ["git", "-C", str(Path(site_dir)), "remote", "get-url", "origin"],
            text=True,
        ).strip()
        match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
        if not match:
            raise RuntimeError(f"Origin is not a GitHub repository: {remote}")
        owner_repo = match.group(1)
        pr_title = f"feat(blog): publish {result['slug'].replace('-', ' ').title()}"
        payload = json.dumps({
            "title": pr_title,
            "head": branch_name,
            "base": "main",
            "body": f"Generated {CONFIG['brand']['name']} article for `{result['slug']}`. Please review content, links, and image attribution before merging.",
        }).encode()
        request = urllib.request.Request(
            f"https://api.github.com/repos/{owner_repo}/pulls",
            data=payload,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "wayzyy-graftcode-publisher",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                pr = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"GitHub PR creation failed ({error.code}): {detail}") from error

        return _to_json(PullRequestResult(
            status="pr_created",
            branch=branch_name,
            target_repo=owner_repo,
            target_branch="main",
            pr_title=pr_title,
            commit_hash=result.get("commit_hash", ""),
            pr_url=pr["html_url"],
            files_modified=[str(p) for p in (result.get("tsx_path"), result.get("hero_image_path")) if p],
            message="Real GitHub pull request created. Nothing was merged into main.",
        ))
