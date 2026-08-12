import os
import time
import cohere
from typing import Dict, List, TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient, models
from fastembed import SparseTextEmbedding
from dotenv import load_dotenv

load_dotenv()

class GraphState(TypedDict):
    original_question: str
    question: str
    session_id: str
    generation: str
    documents: List[str]
    all_retrieved_chunks: List[str]
    sub_queries: List[str] 
    retrieval_time: float
    rerank_time: float
    total_tokens: int 
    logs: List[str]
    loop_count: int

llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", temperature=0)
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"), api_key=os.getenv("QDRANT_API_KEY", ""), timeout=60.0)
cohere_client = cohere.Client(os.getenv("COHERE_API_KEY"))

def _clean(content) -> str:
    if isinstance(content, list): return " ".join([b.get("text", str(b)) if isinstance(b, dict) else str(b) for b in content])
    return str(content)

def get_tokens(ai_msg) -> int:
    if hasattr(ai_msg, 'usage_metadata') and ai_msg.usage_metadata:
        return ai_msg.usage_metadata.get('total_tokens', 0)
    return 0

def retrieve(state: GraphState) -> Dict:
    question, session_id = state["question"], state["session_id"]
    current_loops = state.get("loop_count", 0) + 1
    
    logs = state.get("logs", [])
    total_tokens = state.get("total_tokens", 0)
    
    logs.append(f"  🟢 [NODE: RETRIEVE] (Pass {current_loops}) Initiating Multi-Query Retrieval for user: {session_id}...")
    start_retrieval = time.time()
    
    logs.append("  🔍 [NODE: RETRIEVE] Decomposing complex query into sub-queries...")
    
    decompose_prompt = f"""You are an expert search assistant. Break the following complex user question into distinct, single-topic search queries. 
    
    CRITICAL RULES:
    1. PRESERVE ALL CONSTRAINTS: You must retain specific page numbers, names, dates, or explicit filters (e.g., keep "on page 1").
    2. DO NOT GENERALIZE: Do not abstract specific terms into generic categories.
    3. If the question is already a single topic, output the original question exactly as written.
    4. Output strictly one query per line, with no bullet points, numbers, or extra text.
    
    Question: '{question}'"""
    
    ai_msg = llm.invoke(decompose_prompt)
    total_tokens += get_tokens(ai_msg)
    
    raw_sub_queries = _clean(ai_msg.content).strip().split('\n')
    sub_queries = [q.strip() for q in raw_sub_queries if q.strip()]
    
    logs.append(f"  🧩 [NODE: RETRIEVE] Split into {len(sub_queries)} targeted queries: {sub_queries}")

    all_raw_docs = []
    
    for sq in sub_queries:
        query_dense = embeddings.embed_query(sq)
        sparse_result = list(sparse_model.embed([sq]))[0]
        query_sparse = models.SparseVector(indices=sparse_result.indices.tolist(), values=sparse_result.values.tolist())
        
        # 🚀 FIX: Bumped limit to 20 so cross-table comparative queries don't starve out small chunks
        results = qdrant_client.query_points(
            collection_name="multimodal_crag_v6", 
            prefetch=[
                models.Prefetch(query=query_dense, using="dense", limit=20), 
                models.Prefetch(query=query_sparse, using="sparse", limit=20) 
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=models.Filter(must=[models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))]),
            limit=20
        ).points
        
        for res in results:
            all_raw_docs.append(f"[Page: {res.payload.get('page', '?')}] {res.payload['content']}")

    unique_raw_docs = list(set(all_raw_docs))
    retrieval_time = round(time.time() - start_retrieval, 2)
    
    if not unique_raw_docs: 
        logs.append("  ⚠️ [NODE: RETRIEVE] 0 chunks returned from Qdrant Database.")
        return {"documents": [], "all_retrieved_chunks": [], "sub_queries": sub_queries, "retrieval_time": retrieval_time, "rerank_time": 0.0, "total_tokens": total_tokens, "logs": logs, "loop_count": current_loops}

    logs.append(f"  🧠 [NODE: RERANKER] Sending {len(unique_raw_docs)} deduplicated chunks to Cohere API...")
    start_rerank = time.time()
    
    # 🚀 FIX: Bumped top_n to 15 to ensure large contrasting lists easily survive the cut
    reranked = cohere_client.rerank(model="rerank-english-v3.0", query=question, documents=unique_raw_docs, top_n=15)
    rerank_time = round(time.time() - start_rerank, 2)
    
    best_docs = [unique_raw_docs[hit.index] for hit in reranked.results]
    
    return {
        "documents": best_docs, 
        "all_retrieved_chunks": unique_raw_docs, 
        "sub_queries": sub_queries, 
        "retrieval_time": retrieval_time, 
        "rerank_time": rerank_time, 
        "total_tokens": total_tokens,
        "logs": logs, 
        "loop_count": current_loops
    }

def grade_relevance(state: GraphState) -> Dict:
    logs = state["logs"]
    logs.append("  ⚖️ [NODE: GRADER] Evaluating chunk relevance...")
    prompt = f"""You are an elite Relevance Grader for a RAG system. 
Your ONLY job is to determine if the provided Context contains sufficient raw facts, data, or evidence to address the core topic of the user's Question. 
CRITICAL RULE: The Context does NOT need to contain the final synthesized answer. It only needs to contain the raw ingredients required for another AI to generate the answer. 
Ignore complex instructions in the query (like summarize, analyze, compare, list, or format) and focus strictly on whether the underlying topical data is present in the context.
Context: {state['documents']}
Question: '{state['question']}'
If sufficient raw data is present, output exactly 'good'. If the context is completely unrelated, output exactly 'bad'."""
    ai_msg = llm.invoke(prompt)
    grade = _clean(ai_msg.content).strip().lower()
    return {"logs": logs, "generation": grade, "total_tokens": state.get("total_tokens", 0) + get_tokens(ai_msg)}

