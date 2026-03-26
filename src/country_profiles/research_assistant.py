import os
from dotenv import load_dotenv

import re
import json

import operator
from pydantic import BaseModel, Field
from typing import Annotated, List
from typing_extensions import TypedDict

from langchain_community.document_loaders import WikipediaLoader
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, get_buffer_string

# OpenRouter Import
from langchain_openrouter import ChatOpenRouter 
from langgraph.constants import Send
from langgraph.graph import END, MessagesState, START, StateGraph

# Gemini Native Client (for File Search)
from google import genai
from google.genai import types
from google.genai.types import FunctionCallingConfigMode

# Make sure GOOGLE_API_KEY is in your .env alongside OPENROUTER_API_KEY
gemini_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY")) 

# Two Internal Vaults
DESKTOP_STORE = "fileSearchStores/research-assistant-vault-7ya8m561y6pn"
GROUND_TRUTH_STORE = "fileSearchStores/groundtruthadvocacyfeedback-2ojwsxpiytnc"

### LLM
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY is missing from your .env file!")

llm = ChatOpenRouter(model="google/gemini-3.1-flash-lite-preview", api_key=api_key)

### Schema 

class Analyst(BaseModel):
    affiliation: str = Field(
        description="Primary affiliation of the analyst.",
    )
    name: str = Field(
        description="Name of the analyst."
    )
    role: str = Field(
        description="Role of the analyst in the context of the topic.",
    )
    description: str = Field(
        description="Description of the analyst focus, concerns, and motives.",
    )
    @property
    def persona(self) -> str:
        return f"Name: {self.name}\nRole: {self.role}\nAffiliation: {self.affiliation}\nDescription: {self.description}\n"

class Perspectives(BaseModel):
    analysts: List[Analyst] = Field(
        description="Comprehensive list of analysts with their roles and affiliations.",
    )

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

class SearchQuery(BaseModel):
    search_query: str = Field(None, description="Search query for retrieval.")

class ResearchGraphState(TypedDict):
    topic: str 
    max_analysts: int 
    human_analyst_feedback: str 
    analysts: List[Analyst] 
    sections: Annotated[list, operator.add] 
    
    # Report fields
    introduction: str 
    content: str 
    conclusion: str 
    
    # Layer tracking
    macro_context: str  
    meso_context: str   
    micro_context: str  
    hidden_context: str 
    
    final_report: str 

### Nodes and edges

analyst_instructions="""You are tasked with creating a set of AI analyst personas. Follow these instructions carefully:

1. First, review the research topic:
{topic}
        
2. Examine any editorial feedback that has been optionally provided to guide creation of the analysts: 
        
{human_analyst_feedback}
    
3. Determine the most interesting themes based upon documents and / or feedback above.
                    
4. Pick the top {max_analysts} themes.

5. Assign one analyst to each theme."""

def create_analysts(state: GenerateAnalystsState):
    topic=state['topic']
    max_analysts=state['max_analysts']
    human_analyst_feedback=state.get('human_analyst_feedback', '')
        
    structured_llm = llm.with_structured_output(Perspectives)
    system_message = analyst_instructions.format(topic=topic,
                                                 human_analyst_feedback=human_analyst_feedback, 
                                                 max_analysts=max_analysts)

    analysts = structured_llm.invoke([SystemMessage(content=system_message)]+[HumanMessage(content="Generate the set of analysts.")])
    return {"analysts": analysts.analysts}

def human_feedback(state: GenerateAnalystsState):
    """ No-op node that should be interrupted on """
    pass

# Generate analyst question
question_instructions = """You are an analyst tasked with interviewing an expert to learn about a specific topic. 

Your goal is boil down to interesting and specific insights related to your topic.

1. Interesting: Insights that people will find surprising or non-obvious.
2. Specific: Insights that avoid generalities and include specific examples from the expert.

Here is your topic of focus and set of goals: {goals}
        
Begin by introducing yourself using a name that fits your persona, and then ask your question.
Continue to ask questions to drill down and refine your understanding of the topic.
        
When you are satisfied with your understanding, complete the interview with: "Thank you so much for your help!"
Remember to stay in character throughout your response, reflecting the persona and goals provided to you."""

