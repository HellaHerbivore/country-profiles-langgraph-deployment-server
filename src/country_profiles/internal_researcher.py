import os
import re
import json
import operator
from dotenv import load_dotenv
from typing import Annotated, List, cast
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, get_buffer_string
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import Send, Command
from langgraph.graph import END, MessagesState, START, StateGraph

import time
from google import genai
from google.genai import types, errors

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

# Maps a human-readable store key -> (file_search_store_id, description for the planner)
STORE_REGISTRY = {
    "foreign_academic": (FOREIGN_ACADEMIC_STORE, "Foreign / international academic research sources."),
    "onground_advocate": (ON_GROUND_ADVOCATE_STORE, "On-the-ground advocate and field organisation sources."),
    "local_academic": (LOCAL_ACADEMIC_STORE, "India-based academic research sources."),
    "goi_pib": (GOI_PIB_STORE, "Government of India PIB press releases (Ministry of Fisheries, Animal Husbandry & Dairying)."),
}

# Default selection until user-driven selection is wired in.
DEFAULT_SELECTED_STORES = list(STORE_REGISTRY.keys())

# ---------------------------------------------------------------------------
# 1b. Static Country Context
# ---------------------------------------------------------------------------
INDIA_MACRO_STATEMENT = """India's regulatory framework is anchored in the landmark Prevention of Cruelty to Animals Act (1960) and the constitutional duty to show compassion to living creatures. While the legislative foundation is robust, it remains hampered by archaic penalty structures that fail to provide a credible deterrent against systemic abuse. Recent judicial activism, particularly from the Supreme Court, has increasingly recognized animal sentience and personhood, though these rulings often clash with regional cultural practices. The Animal Welfare Board of India (AWBI) serves as the primary statutory advisory body, but its efficacy is frequently constrained by fluctuating political priorities and bureaucratic inertia. Consequently, the macro environment is characterized by a high degree of legal idealism versus enforcement deficit."""

INDIA_DATA_POINTS = ["1.4B population", "~4.5B Land Animals/Year", "62 FAOI", "32 WAPI"]

# ---------------------------------------------------------------------------
# 1c. Global Rules
# ---------------------------------------------------------------------------
GOODGROWTH_LESSONS = """GOOD GROWTH FRAMING — LESSONS FROM FIELD EXPERIENCE:
These lessons are derived from a study of food systems advocacy campaigns in India. Use them as the analytical lens for identifying actionable opportunities — every opportunity you surface should connect to at least one of these.

For advocates / charities:
1. Contextual homework before launch: campaigns stalled when political timing, enforcement gaps, religious sensitivities, or public sentiment surfaced mid-campaign. A structured pre-launch scan of political climate, regulatory reliability, and the cultural calendar surfaces risk early.
2. Honest internal readiness check: organisations discovered missing infrastructure (follow-up capacity, lead capture, staffing) only after launch. A staffing/skills/funding/decision-making check before finalising scope right-sizes the campaign.
3. Take social identity and economic realities seriously: caste, religion, hunger, livelihoods, and price sensitivity shape what audiences find acceptable — they must be deliberately factored into messages, messengers, and partners.
4. Don't treat stakeholders as fixed obstacles: government, industry, and the public are often wrongly seen as immovable. Stakeholder mapping can reveal alternative engagement strategies — smaller/medium producers, or turning backlash into an opening.
5. Turn experience into reusable knowledge: lessons were usually only articulated after campaigns ended. Milestone and post-campaign debriefs convert ad hoc memory into reusable knowledge.
6. Use peer spaces for practical knowledge-sharing: low-burden exchanges (short calls, shared templates, peer circles) help smaller and volunteer-led groups swap knowledge on enforcement, coalitions, and capacity.

For funders:
1. Budget for structured contextual reflection, not just activity: fund time for environmental scans and integrating findings into plans before launch.
2. Invest in peer learning with smaller organisations in mind: fund shared spaces, mentoring, and convenings so regional and smaller groups can participate, not only large ones.
3. Be patient and flexible in sensitive contexts: where caste, religion, dairy livelihoods, and hunger are salient, iterative testing and relationship-building take time — support pilots, don't penalise course corrections."""


GLOBAL_CITATION_RULES = """CITATION RULES:
1. Cite using the EXACT source name as it appears in the filestore, with any file extension removed (drop .md, .pdf, etc.). Example: a file named `local_welfare_review_2021.pdf` is cited as `local_welfare_review_2021`.
2. EXCEPTION — PIB sources: any source file named `fisheries_releases_<year>` (e.g. `fisheries_releases_2024`, `fisheries_releases_2022_final`) is a yearly collection of press releases from the Government of India Press Information Bureau (PIB). These files must NEVER be cited by filename. Because one file holds many releases, each must instead be cited as: [Date of release, Ministry of Fisheries, Animal Husbandry & Dairying, Exact Title of Press Release, PIB] — with the date and title extracted from the specific release within the file.
3. Every specific detail, claim, statistic, or pivotal finding MUST carry a citation, wrapped exactly like this: <span style="color: #9f635c;">[citation]</span>
4. If citing multiple sources for one claim, separate them with a semicolon inside a single span: <span style="color: #9f635c;">[source_one; source_two]</span>
5. When in doubt, cite the source."""


