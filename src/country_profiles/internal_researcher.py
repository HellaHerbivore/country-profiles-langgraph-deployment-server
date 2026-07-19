import os
import re
import sys
import json
import base64
import operator
from dotenv import load_dotenv
from typing import Annotated, List, cast
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import Send
from langgraph.graph import END, START, StateGraph

import time
from google import genai
from google.genai import types, errors

# The graph is loaded by file path (see langgraph.json), not as a package, so
# sibling modules are imported the same way.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intervention_tags import INTERVENTION_TAGS, build_tag_filter  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Setup and Keys
# ---------------------------------------------------------------------------
load_dotenv()

google_api_key = os.getenv("GOOGLE_API_KEY")

if not google_api_key:
    raise ValueError("GOOGLE_API_KEY is missing from your .env file!")

llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", api_key=google_api_key, temperature=0.0)
llm_creative = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", api_key=google_api_key, temperature=0.5)

gemini_client = genai.Client(api_key=google_api_key)

# Internal Vaults
FOREIGN_ACADEMIC_STORE = "fileSearchStores/foreign-academic-sources-bqaqi98at2b3"
ON_GROUND_ADVOCATE_STORE = "fileSearchStores/onground-advocate-sources-y9falvyy92h3"
LOCAL_ACADEMIC_STORE = "fileSearchStores/local-academic-sources-cxae72dsk44n"
GOI_PIB_STORE = "fileSearchStores/governmentofindiapressinfor-7wwkcyy8ijd9"
REGULATORY_ENVIRONMENT_STORE = "fileSearchStores/regulatory-environment-o2q9s4tpmr2g"
MOVEMENT_MAP_STORE = "fileSearchStores/movement-map-jzf154g2op6j"

# Maps a human-readable store key -> (file_search_store_id, description for retrieval scoping)
STORE_REGISTRY = {
    "foreign_academic": (FOREIGN_ACADEMIC_STORE, "Foreign / international academic research sources."),
    "onground_advocate": (ON_GROUND_ADVOCATE_STORE, "On-the-ground advocate and field organisation sources."),
    "local_academic": (LOCAL_ACADEMIC_STORE, "India-based academic research sources."),
    "goi_pib": (GOI_PIB_STORE, "Government of India PIB press releases (Ministry of Fisheries, Animal Husbandry & Dairying)."),
    "regulatory_environment": (REGULATORY_ENVIRONMENT_STORE, "ICNL Civic Freedom Monitor — India's legal/regulatory environment for civil society (NGO registration, FCRA foreign-funding rules, and barriers to formation, operations, resources, expression and assembly)."),
    "movement_map": (MOVEMENT_MAP_STORE, "Movement maps — two collections of animal-advocacy organisation profiles: the ACE Movement Map 2026 (worldwide, ~950 orgs: country of registration, regions of operation, animals helped, interventions used, budget tier, recent major funders, ACE evaluation history) and the Stray Dog Institute India Partner Directory (~68 India orgs and India programs of international orgs: role in movement, movement position, intervention tags, status, location)."),
}

# Default selection until user-driven selection is wired in.
DEFAULT_SELECTED_STORES = list(STORE_REGISTRY.keys())

# Gemini File Search rejects requests with more than 5 stores ("Max 5 corpora
# can be specified"). Every retrieval must cap its store list; dimension store
# lists are priority-ordered so the cap drops the least relevant stores first.
MAX_FILE_SEARCH_STORES = 5

# Plain-language descriptions used in user-facing text. These are by DATA TYPE,
# never the internal store keys. The on-the-ground advocate source is surfaced as
# the Stray Dog Regional Advisory Panel Commentary.
DATA_SOURCE_DESCRIPTIONS = {
    "foreign_academic": "international academic research",
    "local_academic": "India-based academic research",
    "goi_pib": "Government of India press information (Ministry of Fisheries, Animal Husbandry & Dairying)",
    "onground_advocate": "commentary from the Stray Dog Regional Advisory Panel",
    "regulatory_environment": "the regulatory and legal environment for civil society (ICNL Civic Freedom Monitor)",
    "movement_map": "maps of the animal-advocacy ecosystem (ACE's global organisation profiles and Stray Dog Institute's India partner directory: focus, interventions, budgets and funders)",
}

# ---------------------------------------------------------------------------
# 1b. Static Country Context (India only — no multi-country routing)
# ---------------------------------------------------------------------------
INDIA_MACRO_STATEMENT = """India's regulatory framework is anchored in the landmark Prevention of Cruelty to Animals Act (1960) and the constitutional duty to show compassion to living creatures. While the legislative foundation is robust, it remains hampered by archaic penalty structures that fail to provide a credible deterrent against systemic abuse. Recent judicial activism, particularly from the Supreme Court, has increasingly recognized animal sentience and personhood, though these rulings often clash with regional cultural practices. The Animal Welfare Board of India (AWBI) serves as the primary statutory advisory body, but its efficacy is frequently constrained by fluctuating political priorities and bureaucratic inertia. Consequently, the macro environment is characterized by a high degree of legal idealism versus enforcement deficit."""

INDIA_DATA_POINTS = ["1.4B population", "~4.5B Land Animals/Year", "62 FAOI", "32 WAPI"]

# ---------------------------------------------------------------------------
# 1c. Field-experience lens (internal only — NEVER named in the output)
# ---------------------------------------------------------------------------
# These lessons shape what counts as an actionable opportunity / a real challenge.
# They are passed to the relevant writers as a hidden lens and must not be named,
# quoted as a framework, or referenced by label in the rendered report.
FIELD_LESSONS = """FIELD-EXPERIENCE LESSONS (internal lens — do not name or reference these in the output):
Derived from a study of food-systems advocacy campaigns in India.

For advocates / charities:
1. Contextual homework before launch: campaigns stalled when political timing, enforcement gaps, religious sensitivities, or public sentiment surfaced mid-campaign. A structured pre-launch scan of political climate, regulatory reliability, and the cultural calendar surfaces risk early.
2. Honest internal readiness check: organisations discovered missing infrastructure (follow-up capacity, lead capture, staffing) only after launch. A staffing/skills/funding/decision-making check before finalising scope right-sizes the campaign.
3. Take social identity and economic realities seriously: caste, religion, hunger, livelihoods, and price sensitivity shape what audiences find acceptable — they must be deliberately factored into messages, messengers, and partners.
4. Don't treat stakeholders as fixed obstacles: government, industry, and the public are often wrongly seen as immovable. Stakeholder mapping can reveal alternative engagement strategies — smaller/medium producers, or turning backlash into an opening.
5. Turn experience into reusable knowledge: lessons were usually only articulated after campaigns ended. Milestone and post-campaign debriefs convert ad hoc memory into reusable knowledge.
6. Use peer spaces for practical knowledge-sharing: low-burden exchanges (short calls, shared templates, peer circles) help smaller and volunteer-led groups swap knowledge on enforcement, coalitions, and capacity.

For funders:
1. Budget for structured contextual reflection, not just activity.
2. Invest in peer learning with smaller organisations in mind.
3. Be patient and flexible in sensitive contexts where caste, religion, dairy livelihoods, and hunger are salient."""


GLOBAL_CITATION_RULES = """CITATION RULES:
1. Cite using the EXACT source name as it appears in the filestore, with any file extension removed (drop .md, .pdf, etc.). Example: a file named `local_welfare_review_2021.pdf` is cited as `local_welfare_review_2021`.
2. EXCEPTION — PIB sources: any source file named `fisheries_releases_<year>` (e.g. `fisheries_releases_2024`, `fisheries_releases_2022_final`) is a yearly collection of press releases from the Government of India Press Information Bureau (PIB). These files must NEVER be cited by filename. Because one file holds many releases, each must instead be cited as: [Date of release, Ministry of Fisheries, Animal Husbandry & Dairying, Exact Title of Press Release, PIB] — with the date and title extracted from the specific release within the file.
3. Every specific detail, claim, statistic, or pivotal finding MUST carry a citation, wrapped exactly like this: <span style="color: #843468;">[citation]</span>
4. If citing multiple sources for one claim, separate them with a semicolon inside a single span: <span style="color: #843468;">[source_one; source_two]</span>
5. When in doubt, cite the source."""


# ----------------------------------------------------------------------------
# 2. Shapes of our Data (Schemas)
# ----------------------------------------------------------------------------
class PathSpec(BaseModel):
    """The normalised, internal representation of a single theory-of-change path.

    Whatever form the path arrives in (table, prose, uploaded file, pasted text),
    it is read once into this shape and every downstream step reads from here.
    """
    summary: str = Field(description="A short, neutral restatement of what the charity is proposing (2-4 sentences).")
    activities: List[str] = Field(default_factory=list, description="The concrete actions the charity plans to take.")
    outputs: List[str] = Field(default_factory=list, description="The direct products of those activities.")
    outcome_chain: List[str] = Field(default_factory=list, description="The ordered chain of expected changes, earliest first.")
    final_impact: str = Field(default="", description="The ultimate impact the charity is aiming at.")
    charity_flagged_opportunities: List[str] = Field(default_factory=list, description="Opportunities the charity itself names or clearly implies.")
    charity_assumptions: List[str] = Field(default_factory=list, description="Assumptions the charity makes (stated or clearly implied).")
    method_descriptor: str = Field(default="", description="A short label for the KIND of intervention, e.g. 'corporate cage-free commitments', 'welfare-legislation advocacy', 'public-awareness campaign'.")
    team_info: str = Field(default="", description="Any information about the charity's team, skills, capacity, or track record present in the input. Empty string if none.")