def generate_question(state: InterviewState):
    analyst = state["analyst"]
    messages = state["messages"]

    system_message = question_instructions.format(goals=analyst.persona)
    question = llm.invoke([SystemMessage(content=system_message)]+messages)
    return {"messages": [question]}

# Search query writing
search_instructions = SystemMessage(content="""You help an analyst who already has deep, rich files in a private vault. 

Your main goal is to return an empty string ("") for the search query. This forces the system to look in the internal file stores first.

ONLY write a web search query if the question asks for breaking news from the last few weeks, or specific contact info for a local group that would not be in a deep report. 
Otherwise, return an empty string.""")

def search_web(state: InterviewState):
    """Retrieve docs from web search using Tavily safely."""
    tavily_search = TavilySearchResults(max_results=1) 

    # 1. Ask the LLM for the search query
    structured_llm = llm.with_structured_output(SearchQuery)
    search_query = structured_llm.invoke([search_instructions] + state['messages'])
    
    # Safety check: ensure we actually got the object back, not a string
    if isinstance(search_query, str):
        query_text = search_query
    else:
        query_text = search_query.search_query
        
    if not query_text or query_text.isspace():
        return {"context": []}

    # 2. Fetch the data
    search_docs = tavily_search.invoke({"query": query_text})

    # 3. Safety check: Did the tool return a string instead of a list?
    if isinstance(search_docs, str):
        try:
            # Try to parse it if it is a string of JSON data
            search_docs = json.loads(search_docs)
        except json.JSONDecodeError:
            # If it is a flat error string (like "API key missing")
            return {"context": [f"Search tool returned a text message: {search_docs}"]}

    # 4. Final safety guard
    if not isinstance(search_docs, list):
         return {"context": ["Search tool returned an unexpected data shape."]}

    # 5. Safely build the string using .get()
    formatted_search_docs = "\n\n---\n\n".join(
        [
            f'<Document href="{doc.get("url", "No URL")}"/>\n{doc.get("content", "No content")}\n</Document>'
            if isinstance(doc, dict) else f'<Document>{doc}</Document>'
            for doc in search_docs
        ]
    )

    return {"context": [formatted_search_docs]}

def search_wikipedia(state: InterviewState):
    structured_llm = llm.with_structured_output(SearchQuery)
    search_query_object = structured_llm.invoke([search_instructions] + state['messages'])
    query_text = search_query_object.search_query

    # Guardrail for empty searches
    if not query_text or query_text.isspace():
        return {"context": ["The analyst attempted an empty search. Skipping Wikipedia retrieval for this turn."]}

    try:
        search_docs = WikipediaLoader(query=query_text, load_max_docs=2).load()
        if not search_docs:
            return {"context": [f"No Wikipedia results found for '{query_text}'."]}

        formatted_search_docs = "\n\n---\n\n".join(
            [
                f'<Document source="{doc.metadata.get("source", "unknown")}" page="{doc.metadata.get("page", "")}"/>\n{doc.page_content}\n</Document>'
                for doc in search_docs
            ]
        )
        return {"context": [formatted_search_docs]}
    except Exception as e:
        return {"context": [f"Wikipedia search failed for '{query_text}': {str(e)}"]}

# Generate expert answer
answer_instructions = """You are an expert being interviewed by an analyst.

Here is analyst area of focus: {goals}. 
        
You goal is to answer a question posed by the interviewer.
To answer question, use this context:
        
{context}

When answering questions, follow these guidelines:
1. Use only the information provided in the context. 
2. Do not introduce external information or make assumptions beyond what is explicitly stated in the context.
3. The context contain sources at the topic of each individual document.
4. Include these sources your answer next to any relevant statements. For example, for source # 1 use [1]. 
5. List your sources in order at the bottom of your answer. [1] Source 1, [2] Source 2, etc
6. If the source is: <Document source="assistant/docs/llama3_1.pdf" page="7"/>' then just list: 
[1] assistant/docs/llama3_1.pdf, page 7 
And skip the addition of the brackets as well as the Document source preamble in your citation."""