# ----------------------------------------------------------------------------
# 2. Shapes of our Data (Schemas)
# ----------------------------------------------------------------------------
class Analyst(BaseModel):
    affiliation: str = Field(description="Primary affiliation of the analyst.")
    name: str = Field(description="Name of the analyst.")
    role: str = Field(description="Role of the analyst in the context of the topic.")
    description: str = Field(description="Description of the analyst focus, concerns, and motives.")

    @property
    def persona(self) -> str:
        return f"Name: {self.name}\nRole: {self.role}\nAffiliation: {self.affiliation}\nDescription: {self.description}\n"

class Perspectives(BaseModel):
    analysts: List[Analyst] = Field(description="Comprehensive list of analysts with their roles and affiliations.")

class GenerateAnalystsState(TypedDict):
    topic: str
    max_analysts: int
    human_analyst_feedback: str
    analysts: List[Analyst]

class InterviewState(MessagesState):
    max_num_turns: int
    context: Annotated[list, operator.add]
    analyst: Analyst
    interview_research_plan: dict
    interview: str
    sections: list
    interview_signals: Annotated[list, operator.add]

class ResearchGraphState(TypedDict):
    topic: str
    max_analysts: int
    human_analyst_feedback: str
    selected_stores: List[str]
    research_plan: dict[str, object]
    analysts: List[Analyst]
    sections: Annotated[list, operator.add]
    content: str
    evidence_section: str
    gaps_section: str
    opportunities_section: str
    players_section: str
    messages: Annotated[list, operator.add]
    final_report: str
    interview_signals: Annotated[list, operator.add]
    # layers_briefing: str


# ---------------------------------------------------------------------------
# 2b. Streaming helpers (user-facing source formatting)
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
    """Apply the script's citation rules to raw filenames for user-facing display:
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


# --- 3a. Research Planning ---

research_plan_instructions = """You are the lead researcher planning how to investigate a topic for an animal advocacy strategic briefing.

Research topic:
{topic}

You have access to ONLY these document filestores (you must not assume any others exist):
{store_menu}

Your job:
1. Choose ONE store as the PRIMARY anchor — the one whose evidence is most central to this specific topic.
2. The remaining selected stores are SECONDARY — used to corroborate the primary evidence and to expose gaps.
3. Decide HOW MANY analyst angles to deploy on this topic. Pick an integer between 1 and 4 inclusive — never more than 4. Use 1 for narrow, single-question topics; 2-3 for typical topics; reserve 4 only for genuinely multi-faceted topics that span distinct stakeholder groups or distinct sub-domains.
4. Explain your reasoning briefly and concretely: why this primary store, why these stores corroborate well for THIS topic, AND why you chose this number of analyst angles.

Respond as JSON with keys:
- "primary": the store key string of the primary store
- "secondary": list of the remaining selected store key strings
- "num_analysts": integer between 1 and 4 inclusive — the number of analyst angles to deploy
- "rationale": 2-4 sentences explaining the choice of primary store AND the number of analyst angles, written for a human reader
- "brief": a short (3-5 sentence) plain-language note to the user describing how you'll approach the research, readable while the rest of the report generates"""


def plan_research(state: ResearchGraphState):
    topic = state.get("topic")
    if not topic and state.get("messages"):
        topic = state["messages"][-1].content

    selected = state.get("selected_stores") or DEFAULT_SELECTED_STORES
    selected = [s for s in selected if s in STORE_REGISTRY]
    if not selected:
        selected = list(STORE_REGISTRY.keys())
        
    print(f"[plan_research] state.selected_stores={state.get('selected_stores')} → filtered={selected}")

    store_menu = "\n".join(f"- {key}: {STORE_REGISTRY[key][1]}" for key in selected)

    result = llm.invoke([
        SystemMessage(content=research_plan_instructions.format(topic=topic, store_menu=store_menu)),
        HumanMessage(content="Produce the research plan as JSON.")
    ])

    content = result.content
    if isinstance(content, list):
        content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
    else:
        content = str(content)

    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: first selected store is primary, rest secondary
        plan = {
            "primary": selected[0],
            "secondary": selected[1:],
            "num_analysts": 3,
            "rationale": "Defaulted to the first selected store as primary due to a planning parse error.",
            "brief": "Proceeding with a default research plan across the selected sources.",
        }

    # Sanitize: make sure primary/secondary only reference selected stores
    if plan.get("primary") not in selected:
        plan["primary"] = selected[0]
    plan["secondary"] = [s for s in plan.get("secondary", []) if s in selected and s != plan["primary"]]
    plan["selected_stores"] = selected

    # Sanitize: clamp num_analysts to [1, 4]
    try:
        num_analysts = int(plan.get("num_analysts", 3))
    except (TypeError, ValueError):
        num_analysts = 3
    num_analysts = max(1, min(4, num_analysts))
    plan["num_analysts"] = num_analysts

    return {
        "research_plan": plan,
        "topic": topic,
        "selected_stores": selected,
        "max_analysts": num_analysts,
        "messages": [AIMessage(
            content=f"[PROGRESS:10] Mapped out the approach.\n\n**How I'll approach this:** {plan.get('brief', '')}",
            name="System"
        )]
    }

