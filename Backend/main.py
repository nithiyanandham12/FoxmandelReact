from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import os
import shutil
import uuid
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import base64
import json
import requests
from googletrans import Translator
import tempfile
import pypandoc
from dotenv import load_dotenv
import time
from pathlib import Path
import cv2
import numpy as np

# Load environment variables
load_dotenv()

# Set Tesseract executable path - update this path to match your Tesseract installation
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\PRAKASH.R\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

app = FastAPI(title="Fox Mandal OCR-AI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the exact frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("images", exist_ok=True)
os.makedirs("temp", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# Environment variables
API_KEY = os.getenv("API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")

# Prompt for the WatsonX AI
LEGAL_PROMPT = '''You are a Senior Legal Associate at a top-tier Indian law firm (e.g., Fox Mandal & Associates), specializing in property due diligence and land title verification.

Your task is to draft a professionally formatted, legally precise, and highly detailed "Report on Title" based strictly on the input provided. The input contains OCR-extracted and translated data from government land records, including RTCs, Mutation Registers, Deeds, and Encumbrance Certificates.

⚖️ LEGAL GUIDELINES
✅ Use only the data found in the input.

❌ Do not hallucinate, infer, or assume facts.

⛔ If information is incomplete or not found, insert "Not Available".

🧾 Maintain a formal legal tone consistent with elite law firm standards.

📐 STRUCTURE & FORMATTING INSTRUCTIONS
Format the report in Markdown.

Begin with a header:
Report On Title
Confidential | Not for Circulation
Prepared exclusively for [Client Name]

Use numbered Roman section headers (I, II, III...)

Use bordered tables (Markdown |) where applicable.

Maintain the following sections and structure:

🧱 REQUIRED SECTIONS
I. DESCRIPTION OF THE LANDS
Table format:
| Survey No. | Extent | A-Kharab | Village | Taluk | District |

II. LIST OF DOCUMENTS REVIEWED
Table format:
| Sl. No. | Document Description | Date / Document No. | Issuing Authority |

III. DEVOLUTION OF TITLE

Timeline table:
| Period | Title Holder(s) | Nature of Right / Document Basis |

Bullet summary (4–6 points) of title flow, mutations, gifts, partitions, etc.

IV. ENCUMBRANCE CERTIFICATE

Use period-wise tables:
| Period | Document Description | Encumbrance Type | Remarks |

List mortgages noted in mutation registers separately.

V. OTHER OBSERVATIONS
Markdown table for boundary details:


Direction	Boundary Details
East	
West	
North	
South	
Also include bullet notes on:

Land ceiling compliance

Grant land / Inam / SC-ST restrictions

Alienation restrictions

Endorsements (PTCL / Tenancy / Acquisition)

VI. FAMILY TREE / GENEALOGICAL DETAILS

List of members, relationships, ages, marital status

Specify if notarized / government issued

VII. INDEPENDENT VERIFICATIONS
Bullet points covering:

Sub-Registrar searches

Revenue department checks

11E Sketch or physical inspection

VIII. LITIGATION SEARCH RESULTS
Bullet format:

Searches conducted by [Advocate Name]

Note any pending litigation or state "No litigation found"

IX. SPECIAL CATEGORY LANDS
Table format:


Category	Status
SC/ST	Yes/No
Minor	Yes/No
Inam	Yes/No
Grant Land	Yes/No
X. OPINION AND RECOMMENDATION

Provide formal legal opinion (paragraph format)

Mention current title holder(s), marketability, pending clarifications

Include table:
| Name of Owner / Co-signatory | Type of Right / Share |

XI. CONTACT DETAILS

Prepared by [Full Name]

Designation

Firm name

Contact info (phone + email)
'''

class ProcessingStatus(BaseModel):
    session_id: str
    status: str
    message: str
    progress: float
    current_stage: str
    total_pages: int
    processed_pages: int
    final_output: Optional[str] = None

class ProcessingResponse(BaseModel):
    session_id: str
    message: str

class PageData(BaseModel):
    page_number: int
    raw_text: str
    translated_text: str

class PageUpdateRequest(BaseModel):
    page_number: int
    edited_text: str
    
class ReportRequest(BaseModel):
    session_id: str
    client_name: Optional[str] = None

# In-memory storage for process tracking
processing_status = {}

def get_ibm_access_token(api_key):
    """Get IBM WatsonX access token"""
    url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey": api_key
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()["access_token"]

def preprocess_image(pil_image):
    """Preprocess image to improve OCR quality"""
    img = np.array(pil_image.convert("RGB"))
    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_LINEAR)
    img = cv2.fastNlMeansDenoising(img, h=30)
    kernel = np.array([[0, -1, 0],
                       [-1, 5,-1],
                       [0, -1, 0]])
    img = cv2.filter2D(img, -1, kernel)
    img = cv2.adaptiveThreshold(img, 255,
                                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 35, 15)
    return Image.fromarray(img)

def extract_text_from_image(image: Image.Image):
    """Extract text from image using OCR"""
    try:
        # Preprocess image
        processed_img = preprocess_image(image)
        
        # Perform OCR with Tesseract
        extracted_text = pytesseract.image_to_string(processed_img, lang='kan+eng')
        return extracted_text
    except Exception as e:
        return f"[OCR failed: {str(e)}]"

def translate_text(text: str, src='kn', dest='en'):
    """Translate text from one language to another"""
    translator = Translator()
    try:
        translated = translator.translate(text, src=src, dest=dest).text
        return translated
    except Exception as e:
        return f"[Translation failed: {str(e)}]"

def chunk_text(text_dict: Dict[str, str], chunk_size=15):
    """Split text into manageable chunks for AI processing"""
    pages = list(text_dict.items())
    return [dict(pages[i:i + chunk_size]) for i in range(0, len(pages), chunk_size)]

def send_chunk_to_watsonx(chunk_text: str, access_token: str):
    """Send text chunk to WatsonX AI for processing"""
    url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2024-01-15"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    payload = {
        "input": LEGAL_PROMPT + chunk_text,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 8100,
            "min_new_tokens": 0,
            "stop_sequences": [],
            "repetition_penalty": 1
        },
        "model_id": "meta-llama/llama-3-3-70b-instruct",
        "project_id": PROJECT_ID
    }

    response = requests.post(url, headers=headers, json=payload)

    try:
        result = response.json()
        return result["results"][0]["generated_text"]
    except Exception as e:
        return f"[WatsonX response error: {str(e)} - Raw: {response.text}]"

