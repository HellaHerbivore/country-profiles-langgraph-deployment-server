import os
import re
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

# The main brain for planning and writing
llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", api_key=google_api_key)

# The reader tool for digging through your files
gemini_client = genai.Client(api_key=google_api_key)

# Internal Vaults
FOREIGN_ACADEMIC_STORE = "fileSearchStores/research-assistant-vault-7ya8m561y6pn"
GROUND_TRUTH_STORE = "fileSearchStores/groundtruthadvocacyfeedback-2ojwsxpiytnc"

# ---------------------------------------------------------------------------
# 2. Shapes of our Data (Schemas)
# ---------------------------------------------------------------------------
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
    interview: str
    sections: list

class ResearchGraphState(TypedDict):
    topic: str
    max_analysts: int
    human_analyst_feedback: str
    analysts: List[Analyst]
    sections: Annotated[list, operator.add]
    introduction: str
    content: str
    conclusion: str
    messages: Annotated[list, operator.add]
    final_report: str
    structured_report: str

# ---------------------------------------------------------------------------
# 3. Work Nodes (The Steps)
# ---------------------------------------------------------------------------
analyst_instructions="""You are tasked with creating a set of AI analyst personas. Follow these instructions carefully:
1. First, review the research topic:
{topic}
2. Pick the top {max_analysts} themes.
3. Assign one analyst to each theme."""

def create_analysts(state: ResearchGraphState):
    # 1. Grab the topic safely, or use the last chat message
    topic = state.get('topic')
    if not topic and state.get('messages'):
        topic = state['messages'][-1].content
        
    # 2. Grab the max number of analysts safely, or default to 3
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

    # CRITICAL: We return the topic and max_analysts here so 
    # the rest of the graph can find them in the state!
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

    expert_instructions = f"""You are a strict data-retrieval expert.
    Analyst focus: {analyst.persona}
    
    CRITICAL RULES:
    1. You have NO knowledge outside of the files in your internal vaults.
    2. If the answer is not in the files, say EXACTLY: "The internal vaults do not contain this information."
    3. Do not use your own training data to fill in gaps.
    4. Use specific filenames for citations [filename.pdf] at the end of the sentence.
    """

    model_config = types.GenerateContentConfig(
        system_instruction=expert_instructions,
        tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=[FOREIGN_ACADEMIC_STORE, GROUND_TRUTH_STORE]))],
        temperature=0.0,
    )

    chat_history = "\n".join([f"{m.type.capitalize()}: {m.content}" for m in messages])
    prompt = f"Read our chat history and answer the latest question using your files:\n\n{chat_history}"

    print(f"\n\n👀 --- WHAT THE EXPERT WAS ASKED ({analyst.name}) ---")
    print(messages[-1].content) 

    # --- THE NEW FALLBACK CODE ---
    max_tries = 3
    response = None
    
    for try_count in range(max_tries):
        try:
            # We try to ask the model...
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=prompt,
                config=model_config
            )
            break # If it works, break out of the loop!
            
        except errors.ServerError as e:
            # If the server drops the ball, we catch the error here
            print(f"\n⚠️ Server glitch on try {try_count + 1}: {e}")
            
            if try_count < max_tries - 1:
                print("Waiting 3 seconds before we try again...")
                time.sleep(3)
            else:
                # If we tried 3 times and it still failed, give up on this specific question
                print("Server is fully down. Moving on without this answer.")
                return {"messages": [AIMessage(content="FLAG_NO_KNOWLEDGE", name="expert")]}
    # -----------------------------

    # If response is somehow empty (even after passing), catch it
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
3. You MUST keep the exact inline citations used in the interview (e.g., [filename.pdf]). Do not change, hide, or rename them."""

def write_section(state: InterviewState):
    interview = state["interview"]
    analyst = state["analyst"]
   
    if "FLAG_NO_KNOWLEDGE" in interview:
        return {"sections": ["FLAG_NO_KNOWLEDGE"]}

    system_message = section_writer_instructions.format(focus=analyst.description)
    section = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content=f"Use this interview to write your section:\n{interview}")]) 
    
    # --- FIX: Extract text if the model wraps it in a list of dictionaries ---
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
    return [Send("conduct_interview", {
        "analyst": analyst,
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
                # --- Extract text from dict blocks ---
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
    return "write_report"

def abort_report(state: ResearchGraphState):
    final_message = "not enough internal knowledge"
    print("\n⚠️ ABORTED: Not enough internal knowledge.\n")
    return {
        "final_report": final_message,
        "messages": [AIMessage(content="[PROGRESS:ABORTED] Not enough internal knowledge to generate report", name="System")]
    }


report_writer_instructions = """You are a Lead Strategist. Synthesize the expert memos into a briefing for: {topic}.

