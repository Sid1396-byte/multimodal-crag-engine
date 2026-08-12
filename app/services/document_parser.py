import os
import uuid
import requests
import time
import base64
import fitz  # PyMuPDF
from qdrant_client import QdrantClient, models
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from fastembed import SparseTextEmbedding
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage 

load_dotenv()

# Configurations
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION_NAME = "multimodal_crag_v6"

# Initialize Qdrant Client 
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60.0)

# Initialize AI Clients
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-2")
vision_llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", temperature=0)
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

# 🚀 FIX: Forces Gemini's block lists into clean, searchable strings
def _clean_content(content) -> str:
    if isinstance(content, list):
        return " ".join([b.get("text", str(b)) if isinstance(b, dict) else str(b) for b in content])
    return str(content)

def init_vector_db():
    """Initializes the Qdrant Collection with isolated workspace payload tracking."""
    if not qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": models.VectorParams(size=3072, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()}
        )
        qdrant_client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="session_id",
            field_schema=models.PayloadSchemaType.KEYWORD
        )

def get_google_embedding_with_retry(text: str, retries: int = 3):
    """Paces and recovers embedding generation requests securely."""
    for attempt in range(retries):
        try:
            time.sleep(0.3) 
            return embeddings.embed_query(text)
        except Exception as e:
            if attempt == retries - 1: raise e
            time.sleep(2.0)