class ResearchGraphState(TypedDict):
    # --- Inputs from the client (frontend posts topic / selected_stores / document_*) ---
    topic: str
    selected_stores: List[str]
    document_b64: str
    document_mime: str
    document_filename: str
    # --- Ingest / normalise ---
    document_text: str
    path_spec: dict
    # --- Per-Send payload carriers (set by the dispatcher, read by gather_evidence) ---
    dimension: dict
    path_brief: str
    # --- Evidence gathered from the vaults (accumulated across parallel jobs) ---
    evidence_memos: Annotated[list, operator.add]
    evidence_signals: Annotated[list, operator.add]
    memos_by_key: dict
    # --- Drafted report sections ---
    stated_work: str
    methodology: str
    regulatory_section: str
    path_analysis_section: str
    windows_section: str
    challenges_section: str
    team_section: str
    followups_section: str
    experts_section: str
    evaluation_summary: str
    # --- Output ---
    final_report: str
    messages: Annotated[list, operator.add]


# ---------------------------------------------------------------------------
# 2b. Small helpers (source formatting + selection)
# ---------------------------------------------------------------------------
def _join_with_and(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _format_source_names(sources: list[str]) -> list[str]:
    """Apply the citation rules to raw filenames for user-facing display:
    drop extensions on normal files; collapse fisheries_releases_<year> files into
    a 'PIB releases from <year>' label without surfacing the raw filename."""
    normal: list[str] = []
    pib_years: set[str] = set()
    seen_normal: set[str] = set()
    for raw in sources:
        if not raw:
            continue
        name = re.sub(r"\.(md|pdf|txt|docx?)$", "", raw, flags=re.IGNORECASE)
        pib_match = re.match(r"fisheries_releases_(\d{4})", name)
        if pib_match:
            pib_years.add(pib_match.group(1))
            continue
        if name not in seen_normal:
            seen_normal.add(name)
            normal.append(name)
    result = list(normal)
    if pib_years:
        result.append(f"PIB releases from {_join_with_and(sorted(pib_years))}")
    return result


def _extract_consulted_sources(response) -> list[str]:
    """Pull file display names out of the Gemini File Search grounding metadata.
    Defensive against SDK shape changes — returns [] on any unexpected structure."""
    sources: list[str] = []
    seen: set[str] = set()
    try:
        grounding = response.candidates[0].grounding_metadata
        if not grounding:
            return sources
        chunks = getattr(grounding, "grounding_chunks", None) or []
        for chunk in chunks:
            rc = getattr(chunk, "retrieved_context", None)
            if not rc:
                continue
            name = getattr(rc, "title", None) or getattr(rc, "uri", None)
            if name and name not in seen:
                seen.add(name)
                sources.append(name)
    except (AttributeError, IndexError, TypeError):
        pass
    return sources


def _strip_system_messages(messages: list) -> list:
    """Drop progress/status emits when reading user-supplied input from the chat —
    those messages are for the user, not part of the request."""
    return [
        m for m in messages
        if not (isinstance(m, AIMessage) and getattr(m, "name", None) == "System")
    ]


def _resolve_selected_stores(selected) -> list[str]:
    """Filter a requested selection against the known stores; default to all."""
    selected = [s for s in (selected or DEFAULT_SELECTED_STORES) if s in STORE_REGISTRY]
    if not selected:
        selected = list(STORE_REGISTRY.keys())
    return selected


def _describe_data_sources(selected: list[str]) -> str:
    """Plain-language, by-type description of the data made available for a run."""
    descs = [DATA_SOURCE_DESCRIPTIONS[k] for k in selected if k in DATA_SOURCE_DESCRIPTIONS]
    return _join_with_and(descs) if descs else "the internal source vaults"


# ---------------------------------------------------------------------------
# 2c. Document ingestion (uploaded PDF / Markdown / text input)
# ---------------------------------------------------------------------------
# Plain-text-like documents we can decode directly. Anything else is treated as
# a PDF and handed to Gemini for native transcription.
_TEXT_MIME_TYPES = {"text/markdown", "text/plain", "text/x-markdown"}
_PDF_MIME_TYPES = {"application/pdf"}

_PDF_TRANSCRIBE_PROMPT = (
    "Transcribe this document into clean, faithful Markdown. Preserve headings, "
    "lists, tables, and the logical reading order. Do not summarise, interpret, "
    "or add commentary — reproduce the document's text content only. If the "
    "document contains diagrams or figures, describe them briefly in square "
    "brackets where they appear."
)


def _guess_mime(mime: str, filename: str) -> str:
    """Resolve a usable MIME type from the provided value, falling back to the
    file extension. Returns '' when the type can't be determined."""
    if mime:
        return mime.lower()
    name = (filename or "").lower()
    if name.endswith((".md", ".markdown")):
        return "text/markdown"
    if name.endswith(".txt"):
        return "text/plain"
    if name.endswith(".pdf"):
        return "application/pdf"
    return ""


def ingest_document(state: ResearchGraphState):
    """Entry node: turn an uploaded PDF/Markdown file into plain `document_text`.

    Markdown/plain text is base64-decoded directly; PDFs are transcribed to
    Markdown by Gemini (native PDF ingestion, no local parser dependency). A
    no-op when no document was supplied, so pasted-text runs are unchanged.
    """
    document_b64 = state.get("document_b64")
    if not document_b64:
        return {}

    filename = state.get("document_filename") or "uploaded document"
    mime = _guess_mime(state.get("document_mime") or "", state.get("document_filename") or "")

    try:
        raw_bytes = base64.b64decode(document_b64)
    except (ValueError, TypeError) as e:
        print(f"[ingest_document] could not decode base64 for {filename}: {e}")
        return {
            "messages": [AIMessage(
                content=f"[PROGRESS:5] Couldn't read the attached file ({filename}); continuing without it.",
                name="System",
            )]
        }

    document_text = ""

    if mime in _TEXT_MIME_TYPES:
        try:
            document_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            document_text = raw_bytes.decode("utf-8", errors="replace")

    elif mime in _PDF_MIME_TYPES:
        max_tries = 3
        for try_count in range(max_tries):
            try:
                response = gemini_client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=[
                        types.Part.from_bytes(data=raw_bytes, mime_type="application/pdf"),
                        _PDF_TRANSCRIBE_PROMPT,
                    ],
                    config=types.GenerateContentConfig(temperature=0.0),
                )
                document_text = (response.text or "").strip()
                break
            except errors.ServerError as e:
                print(f"[ingest_document] Gemini glitch on try {try_count + 1}: {e}")
                if try_count < max_tries - 1:
                    time.sleep(3)
                else:
                    print("[ingest_document] PDF transcription failed; continuing without it.")
            except Exception as e:  # defensive: never crash the run on ingestion
                print(f"[ingest_document] unexpected PDF transcription error: {e}")
                break

    else:
        print(f"[ingest_document] unsupported MIME '{mime}' for {filename}; skipping.")
        return {
            "messages": [AIMessage(
                content=f"[PROGRESS:5] The attached file type isn't supported ({filename}); continuing without it.",
                name="System",
            )]
        }

    if not document_text:
        return {
            "messages": [AIMessage(
                content=f"[PROGRESS:5] Couldn't extract any text from {filename}; continuing without it.",
                name="System",
            )]
        }

    print(f"[ingest_document] extracted {len(document_text)} chars from {filename} ({mime}).")
    return {
        "document_text": document_text,
        "messages": [AIMessage(
            content=f"[PROGRESS:5] Read the attached document ({filename}).",
            name="System",
        )]
    }


# ---------------------------------------------------------------------------
# 3. Normalise the path into one internal representation
# ---------------------------------------------------------------------------
# The path may arrive as a table, prose, an uploaded file, or pasted text. This
# is the single place that reads any of those and pulls out the evaluable
# substance. Everything downstream reads `path_spec`, never the raw entry.
path_extraction_instructions = """You are reading a single PATH from a charity's theory of change and pulling out its evaluable substance.

A theory of change lays out how a charity expects to create change: the activities it carries out, the outputs those produce, the chain of outcomes it expects (early changes in knowledge, behaviour or attitudes, then intermediate and final outcomes), and the ultimate impact it is aiming at. The input below may be a table, prose, a transcribed document, or pasted text, and may describe a single activity or a small cluster of related activities.

Read it and extract:
- summary: a short, neutral restatement of what the charity is proposing (2-4 sentences).
- activities: the concrete actions the charity plans to take.
- outputs: the direct products of those activities.
- outcome_chain: the ordered chain of changes the charity expects, earliest first.
- final_impact: the ultimate impact the charity is aiming at.
- charity_flagged_opportunities: opportunities the charity itself names or clearly implies.
- charity_assumptions: assumptions the charity makes (stated or clearly implied).
- method_descriptor: a short label for the KIND of intervention.
- team_info: any information about the charity's team, skills, capacity, or track record present in the input. Empty string if none.

Use ONLY what is in the input. Do not invent activities, outcomes, or team information. If a field has no basis in the input, return an empty list or empty string for it.

INPUT:
{input_text}"""