# --- 3b. Analyst Creation ---

analyst_instructions="""You are tasked with creating a set of AI analyst personas. Follow these instructions carefully:
1. First, review the research topic:
{topic}
2. Pick the top {max_analysts} themes.
3. Assign one analyst to each theme."""

def create_analysts(state: ResearchGraphState):
    topic = state.get('topic')
    if not topic and state.get('messages'):
        topic = state['messages'][-1].content

    research_plan = state.get('research_plan') or {}
    max_analysts = state.get('max_analysts') or research_plan.get('num_analysts') or 3
    try:
        max_analysts = int(max_analysts)
    except (TypeError, ValueError):
        max_analysts = 3
    max_analysts = max(1, min(4, max_analysts))

    structured_llm = llm.with_structured_output(Perspectives)
    system_message = analyst_instructions.format(
        topic=topic,
        max_analysts=max_analysts
    )

    raw_res = structured_llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Generate the set of analysts.")])
    perspectives_res = cast(Perspectives, raw_res)

    angles = [a.role for a in perspectives_res.analysts]
    return {
        "analysts": perspectives_res.analysts,
        "topic": topic,
        "max_analysts": max_analysts,
        "messages": [
            AIMessage(
                content=f"[PROGRESS:15] Mapped out the angles to investigate.\n\nLooking at: {_join_with_and(angles)}.",
                name="System"
            )
        ]
    }

question_instructions = """You are an analyst tasked with interviewing an expert to learn about a specific topic.
Begin by introducing yourself using a name that fits your persona, and then ask your question.
Continue to ask questions to drill down and refine your understanding of the topic.
When you are satisfied, complete the interview with: "Thank you so much for your help!"
Here is your topic of focus and set of goals: {goals}"""

def generate_question(state: InterviewState):
    analyst = state["analyst"]
    messages = state["messages"]

    system_message = question_instructions.format(goals=analyst.persona)
    question = llm.invoke([SystemMessage(content=system_message)] + messages)
    return {"messages": [question]}