def process_pdf(session_id: str, file_path: str, background_tasks: BackgroundTasks):
    """Process PDF file in background"""
    try:
        # Initialize status tracking
        processing_status[session_id] = {
            "status": "processing",
            "message": "Starting PDF processing",
            "progress": 0.0,
            "current_stage": "initialization",
            "total_pages": 0,
            "processed_pages": 0,
            "extracted_pages": {},
            "translated_pages": {},
            "edited_pages": {},
            "pdf_images": {},
            "final_output": None
        }
        
        # Create session directory for this processing job
        session_dir = os.path.join("temp", session_id)
        os.makedirs(session_dir, exist_ok=True)
        images_dir = os.path.join("images", session_id)
        os.makedirs(images_dir, exist_ok=True)
        
        # Update status
        processing_status[session_id].update({
            "message": "Opening PDF document",
            "progress": 0.05,
            "current_stage": "pdf_loading"
        })
        
        # Extract pages and preload images
        extracted_pages = {}
        translated_pages = {}
        pdf_images = {}
        
        with fitz.open(file_path) as doc:
            total_pages = len(doc)
            processing_status[session_id]["total_pages"] = total_pages
            
            for page_num in range(total_pages):
                # Update progress
                processing_status[session_id].update({
                    "message": f"Processing page {page_num+1} of {total_pages}",
                    "progress": 0.1 + (0.7 * (page_num / total_pages)),
                    "current_stage": "ocr_translation",
                    "processed_pages": page_num
                })
                
                # Get page
                page = doc.load_page(page_num)
                
                # Render page to image for OCR
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                
                # Save image for future reference
                image_path = os.path.join(images_dir, f"page_{page_num+1}.png")
                img.save(image_path)
                
                # Convert to base64 for frontend
                img_base64 = base64.b64encode(img_bytes).decode()
                pdf_images[page_num] = img_base64
                
                # Perform OCR
                extracted_text = extract_text_from_image(img)
                extracted_pages[f"Page {page_num+1}"] = extracted_text
                
                # Translate text
                translated_text = translate_text(extracted_text, src='kn', dest='en')
                translated_pages[f"Page {page_num+1}"] = translated_text
                
                # Add small delay to avoid overwhelming resources
                time.sleep(0.1)
        
        # Update status
        processing_status[session_id].update({
            "message": "OCR and translation completed",
            "progress": 0.8,
            "current_stage": "completed",
            "processed_pages": total_pages,
            "extracted_pages": extracted_pages,
            "translated_pages": translated_pages,
            "edited_pages": {k: v for k, v in translated_pages.items()},
            "pdf_images": pdf_images
        })
        
        # Save results to files for persistence
        with open(os.path.join(session_dir, "extracted_pages.json"), "w", encoding="utf-8") as f:
            json.dump(extracted_pages, f, ensure_ascii=False, indent=2)
            
        with open(os.path.join(session_dir, "translated_pages.json"), "w", encoding="utf-8") as f:
            json.dump(translated_pages, f, ensure_ascii=False, indent=2)
            
        with open(os.path.join(session_dir, "pdf_images.json"), "w", encoding="utf-8") as f:
            json.dump(pdf_images, f, ensure_ascii=False, indent=2)
        
        # Final update
        processing_status[session_id].update({
            "status": "ready_for_review",
            "message": "PDF processing complete! Ready for quality review.",
            "progress": 1.0,
            "current_stage": "waiting_for_review"
        })
        
    except Exception as e:
        # Update status on error
        processing_status[session_id].update({
            "status": "error",
            "message": f"Error processing PDF: {str(e)}",
            "progress": 0,
            "current_stage": "error"
        })
        