def _read_input_text(state: ResearchGraphState) -> str:
    """Combine the typed/pasted text and any uploaded-document text into one blob."""
    document_text = (state.get("document_text") or "").strip()
    topic = state.get("topic")
    if not topic:
        non_system = _strip_system_messages(state.get("messages") or [])
        if non_system:
            topic = non_system[-1].content
    topic = (topic or "").strip()

    parts = []
    if topic:
        parts.append(topic)
    if document_text:
        parts.append(document_text)
    return "\n\n".join(parts).strip()


def normalise_path(state: ResearchGraphState):
    combined = _read_input_text(state)

    # Empty fallback — the run still proceeds; sections will state the gap.
    if not combined:
        empty = PathSpec(summary="No theory-of-change path was provided.").model_dump()
        empty["raw_text"] = ""
        return {
            "path_spec": empty,
            "messages": [AIMessage(
                content="[PROGRESS:10] No path text was found to evaluate; continuing with what is available.",
                name="System",
            )]
        }

    structured_llm = llm.with_structured_output(PathSpec)
    try:
        spec = cast(PathSpec, structured_llm.invoke([
            SystemMessage(content=path_extraction_instructions.format(input_text=combined)),
            HumanMessage(content="Extract the path into the structured form."),
        ]))
        spec_dict = {
            "summary": spec.summary or "",
            "activities": list(spec.activities or []),
            "outputs": list(spec.outputs or []),
            "outcome_chain": list(spec.outcome_chain or []),
            "final_impact": spec.final_impact or "",
            "charity_flagged_opportunities": list(spec.charity_flagged_opportunities or []),
            "charity_assumptions": list(spec.charity_assumptions or []),
            "method_descriptor": spec.method_descriptor or "",
            "team_info": spec.team_info or "",
        }
    except Exception as e:
        print(f"[normalise_path] structured extraction failed: {e}; falling back to raw text.")
        spec_dict = PathSpec(summary=combined[:2000]).model_dump()

    # Keep the normalised raw text once (capped), for the Stated Work writer and as a fallback.
    spec_dict["raw_text"] = combined[:8000]
    if not spec_dict.get("summary"):
        spec_dict["summary"] = combined[:2000]

    print(f"[normalise_path] activities={len(spec_dict['activities'])}, outcomes={len(spec_dict['outcome_chain'])}, team_info={'yes' if spec_dict['team_info'] else 'no'}")
    return {
        "path_spec": spec_dict,
        "messages": [AIMessage(
            content="[PROGRESS:10] Read the charity's path and pulled out the activities, expected outcomes and intended impact.",
            name="System",
        )]
    }


def _path_brief(path_spec: dict) -> str:
    """A compact rendering of the path for relevance-anchoring retrievals."""
    parts = []
    if path_spec.get("summary"):
        parts.append(f"Summary: {path_spec['summary']}")
    if path_spec.get("method_descriptor"):
        parts.append(f"Method: {path_spec['method_descriptor']}")
    if path_spec.get("activities"):
        parts.append("Activities: " + "; ".join(path_spec["activities"]))
    if path_spec.get("outcome_chain"):
        parts.append("Expected outcomes: " + "; ".join(path_spec["outcome_chain"]))
    if path_spec.get("final_impact"):
        parts.append(f"Intended impact: {path_spec['final_impact']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 4. The fixed evaluation checklist (replaces auto-generated analyst angles)
# ---------------------------------------------------------------------------
# Same every run, so one path's write-up lines up against the next. Each entry is
# a vault-backed dimension: a fixed retrieval brief and a static hint of which
# stores are most relevant (intersected with the user's selection at dispatch).
EVAL_DIMENSIONS = [
    {
        "key": "reg_legal",
        "label": "Legal environment",
        "stores": ["regulatory_environment", "goi_pib", "local_academic", "foreign_academic"],
        "brief": "The laws, regulations and formal compliance requirements in India that would apply to a nonprofit carrying out this kind of work — registration, foreign-funding rules (e.g. FCRA) for foreign charities, sector-specific animal-welfare law, and any licensing or permissions the activities would require.",
    },
    {
        "key": "reg_political",
        "label": "Political environment",
        "stores": ["goi_pib", "local_academic", "onground_advocate", "regulatory_environment"],
        "brief": "The political climate in India relevant to this path — government priorities, political will or resistance on animal welfare and adjacent sectors, and how political dynamics could help or hinder the work.",
    },
    {
        "key": "reg_safety",
        "label": "Safety",
        "stores": ["onground_advocate", "local_academic", "goi_pib"],
        "brief": "Safety considerations for people carrying out this kind of work in India — risks to staff, volunteers or partners, and any documented incidents or sensitivities.",
    },
    {
        "key": "reg_charity_attitudes",
        "label": "Cultural attitudes towards foreign and local charities",
        "stores": ["onground_advocate", "local_academic", "foreign_academic", "regulatory_environment"],
        "brief": "How foreign and local charities/nonprofits are perceived in India in this domain — trust, suspicion, acceptance or hostility towards outside organisations versus homegrown ones.",
    },
    {
        "key": "path_public",
        "label": "Public engagement and public consciousness of animal welfare",
        "stores": ["local_academic", "foreign_academic", "onground_advocate"],
        "brief": "The level of public engagement and public consciousness of animal welfare in India relevant to this path — attitudes, awareness, willingness to act, and how receptive the public is likely to be to the activities.",
    },
    {
        "key": "path_tech",
        "label": "Technological feasibility",
        "stores": ["foreign_academic", "local_academic", "onground_advocate"],
        "brief": "The technological feasibility of the charity's activities in the Indian context — whether the methods or technologies the path relies on are available, mature and practical here.",
    },
    {
        "key": "path_cooperation",
        "label": "Industry and government cooperation",
        "stores": ["goi_pib", "onground_advocate", "local_academic"],
        "brief": "The willingness of industry bodies and government bodies in India to cooperate with this kind of work, including their attitudes towards cooperating with nonprofits.",
    },
    {
        "key": "windows_unspotted",
        "label": "Opportunities the charity may not have spotted",
        "stores": ["foreign_academic", "onground_advocate", "local_academic", "goi_pib", "movement_map"],
        "brief": "Time-sensitive openings or levers in India that this charity's path could exploit but may not have noticed — emerging policy moments, market shifts, coalitions, producer segments, electoral cycles or attention spikes relevant to its activities.",
    },
    {
        "key": "challenges_cultural",
        "label": "Cultural challenges",
        "stores": ["local_academic", "onground_advocate", "foreign_academic"],
        "brief": "Cultural challenges in India that could obstruct this path — social identity, religion, caste, dietary and livelihood realities, and other cultural factors that shape what is acceptable.",
    },
    {
        "key": "challenges_landscape",
        "label": "How the movement is performing",
        "stores": ["onground_advocate", "local_academic", "foreign_academic", "movement_map"],
        "brief": "Research or data on how animal-advocacy organisations in India are performing as a whole, relevant to this path — sector capacity, funding trends, documented wins and setbacks, and any survey or evaluation findings on the movement's overall health. The movement-map organisation profiles are a directory, not a scorecard: use them only for aggregate texture (budget tiers, funders, evaluation history), never as evidence of collective performance.",
    },
    {
        "key": "team_players",
        "label": "Existing players doing similar work",
        "stores": ["movement_map", "onground_advocate", "local_academic", "goi_pib"],
        # Supplement semantic retrieval with an exact intervention-tag metadata
        # filter over the movement map — tag equality catches "same intervention"
        # orgs whose profiles aren't semantically close to the path text.
        "tag_filtered": True,
        "brief": "Organisations, coalitions, government bodies or individuals already doing work similar to this charity's path in India, and what the evidence says they are currently doing — including organisations registered in or operating in India, and international organisations using similar interventions or helping the same animal groups.",
    },
    {
        "key": "effectiveness",
        "label": "Effectiveness of the charity's stated actions",
        "stores": ["foreign_academic", "local_academic", "onground_advocate", "goi_pib"],
        "brief": "Evidence in the data that BACKS UP or OBSTRUCTS the effectiveness of the charity's specific stated actions. For each stated action or method, find whether the sources show it tends to work or fail (in India where possible). Treat supporting and contradicting evidence separately, and actively surface MULTIPLE corroborating sources for each point where they exist.",
    },
]


# ---------------------------------------------------------------------------
# 5. Evidence gathering (one File Search retrieval per dimension)
# ---------------------------------------------------------------------------
def dispatch_dimensions(state: ResearchGraphState):
    """Passthrough that emits a progress note; the fan-out happens on its edge."""
    return {
        "messages": [AIMessage(
            content="[PROGRESS:15] Checking the path against the evidence vaults across the full evaluation checklist.",
            name="System",
        )]
    }


def route_to_dimensions(state: ResearchGraphState):
    """Fan out one gather_evidence job per vault-backed dimension."""
    path_spec = state.get("path_spec") or {}
    brief = _path_brief(path_spec)
    selected = _resolve_selected_stores(state.get("selected_stores"))
    return [
        Send("gather_evidence", {"dimension": dim, "path_brief": brief, "selected_stores": selected})
        for dim in EVAL_DIMENSIONS
    ]


class InterventionTagPick(BaseModel):
    """Intervention-tag codes matching a charity's proposed activities."""
    codes: List[str] = Field(
        description="1-4 codes from the intervention tag legend that best describe the charity's proposed interventions."
    )


_TAG_LEGEND = "\n".join(f"{code}: {label}" for code, label in INTERVENTION_TAGS.items())


def _select_intervention_tags(path_brief: str) -> List[str]:
    """Classify the charity's path into 1-4 taxonomy codes for the movement-map
    metadata filter."""
    picker = llm.with_structured_output(InterventionTagPick)
    result = picker.invoke([
        SystemMessage(content=(
            "Classify a charity's proposed activities against an intervention-tag legend. "
            "Return only codes that appear in the legend.\n\nLEGEND:\n" + _TAG_LEGEND
        )),
        HumanMessage(content=(
            f"The charity's proposed path:\n{path_brief}\n\n"
            "Pick the 1-4 codes that best describe the interventions it plans to use."
        )),
    ])
    codes = [c for c in (result.codes if result else []) if c in INTERVENTION_TAGS]
    return codes[:4]


def _tag_filtered_movement_scan(path_brief: str, expert_instructions: str) -> tuple[str, list]:
    """Supplementary movement-map-only retrieval filtered by intervention tag.

    Runs ONLY against the movement-map store: a metadata_filter applies to every
    store in a File Search call, and no other store carries intervention_tags
    metadata — a shared call would filter the other stores down to nothing.
    Any failure degrades to no supplement; the main retrieval stands alone.
    """
    try:
        codes = _select_intervention_tags(path_brief)
        if not codes:
            return "", []
        metadata_filter = build_tag_filter(codes)
        print(f"[gather_evidence] tag-filtered movement-map scan: {codes}")
        labels = "; ".join(INTERVENTION_TAGS[c] for c in codes)
        prompt = (
            f"The charity's proposed path is:\n{path_brief}\n\n"
            f"The files provided are organisation profiles pre-filtered to those tagged with the "
            f"intervention(s): {labels}. List the organisations these files describe and, for each, "
            "what its profile says it does that is relevant to the charity's path. Report only what "
            "the files contain; if nothing is relevant, say so using the exact phrase from the rules."
        )
        response = gemini_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=expert_instructions,
                tools=[types.Tool(file_search=types.FileSearch(
                    file_search_store_names=[MOVEMENT_MAP_STORE],
                    metadata_filter=metadata_filter,
                ))],
                temperature=0.0,
            ),
        )
        text = (response.text or "").strip()
        sources = _extract_consulted_sources(response)
        if not text or "do not contain this information" in text.lower() or not sources:
            return "", []
        return f"Organisations matched by intervention tag ({', '.join(codes)}):\n{text}", sources
    except Exception as e:
        print(f"[gather_evidence] tag-filtered scan failed (non-fatal): {e}")
        return "", []