def generate_answer(state: InterviewState):
    """Answers questions strictly using internal vaults via Gemini File Search."""
    analyst = state["analyst"]
    messages = state["messages"]
    research_plan = state.get("interview_research_plan", {}) or {}

    selected = research_plan.get("selected_stores") or DEFAULT_SELECTED_STORES
    selected = [str(s) for s in selected if s in STORE_REGISTRY]
    if not selected:
        selected = list(STORE_REGISTRY.keys())

    primary = research_plan.get("primary")
    if not isinstance(primary, str) or primary not in selected:
        primary = selected[0]
    secondary = [s for s in selected if s != primary]

    active_store_ids = [STORE_REGISTRY[k][0] for k in selected]

    print(f"[generate_answer] research_plan.selected={selected}, active_store_ids={active_store_ids}")

    primary_desc = STORE_REGISTRY[primary][1]
    secondary_desc = "\n".join(f"    - {STORE_REGISTRY[k][1]}" for k in secondary) or "    - (none — only the primary store is selected)"

    pib_selected = "goi_pib" in selected

    expert_instructions = f"""You are a strict data-retrieval expert.
    Analyst focus: {analyst.persona}

    SOURCE STRATEGY FOR THIS RESEARCH:
    - PRIMARY anchor store: {primary_desc}
      Treat this as your main source of evidence — lead with it.
    - SECONDARY stores (use to corroborate the primary evidence and to expose gaps):
{secondary_desc}
    You may ONLY use the stores listed above. No other stores exist for this task.

    CRITICAL RULES:
    1. You have NO knowledge outside of the files in the stores listed above.
    2. If the answer is not in the files, say EXACTLY: "The internal vaults do not contain this information."
    3. Do not use your own training data to fill in gaps.
    4. CORROBORATION PROTOCOL: For every major claim drawn from the primary store, you MUST actively cross-reference it against the secondary stores and state whether they corroborate, contradict, or are silent on the issue. Where the secondary stores are silent on something the primary store treats as important, name that explicitly as a GAP.
    {"5. PIB SOURCES: Government of India press releases are stored in files named `fisheries_releases_<year>` (e.g. `fisheries_releases_2024`, `fisheries_releases_2022_final`). For any claim drawn from one of these files, you MUST extract the date of release and the exact title of the specific press release — these are required for its citation, because the filename cannot serve as the citation. For all non-PIB sources, the citation is just the filename." if pib_selected else "5. (No PIB store selected for this task.)"}
    6. ONE-CLAIM-ONE-SOURCE BY DEFAULT. A citation must support the specific claim it sits next to. If you make a claim drawn from source A, cite source A; don't cite source B because it's topically nearby. Place citations mid-sentence at the point each source's contribution applies, rather than parking them all at the end of a sentence.
    7. WHEN YOU DO COMBINE SOURCES, SAY SO. If you produce a claim that genuinely combines information from multiple sources to suggest a mechanism, recommendation, or causal link that no single source states, this is your own synthesis — flag it as such with explicit framing ("taken together, these sources suggest…", "this implies…") and cite ALL contributing sources at the point of synthesis. Do not present a synthesis under a single citation as if that one source made the claim.

    {GLOBAL_CITATION_RULES}
    """

    model_config = types.GenerateContentConfig(
        system_instruction=expert_instructions,
        tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=active_store_ids))],
        temperature=0.0,
    )

    chat_history = "\n".join([f"{m.type.capitalize()}: {m.content}" for m in messages])
    prompt = f"Read our chat history and answer the latest question using your files:\n\n{chat_history}"

    print(f"\n\n👀 --- WHAT THE EXPERT WAS ASKED ({analyst.name}) ---")
    print(messages[-1].content)

    max_tries = 3
    response = None

    for try_count in range(max_tries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=model_config
            )
            break

        except errors.ServerError as e:
            print(f"\n⚠️ Server glitch on try {try_count + 1}: {e}")

            if try_count < max_tries - 1:
                print("Waiting 3 seconds before we try again...")
                time.sleep(3)
            else:
                print("Server is fully down. Moving on without this answer.")
                return {
                    "messages": [AIMessage(content="FLAG_NO_KNOWLEDGE", name="expert")],
                    "interview_signals": [{
                        "role": analyst.role,
                        "sources": [],
                        "no_knowledge": True,
                    }],
                }

    if response and response.text:
        answer_text = response.text
    else:
        answer_text = "The internal vaults do not contain this information."

    consulted_sources = _extract_consulted_sources(response) if response else []
    used_files = bool(consulted_sources) or (
        response is not None
        and response.candidates
        and response.candidates[0].grounding_metadata is not None
    )

    print(f"\n🧠 --- RAW EXPERT ANSWER ---")
    print(answer_text)
    print(f"\n✅ [TRIGGER] Did the Expert use internal files? -> {used_files}")
    if consulted_sources:
        print(f"📚 [SOURCES] Consulted: {consulted_sources}")
    print("---------------------------------------------------\n")

    if not used_files or "do not contain this information" in answer_text.lower():
        answer_text = "FLAG_NO_KNOWLEDGE"

    no_knowledge = (answer_text == "FLAG_NO_KNOWLEDGE")
    return {
        "messages": [AIMessage(content=answer_text, name="expert")],
        "interview_signals": [{
            "role": analyst.role,
            "sources": consulted_sources,
            "no_knowledge": no_knowledge,
        }],
    }

def save_interview(state: InterviewState):
    messages = state["messages"]
    interview = get_buffer_string(messages)
    return {"interview": interview}

def route_messages(state: InterviewState, name: str = "expert"):
    messages = state["messages"]
    max_num_turns = state.get('max_num_turns', 2)

    last_message = messages[-1]
    if last_message.content == "FLAG_NO_KNOWLEDGE":
        return 'save_interview'

    num_responses = len([m for m in messages if isinstance(m, AIMessage) and m.name == name])
    if num_responses >= max_num_turns:
        return 'save_interview'

    last_question = messages[-2]
    if "Thank you so much for your help" in last_question.content:
        return 'save_interview'

    return "ask_question"

section_writer_instructions = """You are an expert technical writer.
Write a short section of a report based on the interview.
Make your title engaging based upon the focus area: {focus}

CRITICAL RULES:
1. Write from a completely objective, third-person view.
2. DO NOT mention the interviewer, the expert, or any of the AI persona names in your text.
3. You MUST preserve every inline citation from the interview EXACTLY as written — including the <span> wrapper and its contents. Never reformat, rename, shorten, or drop a citation.
4. NEVER summarise away numeric or statistical data. Preserve all figures, percentages, currency values, and multipliers exactly as stated."""

def write_section(state: InterviewState):
    interview = state["interview"]
    analyst = state["analyst"]

    if "FLAG_NO_KNOWLEDGE" in interview:
        return {"sections": ["FLAG_NO_KNOWLEDGE"]}

    system_message = section_writer_instructions.format(focus=analyst.description)
    section = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content=f"Use this interview to write your section:\n{interview}")])

    content = section.content
    if isinstance(content, list):
        content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
    else:
        content = str(content)

    return {"sections": [content]}

# ---------------------------------------------------------------------------
# 4. Build the Interview Graph (The Inner Loop)
# ---------------------------------------------------------------------------
interview_builder = StateGraph(InterviewState)
interview_builder.add_node("ask_question", generate_question)
interview_builder.add_node("answer_question", generate_answer)
interview_builder.add_node("save_interview", save_interview)
interview_builder.add_node("write_section", write_section)