CRITICAL RULES:
1. Present this as a unified, objective briefing. DO NOT mention any AI analyst names, interviewers, or experts. 
2. You MUST keep the exact inline citations from the memos (e.g., [filename.pdf]). 
3. DO NOT change, rename, or translate the file names into formal titles. 
4. List these exact file names at the bottom under ## Sources.

Memos: 
{context}"""

def write_report(state: ResearchGraphState):
    sections = state.get("sections", [])
    topic = state["topic"]

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
    formatted_str_sections = "\n\n".join(valid_sections)
    
    system_message = report_writer_instructions.format(topic=topic, context=formatted_str_sections)    
    report = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Write a report based upon these memos.")]) 
    
    # --- Ensure final report content is a string too ---
    content = report.content
    if isinstance(content, list):
        content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
    else:
        content = str(content)
        
    return {
        "content": content,
        "messages": [AIMessage(content="[PROGRESS:65] Report draft complete", name="System")]
    }


intro_instructions = "Write the Executive Summary for: {topic} based strictly on the main body:\n{main_report_body}\n\nCRITICAL: Do not mention any analyst or expert names."
conclusion_instructions = "Write the Tractable Interventions for: {topic} based strictly on the main body:\n{main_report_body}\n\nCRITICAL: Do not mention any analyst or expert names."

def write_introduction(state: ResearchGraphState):
    main_body = state.get("content", "")
    topic = state["topic"]
    instructions = intro_instructions.format(topic=topic, main_report_body=main_body)    
    intro = llm.invoke([SystemMessage(content=instructions)] + [HumanMessage(content="Write the report introduction")]) 
    
    content = intro.content
    if isinstance(content, list):
        content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
    else:
        content = str(content)
    return {
        "introduction": content,
        "messages": [AIMessage(content="[PROGRESS:75] Executive summary written", name="System")]
    }


def write_conclusion(state: ResearchGraphState):
    main_body = state.get("content", "")
    topic = state["topic"]
    instructions = conclusion_instructions.format(topic=topic, main_report_body=main_body)    
    conclusion = llm.invoke([SystemMessage(content=instructions)] + [HumanMessage(content="Write the report conclusion")]) 
    
    content = conclusion.content
    if isinstance(content, list):
        content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
    else:
        content = str(content)
    return {"conclusion": content}

def finalize_report(state: ResearchGraphState):
    # 1. Gather the pieces
    content = state.get("content", "")
    intro = state.get("introduction", "")
    conclusion = state.get("conclusion", "")
    topic = state["topic"]
    
    # 2. Build the final string
    if content.startswith("## Strategic Analysis"):
        content = content.replace("## Strategic Analysis", "").strip()
        
    final_report_str = f"{intro}\n\n---\n\n{content}\n\n---\n\n{conclusion}"

    # 3. Return the update (flow continues to restructure_report via graph edges)
    return {
        "final_report": final_report_str,
        "messages": [AIMessage(content=f"[PROGRESS:85] Report finalized\n\n### ✅ Report Finalized\n\n{final_report_str}", name="System")]
    }


# ---------------------------------------------------------------------------
# 5b. Restructure Report Node — Macro / Meso / Micro / Hidden × 7 Themes
# ---------------------------------------------------------------------------
restructure_instructions = """You are an expert policy-research editor. You will receive a completed strategic
country profile report. Your job is to RESTRUCTURE its content — without removing any
detail or any source citations — into the analytical matrix described below.
 
═══════════════════════════════════════════════════════════════════
STRUCTURAL LEVELS  (rows)
═══════════════════════════════════════════════════════════════════
1. **MACRO-LEVEL ACTORS & LEVERS**
   Systemic, national-to-global forces: government bodies, international organisations,
   constitutional or legal frameworks, macroeconomic trends, national-level policy.
 