def gather_evidence(state: ResearchGraphState):
    """Strictly retrieve, in ONE call, what the vaults hold for a single dimension.

    Carries over the strict-retrieval contract from the old expert node: no outside
    knowledge, an exact no-knowledge phrase, the PIB citation handling, and the
    citation rules — but as a single targeted retrieval rather than an interview.
    """
    dimension = state["dimension"]
    path_brief = state.get("path_brief", "")
    selected = _resolve_selected_stores(state.get("selected_stores"))

    store_keys = ([k for k in dimension.get("stores", []) if k in selected] or selected)[:MAX_FILE_SEARCH_STORES]
    active_store_ids = [STORE_REGISTRY[k][0] for k in store_keys]
    pib_selected = "goi_pib" in store_keys

    print(f"[gather_evidence] {dimension['key']} → stores={store_keys}")

    pib_rule = (
        "5. PIB SOURCES: Government of India press releases live in files named `fisheries_releases_<year>`. For any claim drawn from one of these, extract the date and exact title of the specific release — these are required for the citation, because the filename cannot serve as the citation. For all non-PIB sources, the citation is just the filename."
        if pib_selected else
        "5. (No PIB store is in scope for this retrieval.)"
    )

    expert_instructions = f"""You are a strict data-retrieval analyst evaluating one part of a charity's theory of change against internal source vaults.

FOCUS OF THIS RETRIEVAL — {dimension['label']}:
{dimension['brief']}

CRITICAL RULES:
1. You have NO knowledge outside the files in the stores provided to you.
2. If the files do not contain information relevant to the focus, say EXACTLY: "The internal vaults do not contain this information."
3. Do not use your own training data to fill gaps.
4. Be specific and preserve all figures, percentages and statistics exactly as written.
{pib_rule}
6. ONE-CLAIM-ONE-SOURCE BY DEFAULT. A citation must support the specific claim it sits next to. Place citations mid-sentence at the point each source's contribution applies.
7. WHEN YOU COMBINE SOURCES, SAY SO. If a claim genuinely combines multiple sources into a mechanism or link no single source states, flag it as synthesis ("taken together, these sources suggest…") and cite ALL contributing sources.
8. CORROBORATION IS VALUABLE. Where several sources support (or several contradict) the same point, surface them together and cite all of them — multiple corroborating citations strengthen a finding. Never invent corroboration the files don't contain.

{GLOBAL_CITATION_RULES}
"""

    prompt = (
        f"{dimension['brief']}\n\n"
        f"For relevance, the charity's proposed path is:\n{path_brief}\n\n"
        "Report only what the provided files actually contain that bears on the focus above. "
        "If they contain nothing relevant, say so using the exact phrase from the rules."
    )

    model_config = types.GenerateContentConfig(
        system_instruction=expert_instructions,
        tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=active_store_ids))],
        temperature=0.0,
    )

    max_tries = 3
    response = None
    for try_count in range(max_tries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=model_config,
            )
            break
        except errors.ServerError as e:
            print(f"[gather_evidence] server glitch on try {try_count + 1} ({dimension['key']}): {e}")
            if try_count < max_tries - 1:
                time.sleep(3)
        except Exception as e:
            # Client errors (bad request, permissions, rate caps) won't heal on
            # retry. Degrade this dimension to "no information" instead of
            # letting one bad retrieval kill the entire run.
            print(f"[gather_evidence] retrieval failed ({dimension['key']}): {e}")
            break

    if response is None:
        return {
            "evidence_memos": [{
                "key": dimension["key"], "label": dimension["label"],
                "memo": "", "no_knowledge": True, "sources": [],
            }],
            "evidence_signals": [{
                "label": dimension["label"], "sources": [], "no_knowledge": True,
            }],
            "messages": [AIMessage(
                content=f"[PROGRESS:30] The {dimension['label'].lower()} check couldn't be completed — a source vault was unreachable.",
                name="System",
            )],
        }

    answer_text = response.text if (response and response.text) else "The internal vaults do not contain this information."
    consulted_sources = _extract_consulted_sources(response) if response else []
    used_files = bool(consulted_sources) or (
        response is not None
        and response.candidates
        and response.candidates[0].grounding_metadata is not None
    )

    no_knowledge = (not used_files) or ("do not contain this information" in answer_text.lower())
    memo = "" if no_knowledge else answer_text

    if dimension.get("tag_filtered") and "movement_map" in store_keys:
        tag_memo, tag_sources = _tag_filtered_movement_scan(path_brief, expert_instructions)
        if tag_memo:
            memo = f"{memo}\n\n{tag_memo}" if memo else tag_memo
            consulted_sources = consulted_sources + [s for s in tag_sources if s not in consulted_sources]
            no_knowledge = False

    formatted_sources = _format_source_names(consulted_sources)
    if no_knowledge:
        signal_text = f"[PROGRESS:30] No vault information found for the {dimension['label'].lower()} check."
    elif formatted_sources:
        signal_text = f"[PROGRESS:30] Consulted {_join_with_and(formatted_sources)} for the {dimension['label'].lower()} check."
    else:
        signal_text = f"[PROGRESS:30] Returned information for the {dimension['label'].lower()} check."

    return {
        "evidence_memos": [{
            "key": dimension["key"], "label": dimension["label"],
            "memo": memo, "no_knowledge": no_knowledge, "sources": consulted_sources,
        }],
        "evidence_signals": [{
            "label": dimension["label"], "sources": consulted_sources, "no_knowledge": no_knowledge,
        }],
        "messages": [AIMessage(content=signal_text, name="System")],
    }