interview_builder.add_edge(START, "ask_question")
interview_builder.add_edge("ask_question", "answer_question")
interview_builder.add_conditional_edges("answer_question", route_messages, ['ask_question', 'save_interview'])
interview_builder.add_edge("save_interview", "write_section")
interview_builder.add_edge("write_section", END)

# ---------------------------------------------------------------------------
# 5. Build the Main Report Graph (The Outer Loop)
# ---------------------------------------------------------------------------
def initiate_all_interviews(state: ResearchGraphState):
    topic = state["topic"]
    interview_research_plan = state.get("research_plan", {})
    return [Send("conduct_interview", {
        "analyst": analyst,
        "interview_research_plan": interview_research_plan,
        "messages": [HumanMessage(
            content=f"We are building a Strategic Country Profile for {topic}. As our {analyst.name}, identify the key advocacy bottlenecks and windows of opportunity in your specialized area."
        )]
    }) for analyst in state["analysts"]]


def collect_sections(state: ResearchGraphState):
    """Join point — waits for all parallel interviews to complete before checking knowledge."""
    signals = state.get("interview_signals", []) or []

    all_sources: list[str] = []
    seen_sources: set[str] = set()
    empty_roles: list[str] = []
    seen_empty: set[str] = set()
    for sig in signals:
        role = sig.get("role") or "an unspecified angle"
        if sig.get("no_knowledge") and role not in seen_empty:
            seen_empty.add(role)
            empty_roles.append(role)
        for src in sig.get("sources", []) or []:
            if src not in seen_sources:
                seen_sources.add(src)
                all_sources.append(src)

    formatted_sources = _format_source_names(all_sources)

    parts: list[str] = ["[PROGRESS:50] Gathered evidence from the source vaults."]
    if formatted_sources:
        parts.append("")
        parts.append(f"Drawing on: {_join_with_and(formatted_sources)}.")
    for role in empty_roles:
        parts.append("")
        parts.append(
            f"One investigative angle (the {role}) returned no information from the available sources."
        )

    return {
        "messages": [AIMessage(content="\n".join(parts), name="System")]
    }


def check_knowledge(state: ResearchGraphState):
    sections = state.get("sections", [])

    flat_sections = []
    for s in sections:
        if isinstance(s, list):
            for item in s:
                if isinstance(item, dict):
                    flat_sections.append(item.get("text", ""))
                else:
                    flat_sections.append(str(item))
        else:
            if isinstance(s, dict):
                flat_sections.append(s.get("text", ""))
            else:
                flat_sections.append(str(s))

    valid_sections = [s for s in flat_sections if s != "FLAG_NO_KNOWLEDGE"]

    if not valid_sections:
        return "abort_report"
    return "prepare_writing"

def abort_report(state: ResearchGraphState):
    final_message = "not enough internal knowledge"
    print("\n⚠️ ABORTED: Not enough internal knowledge.\n")
    return {
        "final_report": final_message,
        "messages": [AIMessage(
            content="[PROGRESS:ABORTED] Not enough information in the available source vaults to produce a confident briefing on this topic.",
            name="System"
        )]
    }


def prepare_writing(state: ResearchGraphState):
    """Flatten and prepare raw interview sections for the section writers."""
    sections = state.get("sections", [])

    flat_sections = []
    for s in sections:
        if isinstance(s, list):
            for item in s:
                if isinstance(item, dict):
                    flat_sections.append(item.get("text", ""))
                else:
                    flat_sections.append(str(item))
        else:
            if isinstance(s, dict):
                flat_sections.append(s.get("text", ""))
            else:
                flat_sections.append(str(s))

    valid_sections = [s for s in flat_sections if s != "FLAG_NO_KNOWLEDGE"]
    formatted_str_sections = "\n\n---\n\n".join(valid_sections)

    return {
        "content": formatted_str_sections,
        "messages": [AIMessage(
            content="[PROGRESS:55] Drafting the briefing — synthesizing evidence, gaps, opportunities, and players in parallel.",
            name="System"
        )]
    }


# ---------------------------------------------------------------------------
# 5b. Four Report Section Writers
# ---------------------------------------------------------------------------