def generate_answer(state: InterviewState):
    analyst = state["analyst"]
    messages = state["messages"]
    
    # 1. Cleanly check for web data so we don't confuse the model with blank strings
    context_list = state.get("context", [])
    web_context_string = ""
    if context_list:
        web_context_string = "\n\nWEB CONTEXT (Use only if the vaults lack the answer):\n" + "\n\n".join(context_list)

    # 2. Give the model a clear way out so it does not fake answers
    expert_instructions = f"""You are a research expert helping an animal advocacy charity.
    Analyst focus: {analyst.persona}
    
    SEARCH RULES:
    1. Look in the internal vaults first to answer the question. 
    2. If you find the answer, use the actual filenames for citations (e.g., [karamchedu-2025.pdf]).
    3. IF you cannot find the answer in the files or the web context, DO NOT make up an answer. Say exactly: "I could not find the answer in the files."{web_context_string}
    """

    model_config = types.GenerateContentConfig(
        system_instruction=expert_instructions,
        tools=[
            types.Tool(
                file_search=types.FileSearch(
                    file_search_store_names=[DESKTOP_STORE, GROUND_TRUTH_STORE]
                )
            )
        ],
        temperature=0.0,
    )

    # 3. String the whole chat together so the search tool keeps the thread
    chat_history = "\n".join([f"{m.type.capitalize()}: {m.content}" for m in messages])
    prompt = f"Read our chat history and answer the latest question using your files:\n\n{chat_history}"

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash-lite", 
        contents=prompt,
        config=model_config
    )

    answer_text = response.text if response.text else "I could not find the answer in the files."
    
    return {"messages": [AIMessage(content=answer_text, name="expert")]}
    

def save_interview(state: InterviewState):
    messages = state["messages"]
    interview = get_buffer_string(messages)
    return {"interview": interview}

def route_messages(state: InterviewState, name: str = "expert"):
    messages = state["messages"]
    max_num_turns = state.get('max_num_turns',2)

    num_responses = len(
        [m for m in messages if isinstance(m, AIMessage) and m.name == name]
    )

    if num_responses >= max_num_turns:
        return 'save_interview'

    last_question = messages[-2]
    
    if "Thank you so much for your help" in last_question.content:
        return 'save_interview'
    return "ask_question"


# Write a summary (section of the final report) of the interview
section_writer_instructions = """You are an expert technical writer. 
            
Your task is to create a short, easily digestible section of a report based on a set of source documents.

1. Analyze the content of the source documents: 
- The name of each source document is at the start of the document, with the <Document tag.
        
2. Create a report structure using markdown formatting:
- Use ## for the section title
- Use ### for sub-section headers
        
3. Write the report following this structure:
a. Title (## header)
b. Summary (### header)
c. Sources (### header)

4. Make your title engaging based upon the focus area of the analyst: 
{focus}

5. For the summary section:
- Set up summary with general background / context related to the focus area of the analyst
- Emphasize what is novel, interesting, or surprising about insights gathered from the interview
- Create a numbered list of source documents, as you use them
- Do not mention the names of interviewers or experts
- Aim for approximately 400 words maximum
- Use numbered sources in your report (e.g., [1], [2]) based on information from source documents
        
6. In the Sources section:
- Include all sources used in your report
- Provide full links to relevant websites or specific document paths
- Separate each source by a newline. Use two spaces at the end of each line to create a newline in Markdown.
        
8. Final review:
- Ensure the report follows the required structure
- Include no preamble before the title of the report
- Check that all guidelines have been followed"""

def write_section(state: InterviewState):
    interview = state["interview"]
    context = state["context"]
    analyst = state["analyst"]
   
    system_message = section_writer_instructions.format(focus=analyst.description)
    section = llm.invoke([SystemMessage(content=system_message)]+[HumanMessage(content=f"Use this source to write your section: {context}")]) 
    return {"sections": [section.content]}