def collect_sections(state: ResearchGraphState):
    """Join point — waits for all parallel retrievals, then reports what was found.
    No abort: thin knowledge is handled per-paragraph by the writers."""
    signals = state.get("evidence_signals", []) or []

    all_sources: list[str] = []
    seen_sources: set[str] = set()
    empty_labels: list[str] = []
    seen_empty: set[str] = set()
    for sig in signals:
        label = sig.get("label") or "an evaluation point"
        if sig.get("no_knowledge") and label not in seen_empty:
            seen_empty.add(label)
            empty_labels.append(label)
        for src in sig.get("sources", []) or []:
            if src not in seen_sources:
                seen_sources.add(src)
                all_sources.append(src)

    formatted_sources = _format_source_names(all_sources)
    parts: list[str] = ["[PROGRESS:50] Gathered the available evidence from the source vaults."]
    if formatted_sources:
        parts.append("")
        parts.append(f"Drawing on: {_join_with_and(formatted_sources)}.")
    if empty_labels:
        parts.append("")
        parts.append(
            "Some checks found no information in the available sources and will be flagged for more data: "
            + _join_with_and([lbl.lower() for lbl in empty_labels]) + "."
        )

    return {"messages": [AIMessage(content="\n".join(parts), name="System")]}


def prepare_writing(state: ResearchGraphState):
    """Bucket the gathered memos by dimension key so each writer reads only its own."""
    memos = state.get("evidence_memos", []) or []
    memos_by_key = {m["key"]: m for m in memos}
    return {
        "memos_by_key": memos_by_key,
        "messages": [AIMessage(
            content="[PROGRESS:55] Drafting the evaluation — regulatory picture, path relevance, opportunities, challenges and team in parallel.",
            name="System",
        )]
    }


# ---------------------------------------------------------------------------
# 5b. Shared writer scaffolding
# ---------------------------------------------------------------------------
# Universal rules every section writer inherits.
WRITER_BASE_RULES = """SHARED RULES:
1. Write in objective, third-person prose. Never mention this tool, the analysis software, "the model", AI personas, interviewers, or the internal source/vault names.
2. Preserve every inline citation EXACTLY as given — the <span> wrapper and its contents. Never reformat, rename, shorten or drop a citation.
3. Never summarise away numeric or statistical data. Preserve all figures, percentages and currency values exactly.
4. Work point by point. Include what the evidence supports; where a specific point isn't supported by the provided material, write a short, plain-language note that more data is needed on that point and move on. Never write internal markers verbatim, never invent content, and never drop a subsection or its title."""

# Used inside a memo block to tell the writer (not the reader) that a point is empty.
_GAP_MARKER = "(No relevant information was found in the available sources for this point. Write a brief, plain-language note that the tool needs more data here, and keep the subsection in place.)"


def _format_memo_block(memos_by_key: dict, key: str, fallback_label: str) -> str:
    m = memos_by_key.get(key)
    label = (m or {}).get("label") or fallback_label
    if m and not m.get("no_knowledge") and (m.get("memo") or "").strip():
        return f"### {label}\n{m['memo'].strip()}"
    return f"### {label}\n{_GAP_MARKER}"


def _bullet_list(items: list[str]) -> str:
    items = [i for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else "(none provided)"


def _md_table_cell(text) -> str:
    """Flatten a value into a single markdown table cell: collapse whitespace,
    neutralise pipes, and show an em-dash for empty cells."""
    cell = " ".join(str(text or "").replace("|", "/").split())
    return cell or "—"


def _render_md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a markdown pipe table at the headers' width, padding short rows."""
    width = len(headers)
    lines = [
        "| " + " | ".join(_md_table_cell(h) for h in headers) + " |",
        "|" + " --- |" * width,
    ]
    for row in rows:
        padded = (list(row) + [""] * width)[:width]
        lines.append("| " + " | ".join(_md_table_cell(c) for c in padded) + " |")
    return "\n".join(lines)


def _llm_text(result) -> str:
    text = result.content
    if isinstance(text, list):
        text = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in text])
    return str(text)


# Structured-output schemas for the multi-subsection writers. Each field is the
# BODY of one subsection (no heading) — the canonical Title-Case headings are
# injected deterministically by _render_subsections so they can never drift or
# duplicate.
class RegulatoryContent(BaseModel):
    legal: str = Field(default="", description="Body for the Legal subsection. No heading.")
    political: str = Field(default="", description="Body for the Political subsection. No heading.")
    safety: str = Field(default="", description="Body for the Safety subsection. No heading.")
    charity_attitudes: str = Field(default="", description="Body on cultural attitudes towards foreign/local charities. No heading.")


class PathAnalysisContent(BaseModel):
    public_engagement: str = Field(default="", description="Body for the Public Engagement subsection. No heading.")
    tech_feasibility: str = Field(default="", description="Body for the Tech Feasibility subsection. No heading.")
    industry_government_cooperation: str = Field(default="", description="Body for the Industry and Government Cooperation subsection. No heading.")


class WindowsContent(BaseModel):
    flagged: str = Field(default="", description="Body summarising opportunities the charity itself flagged. No heading.")
    unspotted: str = Field(default="", description="Body for opportunities the charity likely hasn't spotted. No heading.")


class ChallengesContent(BaseModel):
    effectiveness: str = Field(default="", description="Body for the Effectiveness Check: action-by-action, every claim cited, no summary preamble. No heading.")
    cultural: str = Field(default="", description="Body for the Cultural Challenges subsection. No heading.")
    landscape: str = Field(default="", description="Body for the How the Movement Is Performing subsection. No heading.")


class TeamContent(BaseModel):
    capacity: str = Field(default="", description="Body for the Team Capacity subsection. No heading.")
    track_record: str = Field(default="", description="Body for the Track Record and Achievements subsection. No heading.")
    existing_players: str = Field(default="", description="Body for the Existing Players Doing Similar Work subsection. No heading.")


def _render_subsections(pairs: list[tuple[str, str]]) -> str:
    """Inject canonical '### a. …' headings around body-only fields."""
    blocks = []
    for heading, body in pairs:
        body = (body or "").strip() or (
            "There isn't enough information in the available sources to speak to this point yet; more data is needed."
        )
        blocks.append(f"### {heading}\n\n{body}")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# 5c. Section writers
# ---------------------------------------------------------------------------
# One row of the stated-work table: an activity and its own expected-outcome chain.
class ActivityOutcomeRow(BaseModel):
    activity: str = Field(description="One concrete activity the charity plans to carry out, stated briefly.")
    outcomes: List[str] = Field(default_factory=list, description="The ordered chain of outcomes the charity expects to follow from THIS activity, earliest first. Each entry is one short phrase.")


class StatedWorkContent(BaseModel):
    impact_paragraph: str = Field(default="", description="A brief paragraph (1-3 sentences) stating the ultimate impact the charity is aiming at.")
    rows: List[ActivityOutcomeRow] = Field(default_factory=list, description="One row per stated activity.")


stated_work_instructions = """You are preparing the "Charity's Stated Work" snapshot of an evaluation: a glanceable, faithful restatement of what the charity put forward, with NO evaluation, judgement or recommendations.

From the path details below, produce:
- impact_paragraph: a brief paragraph (1-3 sentences) stating the ultimate impact the charity is aiming at. If no ultimate impact was stated, say plainly that the charity did not state one.
- rows: one row per stated activity. For each activity, give the ordered chain of outcomes the charity expects to follow from THAT activity, earliest first. Use only outcomes the charity states or clearly implies; where several activities share the same expected outcomes, repeat them on each relevant row. Keep every activity and outcome to one short phrase. If no outcomes are tied to an activity, return an empty list for it.

Use ONLY the details provided. Do not invent activities or outcomes, do not assess feasibility, do not cite sources, and do not mention this tool.

PATH DETAILS:
{details}"""


def write_stated_work(state: ResearchGraphState):
    """Section 1 — glanceable snapshot of the charity's path: the intended
    ultimate impact as a brief paragraph, then an activities × expected-outcomes
    table. Emitted into the stream as soon as it is ready (inside [STATED_WORK]
    markers) so the user can read it while the rest of the report runs."""
    ps = state.get("path_spec") or {}
    details = (
        f"Summary: {ps.get('summary', '')}\n\n"
        f"Activities:\n{_bullet_list(ps.get('activities'))}\n\n"
        f"Outputs:\n{_bullet_list(ps.get('outputs'))}\n\n"
        f"Expected chain of outcomes (earliest first):\n{_bullet_list(ps.get('outcome_chain'))}\n\n"
        f"Intended ultimate impact: {ps.get('final_impact', '') or '(not stated)'}\n\n"
        f"Original text (for attributing outcomes to activities):\n{(ps.get('raw_text') or '')[:4000]}"
    )

    impact_paragraph = ""
    rows: list[list[str]] = []
    try:
        res = cast(StatedWorkContent, llm.with_structured_output(StatedWorkContent).invoke([
            SystemMessage(content=stated_work_instructions.format(details=details)),
            HumanMessage(content="Produce the impact paragraph and the activity rows."),
        ]))
        impact_paragraph = " ".join((res.impact_paragraph or "").split())
        rows = [
            [r.activity] + [o for o in (r.outcomes or []) if str(o).strip()]
            for r in (res.rows or []) if (r.activity or "").strip()
        ]
    except Exception as e:
        print(f"[write_stated_work] structured snapshot failed: {e}; falling back to the normalised path.")

    if not rows:
        chain = "; ".join(ps.get("outcome_chain") or [])
        rows = [[a] + ([chain] if chain else []) for a in (ps.get("activities") or [])]
    if not impact_paragraph:
        impact_paragraph = (ps.get("final_impact") or "").strip() or (
            "The charity did not state an ultimate impact for this path."
        )

    if rows:
        outcome_cols = max(len(r) - 1 for r in rows)
        headers = ["Activity", "First Expected Outcome"] + ["Then"] * max(outcome_cols - 1, 0)
        table = _render_md_table(headers, rows)
    else:
        table = "No activities were stated in the submitted path."

    section = f"**Intended ultimate impact:** {impact_paragraph}\n\n{table}"

    return {
        "stated_work": section,
        "messages": [AIMessage(
            # [STATED_WORK]…[/STATED_WORK] is sliced out of the stream by the
            # frontend and rendered above the loading indicator while the rest
            # of the report is still being generated.
            content=(
                "[PROGRESS:18] Summarised the charity's stated work — activities and expected outcomes.\n\n"
                f"[STATED_WORK]\n{section}\n[/STATED_WORK]"
            ),
            name="System",
        )],
    }