2. **MESO-LEVEL ACTORS & LEVERS**
   Sector and institutional forces: industry associations, professional bodies, regional
   government, large NGOs, media networks, religious institutions operating at
   institutional/organisational scale.
 
3. **MICRO-LEVEL ACTORS & LEVERS**
   Ground-level and individual forces: grassroots organisations, community leaders,
   individual consumers, local activists, household-level dynamics, frontline workers.
 
4. **HIDDEN / UNDER-EXAMINED ACTORS & LEVERS**
   Forces that are present in the source material but easily overlooked: informal
   economies, unregulated supply chains, cultural taboos, data gaps, silent stakeholders,
   unintended policy side-effects, or any factor the report implies but does not
   foreground.
 
═══════════════════════════════════════════════════════════════════
THEMATIC TAGS  (applied within each level)
═══════════════════════════════════════════════════════════════════
Tag every paragraph or sub-section with ALL themes that apply.
Use the exact tag labels below as inline markers, e.g. `[Legal & Regulatory]`:
 
  [Legal & Regulatory]
  [Political & Policy]
  [Civil Society & Advocacy]
  [Cultural, Religious & Social Context]
  [Economic Factors & Industry]
  [Consumer Profiles & Market Dynamics]
  [Data Availability & Research Landscape]
 
A single paragraph may carry multiple tags.
 
═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════
Return the report in EXACTLY this markdown structure:
 
# Structured Strategic Profile: <topic>
 
## Executive Summary
(Keep the original executive summary intact — every sentence, every figure.)
 
---
 
## 1. Macro-Level Actors & Levers
 
(All macro-level content grouped here. Preserve every detail and every
inline citation such as [filename.pdf]. Prefix each paragraph or
sub-section with the applicable thematic tags.)
 
---
 
## 2. Meso-Level Actors & Levers
 
(Same rules.)
 
---
 
## 3. Micro-Level Actors & Levers
 
(Same rules.)
 
---
 
## 4. Hidden / Under-Examined Actors & Levers
 
(Same rules. If the original report only hints at something, surface it
explicitly here. Keep the inferred statement, but tag it with the specific
source file it is implied from, e.g. *"Implied from [filename.pdf]."*
Do NOT use a vague label like "Implied by source" without naming the file.)
 
---
 
**## Sources**
**THIS SECTION IS MANDATORY. You MUST include it as the final section.**
Copy the EXACT original source list verbatim. Do NOT rename, translate,
remove, or reorder any filename. Every citation that appears anywhere in
the body must also appear in this list.
 
═══════════════════════════════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════════════════════════════
• DO NOT summarise, shorten, or paraphrase. Every sentence of substance from
  the original must appear in the restructured output.
• DO NOT invent new information. Only reorganise what exists.
• If a piece of content fits more than one level, place it in the MOST
  relevant level and add a cross-reference note pointing to the other level,
  e.g. *(See also: Section 2, Meso-Level — Ahimsa reinterpretation)*.
  Apply cross-references generously wherever content touches multiple levels.
• Keep EVERY inline citation exactly as it appeared (e.g., [filename.pdf]).
• The ## Sources section must be identical to the original.
• The Tractable Interventions / conclusion section content should be
  distributed into the appropriate level and tagged, NOT kept as a
  separate section. When merging intervention content into a level,
  INTEGRATE it into the existing analytical paragraph — do NOT append it
  as a separate sentence that restates the same point. Avoid duplication.

WINDOW-OF-OPPORTUNITY MARKING
• Whenever a statement describes a strategic window, time-limited opening,
  or opportunity that could close, prefix the sentence with the 🪟 emoji.
  Windows of opportunity may remain interspersed throughout the body wherever
  they naturally belong — do NOT consolidate them into a separate section.

DETAIL-PRESERVATION GUARDRAILS
• HUMAN-DIMENSION DETAILS ARE NON-NEGOTIABLE. When the source describes
  lived realities — individual actors caught between competing pressures,
  household-level dynamics, ground-level tensions (e.g., livelihood vs.
  conservation, smallholder vs. industry, caste vs. advocacy goals) — you
  MUST preserve the full texture: specific actors named, the nature of the
  tension, who bears the cost, and any qualifying language about scale or
  severity. Condensing "individual small-scale fishers are often caught in
  the crossfire" and "household-level dynamics shape pressure against
  seasonal bans" into a single abstract sentence like "livelihoods and
  conservation goals are in tension" is a CRITICAL FAILURE.