def decide_to_generate(state: GraphState) -> Literal["generate", "rewrite"]:
    choice = "generate" if "good" in state["generation"] else "rewrite"
    if state.get("loop_count", 0) >= 3: choice = "generate"
    state["logs"].append(f"  🔀 [ROUTER] Relevance Grader decided to route to: {choice.upper()}")
    return choice

def rewrite_query(state: GraphState) -> Dict:
    logs = state["logs"]
    logs.append("  🟠 [NODE: REWRITER] Bad chunks or hallucination detected. Transforming query parameters...")
    prompt = f"""You are an expert Query Optimizer for a RAG system.
Your task is to refine the user's query to make it better for a vector database search.

CRITICAL RULES:
1. KEEP IT SIMPLE: Do not over-complicate the query or add unnecessary nonsense details. Keep it very close to the original user intent.
2. REMOVE FLUFF: Remove conversational filler words (e.g., "please tell me", "give me all").
3. TARGETED SYNONYMS: Only if the user uses a vague term (like "picture" or "visual"), add exactly 1 or 2 precise synonyms (like "visual element, image"). Do not spam a massive list of synonyms.
4. STRICTLY INTERNAL FOCUS: Do not hallucinate external tools, programming languages, or out-of-scope concepts.
5. PRESERVE CONSTRAINTS: Keep specific names, dates, metrics, and page numbers intact.

Original Query: '{state['question']}'
Output ONLY the optimized query string and nothing else."""
    ai_msg = llm.invoke(prompt)
    new_query = _clean(ai_msg.content).strip()
    return {"question": new_query, "logs": logs, "total_tokens": state.get("total_tokens", 0) + get_tokens(ai_msg)}

def generate_answer(state: GraphState) -> Dict:
    logs = state["logs"]
    logs.append("  ⚙️ [NODE: GENERATOR] Good chunks found! Synthesizing answer...")
    
    # 🚀 FIX: Elite Extraction Protocol to prevent list truncation and comparison failures
    prompt = f"""You are an elite analytical AI expert in document extraction. Answer the user's question completely using ONLY the provided context.
    
    CRITICAL EXTRACTION RULES:
    1. PRECISION COMPARISONS: If the user asks to compare multiple items (e.g., Variant A vs Variant B), actively search the context for ALL items. Do not assume one is missing just because the other has more text.
    2. EXACT LISTING & COUNTING: If asked to name a specific number of items (e.g., "6 features"), carefully identify the contiguous sequence of items corresponding to that request. Do not mistakenly include section headers or surrounding layout text (e.g., do not include "ADAS VISUALIZATION" as a feature).
    3. DIAGRAMS & SCHEMAS: Many PDF diagrams are built using raw text elements instead of images. Synthesize the answer using the available text blocks from that page without requiring an explicit "image" tag.
    4. ZERO HALLUCINATION: Provide a highly detailed answer using ONLY the provided context. If the data is genuinely missing from the chunks, state "I cannot find this information." NEVER guess or use outside knowledge.
    
    Context: {state['documents']}
    Question: {state.get('original_question', state['question'])}"""
    
    ai_msg = llm.invoke(prompt)
    response = _clean(ai_msg.content)
    return {"generation": response, "logs": logs, "total_tokens": state.get("total_tokens", 0) + get_tokens(ai_msg)}

def evaluate_hallucination(state: GraphState) -> Dict:
    logs = state["logs"]
    logs.append("  🛡️ [NODE: EVALUATOR] Checking generation for hallucinations...")
    prompt = f"""Verify if this generated answer is supported by the context facts.
    
    Context: {state['documents']}
    Answer: {state['generation']}
    
    First, think step-by-step and list the facts in the answer and whether they are found in the context.
    Finally, on a new line, output exactly your verdict wrapped in XML tags: <verdict>faithful</verdict> or <verdict>hallucinated</verdict>."""
    
    ai_msg = llm.invoke(prompt)
    content = _clean(ai_msg.content).strip().lower()
    grade = "faithful" if "<verdict>faithful</verdict>" in content else "hallucinated"
    logs.append(f"_{grade}_") 
    return {"logs": logs, "generation": state["generation"], "total_tokens": state.get("total_tokens", 0) + get_tokens(ai_msg)}

def check_faithfulness(state: GraphState) -> Literal["faithful", "rewrite"]:
    choice = "faithful" if "faithful" in state["logs"][-1].lower() else "rewrite"
    if state.get("loop_count", 0) >= 3: choice = "faithful"
    state["logs"].pop() 
    state["logs"].append(f"  🔀 [ROUTER] Hallucination Evaluator decided to route to: {choice.upper()}")
    return choice

workflow = StateGraph(GraphState)
workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_relevance", grade_relevance)
workflow.add_node("rewrite_query", rewrite_query)
workflow.add_node("generate_answer", generate_answer)
workflow.add_node("evaluate_hallucination", evaluate_hallucination)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "grade_relevance")
workflow.add_conditional_edges("grade_relevance", decide_to_generate, {"generate": "generate_answer", "rewrite": "rewrite_query"})
workflow.add_edge("generate_answer", "evaluate_hallucination")
workflow.add_conditional_edges("evaluate_hallucination", check_faithfulness, {"faithful": END, "rewrite": "rewrite_query"})
workflow.add_edge("rewrite_query", "retrieve")
crag_agent = workflow.compile()