def write_methodology(state: ResearchGraphState):
    """Section 3 — plain-language description of how the analysis was carried out.
    No code, function, variable or internal store names; data described by type."""
    selected = _resolve_selected_stores(state.get("selected_stores"))
    data_types = _describe_data_sources(selected)
    text = (
        "This evaluation took the single path the charity submitted and broke it down into its core "
        "parts — the activities the charity plans to carry out, the outputs those produce, the chain of "
        "outcomes expected to follow, and the ultimate impact it is aiming at.\n\n"
        "Each part of the path was then checked, point by point, against the information available for "
        f"India: {data_types}; alongside general knowledge of how comparable interventions tend to "
        "perform. The same fixed checklist was applied to every path, so the evaluation consistently "
        "covers the regulatory environment, the relevance and feasibility of the path, windows of "
        "opportunity, challenges and risks, the team, and suggested follow-ups and contacts.\n\n"
        "Where the available information did not cover a specific point, the evaluation says so plainly "
        "rather than filling the gap with speculation. Findings are drawn from the sources above, and "
        "specific claims are cited to the source they came from."
    )
    return {
        "methodology": text,
        "messages": [AIMessage(content="[PROGRESS:20] Recorded how the analysis was carried out.", name="System")],
    }


regulatory_instructions = """You are writing the "Regulatory Environment for Nonprofits in India" section of a theory-of-change evaluation for an animal-advocacy charity operating in India.

Background context on India (use as orientation; cite specific claims to the research memos where they support them — do not cite this background itself):
{india_macro}

Provide the BODY TEXT for four subsections, anchored in their matching research memos below:
- legal — the laws, regulations and compliance requirements a nonprofit doing this work would face.
- political — the political climate relevant to the path.
- safety — safety considerations for people carrying out this work.
- charity_attitudes — cultural attitudes towards foreign and local charities.

Do NOT include any markdown headings in your fields — the headings are added automatically. For any subsection whose memo indicates nothing relevant was found (for example, the specific laws or licensing rules a nonprofit must follow are not covered), write one short, plain-language note that the tool needs more data on that point.

{base_rules}

{citation_rules}

Research memos:
{memos}"""


def write_regulatory(state: ResearchGraphState):
    memos_by_key = state.get("memos_by_key") or {}
    blocks = "\n\n".join([
        _format_memo_block(memos_by_key, "reg_legal", "Legal environment"),
        _format_memo_block(memos_by_key, "reg_political", "Political environment"),
        _format_memo_block(memos_by_key, "reg_safety", "Safety"),
        _format_memo_block(memos_by_key, "reg_charity_attitudes", "Cultural attitudes towards foreign and local charities"),
    ])
    system_message = regulatory_instructions.format(
        india_macro=INDIA_MACRO_STATEMENT,
        base_rules=WRITER_BASE_RULES,
        citation_rules=GLOBAL_CITATION_RULES,
        memos=blocks,
    )
    res = cast(RegulatoryContent, llm.with_structured_output(RegulatoryContent).invoke(
        [SystemMessage(content=system_message), HumanMessage(content="Write the four subsection bodies.")]
    ))
    return {"regulatory_section": _render_subsections([
        ("a. Legal Environment for Nonprofits in India", res.legal),
        ("b. Political Environment for Nonprofits in India", res.political),
        ("c. Safety for Nonprofit Operations in India", res.safety),
        ("d. Cultural Attitudes Towards Foreign and Local Charities", res.charity_attitudes),
    ])}


path_analysis_instructions = """You are writing the "Path Analysis" section of a theory-of-change evaluation for an animal-advocacy charity operating in India. This section checks how RELEVANT and workable the charity's path is against the realities below.

The charity's proposed path:
{path_brief}

Provide the BODY TEXT for three subsections, each judged against its matching research memo:
- public_engagement — how receptive the public is (incl. public consciousness of animal welfare).
- tech_feasibility — whether the methods the path relies on are technically feasible here.
- industry_government_cooperation — how willing industry and government bodies are to cooperate, incl. their attitudes to working with nonprofits.

Do NOT include any markdown headings in your fields — the headings are added automatically. For any subsection whose memo indicates nothing relevant was found, write a short, plain-language note that the tool needs more data on that point.

{base_rules}

{citation_rules}

Research memos:
{memos}"""


def write_path_analysis(state: ResearchGraphState):
    memos_by_key = state.get("memos_by_key") or {}
    blocks = "\n\n".join([
        _format_memo_block(memos_by_key, "path_public", "Public engagement"),
        _format_memo_block(memos_by_key, "path_tech", "Tech feasibility"),
        _format_memo_block(memos_by_key, "path_cooperation", "Industry and government cooperation"),
    ])
    system_message = path_analysis_instructions.format(
        path_brief=_path_brief(state.get("path_spec") or {}),
        base_rules=WRITER_BASE_RULES,
        citation_rules=GLOBAL_CITATION_RULES,
        memos=blocks,
    )
    res = cast(PathAnalysisContent, llm.with_structured_output(PathAnalysisContent).invoke(
        [SystemMessage(content=system_message), HumanMessage(content="Write the three subsection bodies.")]
    ))
    return {"path_analysis_section": _render_subsections([
        ("a. Public Engagement", res.public_engagement),
        ("b. Tech Feasibility", res.tech_feasibility),
        ("c. Industry and Government Cooperation", res.industry_government_cooperation),
    ])}


windows_instructions = """You are writing the "Windows of Opportunity" section of a theory-of-change evaluation for an animal-advocacy charity operating in India.

Provide the BODY TEXT for two subsections (no markdown headings — they are added automatically):
- flagged — summarise the opportunities the charity itself put forward, listed here. If none were provided, say so plainly.
  Charity-flagged opportunities:
  {flagged}
- unspotted — using the research memo below, identify time-sensitive openings the charity likely hasn't spotted: concrete levers an advocate could act on (a policy moment, a producer segment, a coalition, an attention spike). Be concrete about WHY each is time-sensitive. Ground each in the evidence; where the evidence shows no time-sensitive opening, say so rather than inventing urgency. If the memo indicates nothing relevant was found, write a short, plain-language note that the tool needs more data.

[INTERNAL GUIDANCE — DO NOT name, quote, or reference this in your output. Let these field-experience lessons shape what you treat as a real, actionable opportunity:
{field_lessons}]

{base_rules}

{citation_rules}

Research memo (for unspotted opportunities):
{memo}"""


def write_windows(state: ResearchGraphState):
    ps = state.get("path_spec") or {}
    memos_by_key = state.get("memos_by_key") or {}
    memo_block = _format_memo_block(memos_by_key, "windows_unspotted", "Opportunities the charity may not have spotted")
    system_message = windows_instructions.format(
        flagged=_bullet_list(ps.get("charity_flagged_opportunities")),
        field_lessons=FIELD_LESSONS,
        base_rules=WRITER_BASE_RULES,
        citation_rules=GLOBAL_CITATION_RULES,
        memo=memo_block,
    )
    res = cast(WindowsContent, llm.with_structured_output(WindowsContent).invoke(
        [SystemMessage(content=system_message), HumanMessage(content="Write the two subsection bodies.")]
    ))
    return {"windows_section": _render_subsections([
        ("a. Opportunities Flagged by the Charity", res.flagged),
        ("b. Opportunities Likely Unspotted by the Charity", res.unspotted),
    ])}