• QUALIFYING LANGUAGE MATTERS. If the original says "often", "sometimes",
  "in some states", "particularly among X group", keep those qualifiers.
  Stripping them generalises the claim beyond what the source supports.
• NARRATIVE CHAINS MUST SURVIVE. If the original builds a causal chain
  (e.g., policy → enforcement gap → informal workaround → livelihood
  impact → political backlash), every link in that chain must appear in
  the restructured output. Dropping middle links destroys the analytical
  value.
 
═══════════════════════════════════════════════════════════════════
ZERO-LOSS VERIFICATION CHECKLIST  (perform before returning output)
═══════════════════════════════════════════════════════════════════
Before you return the restructured report, mentally verify ALL of these:
 
  ✓ Every statistic and numeric figure from the original appears in the output
    (e.g., currency values, percentages, multipliers like "1.5 to 3 times").
  ✓ Every proper noun, programme name, and named concept is present
    (e.g., "White Revolution", "Green Premium", specific city tiers).
  ✓ Every unique [filename.pdf] citation from the original body appears
    at least once in the restructured body AND in the ## Sources list.
  ✓ No two consecutive sentences in the output say the same thing in
    different words (de-duplicate intervention merges).
  ✓ The ## Sources section exists and is the last section of the output.
  ✓ Cross-reference notes exist wherever content spans multiple levels.
  ✓ Every window-of-opportunity statement is prefixed with the 🪟 emoji.
  ✓ Every "implied from" statement in Section 4 names a specific
    [filename.pdf] — none say just "implied by source".
  ✓ DETAIL-LOSS SCAN: Re-read every paragraph in the original that
    describes a tension, trade-off, or lived reality involving specific
    actors (e.g., smallholders, fishers, marginalised communities).
    Confirm the restructured version preserves the SAME level of
    specificity — named actors, qualifying language, causal links,
    and human-scale framing. If any such detail has been abstracted
    or condensed, restore it before returning.
 
If any check fails, fix it before returning.
 
═══════════════════════════════════════════════════════════════════
REPORT TO RESTRUCTURE:
═══════════════════════════════════════════════════════════════════
{report}
"""


def restructure_report(state: ResearchGraphState):
    """Restructure the finalized report into macro/meso/micro/hidden levels with thematic tags."""
    final_report = state.get("final_report", "")
    topic = state["topic"]

    system_message = restructure_instructions.format(report=final_report)
    result = llm.invoke(
        [SystemMessage(content=system_message)]
        + [HumanMessage(content="Restructure this report into the macro/meso/micro/hidden analytical matrix with thematic tags. Preserve all detail and citations.")]
    )

    content = result.content
    if isinstance(content, list):
        content = " ".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])
    else:
        content = str(content)

    return Command(
        update={
            "structured_report": content,
            "messages": [AIMessage(
                content=f"[PROGRESS:100] Complete\n\n### 📊 Structured Profile Complete\n\n{content}",
                name="System"
            )]
        },
        goto=END
    )


builder = StateGraph(ResearchGraphState)
builder.add_node("create_analysts", create_analysts)
builder.add_node("conduct_interview", interview_builder.compile())
builder.add_node("collect_sections", collect_sections)
builder.add_node("abort_report", abort_report)       
builder.add_node("write_report", write_report)
builder.add_node("write_introduction", write_introduction)
builder.add_node("write_conclusion", write_conclusion)
builder.add_node("finalize_report", finalize_report)
builder.add_node("restructure_report", restructure_report)

builder.add_edge(START, "create_analysts")
builder.add_conditional_edges("create_analysts", initiate_all_interviews, ["conduct_interview"])

# All parallel interviews join here, THEN check knowledge once
builder.add_edge("conduct_interview", "collect_sections")
builder.add_conditional_edges("collect_sections", check_knowledge, ["write_report", "abort_report"])

builder.add_edge("write_report", "write_introduction")
builder.add_edge("write_report", "write_conclusion")
builder.add_edge(["write_conclusion", "write_introduction"], "finalize_report")
builder.add_edge("finalize_report", "restructure_report")
builder.add_edge("restructure_report", END)
builder.add_edge("abort_report", END)

graph = builder.compile()