evidence_instructions = """You are a Lead Strategist writing the "What the Evidence Says" section of a strategic briefing for: {topic}.

You will receive raw research memos gathered from internal document vaults. Your job is to synthesize what the evidence actually tells us into a clear, unified analytical narrative.

CRITICAL RULES:
1. Present this as a unified, objective briefing. DO NOT mention any AI analyst names, interviewers, or experts.
2. NEVER summarise away numeric or statistical data. Every figure, percentage, currency value, multiplier, or statistic from the memos MUST appear in your output exactly as stated.
3. Preserve highly insightful information verbatim — do not water down sharp observations.
4. The memos contain explicit corroboration findings (where sources agree or contradict each other). Extract and foreground these — when multiple sources corroborate a claim, say so; when they conflict, present the conflict rather than picking a side.
5. You are receiving the full set of interview memos. Pull only what speaks to what the evidence SAYS — leave gaps, opportunities, and player mapping to the other sections.
6. SYNTHESIS VS. EVIDENCE. If a claim combines information from multiple sources to produce a recommendation, mechanism, or causal link that no single source states, it is synthesis — not direct evidence. Default to rewriting such claims as separate claims each tied to what its source actually says. Only when the synthesis itself is genuinely the useful insight, keep it but frame it transparently as analysis ("the evidence taken together suggests…", "these findings point toward…") and cite ALL the sources it draws on.
7. CITATIONS MUST SUPPORT THE SPECIFIC CLAIM THEY SIT NEXT TO. A citation is not a topic tag — it is a guarantee that the cited source contains that specific claim. If a claim has roots in two sources, both must be cited. If one citation covers only part of a claim, the rest must either be cited from its actual source or removed. A source whose connection to the claim is your inference, not the source's own statement, is not a valid citation.
8. PLACE CITATIONS WHERE THEY ARE EARNED. Citations do NOT have to sit at the end of a sentence. When a sentence draws on one source for one part and another for another, place each citation mid-sentence at the point its source applies — this keeps attribution tight and exposes any unsupported bridging. Only put a citation at the end of a sentence when the entire sentence is genuinely supported by that source, OR when the sentence is an explicit synthesis (per rule 6) and all contributing sources are cited together at the end.

{citation_rules}

Research memos:
{context}"""


def write_evidence(state: ResearchGraphState):
    content = state.get("content", "")
    topic = state["topic"]

    system_message = evidence_instructions.format(
        topic=topic, 
        context=content, 
        citation_rules=GLOBAL_CITATION_RULES
    )
    result = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Write the 'What the Evidence Says' section based on these research memos.")])

    text = result.content
    if isinstance(text, list):
        text = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in text])
    else:
        text = str(text)

    return {
        "evidence_section": text,
    }


gaps_instructions = """You are a strategic research analyst writing the "Gaps in the Evidence" section of a briefing for: {topic}.

You will receive research memos gathered from internal document vaults. Your job is to identify what we DON'T know — what is missing, unstudied, underrepresented, or left unanswered by the available evidence.

INSTRUCTIONS:
1. Be specific about what's missing. Don't just say "more research is needed" — name the exact topics, populations, geographies, time periods, or dynamics that are absent.
2. Reference what evidence DOES exist to frame the boundaries of knowledge — this shows where the gaps begin.
3. Consider: What questions does the available evidence raise but not answer? What assumptions does it make without supporting data?
4. Think about: Are there stakeholder perspectives missing? Geographic blind spots? Temporal gaps (outdated data)? Methodological limitations?
5. DO NOT mention any AI analyst names, interviewers, or experts.
6. Preserve any numeric data that contextualizes a gap.
7. The memos contain explicit GAP findings flagged during research (where the primary source raised something the secondary sources were silent on). Extract these flagged gaps directly — they are the backbone of this section — and supplement them with any further gaps you identify.
8. You are receiving the full set of interview memos. Pull only what speaks to what is MISSING or unanswered — leave confirmed evidence, opportunities, and player mapping to the other sections.
9. SYNTHESIS VS. EVIDENCE. If a claim combines information from multiple sources to produce a recommendation, mechanism, or causal link that no single source states, it is synthesis — not direct evidence. Default to rewriting such claims as separate claims each tied to what its source actually says. Only when the synthesis itself is genuinely the useful insight, keep it but frame it transparently as analysis ("the evidence taken together suggests…", "these findings point toward…") and cite ALL the sources it draws on.
10. CITATIONS MUST SUPPORT THE SPECIFIC CLAIM THEY SIT NEXT TO. A citation is not a topic tag — it is a guarantee that the cited source contains that specific claim. If a claim has roots in two sources, both must be cited. If one citation covers only part of a claim, the rest must either be cited from its actual source or removed. A source whose connection to the claim is your inference, not the source's own statement, is not a valid citation.
11. PLACE CITATIONS WHERE THEY ARE EARNED. Citations do NOT have to sit at the end of a sentence. When a sentence draws on one source for one part and another for another, place each citation mid-sentence at the point its source applies — this keeps attribution tight and exposes any unsupported bridging. Only put a citation at the end of a sentence when the entire sentence is genuinely supported by that source, OR when the sentence is an explicit synthesis (per rule 9) and all contributing sources are cited together at the end.

{citation_rules}

Research memos:
{context}"""


def write_gaps(state: ResearchGraphState):
    content = state.get("content", "")
    topic = state["topic"]

    system_message = gaps_instructions.format(
        topic=topic, 
        context=content,
        citation_rules=GLOBAL_CITATION_RULES
    )
    result = llm_creative.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Write the 'Gaps in the Evidence' section. Identify what we don't know based on the available evidence.")])

    text = result.content
    if isinstance(text, list):
        text = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in text])
    else:
        text = str(text)

    return {
        "gaps_section": text,
    }


