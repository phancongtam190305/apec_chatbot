from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import logging
import traceback
from langdetect import detect, DetectorFactory
from dotenv import load_dotenv
import asyncio
import time

# Import QdrantClient từ thư viện qdrant-client
from qdrant_client import QdrantClient 

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI 
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import Qdrant 
from langchain_core.prompts import ChatPromptTemplate # Vẫn dùng để tạo prompt
# Không cần RunnablePassthrough và StrOutputParser nếu không dùng LCEL chain
# from langchain_core.runnables import RunnablePassthrough 
# from langchain_core.output_parsers import StrOutputParser

# Thiết lập seed cho langdetect
DetectorFactory.seed = 0 

# --- Cấu hình ---
load_dotenv() # Load environment variables from .env file

QDRANT_CLOUD_URL = os.getenv("QDRANT_CLOUD_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") 
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "apec_chatbot_data")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") 

if not QDRANT_CLOUD_URL:
    raise ValueError("Biến môi trường 'QDRANT_CLOUD_URL' chưa được thiết lập. Vui lòng thêm vào file .env")
if not QDRANT_API_KEY:
    raise ValueError("Biến môi trường 'QDRANT_API_KEY' chưa được thiết lập. Vui lòng thêm vào file .env")
if not GOOGLE_API_KEY:
    raise ValueError("Biến môi trường 'GOOGLE_API_KEY' chưa được thiết lập. Vui lòng thêm vào file .env")

LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash") 
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# --- Khởi tạo Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apec_chatbot_backend")

# --- Khởi tạo LLM, Embeddings và Qdrant (Global) ---
llm = None
embeddings = None
qdrant_vectorstore = None

def initialize_llm_and_embeddings():
    global llm, embeddings
    try:
        logger.info(f"Đang khởi tạo LLM: {LLM_MODEL_NAME} (Google Gemini API)...")
        llm = ChatGoogleGenerativeAI(model=LLM_MODEL_NAME, google_api_key=GOOGLE_API_KEY, temperature=0.7)
        llm.invoke("Hello") 
        logger.info(f"Đã khởi tạo LLM '{LLM_MODEL_NAME}' thành công.")
    except Exception as e:
        logger.critical(f"Không thể khởi tạo LLM '{LLM_MODEL_NAME}'. Lỗi: {e}")
        logger.critical("Đảm bảo 'GOOGLE_API_KEY' đã được cung cấp chính xác và có quyền truy cập API Gemini.")
        raise RuntimeError("LLM initialization failed.") from e

    try:
        logger.info(f"Đang khởi tạo Embedding Model: {EMBEDDING_MODEL_NAME}...")
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        logger.info(f"Đã khởi tạo Embedding Model '{EMBEDDING_MODEL_NAME}' thành công.")
    except Exception as e:
        logger.critical(f"Không thể khởi tạo Embedding Model '{EMBEDDING_MODEL_NAME}'. Lỗi: {e}")
        logger.critical("Đảm bảo thư viện 'sentence-transformers' đã được cài đặt.")
        raise RuntimeError("Embedding model initialization failed.") from e