challenges_instructions = """You are writing the "Challenges, Risks & Effectiveness" section of a theory-of-change evaluation for an animal-advocacy charity operating in India.

The charity's proposed path:
{path_brief}

Provide the BODY TEXT for three subsections (no markdown headings — they are added automatically):
- effectiveness — Check the charity's stated actions against the evidence. Go ACTION BY ACTION: for each action, state whether the data BACKS IT UP or OBSTRUCTS its effectiveness, and cite every claim. Do NOT open with a general summary paragraph. Favour MULTIPLE corroborating citations where the data contains them. Where the data is silent on an action, write a short, plain-language note that the tool needs more data — do NOT fall back on uncited general knowledge.
- cultural — cultural challenges that could obstruct the path, from its memo.
- landscape — how animal-advocacy organisations in India are performing as a whole, from its memo: sector capacity, funding trends, documented wins and setbacks, and any survey or evaluation findings on movement health. Where the memo shows other organisations working on the same interventions, present that neutrally or as coalition potential — never frame a well-populated space as a negative by itself.

For cultural, where the memo indicates nothing relevant was found, write a short, plain-language note that the tool needs more data on that point. For landscape, be upfront about data scarcity: if its memo indicates little or nothing was found, state plainly that the tool does not yet hold sector-level performance data on the Indian animal-advocacy movement and this subsection cannot be answered until such data is added — do not pad the gap with adjacent material.

[INTERNAL GUIDANCE — DO NOT name, quote, or reference this in your output. Let these field-experience lessons sharpen which challenges genuinely matter:
{field_lessons}]

{base_rules}

{citation_rules}

Research memos:
{memos}"""


def write_challenges(state: ResearchGraphState):
    memos_by_key = state.get("memos_by_key") or {}
    blocks = "\n\n".join([
        _format_memo_block(memos_by_key, "effectiveness", "Effectiveness of the charity's stated actions"),
        _format_memo_block(memos_by_key, "challenges_cultural", "Cultural challenges"),
        _format_memo_block(memos_by_key, "challenges_landscape", "How the movement is performing"),
    ])
    system_message = challenges_instructions.format(
        path_brief=_path_brief(state.get("path_spec") or {}),
        field_lessons=FIELD_LESSONS,
        base_rules=WRITER_BASE_RULES,
        citation_rules=GLOBAL_CITATION_RULES,
        memos=blocks,
    )
    res = cast(ChallengesContent, llm.with_structured_output(ChallengesContent).invoke(
        [SystemMessage(content=system_message), HumanMessage(content="Write the three subsection bodies.")]
    ))
    return {"challenges_section": _render_subsections([
        ("a. Effectiveness Check", res.effectiveness),
        ("b. Cultural Challenges", res.cultural),
        ("c. How the Movement Is Performing", res.landscape),
    ])}


team_instructions = """You are writing the "Team" section of a theory-of-change evaluation for an animal-advocacy charity operating in India.

Provide the BODY TEXT for three subsections (no markdown headings — they are added automatically):
- capacity — the team's capacity, talents and skills, using ONLY the team information provided below.
- track_record — the team's track record and achievements, using ONLY the team information provided below.
- existing_players — using the research memo below, organisations, coalitions, government bodies or individuals already doing similar work in India and what the evidence says they are doing.

For capacity and track_record: if little or nothing was provided, state plainly that the tool needs more data on the team (this information isn't yet available to the tool). Do not invent team details.
Team information from the charity:
{team_info}

For existing_players: do not treat any player as a fixed obstacle — note where one could be a partner or an alternative ally. Where another organisation runs the SAME or overlapping interventions as this charity, present that overlap explicitly as alliance or coalition potential. If carrying out this path would likely face significant regulatory hurdles, give existing players more weight (as partners or as groups that already navigate those hurdles). Where the memo indicates nothing relevant was found, write a short, plain-language note that the tool needs more data.

{base_rules}

{citation_rules}

Research memo (existing players):
{memo}"""


def write_team(state: ResearchGraphState):
    ps = state.get("path_spec") or {}
    memos_by_key = state.get("memos_by_key") or {}
    team_info = (ps.get("team_info") or "").strip() or "(no team information was provided in the path)"
    memo_block = _format_memo_block(memos_by_key, "team_players", "Existing players doing similar work")
    system_message = team_instructions.format(
        team_info=team_info,
        base_rules=WRITER_BASE_RULES,
        citation_rules=GLOBAL_CITATION_RULES,
        memo=memo_block,
    )
    res = cast(TeamContent, llm.with_structured_output(TeamContent).invoke(
        [SystemMessage(content=system_message), HumanMessage(content="Write the three subsection bodies.")]
    ))
    return {"team_section": _render_subsections([
        ("a. Team Capacity", res.capacity),
        ("b. Track Record and Achievements", res.track_record),
        ("c. Existing Players Doing Similar Work", res.existing_players),
    ])}


def _sections_digest(state: ResearchGraphState, trim: int | None = 1200) -> str:
    """A digest of the drafted analysis sections, for the derived writers."""
    labelled = [
        ("Regulatory Environment for Nonprofits in India", state.get("regulatory_section", "")),
        ("Path Analysis", state.get("path_analysis_section", "")),
        ("Windows of Opportunity", state.get("windows_section", "")),
        ("Challenges, Risks & Effectiveness", state.get("challenges_section", "")),
        ("Team", state.get("team_section", "")),
    ]
    parts = []
    for title, txt in labelled:
        txt = (txt or "").strip()
        if not txt:
            continue
        if trim and len(txt) > trim:
            txt = txt[:trim] + " …"
        parts.append(f"## {title}\n{txt}")
    return "\n\n".join(parts)


def write_followups(state: ResearchGraphState):
    """Section 10 — depends on the gaps surfaced across the analysis sections."""
    ps = state.get("path_spec") or {}
    system_message = (
        "You are writing the \"Follow-Up Questions for the Charity\" section of an evaluation. Based on the "
        "evaluation so far and the gaps it surfaced, write a concise, prioritised list of the most useful "
        "questions to put to the charity — focused on its stated assumptions, any missing team or "
        "track-record information, and anywhere the evaluation lacked the data to reach a view. Write the "
        "questions as a numbered list, objective tone. Do not mention this tool or internal sources. "
        "Do not include a section heading; start directly with the questions."
    )
    human = (
        f"The charity's stated assumptions:\n{_bullet_list(ps.get('charity_assumptions'))}\n\n"
        f"The evaluation so far:\n{_sections_digest(state)}"
    )
    result = llm.invoke([SystemMessage(content=system_message), HumanMessage(content=human)])
    return {
        "followups_section": _llm_text(result),
        "messages": [AIMessage(content="[PROGRESS:80] Drafted follow-up questions and on-the-ground contacts.", name="System")],
    }


experts_instructions = """You are writing the "On-the-Ground Experts" section of a theory-of-change evaluation for work in India. Richer expert data will be added to this tool later; for now, work with what the provided files contain.

From the files, surface real, named people and organisations who could be worth contacting — in particular the AUTHORS of the research sources and any ORGANISATIONS or officials named in the government information — who are relevant to the gaps and findings below. Only use names that actually appear in the files; do not invent people or organisations.

Do not include a top-level section heading; start directly with the experts. For each expert or organisation, use this format:
### <Name or Organisation>
- **Why Selected:** tie back to a specific gap or finding from the evaluation.
- **Questions to Ask:** 2-3 concrete questions.
- **Contact Details:** any contact details present in the files; if none are available, say plainly that contact details aren't available to the tool yet.

If the files surface no relevant names at all, write a short, plain-language note that the tool needs more data to recommend specific experts.

{base_rules}

{citation_rules}

Gaps and findings to tie experts to:
{gaps_digest}"""


def write_experts(state: ResearchGraphState):
    """Section 11 — gap-dependent retrieval for named experts/organisations to contact."""
    selected = _resolve_selected_stores(state.get("selected_stores"))
    store_keys = ([k for k in ["onground_advocate", "movement_map", "local_academic", "goi_pib", "foreign_academic", "regulatory_environment"] if k in selected] or selected)[:MAX_FILE_SEARCH_STORES]
    active_store_ids = [STORE_REGISTRY[k][0] for k in store_keys]
    gaps_digest = _sections_digest(state)

    system_message = experts_instructions.format(
        base_rules=WRITER_BASE_RULES,
        citation_rules=GLOBAL_CITATION_RULES,
        gaps_digest=gaps_digest or "(no prior findings available)",
    )
    prompt = (
        "Identify named authors, experts, organisations or officials in the files who are relevant to the "
        "gaps and findings provided, with any contact details that appear in the files. Use only names that "
        "actually appear in the files."
    )
    model_config = types.GenerateContentConfig(
        system_instruction=system_message,
        tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=active_store_ids))],
        temperature=0.0,
    )

    text = ""
    for try_count in range(3):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=model_config,
            )
            text = (response.text or "").strip()
            break
        except errors.ServerError as e:
            print(f"[write_experts] server glitch on try {try_count + 1}: {e}")
            if try_count < 2:
                time.sleep(3)
        except Exception as e:
            print(f"[write_experts] unexpected error: {e}")
            break

    if not text:
        text = (
            "There isn't enough information in the available sources yet to recommend specific on-the-ground "
            "experts to contact. More data will be added to the tool to support this."
        )
    return {"experts_section": text}


# One row of the evidence snapshot. The three cells are anchored to each other:
# `known` and `critical` must both be ABOUT this row's assumption, so every row
# reads left to right as one coherent line of reasoning.
class EvidenceSnapshotRow(BaseModel):
    assumption: str = Field(description="One major assumption the intervention is built on, as one short sentence.")
    known: str = Field(default="", description="What we know — the evaluation's clearest finding(s) bearing on THIS assumption, one short sentence. Empty if the evaluation surfaced nothing that bears on it.")
    critical: str = Field(default="", description="What's critical to figure out — the open question that most determines whether THIS assumption holds, one short sentence. Empty if nothing critical remains.")