opportunities_instructions = """You are a strategic analyst writing the "Windows of Opportunity" section of a briefing for: {topic}.

You will receive research memos gathered from internal document vaults. Your job is to identify time-sensitive opportunities the animal advocacy movement should act on, framed through the lessons below.

{goodgrowth_lessons}

INSTRUCTIONS:
1. Anchor every opportunity in the Good Growth lessons above — for each opportunity, make explicit which lesson(s) it draws on (e.g. a regulatory opening connects to "contextual homework"; a coalition opening connects to "peer spaces" or "stakeholders aren't fixed obstacles").
2. Be concrete about LEVERS: name the specific thing an advocate or funder could actually do — a policy moment to act on, a producer segment to engage, a coalition to build, a debrief practice to fund.
3. Where the memos name on-the-ground organisations, community leaders, or producers, identify them as potential COLLABORATORS and say what role they could play.
4. Focus on windows that could CLOSE — emerging leverage points, policy moments, market shifts, electoral cycles, attention spikes, crises requiring response. Be concrete about WHY each is time-sensitive.
5. FAVOUR RECENT DATA: when memos conflict or span different time periods, weight the most recent evidence most heavily, and note when an opportunity rests on older data that may have shifted.
6. Ground every opportunity in specific evidence from the memos. Do not speculate beyond what the data supports. If the evidence does not indicate time-sensitive opportunities, say so transparently rather than fabricating urgency.
7. NEVER summarise away numeric or statistical data. Preserve all figures exactly.
8. DO NOT mention any AI analyst names, interviewers, or experts.
9. SYNTHESIS VS. EVIDENCE. Opportunities ARE often syntheses — combining evidence into a lever is this section's job — but the synthesis must still be honest. When you produce an opportunity that combines information from multiple sources to suggest a mechanism, recommendation, or causal link that no single source states, frame it transparently as analysis ("the evidence taken together suggests…", "these findings point toward…") and cite ALL the sources it draws on. Do not present a synthesis under a single citation as if that one source made the claim.
10. CITATIONS MUST SUPPORT THE SPECIFIC CLAIM THEY SIT NEXT TO. A citation is not a topic tag — it is a guarantee that the cited source contains that specific claim. If a claim has roots in two sources, both must be cited. If one citation covers only part of a claim, the rest must either be cited from its actual source or removed. A source whose connection to the claim is your inference, not the source's own statement, is not a valid citation.
11. PLACE CITATIONS WHERE THEY ARE EARNED. Citations do NOT have to sit at the end of a sentence. When a sentence draws on one source for one part and another for another, place each citation mid-sentence at the point its source applies — this keeps attribution tight and exposes any unsupported bridging. Only put a citation at the end of a sentence when the entire sentence is genuinely supported by that source, OR when the sentence is an explicit synthesis (per rule 9) and all contributing sources are cited together at the end.

{citation_rules}

Research memos:
{context}"""


def write_opportunities(state: ResearchGraphState):
    content = state.get("content", "")
    topic = state["topic"]

    system_message = opportunities_instructions.format(
        topic=topic,
        context=content,
        goodgrowth_lessons=GOODGROWTH_LESSONS,
        citation_rules=GLOBAL_CITATION_RULES
    )
    result = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Write the 'Windows of Opportunity' section. Identify time-sensitive opportunities or crises for animal advocacy.")])

    text = result.content
    if isinstance(text, list):
        text = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in text])
    else:
        text = str(text)

    return {
        "opportunities_section": text,
    }


players_instructions = """You are a strategic analyst writing the "Current Players" section of a briefing for: {topic}.

You will receive research memos gathered from internal document vaults. Your job is to identify current players in the animal advocacy ecosystem relevant to the query and what they're currently up to.

INSTRUCTIONS:
1. List organisations, coalitions, government bodies, or key individuals mentioned in the evidence that are active on this topic. Do not treat any of them as fixed or immovable — where the evidence allows, note whether a player could be an alternative ally, a smaller/medium producer worth engaging, or a source of backlash that could become a strategic opening.
2. For each player, note what the evidence says about their current activities, positions, or campaigns.
3. BE TRANSPARENT ABOUT LIMITATIONS: The internal document vaults may have limited information about who the current players are and what they're doing right now. If the evidence doesn't clearly identify active players, say so explicitly. Do NOT invent or assume what organisations are doing.
4. DO NOT mention any AI analyst names, interviewers, or experts.
5. Preserve any numeric data (e.g., membership numbers, funding figures) exactly as stated.
6. If very little information about players exists in the vaults, a short honest section is better than a padded speculative one.
7. SYNTHESIS VS. EVIDENCE. If a claim about a player combines information from multiple sources to attribute a position, strategy, or relationship that no single source states, it is synthesis — not direct evidence. Default to rewriting such claims as separate claims each tied to what its source actually says. Only when the synthesis itself is genuinely the useful insight, frame it transparently as analysis ("the evidence taken together suggests…") and cite ALL the sources it draws on.
8. CITATIONS MUST SUPPORT THE SPECIFIC CLAIM THEY SIT NEXT TO. A citation is not a topic tag — it is a guarantee that the cited source contains that specific claim. If a claim has roots in two sources, both must be cited. If one citation covers only part of a claim, the rest must either be cited from its actual source or removed. A source whose connection to the claim is your inference, not the source's own statement, is not a valid citation.
9. PLACE CITATIONS WHERE THEY ARE EARNED. Citations do NOT have to sit at the end of a sentence. When a sentence draws on one source for one part and another for another, place each citation mid-sentence at the point its source applies — this keeps attribution tight and exposes any unsupported bridging. Only put a citation at the end of a sentence when the entire sentence is genuinely supported by that source, OR when the sentence is an explicit synthesis (per rule 7) and all contributing sources are cited together at the end.

{citation_rules}

Research memos:
{context}"""