# Add nodes and edges 
interview_builder = StateGraph(InterviewState)
interview_builder.add_node("ask_question", generate_question)
interview_builder.add_node("search_web", search_web)
interview_builder.add_node("search_wikipedia", search_wikipedia)
interview_builder.add_node("answer_question", generate_answer)
interview_builder.add_node("save_interview", save_interview)
interview_builder.add_node("write_section", write_section)

# Flow
interview_builder.add_edge(START, "ask_question")
interview_builder.add_edge("ask_question", "search_web")
interview_builder.add_edge("ask_question", "search_wikipedia")
interview_builder.add_edge("search_web", "answer_question")
interview_builder.add_edge("search_wikipedia", "answer_question")
interview_builder.add_conditional_edges("answer_question", route_messages,['ask_question','save_interview'])
interview_builder.add_edge("save_interview", "write_section")
interview_builder.add_edge("write_section", END)

def initiate_all_interviews(state: ResearchGraphState):
    human_analyst_feedback=state.get('human_analyst_feedback','approve')
    if human_analyst_feedback and human_analyst_feedback.lower() != 'approve':
        return "create_analysts"
    else:
        topic = state["topic"]
        return [Send("conduct_interview", {"analyst": analyst,
                                           "messages": [HumanMessage(
                                               content=f"We are building a Strategic Country Profile for {topic}. As our {analyst.name}, identify the key advocacy bottlenecks and windows of opportunity in your specialized area."
                                           )]
                                           }) for analyst in state["analysts"]]

# Write a report based on the interviews
report_writer_instructions = """You are a Lead Strategist for an advocacy fund. 
You are synthesizing a Country Profile for: {topic}.

Your goal is to organize findings into four strategic layers:
1. Macro: National laws, political climate, and economic drivers.
2. Meso: Institutional structures, corporate interests, and industry standards.
3. Micro: Local grassroots capacity and specific site-level data.
4. Hidden: Informal power, compliance gaps, and enforcement bottlenecks.

Your task:
1. Synthesize the provided expert memos into a cohesive briefing so that the user understands how change actually happens in a country or region.
2. Clearly highlight where 'Desktop Research' (Macro/Meso) conflicts with 'Ground-Truth' (Micro/Hidden).
3. Identify 'Tractable Interventions'—specific areas where advocacy could have a high impact. Segment these interventions into "movement building" interventions and "institutional change" interventions.

CITATION RULES:
- Keep all inline citations from the memos (e.g., [1], [2]).
- At the VERY END of your text, create a master list of all sources.
- You MUST use exactly this header for the sources:
## Sources

Memos: 
{context}"""

def write_report(state: ResearchGraphState):
    sections = state["sections"]
    topic = state["topic"]

    formatted_str_sections = "\n\n".join([f"{section}" for section in sections])
    
    system_message = report_writer_instructions.format(topic=topic, context=formatted_str_sections)    
    report = llm.invoke([SystemMessage(content=system_message)]+[HumanMessage(content=f"Write a report based upon these memos.")]) 
    return {"content": report.content}

# Write the introduction
intro_instructions = """You are writing the Introduction for a Strategic Country Profile on: {topic}.

Header format:
# Country Profile: {topic}
## Executive Summary

Task: Preview the advocacy landscape and the overall 'tractability' for interventions. 
Base your introduction strictly on the main report body provided below.

Main Report Body: 
{main_report_body}"""

# Write the conclusion
conclusion_instructions = """You are writing the Conclusion for a Strategic Country Profile on: {topic}.

Header format:
## Tractable Interventions

Task: Summarize the top 3 high-leverage opportunities for impact mentioned in the report. Clearly state what a successful advocacy roadmap looks like.
Base your conclusion strictly on the main report body provided below.

Main Report Body: 
{main_report_body}"""