class EvidenceSnapshotContent(BaseModel):
    rows: List[EvidenceSnapshotRow] = Field(default_factory=list, description="One row per major assumption, most important first.")


evidence_snapshot_instructions = """You are writing the "Snapshot of the Evidence" of a theory-of-change evaluation — a glanceable table distilled from the finished evaluation. Each row is anchored on ONE major assumption the intervention is built on (stated by the charity or surfaced by the evaluation), and reads left to right as a single line of reasoning:
- assumption: the assumption itself.
- known: what we know — the evaluation's clearest finding(s) that bear on THIS assumption.
- critical: what's critical to figure out — the open question that most determines whether THIS assumption holds.

Rules:
- 3-6 rows, most important assumption first.
- `known` and `critical` MUST be about the row's assumption. Never place an unrelated finding or question in a row; if a finding from the evaluation does not bear on any major assumption, leave it out of this table.
- Where the evaluation surfaced nothing bearing on an assumption, leave `known` empty — that gap is itself informative.
- Each cell is ONE short, self-contained sentence.
- Draw only on the evaluation sections provided; do not introduce new claims.
- Do not include citations — they live in the body sections.
- Do not mention this tool or internal sources.

The charity's stated assumptions (fold in the ones that matter):
{assumptions}

The full evaluation:
{digest}"""


def write_evaluation_summary(state: ResearchGraphState):
    """Section 2 — written LAST; the "Snapshot of the Evidence" table distilled
    from the finished evaluation. Each row anchors what we know and what's
    critical to figure out to one major assumption."""
    ps = state.get("path_spec") or {}
    system_message = evidence_snapshot_instructions.format(
        assumptions=_bullet_list(ps.get("charity_assumptions")),
        digest=_sections_digest(state, trim=None),
    )
    rows: list[list[str]] = []
    try:
        res = cast(EvidenceSnapshotContent, llm.with_structured_output(EvidenceSnapshotContent).invoke([
            SystemMessage(content=system_message),
            HumanMessage(content="Produce the snapshot rows."),
        ]))
        rows = [
            [r.assumption, r.known, r.critical]
            for r in (res.rows or []) if (r.assumption or "").strip()
        ]
    except Exception as e:
        print(f"[write_evaluation_summary] structured snapshot failed: {e}")

    if not rows:
        summary = "The evaluation did not produce enough material to summarise; see the sections below."
    else:
        summary = _render_md_table(
            ["Major Assumption the Intervention Is Built On", "What We Know", "What's Critical to Figure Out"],
            rows,
        )
    return {
        "evaluation_summary": summary,
        "messages": [AIMessage(content="[PROGRESS:90] Wrote the snapshot of the evidence.", name="System")],
    }


# ---------------------------------------------------------------------------
# 5d. Finalize Report (fixed 11-section layout)
# ---------------------------------------------------------------------------
def _make_report_title(state: ResearchGraphState) -> str:
    """A concise title naming the intervention(s) this report evaluates."""
    path_spec = state.get("path_spec") or {}
    descriptor = (path_spec.get("method_descriptor") or "").strip()
    summary = (path_spec.get("summary") or "").strip()

    phrase = ""
    if descriptor or summary:
        try:
            result = llm.invoke([
                SystemMessage(content=(
                    "You name evaluation reports. Reply with only a short Title Case phrase "
                    "(3-8 words) naming the charity intervention(s) described, e.g. "
                    "'Corporate Cage-Free Commitments' or 'Stray Dog Sterilisation Programmes'. "
                    "No quotes, no markdown, no trailing punctuation."
                )),
                HumanMessage(content=(
                    f"Kind of intervention: {descriptor or '(not stated)'}\n\n"
                    f"What the charity proposes: {summary[:1500] or '(not stated)'}"
                )),
            ])
            phrase = _llm_text(result).strip().strip('"').strip()
            phrase = phrase.splitlines()[0].strip() if phrase else ""
        except Exception as e:
            print(f"[finalize_report] title generation failed: {e}")
        if not phrase:
            phrase = descriptor
    if phrase and len(phrase) <= 80:
        return f"Tractability Evaluation: {phrase}"
    return "Theory of Change Evaluation"


def finalize_report(state: ResearchGraphState):
    stated_work = state.get("stated_work", "")
    summary = state.get("evaluation_summary", "")
    methodology = state.get("methodology", "")
    regulatory = state.get("regulatory_section", "")
    path_analysis = state.get("path_analysis_section", "")
    windows = state.get("windows_section", "")
    challenges = state.get("challenges_section", "")
    team = state.get("team_section", "")
    followups = state.get("followups_section", "")
    experts = state.get("experts_section", "")

    # Collect every citation across the cited sections (matches the colored-span wrapper).
    all_sources = set()
    for section_text in [regulatory, path_analysis, windows, challenges, team, experts]:
        for f in re.findall(r'<span style="color: #[0-9a-fA-F]+;">\[(.*?)\]</span>', section_text or ""):
            for one in f.split(";"):
                if one.strip():
                    all_sources.add(one.strip())
    sources_list = "\n".join(f"- {s}" for s in sorted(all_sources)) if all_sources else "- No sources were cited."

    final_report_str = f"""# {_make_report_title(state)}

## 1. Charity's Stated Work

{stated_work}

---

## 2. Snapshot of the Evidence

{summary}

---

## 3. Methodology of This Evaluation

{methodology}

---

## 4. Regulatory Environment for Nonprofits in India

{regulatory}

---

## 5. Path Analysis

{path_analysis}

---

## 6. Windows of Opportunity

{windows}

---

## 7. Challenges, Risks & Effectiveness

{challenges}

---

## 8. Team

{team}

---

## 9. Follow-Up Questions for the Charity

{followups}

---

## 10. On-the-Ground Experts

{experts}

---

## 11. Sources Cited

{sources_list}"""

    return {
        "final_report": final_report_str,
        "messages": [AIMessage(
            # [FINAL_REPORT] is the marker the frontend slices on to find the
            # report in the stream, now that the title line is dynamic.
            content=f"[PROGRESS:100] Evaluation complete.\n\n[FINAL_REPORT]\n{final_report_str}",
            name="System",
        )]
    }


# ---------------------------------------------------------------------------
# 6. Build the Graph
# ---------------------------------------------------------------------------
builder = StateGraph(ResearchGraphState)
builder.add_node("ingest_document", ingest_document)
builder.add_node("normalise_path", normalise_path)
builder.add_node("dispatch_dimensions", dispatch_dimensions)
builder.add_node("gather_evidence", gather_evidence)
builder.add_node("collect_sections", collect_sections)
builder.add_node("prepare_writing", prepare_writing)
builder.add_node("write_stated_work", write_stated_work)
builder.add_node("write_methodology", write_methodology)
builder.add_node("write_regulatory", write_regulatory)
builder.add_node("write_path_analysis", write_path_analysis)
builder.add_node("write_windows", write_windows)
builder.add_node("write_challenges", write_challenges)
builder.add_node("write_team", write_team)
builder.add_node("write_followups", write_followups)
builder.add_node("write_experts", write_experts)
builder.add_node("write_evaluation_summary", write_evaluation_summary)
builder.add_node("finalize_report", finalize_report)

# Entry: read the file, then normalise the path into one representation.
builder.add_edge(START, "ingest_document")
builder.add_edge("ingest_document", "normalise_path")

# Front fan-out: path-only / process-only / trained-only nodes run alongside
# the vault retrievals — none of them depend on the gathered evidence.
builder.add_edge("normalise_path", "write_stated_work")
builder.add_edge("normalise_path", "write_methodology")
builder.add_edge("normalise_path", "dispatch_dimensions")

# Vault retrievals fan out per dimension, then join.
builder.add_conditional_edges("dispatch_dimensions", route_to_dimensions, ["gather_evidence"])
builder.add_edge("gather_evidence", "collect_sections")
builder.add_edge("collect_sections", "prepare_writing")

# Main section writers run in parallel off the bucketed memos.
builder.add_edge("prepare_writing", "write_regulatory")
builder.add_edge("prepare_writing", "write_path_analysis")
builder.add_edge("prepare_writing", "write_windows")
builder.add_edge("prepare_writing", "write_challenges")
builder.add_edge("prepare_writing", "write_team")

# Follow-ups and experts depend on the gaps surfaced by the five main writers.
_MAIN_WRITERS = ["write_regulatory", "write_path_analysis", "write_windows", "write_challenges", "write_team"]
builder.add_edge(_MAIN_WRITERS, "write_followups")
builder.add_edge(_MAIN_WRITERS, "write_experts")

# The summary is written last — it waits on everything (the derived writers plus
# the front fan-out branches).
builder.add_edge(
    ["write_followups", "write_experts", "write_stated_work", "write_methodology"],
    "write_evaluation_summary",
)
builder.add_edge("write_evaluation_summary", "finalize_report")
builder.add_edge("finalize_report", END)

graph = builder.compile()