def write_players(state: ResearchGraphState):
    content = state.get("content", "")
    topic = state["topic"]

    system_message = players_instructions.format(
        topic=topic, 
        context=content,
        citation_rules=GLOBAL_CITATION_RULES
    )
    result = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Write the 'Current Players' section. Identify active players in the animal advocacy ecosystem relevant to this topic.")])

    text = result.content
    if isinstance(text, list):
        text = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in text])
    else:
        text = str(text)

    return {
        "players_section": text,
    }


# ---------------------------------------------------------------------------
# 5c. Finalize Report
# ---------------------------------------------------------------------------

def finalize_report(state: ResearchGraphState):
    evidence = state.get("evidence_section", "")
    gaps = state.get("gaps_section", "")
    opportunities = state.get("opportunities_section", "")
    players = state.get("players_section", "")
    topic = state["topic"]
    research_plan = state.get("research_plan", {}) or {}
    analysts = state.get("analysts") or []

    # Collect every citation from all sections (matches the colored-span wrapper)
    all_sources = set()
    for section_text in [evidence, gaps, opportunities, players]:
        found = re.findall(r'<span style="color: #[0-9a-fA-F]+;">\[(.*?)\]</span>', section_text)
        for f in found:
            # a single span may hold semicolon-separated sources — split them out
            for one in f.split(";"):
                all_sources.add(one.strip())

    sources_list = "\n".join(f"- {s}" for s in sorted(all_sources)) if all_sources else "- No sources cited"

    primary_key = research_plan.get("primary", "")
    if isinstance(primary_key, str) and primary_key in STORE_REGISTRY:
        primary_label = STORE_REGISTRY[primary_key][1]
    else:
        primary_label = "Not specified"

    rationale_raw = research_plan.get("rationale", "No research plan rationale available.")
    plan_rationale = rationale_raw if isinstance(rationale_raw, str) else "No research plan rationale available."

    num_analysts = len(analysts) if analysts else research_plan.get("num_analysts", 0)
    if analysts:
        angle_lines = "\n".join(f"- **{a.role}** — {a.description}" for a in analysts)
        angle_word = "angle" if num_analysts == 1 else "angles"
        analyst_block = (
            f"**Analyst angles chosen:** {num_analysts} {angle_word} were deployed to investigate this topic:\n\n"
            f"{angle_lines}"
        )
    else:
        analyst_block = "**Analyst angles chosen:** No analyst angles were recorded for this run."

    final_report_str = f"""# Strategic Briefing: {topic}

## How This Research Was Approached

**Primary source store:** {primary_label}

{plan_rationale}

{analyst_block}

---

## What the Evidence Says

{evidence}

---

## Gaps in the Evidence

{gaps}

---

## Windows of Opportunity

{opportunities}

---

## Current Players

{players}

---

## Sources

{sources_list}"""

    return {
        "final_report": final_report_str,
        "messages": [AIMessage(
            content=f"[PROGRESS:100] Briefing complete.\n\n{final_report_str}",
            name="System"
        )]
    }


# ---------------------------------------------------------------------------
# 6. Build the Graph
# ---------------------------------------------------------------------------
builder = StateGraph(ResearchGraphState)
builder.add_node("plan_research", plan_research)
builder.add_node("create_analysts", create_analysts)
builder.add_node("conduct_interview", interview_builder.compile())
builder.add_node("collect_sections", collect_sections)
builder.add_node("abort_report", abort_report)
builder.add_node("prepare_writing", prepare_writing)
builder.add_node("write_evidence", write_evidence)
builder.add_node("write_gaps", write_gaps)
builder.add_node("write_opportunities", write_opportunities)
builder.add_node("write_players", write_players)
builder.add_node("finalize_report", finalize_report)

builder.add_edge(START, "plan_research")
builder.add_edge("plan_research", "create_analysts")
builder.add_conditional_edges("create_analysts", initiate_all_interviews, ["conduct_interview"])

builder.add_edge("conduct_interview", "collect_sections")
builder.add_conditional_edges("collect_sections", check_knowledge, ["prepare_writing", "abort_report"])

builder.add_edge("prepare_writing", "write_evidence")
builder.add_edge("prepare_writing", "write_gaps")
builder.add_edge("prepare_writing", "write_opportunities")
builder.add_edge("prepare_writing", "write_players")
builder.add_edge(["write_evidence", "write_gaps", "write_opportunities", "write_players"], "finalize_report")
builder.add_edge("finalize_report", END)
builder.add_edge("abort_report", END)

graph = builder.compile()