def generate_report(session_id: str, client_name: Optional[str] = None):
    """Generate final report using WatsonX AI"""
    try:
        # Update status
        processing_status[session_id].update({
            "status": "generating_report",
            "message": "Starting report generation",
            "progress": 0.0,
            "current_stage": "starting_report"
        })
        
        session_dir = os.path.join("temp", session_id)
        output_dir = os.path.join("outputs", session_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # Get edited pages
        edited_pages = processing_status[session_id]["edited_pages"]
        
        # Get IBM WatsonX token
        processing_status[session_id].update({
            "message": "Getting IBM WatsonX token",
            "progress": 0.1,
            "current_stage": "getting_token"
        })
        
        token = get_ibm_access_token(API_KEY)
        
        # Chunk text for processing
        text_chunks = chunk_text(edited_pages, chunk_size=90)  # Adjust chunk size as needed
        watsonx_outputs = []
        
        # Process each chunk
        for i, chunk in enumerate(text_chunks):
            processing_status[session_id].update({
                "message": f"Processing chunk {i+1} of {len(text_chunks)}",
                "progress": 0.2 + (0.6 * (i / len(text_chunks))),
                "current_stage": "processing_chunks"
            })
            
            combined_text = "\n".join(chunk.values())
            result = send_chunk_to_watsonx(combined_text, token)
            watsonx_outputs.append(result)
        
        # Combine results
        final_output = "\n\n".join(watsonx_outputs)
        
        # Insert client name if provided
        if client_name:
            final_output = final_output.replace("[Client Name]", client_name)
        
        # Save final output
        markdown_path = os.path.join(output_dir, "report.md")
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(final_output)
        
        # Generate Word document
        processing_status[session_id].update({
            "message": "Generating Word document",
            "progress": 0.9,
            "current_stage": "generating_docx"
        })
        
        try:
            # Ensure pandoc is installed
            pypandoc.download_pandoc()
            
            # Convert markdown to DOCX
            docx_path = os.path.join(output_dir, "report.docx")
            pypandoc.convert_text(final_output, 'docx', format='md', outputfile=docx_path)
            
            # Store final output in status
            processing_status[session_id].update({
                "status": "completed",
                "message": "Report generation complete!",
                "progress": 1.0,
                "current_stage": "completed",
                "final_output": final_output,
                "markdown_path": markdown_path,
                "docx_path": docx_path
            })
            
        except Exception as e:
            # Fallback to text file if Word conversion fails
            processing_status[session_id].update({
                "status": "completed_with_warning",
                "message": f"Report generated but Word conversion failed: {str(e)}",
                "progress": 1.0,
                "current_stage": "completed_with_warning",
                "final_output": final_output,
                "markdown_path": markdown_path
            })
    
    except Exception as e:
        # Update status on error
        processing_status[session_id].update({
            "status": "error",
            "message": f"Error generating report: {str(e)}",
            "progress": 0,
            "current_stage": "error"
        })

@app.post("/upload", response_model=ProcessingResponse)
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload PDF file for processing"""
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    # Create file path
    file_path = os.path.join("uploads", f"{session_id}_{file.filename}")
    
    # Save uploaded file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Start processing in background
    background_tasks.add_task(process_pdf, session_id, file_path, background_tasks)
    
    return {"session_id": session_id, "message": "PDF upload successful. Processing started."}

@app.get("/status/{session_id}", response_model=ProcessingStatus)
async def get_status(session_id: str):
    """Get current processing status"""
    if session_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processing session not found")
    
    status_data = processing_status[session_id]
    
    return {
        "session_id": session_id,
        "status": status_data.get("status", "unknown"),
        "message": status_data.get("message", ""),
        "progress": status_data.get("progress", 0.0),
        "current_stage": status_data.get("current_stage", "unknown"),
        "total_pages": status_data.get("total_pages", 0),
        "processed_pages": status_data.get("processed_pages", 0),
        "final_output": status_data.get("final_output", None)  # Include the final report content
    }

@app.get("/pages/{session_id}/{page_number}", response_model=PageData)
async def get_page_data(session_id: str, page_number: int):
    """Get data for a specific page"""
    if session_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processing session not found")
    
    status_data = processing_status[session_id]
    page_key = f"Page {page_number}"
    
    if page_key not in status_data.get("extracted_pages", {}):
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found")
    
    return {
        "page_number": page_number,
        "raw_text": status_data["extracted_pages"].get(page_key, ""),
        "translated_text": status_data["translated_pages"].get(page_key, "")
    }

@app.get("/image/{session_id}/{page_number}")
async def get_page_image(session_id: str, page_number: int):
    """Get image for a specific page"""
    if session_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processing session not found")
    
    status_data = processing_status[session_id]
    
    if int(page_number)-1 not in status_data.get("pdf_images", {}):
        raise HTTPException(status_code=404, detail=f"Image for page {page_number} not found")
    
    # Return base64 encoded image
    return {"image": status_data["pdf_images"].get(int(page_number)-1, "")}

@app.put("/update-page/{session_id}", response_model=dict)
async def update_page_text(session_id: str, data: PageUpdateRequest):
    """Update edited text for a page"""
    if session_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processing session not found")
    
    page_key = f"Page {data.page_number}"
    processing_status[session_id]["edited_pages"][page_key] = data.edited_text
    
    # Save updated edited pages
    session_dir = os.path.join("temp", session_id)
    with open(os.path.join(session_dir, "edited_pages.json"), "w", encoding="utf-8") as f:
        json.dump(processing_status[session_id]["edited_pages"], f, ensure_ascii=False, indent=2)
    
    return {"status": "success", "message": f"Page {data.page_number} updated successfully"}

@app.post("/generate-report/{session_id}", response_model=dict)
async def start_report_generation(data: ReportRequest, background_tasks: BackgroundTasks):
    """Start report generation process"""
    session_id = data.session_id
    
    if session_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processing session not found")
    
    # Start report generation in background
    background_tasks.add_task(generate_report, session_id, data.client_name)
    
    return {"status": "success", "message": "Report generation started"}

@app.get("/download/{session_id}/{file_type}")
async def download_file(session_id: str, file_type: str):
    """Download generated report file"""
    if session_id not in processing_status:
        raise HTTPException(status_code=404, detail="Processing session not found")
    
    status_data = processing_status[session_id]
    
    if file_type == "markdown":
        file_path = status_data.get("markdown_path")
        media_type = "text/markdown"
        filename = "report.md"
    elif file_type == "docx":
        file_path = status_data.get("docx_path")
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "report.docx"
    else:
        raise HTTPException(status_code=400, detail="Invalid file type requested")
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"{file_type.capitalize()} file not found")
    
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename
    )

# Mount static files for frontend
app.mount("/", StaticFiles(directory="../frontend/build", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