def process_and_store_pdf(file_path: str, session_id: str):
    """Dual-Track Document Parser: Unstructured for text/tables, PyMuPDF for Vector & Raster Graphics."""
    init_vector_db()
    points = []
    
    # ==========================================
    # 🚀 TRACK 1: UNSTRUCTURED (Text, Layout & Tables)
    # ==========================================
    print(f"📄 [TRACK 1] Starting Unstructured text and table extraction...")
    api_url = os.getenv("UNSTRUCTURED_API_URL", "https://api.unstructured.io/general/v0/general")
    api_key = os.getenv("UNSTRUCTURED_API_KEY", "")
    headers = {"accept": "application/json", "unstructured-api-key": api_key}
    
    with open(file_path, "rb") as f:
        files = {"files": (os.path.basename(file_path), f, "application/pdf")}
        data = {
            "strategy": "hi_res",
            "pdf_infer_table_structure": "true",
            "chunking_strategy": "by_title",  
            "max_characters": 1500,            
            "combine_under_n_chars": 500,
            "extract_image_block_types": '["Image", "Figure", "Picture", "Graphic"]' 
        }
        response = requests.post(api_url, headers=headers, files=files, data=data, timeout=120.0)
        if response.status_code != 200:
            raise Exception(f"Unstructured API Error {response.status_code}: {response.text}")
        elements = response.json()
    
    for i, el in enumerate(elements):
        el_type = el.get("type", "")
        text_content = str(el.get("text", "")).strip()
        page_num = el.get("metadata", {}).get("page_number", "Unknown")
        
        metadata = {"source": os.path.basename(file_path), "page": page_num}
        
        # Handle Embedded Images caught by Unstructured
        if el_type in ["Image", "Figure", "Picture", "Graphic"]:
            caption_text = next((str(elements[i+j].get("text", "")) for j in range(1, 3) if i+j < len(elements) and any(kw in str(elements[i+j].get("text", "")).lower() for kw in ["figure", "fig", "chart"])), "")
            image_base64 = el.get("metadata", {}).get("image_base64")
            
            try: 
                if image_base64:
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": f"Carefully analyze this document graphic. You MUST describe the actual semantic content, meaning, and exact visual details of the image. Do not just say 'an image'. Describe EXACTLY what the image shows, what text is written inside it, what colors it uses, and what its purpose is. Contextual Caption: {caption_text}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                        ]
                    )
                    # 🚀 FIX: Apply string sanitizer
                    summary = _clean_content(vision_llm.invoke([message]).content)
                else:
                    # 🚀 FIX: Apply string sanitizer
                    summary = _clean_content(vision_llm.invoke(f"Analyze this layout based on this caption: {caption_text}.").content)
            except Exception as e: 
                summary = "Visual extraction unavailable."
                
            target_text = f"[VISUAL ASSET ON PAGE {page_num}] Caption: {caption_text} | Structure Analysis: {summary}"
            
        elif el_type == "Table":
            html_table = el.get("metadata", {}).get("text_as_html", "")
            table_data = html_table if html_table else text_content
            target_text = f"[STRUCTURED TABLE DATA]\n{table_data}"
        else:
            target_text = text_content
            
        if not target_text.strip(): continue
            
        dense_vec = get_google_embedding_with_retry(target_text)
        sparse_result = list(sparse_model.embed([target_text]))[0]
        
        points.append(models.PointStruct(
            id=str(uuid.uuid4()),
            vector={"dense": dense_vec, "sparse": models.SparseVector(indices=sparse_result.indices.tolist(), values=sparse_result.values.tolist())},
            payload={"session_id": session_id, "element_type": el_type.lower(), "content": target_text, **metadata}
        ))

    # ==========================================
    # 🚀 TRACK 2: PYMUPDF (Smart Radar for Vectors AND Raster Images)
    # ==========================================
    print(f"📊 [TRACK 2] Running PyMuPDF Smart Radar for Vector Charts & Images...")
    try:
        doc = fitz.open(file_path)
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            
            drawings = page.get_drawings()
            images = page.get_images()
            
            # 🚀 FIX: The radar now triggers if it finds ANY vector charts OR physical images (like QR codes!)
            if len(drawings) == 0 and len(images) == 0:
                continue 
                
            page_number = page_index + 1
            print(f"  --> Radar hit! Visual asset detected on Page {page_number}. Calculating optimal bounding box...")
            
            # 🚀 FIX: Enterprise Bounding Box Cropping to save API costs and minimize token usage
            combined_rect = fitz.Rect()
            for d in drawings: combined_rect |= d["rect"]
            for img in images:
                for r in page.get_image_rects(img[0]):
                    combined_rect |= r
                    
            if combined_rect.is_empty or combined_rect.is_infinite: continue
            
            # Add a 20px padding to the bounding box and constrain it to the page boundaries
            clip_rect = (combined_rect + (-20, -20, 20, 20)).intersect(page.rect)
            
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip_rect) 
            
            # 🚀 NEW: Save debug crop to disk so the user can visually verify!
            os.makedirs("debug_crops", exist_ok=True)
            pix.save(f"debug_crops/page_{page_number}_crop.png")
            print(f"  --> [DEBUG] Saved cropped image to debug_crops/page_{page_number}_crop.png")
            
            img_base64 = base64.b64encode(pix.tobytes("png")).decode('utf-8')
            
            message = HumanMessage(
                content=[
                    {"type": "text", "text": f"You are an elite Visual Data Analyst. This is Page {page_number}. Look closely for ANY visual elements including logos, signatures, statistical charts, graphs, plots, diagrams, QR codes, photographs, or colored advertisement banners. If they exist, you MUST describe their actual semantic meaning and exact visual contents. Start each description with 'VISUAL ELEMENT DETECTED:'. Do not just say 'there is an image' or 'there is a logo'. Describe EXACTLY what the image shows, what text is written inside it, what colors it uses, and what its purpose is. IMPORTANT: DO NOT transcribe the standard body text or paragraphs of the page; another system is handling the text. Focus ONLY on the visual elements. DO NOT output raw JSON, code blocks, or bounding box coordinates. Describe all visual elements naturally in rich, descriptive paragraphs. If the page is ONLY standard text with absolutely ZERO visual elements (no logos, no signatures, nothing), output exactly 'NO_VISUALS_FOUND'."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            )
            
            # 🚀 FIX: Apply string sanitizer to prevent JSON block leakage
            vision_summary = _clean_content(vision_llm.invoke([message]).content)
            
            if "NO_VISUALS_FOUND" not in vision_summary:
                target_text = f"[COMPREHENSIVE VISUAL DATA FOR PAGE {page_number}] {vision_summary}"
                
                dense_vec = get_google_embedding_with_retry(target_text)
                sparse_result = list(sparse_model.embed([target_text]))[0]
                
                points.append(models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector={"dense": dense_vec, "sparse": models.SparseVector(indices=sparse_result.indices.tolist(), values=sparse_result.values.tolist())},
                    payload={"session_id": session_id, "element_type": "page_visual_summary", "content": target_text, "source": os.path.basename(file_path), "page": page_number}
                ))
        doc.close()
    except Exception as e:
        print(f"⚠️ PyMuPDF Vision Track Error: {str(e)}")

    if points: 
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"✅ Successfully ingested {len(points)} chunks into Qdrant.")
        
    return len(points)