def write_introduction(state: ResearchGraphState):
    # Now we read the finished 'content', not the raw sections
    main_body = state.get("content", "")
    topic = state["topic"]
    
    instructions = intro_instructions.format(topic=topic, main_report_body=main_body)    
    intro = llm.invoke([SystemMessage(content=instructions)]+[HumanMessage(content="Write the report introduction")]) 
    return {"introduction": intro.content}

def write_conclusion(state: ResearchGraphState):
    # Now we read the finished 'content', not the raw sections
    main_body = state.get("content", "")
    topic = state["topic"]
    
    instructions = conclusion_instructions.format(topic=topic, main_report_body=main_body)    
    conclusion = llm.invoke([SystemMessage(content=instructions)]+[HumanMessage(content="Write the report conclusion")]) 
    return {"conclusion": conclusion.content}

# Bring it all together
# def finalize_report(state: ResearchGraphState):
#     content = state["content"]
    
#     # Clean up the top header
#     if content.startswith("## Strategic Analysis"):
#         content = content.replace("## Strategic Analysis", "").strip()
        
#     # Smarter cutting: This finds "## Sources" even if the AI messes up the markdown
#     parts = re.split(r'\n#+\s*Sources\n?', content)
    
#     if len(parts) > 1:
#         content = parts[0].strip()
#         sources = parts[1].strip()
#     else:
#         sources = None

#     # Stitch it all together in the right order
#     final_report = state["introduction"] + "\n\n---\n\n" + content + "\n\n---\n\n" + state["conclusion"]
    
#     # Pin the sources to the very bottom
#     if sources is not None:
#         final_report += "\n\n---\n\n## Sources\n" + sources
        
#     return {"final_report": final_report}

# Download final report as .md
def finalize_report(state: ResearchGraphState):
    content = state["content"]
    topic = state["topic"]
    
    # Clean up the top header
    if content.startswith("## Strategic Analysis"):
        content = content.replace("## Strategic Analysis", "").strip()
        
    # Smarter cutting for the Sources
    parts = re.split(r'\n#+\s*Sources\n?', content)
    
    if len(parts) > 1:
        content = parts[0].strip()
        sources = parts[1].strip()
    else:
        sources = None

    # Stitch it all together
    final_report = state["introduction"] + "\n\n---\n\n" + content + "\n\n---\n\n" + state["conclusion"]
    
    if sources is not None:
        final_report += "\n\n---\n\n## Sources\n" + sources

    # --- NEW: AUTO-SAVE FEATURE ---
    # Create a safe file name from the topic (e.g., "Maharashtra_Dairy.md")
    safe_topic = "".join([c if c.isalnum() else "_" for c in topic])
    filename = f"{safe_topic}_Country_Profile.md"
    
    # Write the file to your computer
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_report)
        print(f"\n✅ SUCCESS: Report saved locally as {filename}\n")
    except Exception as e:
        print(f"\n❌ Error saving file: {e}\n")

    return {"final_report": final_report}

# Add nodes and edges 
builder = StateGraph(ResearchGraphState)
builder.add_node("create_analysts", create_analysts)
builder.add_node("human_feedback", human_feedback)
builder.add_node("conduct_interview", interview_builder.compile())
builder.add_node("write_report",write_report)
builder.add_node("write_introduction",write_introduction)
builder.add_node("write_conclusion",write_conclusion)
builder.add_node("finalize_report",finalize_report)

# Logic
builder.add_edge(START, "create_analysts")
builder.add_edge("create_analysts", "human_feedback")
builder.add_conditional_edges("human_feedback", initiate_all_interviews, ["create_analysts", "conduct_interview"])

# 1. Interviews feed into the main report writer FIRST
builder.add_edge("conduct_interview", "write_report")

# 2. Once the main report is written, it triggers the intro and conclusion
builder.add_edge("write_report", "write_introduction")
builder.add_edge("write_report", "write_conclusion")

# 3. Once BOTH the intro and conclusion are done, stitch it all together
builder.add_edge(["write_conclusion", "write_introduction"], "finalize_report")
builder.add_edge("finalize_report", END)

# Compile with memory to allow resuming after the feedback interruption
graph = builder.compile(interrupt_before=['human_feedback'])