# --- Khởi tạo FastAPI App ---
app = FastAPI(
    title="APEC 2025 Chatbot API",
    description="API backend for APEC 2025 multilingual chatbot using RAG.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Sự kiện khởi động ứng dụng ---
@app.on_event("startup")
async def startup_event():
    global qdrant_vectorstore, llm, embeddings 

    try:
        initialize_llm_and_embeddings()
    except RuntimeError:
        logger.critical("App startup aborted due to LLM/Embedding initialization failure.")
        exit(1)

    logger.info("Đang kết nối tới Qdrant Vector Store trong sự kiện startup...")

    retries = 5 
    delay = 5 

    for i in range(retries):
        try:
            logger.info(f"Đang thử kết nối Qdrant (lần {i+1}/{retries})...")
            qdrant_client_instance = QdrantClient(
                url=QDRANT_CLOUD_URL, 
                api_key=QDRANT_API_KEY 
            )

            # Cải tiến chỗ này: Cấu hình ánh xạ payload
            qdrant_vectorstore = Qdrant(
                client=qdrant_client_instance,  
                embeddings=embeddings, 
                collection_name=QDRANT_COLLECTION_NAME,
                # THÊM HAI THAM SỐ QUAN TRỌNG NÀY:
                content_payload_key="content_text", # Tên trường trong payload chứa nội dung chính
                # metadata_payload_key=["id", "topic", "sub_topic", "source_file", "source_url"] # Danh sách các trường metadata bạn muốn giữ
            )

            collection_info = qdrant_vectorstore.client.count(
                collection_name=QDRANT_COLLECTION_NAME,
                exact=True 
            )

            logger.info(f"Collection '{QDRANT_COLLECTION_NAME}' có {collection_info.count} points.")
            logger.info("Đã kết nối và xác nhận Qdrant Vector Store thành công.")
            break 

        except Exception as e:
            logger.warning(f"Lỗi kết nối tới Qdrant (lần {i+1}): {e}")
            if i < retries - 1:
                logger.info(f"Đang thử lại sau {delay} giây...")
                await asyncio.sleep(delay)
            else:
                logger.critical(f"Không thể kết nối tới Qdrant sau {retries} lần thử. Lỗi cuối cùng: {e}")
                logger.critical("Đảm bảo Qdrant Cloud URL và API Key chính xác và Qdrant server đang hoạt động.")
                raise RuntimeError("Qdrant connection failed, cannot start API.") from e


class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str
    lang: str
    suggestions: list[str] = []

def get_contextual_quick_replies(user_message: str, lang: str) -> list:
    message = user_message.lower()
    
    # Gợi ý chung ban đầu (sẽ được ưu tiên nếu không có gợi ý cụ thể nào khác)
    general_suggestions_vi = [
        "Giới thiệu APEC 2025",
        "Lịch trình các cuộc họp chính",
        "Thông tin về địa điểm APEC",
        "Các bài báo mới nhất",
        "Hỗ trợ nhập cảnh"
    ]
    general_suggestions_en = [
        "Overview of APEC 2025",
        "Key meetings schedule",
        "APEC venue information",
        "Latest press releases",
        "Entry support"
    ]

    suggestions = []

    # Gợi ý dựa trên các chủ đề chính trong dữ liệu bạn có
    # Tiếng Việt
    if lang == "vi":
        if "apec" in message or "tổng quan" in message or "giới thiệu" in message:
            suggestions.extend([
                "APEC là gì?",
                "Tầm nhìn APEC 2040",
                "Các nền kinh tế thành viên APEC",
                "Đóng góp của Hàn Quốc cho APEC",
                "Biểu tượng và chủ đề APEC 2025"
            ])
        if "lịch" in message or "sự kiện" in message or "cuộc họp" in message:
            suggestions.extend([
                "Lịch trình các cuộc họp chính",
                "Các sự kiện bên lề APEC",
                "Họp SOM1 diễn ra khi nào?"
            ])
        if "địa điểm" in message or "tổ chức" in message or "nơi" in message:
            suggestions.extend([
                "Giới thiệu về Gyeongju",
                "Thông tin về Jeju",
                "Khám phá Incheon",
                "Địa điểm ở Busan",
                "Địa điểm ở Seoul"
            ])
        if "thủ tục" in message or "nhập cảnh" in message or "visa" in message or "di chuyển" in message:
            suggestions.extend([
                "Thông tin di chuyển đến Gyeongju",
                "Di chuyển nội địa ở Jeju",
                "Thông tin thực tế APEC (khí hậu, tiền tệ)",
                "Số điện thoại khẩn cấp"
            ])
        if "tin tức" in message or "báo chí" in message or "mới nhất" in message:
            suggestions.extend([
                "Đọc các thông cáo báo chí mới",
                "Tin tức về cuộc họp MRT",
                "Tin tức về SOM2 Jeju"
            ])
        if "văn hóa" in message or "ẩm thực" in message or "du lịch" in message:
            suggestions.extend([
                "Điểm tham quan ở Gyeongju",
                "Văn hóa & Thiên nhiên Jeju",
                "Du lịch chủ đề ở Jeju",
                "Địa điểm ăn uống ở Incheon",
                "Địa điểm tham quan ở Incheon"
            ])

    # Tiếng Anh
    elif lang == "en":
        if "apec" in message or "overview" in message or "introduction" in message:
            suggestions.extend([
                "What is APEC?",
                "APEC 2040 Vision",
                "APEC member economies",
                "Korea's contribution to APEC",
                "APEC 2025 Emblem and Theme"
            ])
        if "schedule" in message or "event" in message or "meetings" in message:
            suggestions.extend([
                "Key meetings schedule",
                "APEC Side Events",
                "When is SOM1?"
            ])
        if "location" in message or "where" in message or "venue" in message:
            suggestions.extend([
                "About Gyeongju",
                "About Jeju",
                "Explore Incheon",
                "About Busan",
                "About Seoul"
            ])
        if "procedure" in message or "entry" in message or "visa" in message or "travel" in message:
            suggestions.extend([
                "Transportation to Gyeongju",
                "Jeju domestic travel",
                "Practical APEC information (climate, currency)",
                "Emergency phone numbers"
            ])
        if "news" in message or "press" in message or "latest" in message:
            suggestions.extend([
                "Read latest press releases",
                "News about MRT Meeting",
                "News about SOM2 Jeju"
            ])
        if "culture" in message or "cuisine" in message or "tourism" in message or "attractions" in message:
            suggestions.extend([
                "Gyeongju attractions",
                "Jeju Nature & Culture",
                "Jeju themed travel",
                "Incheon local eateries",
                "Incheon attractions"
            ])
    
    unique_suggestions = list(dict.fromkeys(suggestions))
    
    if not unique_suggestions:
        return general_suggestions_vi if lang == "vi" else general_suggestions_en
        
    return unique_suggestions[:5]

# --- API Endpoint ---
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    start_total_time = time.time() # Bắt đầu tính tổng thời gian
    user_message = req.message
    if not user_message:
        logger.warning("Nhận được câu hỏi rỗng từ frontend.")
        return ChatResponse(answer="Vui lòng cung cấp một câu hỏi.", lang="unknown", suggestions=[])
    
    logger.info(f"Nhận được câu hỏi: {user_message}")

    if llm is None or embeddings is None or qdrant_vectorstore is None:
        logger.critical("LLM, Embedding Model hoặc Qdrant vectorstore chưa được khởi tạo. API không sẵn sàng.")
        error_answer_vi = "Hệ thống chưa sẵn sàng. Vui lòng thử lại sau hoặc liên hệ quản trị viên."
        error_answer_en = "System not ready. Please try again later or contact the administrator."
        
        try:
            detected_lang_for_error = detect(user_message)
        except Exception:
            detected_lang_for_error = "en" 

        return ChatResponse(
            answer=error_answer_vi if detected_lang_for_error == "vi" else error_answer_en, 
            lang=detected_lang_for_error, 
            suggestions=[]
        )

    # Log thời gian phát hiện ngôn ngữ
    start_lang_detect_time = time.time()
    try:
        detected_lang = detect(user_message)
        logger.info(f"Ngôn ngữ được nhận diện: {detected_lang} (thời gian: {time.time() - start_lang_detect_time:.4f}s)")
    except Exception as e:
        detected_lang = "en" 
        logger.warning(f"Không thể nhận diện ngôn ngữ, mặc định là tiếng Anh. Lỗi: {e} (thời gian: {time.time() - start_lang_detect_time:.4f}s)")

    language_instruction = ""
    if detected_lang == 'vi':
        language_instruction = "Hãy trả lời câu hỏi bằng tiếng Việt."
    elif detected_lang == 'en':
        language_instruction = "Please answer the question in English."
    else:
        language_instruction = "Please answer the question in English if possible."

    prompt_template = f"""
    Bạn là một trợ lý chatbot thân thiện, thông tin, và đa ngôn ngữ cho sự kiện APEC 2025. 
    Nhiệm vụ của bạn là trả lời các câu hỏi của người dùng một cách chính xác và hữu ích dựa trên thông tin được cung cấp.

    **Data liên quan:**
    {{context}}

    **Câu hỏi của người dùng:**
    {{question}}

    ---
    **Hướng dẫn trả lời:**
    1.  Sử dụng chỉ các thông tin được cung cấp trong "Ngữ cảnh liên quan" để trả lời câu hỏi.
    2.  Nếu ngữ cảnh không chứa đủ thông tin để trả lời câu hỏi, hãy nói rằng "Tôi xin lỗi, tôi không tìm thấy thông tin cụ thể cho câu hỏi này trong dữ liệu của mình. Bạn có muốn hỏi về chủ đề khác không?".
    3.  **{language_instruction}**
    4.  Tránh đưa ra thông tin không có trong ngữ cảnh.
    5.  Giữ câu trả lời ngắn gọn, trực tiếp và tập trung vào câu hỏi.
    """
    
    context_str = ""
    start_retrieval_time = time.time() # Bắt đầu tính thời gian truy vấn
    try:
        logger.info("Bắt đầu truy vấn Qdrant...")
        retriever = qdrant_vectorstore.as_retriever(search_kwargs={"k": 10})
        
        retrieved_docs = await retriever.ainvoke(user_message) # SỬA THÀNH AINVOKE VÌ HÀM CHAT LÀ ASYNC
        
        logger.info(f"Đã truy vấn Qdrant. Tìm thấy {retrieved_docs} tài liệu liên quan (thời gian: {time.time() - start_retrieval_time:.4f}s):")
        
        context_str_parts = []
        if retrieved_docs:
            for i, doc in enumerate(retrieved_docs):
                # logger.info(f"  --- Tài liệu {i+1} ---") # Bỏ hoặc comment dòng này để tránh log quá dài
                # logger.info(f"  Content (đầu): {doc.page_content[:300]}...") # Bỏ hoặc comment dòng này
                # logger.info(f"  Metadata: {json.dumps(doc.metadata, ensure_ascii=False)}") # Bỏ hoặc comment dòng này
                context_str_parts.append(doc.page_content)
            
            context_str = "\n\n".join(context_str_parts)
            # logger.info("="*100) # Bỏ hoặc comment dòng này
            # logger.info(f"CONTEXT ĐƯỢC GỬI ĐẾN LLM:\n{len(context_str)} ký tự") # Sửa lại log
            # logger.info("="*100) # Bỏ hoặc comment dòng này
        else:
            logger.warning("Không tìm thấy tài liệu nào từ Qdrant cho câu hỏi này.")
            context_str = "Không tìm thấy thông tin liên quan."

    except Exception as e:
        logger.error(f"Lỗi khi truy vấn Qdrant để lấy context: {e}\n{traceback.format_exc()} (thời gian: {time.time() - start_retrieval_time:.4f}s)")
        context_str = "Lỗi khi truy vấn thông tin."

    final_prompt = prompt_template.format(context=context_str, question=user_message)
    
    response_text = ""
    start_llm_time = time.time() # Bắt đầu tính thời gian gọi LLM
    try:
        logger.info("Bắt đầu gọi LLM...")
        llm_response = await llm.ainvoke(final_prompt) # SỬA THÀNH AINVOKE
        response_text = llm_response.content
        logger.info(f"Trả lời của LLM đã nhận (thời gian: {time.time() - start_llm_time:.4f}s). Tổng thời gian xử lý: {time.time() - start_total_time:.4f}s")
        
        suggestions = get_contextual_quick_replies(user_message, detected_lang)
        
        return ChatResponse(answer=response_text, lang=detected_lang, suggestions=suggestions)
    except Exception as e:
        logger.error(f"Lỗi khi xử lý yêu cầu chat (gọi LLM): {e}\n{traceback.format_exc()} (thời gian: {time.time() - start_llm_time:.4f}s)")
        error_answer_vi = "Đã xảy ra lỗi trong quá trình xử lý câu hỏi của bạn. Vui lòng thử lại sau."
        error_answer_en = "An error occurred while processing your request. Please try again later."
        error_answer = error_answer_vi if detected_lang == 'vi' else error_answer_en
        
        return ChatResponse(answer=error_answer, lang=detected_lang, suggestions=[])