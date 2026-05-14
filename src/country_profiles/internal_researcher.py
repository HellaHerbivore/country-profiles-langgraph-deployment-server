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
GLOBAL_CITATION_RULES = """CITATION RULES:
1. Cite using the EXACT source name as it appears in the filestore, with any file extension removed (drop .md, .pdf, etc.). Example: a file named `local_welfare_review_2021.pdf` is cited as `local_welfare_review_2021`.
2. EXCEPTION — PIB sources: any source file named `fisheries_releases_<year>` (e.g. `fisheries_releases_2024`, `fisheries_releases_2022_final`) is a yearly collection of press releases from the Government of India Press Information Bureau (PIB). These files must NEVER be cited by filename. Because one file holds many releases, each must instead be cited as: [Date of release, Ministry of Fisheries, Animal Husbandry & Dairying, Exact Title of Press Release, PIB] — with the date and title extracted from the specific release within the file.
3. Every specific detail, claim, statistic, or pivotal finding MUST carry a citation, wrapped exactly like this: <span style="color: #693f3a;">[citation]</span>
4. If citing multiple sources for one claim, separate them with a semicolon inside a single span: <span style="color: #693f3a;">[source_one; source_two]</span>
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
    research_plan: dict
    interview: str
    sections: list

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
    # layers_briefing: str


# ---------------------------------------------------------------------------
# 3. Work Nodes (The Steps)
# ---------------------------------------------------------------------------

# # --- 3a. Layers Briefing (static macro + dynamic meso/micro/hidden) ---

# layers_briefing_instructions = """You are a strategic analyst for animal advocacy. Given the research topic below, provide a brief (2–4 sentences each) overview of the actors and forces of change at three levels:

# - **Meso**: Sector and institutional forces relevant to this topic — industry associations, professional bodies, regional government, large NGOs, media networks, religious institutions operating at organisational scale.
# - **Micro**: Ground-level and individual forces — grassroots organisations, community leaders, individual consumers, local activists, household-level dynamics, frontline workers.
# - **Hidden**: Forces that are present but easily overlooked — informal economies, unregulated supply chains, cultural taboos, data gaps, silent stakeholders, unintended policy side-effects.

# Bold the 1–2 most important phrases per level using markdown **bold**.
# Respond as JSON with keys: meso, micro, hidden."""

# def generate_layers_briefing(state: ResearchGraphState):
#     topic = state.get("topic")
#     if not topic and state.get("messages"):
#         topic = state["messages"][-1].content

#     result = llm.invoke([
#         SystemMessage(content=layers_briefing_instructions),
#         HumanMessage(content=f"Topic: {topic}")
#     ])

#     content = result.content
#     if isinstance(content, list):
#         content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
#     else:
#         content = str(content)

#     content = content.strip()
#     if content.startswith("```"):
#         content = re.sub(r'^```(?:json)?\s*', '', content)
#         content = re.sub(r'\s*```$', '', content)

#     # Parse dynamic layers and combine with static macro
#     try:
#         dynamic_layers = json.loads(content)
#     except json.JSONDecodeError:
#         dynamic_layers = {"meso": content, "micro": "", "hidden": ""}

#     full_briefing = json.dumps({
#         "macro_statement": INDIA_MACRO_STATEMENT,
#         "data_points": INDIA_DATA_POINTS,
#         "meso": dynamic_layers.get("meso", ""),
#         "micro": dynamic_layers.get("micro", ""),
#         "hidden": dynamic_layers.get("hidden", ""),
#     })

#     return {
#         "layers_briefing": full_briefing,
#         "topic": topic,
#         "messages": [AIMessage(
#             content=f"[LAYERS_BRIEFING]{full_briefing}",
#             name="System"
#         )]
#     }

# --- 3a. Research Planning ---

