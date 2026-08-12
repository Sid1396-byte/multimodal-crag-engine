import os
import uuid
import json
import time 
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from app.services.document_parser import process_and_store_pdf
from app.services.crag_workflow import crag_agent
from app.services.metrics_evaluator import run_deepeval_suite

router = APIRouter()

@router.get("/")
async def serve_landing():
    return FileResponse("frontend/landing.html")

@router.get("/workspace")
async def serve_workspace():
    return FileResponse("frontend/index.html")

# 🚀 NEW: Added route for the Architecture Page
@router.get("/architecture")
async def serve_architecture_page():
    return FileResponse("frontend/architecture.html")

BOOT_ID = str(uuid.uuid4())

@router.get("/api/boot_id")
def get_boot_id():
    return {"boot_id": BOOT_ID}

@router.post("/api/upload")
async def upload_document(file: UploadFile = File(...), session_id: str = Form(...)):
    if not file.filename.endswith(".pdf"): raise HTTPException(status_code=400, detail="Only PDF files allowed.")
    try:
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{file.filename}")
        
        with open(temp_path, "wb") as buffer: buffer.write(await file.read())
        chunks_count = process_and_store_pdf(temp_path, session_id=session_id)
        
        return {"status": "success", "message": f"Processed {chunks_count} elements into Workspace {session_id[:8]}."}
    except Exception as e:
        print(f"❌ [CRASH] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'temp_path' in locals() and os.path.exists(temp_path): os.remove(temp_path)

@router.post("/api/query")
def process_query(question: str = Form(...), session_id: str = Form(...)):
    try:
        start_time = time.time()
        agent_log_start = f"🚀 [AGENT] RAG Query from {session_id}: '{question}'"
        print(agent_log_start)
        
        initial_state = {
            "original_question": question, "question": question, "session_id": session_id, 
            "logs": [], "documents": [], "all_retrieved_chunks": [], "sub_queries": [], 
            "retrieval_time": 0.0, "rerank_time": 0.0, "total_tokens": 0, "generation": "", "loop_count": 0
        }
        
        result = crag_agent.invoke(initial_state, config={"recursion_limit": 25})
        full_logs = [agent_log_start] + result["logs"]
        total_time = round(time.time() - start_time, 2)
        
        return {
            "answer": result["generation"],
            "pipeline_logs": full_logs,
            "sub_queries": result.get("sub_queries", []), 
            "all_chunks": result.get("all_retrieved_chunks", []),
            "top_chunks": result.get("documents", []),
            "retrieval_time": result.get("retrieval_time", 0.0),
            "rerank_time": result.get("rerank_time", 0.0),
            "total_tokens": result.get("total_tokens", 0),
            "total_time": total_time,
            "documents": json.dumps(result["documents"]) 
        }
    except Exception as e:
        print(f"❌ [QUERY CRASH] {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/evaluate")
def evaluate_answer(question: str = Form(...), generation: str = Form(...), contexts: str = Form(...)):
    try:
        context_list = json.loads(contexts)
        return run_deepeval_suite(query=question, output_text=generation, contexts=context_list)
    except Exception as e:
        return {"answer_relevancy": 0.0, "relevancy_reason": "Failed to evaluate.", "faithfulness": 0.0, "faithfulness_reason": "Failed to evaluate."}