research_plan_instructions = """You are the lead researcher planning how to investigate a topic for an animal advocacy strategic briefing.

Research topic:
{topic}

You have access to ONLY these document filestores (you must not assume any others exist):
{store_menu}

Your job:
1. Choose ONE store as the PRIMARY anchor — the one whose evidence is most central to this specific topic.
2. The remaining selected stores are SECONDARY — used to corroborate the primary evidence and to expose gaps.
3. Explain your reasoning briefly and concretely: why this primary, why these stores corroborate well for THIS topic.

Respond as JSON with keys:
- "primary": the store key string of the primary store
- "secondary": list of the remaining selected store key strings
- "rationale": 2-4 sentences explaining the choice, written for a human reader
- "brief": a short (3-5 sentence) plain-language note to the user describing how you'll approach the research, readable while the rest of the report generates"""


def plan_research(state: ResearchGraphState):
    topic = state.get("topic")
    if not topic and state.get("messages"):
        topic = state["messages"][-1].content

    selected = state.get("selected_stores") or DEFAULT_SELECTED_STORES
    selected = [s for s in selected if s in STORE_REGISTRY]
    if not selected:
        selected = list(STORE_REGISTRY.keys())

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
            "rationale": "Defaulted to the first selected store as primary due to a planning parse error.",
            "brief": "Proceeding with a default research plan across the selected sources.",
        }

    # Sanitize: make sure primary/secondary only reference selected stores
    if plan.get("primary") not in selected:
        plan["primary"] = selected[0]
    plan["secondary"] = [s for s in plan.get("secondary", []) if s in selected and s != plan["primary"]]
    plan["selected_stores"] = selected

    return {
        "research_plan": plan,
        "topic": topic,
        "selected_stores": selected,
        "messages": [AIMessage(
            content=f"[PROGRESS:10] Research plan ready\n\n**How I'll approach this:** {plan.get('brief', '')}",
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

    max_analysts = state.get('max_analysts')
    if not max_analysts:
        max_analysts = 3

    structured_llm = llm.with_structured_output(Perspectives)
    system_message = analyst_instructions.format(
        topic=topic,
        max_analysts=max_analysts
    )

    raw_res = structured_llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Generate the set of analysts.")])
    perspectives_res = cast(Perspectives, raw_res)

    return {
        "analysts": perspectives_res.analysts,
        "topic": topic,
        "max_analysts": max_analysts,
        "messages": [
            AIMessage(content=f"[PROGRESS:15] Created {len(perspectives_res.analysts)} analysts: {', '.join(a.role for a in perspectives_res.analysts)}", name="System")
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
    research_plan = state.get("research_plan", {}) or {}

    selected = research_plan.get("selected_stores") or DEFAULT_SELECTED_STORES
    selected = [str(s) for s in selected if s in STORE_REGISTRY]
    if not selected:
        selected = list(STORE_REGISTRY.keys())

    primary = research_plan.get("primary")
    if not isinstance(primary, str) or primary not in selected:
        primary = selected[0]
    secondary = [s for s in selected if s != primary]

    primary_id = STORE_REGISTRY[primary][0]
    active_store_ids = [STORE_REGISTRY[k][0] for k in selected]

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
                return {"messages": [AIMessage(content="FLAG_NO_KNOWLEDGE", name="expert")]}

    if response and response.text:
        answer_text = response.text
    else:
        answer_text = "The internal vaults do not contain this information."

    used_files = False
    if response and response.candidates and response.candidates[0].grounding_metadata:
        used_files = True

    print(f"\n🧠 --- RAW EXPERT ANSWER ---")
    print(answer_text)
    print(f"\n✅ [TRIGGER] Did the Expert use internal files? -> {used_files}")
    print("---------------------------------------------------\n")

    if not used_files or "do not contain this information" in answer_text.lower():
        answer_text = "FLAG_NO_KNOWLEDGE"

    return {"messages": [AIMessage(content=answer_text, name="expert")]}

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
    research_plan = state.get("research_plan", {})
    return [Send("conduct_interview", {
        "analyst": analyst,
        "research_plan": research_plan,
        "messages": [HumanMessage(
            content=f"We are building a Strategic Country Profile for {topic}. As our {analyst.name}, identify the key advocacy bottlenecks and windows of opportunity in your specialized area."
        )]
    }) for analyst in state["analysts"]]


def collect_sections(state: ResearchGraphState):
    """Join point — waits for all parallel interviews to complete before checking knowledge."""
    sections = state.get("sections", [])
    valid = [s for s in sections if s != "FLAG_NO_KNOWLEDGE"]
    return {
        "messages": [AIMessage(content=f"[PROGRESS:50] Interviews complete — {len(valid)} sections collected", name="System")]
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
        "messages": [AIMessage(content="[PROGRESS:ABORTED] Not enough internal knowledge to generate report", name="System")]
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
        "messages": [AIMessage(content="[PROGRESS:55] Preparing report sections...", name="System")]
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
        "messages": [AIMessage(content="[PROGRESS:70] Evidence section complete", name="System")]
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
        "messages": [AIMessage(content="[PROGRESS:75] Gaps section complete", name="System")]
    }


opportunities_instructions = """You are a strategic analyst writing the "Windows of Opportunity" section of a briefing for: {topic}.

You will receive research memos gathered from internal document vaults. Your job is to identify time-sensitive opportunities or crises that the animal advocacy movement should tackle quickly.

INSTRUCTIONS:
1. Focus on windows that could CLOSE — emerging leverage points, policy moments, market shifts, electoral cycles, public attention spikes, or crises requiring immediate response.
2. Ground every opportunity in specific evidence from the memos. Do not speculate beyond what the data supports.
3. Be concrete about WHY the window is time-sensitive — what makes it urgent?
4. NEVER summarise away numeric or statistical data. Preserve all figures exactly.
5. DO NOT mention any AI analyst names, interviewers, or experts.
6. If the evidence does not clearly indicate time-sensitive opportunities, say so transparently rather than fabricating urgency.

{citation_rules}

Research memos:
{context}"""


def write_opportunities(state: ResearchGraphState):
    content = state.get("content", "")
    topic = state["topic"]

    system_message = opportunities_instructions.format(
        topic=topic, 
        context=content,
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
        "messages": [AIMessage(content="[PROGRESS:80] Opportunities section complete", name="System")]
    }


players_instructions = """You are a strategic analyst writing the "Current Players" section of a briefing for: {topic}.

You will receive research memos gathered from internal document vaults. Your job is to identify current players in the animal advocacy ecosystem relevant to the query and what they're currently up to.

INSTRUCTIONS:
1. List organisations, coalitions, government bodies, or key individuals mentioned in the evidence that are active on this topic.
2. For each player, note what the evidence says about their current activities, positions, or campaigns.
3. BE TRANSPARENT ABOUT LIMITATIONS: The internal document vaults may have limited information about who the current players are and what they're doing right now. If the evidence doesn't clearly identify active players, say so explicitly. Do NOT invent or assume what organisations are doing.
4. DO NOT mention any AI analyst names, interviewers, or experts.
5. Preserve any numeric data (e.g., membership numbers, funding figures) exactly as stated.
6. If very little information about players exists in the vaults, a short honest section is better than a padded speculative one.

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
        "messages": [AIMessage(content="[PROGRESS:85] Players section complete", name="System")]
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
    primary_label = STORE_REGISTRY[primary_key][1] if primary_key in STORE_REGISTRY else "Not specified"
    plan_rationale = research_plan.get("rationale", "No research plan rationale available.")

    final_report_str = f"""# Strategic Briefing: {topic}

## How This Research Was Approached

**Primary source store:** {primary_label}

{plan_rationale}

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
            content=f"[PROGRESS:100] Complete\n\n{final_report_str}",
            name="System"
        )]
    }


# ---------------------------------------------------------------------------
# 6. Build the Graph
# ---------------------------------------------------------------------------
builder = StateGraph(ResearchGraphState)
# builder.add_node("generate_layers_briefing", generate_layers_briefing)
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

# builder.add_edge(START, "generate_layers_briefing")
# builder.add_edge("generate_layers_briefing", "create_analysts")
# builder.add_conditional_edges("create_analysts", initiate_all_interviews, ["conduct_interview"])

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
