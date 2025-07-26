import os
import json
from qdrant_client import QdrantClient, models
from langchain_huggingface import HuggingFaceEmbeddings
# from langchain_openai import OpenAIEmbeddings # Nếu bạn muốn dùng OpenAI embeddings
from langchain_core.documents import Document
import uuid

# Cấu hình Qdrant
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env

# --- CÁC BIẾN MÔI TRƯỜNG CẦN ĐỊNH NGHĨA TRONG FILE .env ---
# Nhà tuyển dụng cần điền các giá trị này vào file .env
# Ví dụ:
# QDRANT_URL="https://YOUR_QDRANT_CLUSTER_URL:6333"
# QDRANT_API_KEY="YOUR_API_KEY_HERE"
# QDRANT_COLLECTION_NAME="apec_chatbot_data" (có thể để mặc định nếu không muốn đổi tên collection)

QDRANT_URL = os.getenv("QDRANT_CLOUD_URL") # Đảm bảo biến này được set trong .env là QDRANT_CLOUD_URL
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") 
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "apec_chatbot_data")

# Kiểm tra nếu các biến môi trường quan trọng chưa được thiết lập
if not QDRANT_URL:
    raise ValueError("Biến môi trường 'QDRANT_URL' chưa được thiết lập. Vui lòng thêm vào file .env")
if not QDRANT_API_KEY:
    raise ValueError("Biến môi trường 'QDRANT_API_KEY' chưa được thiết lập. Vui lòng thêm vào file .env")

# Kích thước embedding vector cho 'all-MiniLM-L6-v2' là 384
EMBEDDING_DIMENSION = 384 

# Đường dẫn tới file JSON chứa tất cả các chunk dữ liệu
# Giả định file này nằm ở thư mục gốc của dự án trong data/json_chunks/
# Thay đổi đường dẫn cứng này bằng đường dẫn tương đối nếu file Python này nằm ở thư mục gốc
# Hoặc đảm bảo rằng bạn chạy script từ thư mục gốc của dự án.
DATA_CHUNKS_PATH = os.path.join("backend", "data", "json_chunks", "apec_all_chunks.json")
# Nếu bạn muốn giữ nguyên đường dẫn tuyệt đối, hãy chắc chắn nó đúng trên hệ thống chạy.
# DATA_CHUNKS_PATH = r"D:\Desktop\tap tanh hoc code\.vscode\Summer_2025\SEG301\Hakate_assignment\apec_chatbot\backend\data\json_chunks\apec_all_chunks.json"


def initialize_embeddings_model():
    """
    Initializes and returns the embedding model.
    Chooses between HuggingFaceEmbeddings (local) or OpenAIEmbeddings.
    """
    print("Đang khởi tạo mô hình embedding...")
    try:
        # Sử dụng mô hình Sentence Transformers cục bộ
        # Đảm bảo bạn đã pip install sentence-transformers
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        print("Đã khởi tạo HuggingFaceEmbeddings (all-MiniLM-L6-v2) thành công.")
    except Exception as e:
        print(f"Lỗi khi khởi tạo HuggingFaceEmbeddings: {e}")
        print("Hãy đảm bảo bạn đã cài đặt 'sentence-transformers' (`pip install sentence-transformers`).")
        # Fallback hoặc raise error
        raise
    return embeddings

def get_qdrant_client():
    """
    Connects to Qdrant server and returns the client.
    Sử dụng các biến môi trường QDRANT_URL và QDRANT_API_KEY.
    """
    print(f"Đang kết nối tới Qdrant Cloud tại {QDRANT_URL}...")
    
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    try:
        # Kiểm tra kết nối bằng cách lấy thông tin collections
        collections_info = client.get_collections()
        print(collections_info)
        print("Đã kết nối Qdrant Cloud thành công.")
        return client
    except Exception as e:
        print(f"Lỗi khi kết nối Qdrant Cloud: {e}")
        print("Vui lòng kiểm tra lại 'QDRANT_URL' và 'QDRANT_API_KEY' trong file .env của bạn.")
        raise

def load_data_chunks():
    """
    Loads all processed data chunks from JSON files and converts them to LangChain Document objects.
    """
    all_documents = []

    # Load chunks từ apec_all_chunks.json
    if os.path.exists(DATA_CHUNKS_PATH):
        try:
            with open(DATA_CHUNKS_PATH, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
                for chunk in chunks:
                    # print(chunk.get("content")) # Giữ lại dòng này để kiểm tra nếu muốn
                    # Tạo Document object từ mỗi chunk
                    # Sử dụng `id` từ chunk làm id cho Document nếu có, nếu không thì tạo mới
                    doc_id = chunk.get('id', str(uuid.uuid4())) 
                    all_documents.append(Document(
                        page_content=chunk.get('content', ''), # Đây là nội dung chính của LangChain Document
                        metadata={
                            "id": doc_id, 
                            "topic": chunk.get('topic', 'N/A'),
                            "sub_topic": chunk.get('sub_topic', 'N/A'),
                            "source_file": chunk.get('source_file', 'N/A'),
                            "source_url": chunk.get("source_url", "N/A"),
                            "content_text": chunk.get('content', '') # Thêm nội dung vào metadata với key mới để lưu vào payload
                        }
                    ))
            print(f"Đã tải {len(chunks)} chunks từ '{DATA_CHUNKS_PATH}'.")
        except Exception as e:
            print(f"Lỗi khi tải dữ liệu từ '{DATA_CHUNKS_PATH}': {e}")
    else:
        print(f"Cảnh báo: File '{DATA_CHUNKS_PATH}' không tồn tại. Vui lòng chạy script tiền xử lý trước.")

    if not all_documents:
        print("Không có tài liệu nào được tải để tạo embeddings. Vui lòng kiểm tra các file dữ liệu.")
        return None
        
    print(f"Tổng số {len(all_documents)} tài liệu sẽ được nhúng.")
    return all_documents


def upload_documents_to_qdrant(documents, embeddings, client):
    """
    Creates Qdrant collection and uploads documents with their embeddings.
    """
    print(f"Đang tải dữ liệu lên Qdrant collection: {QDRANT_COLLECTION_NAME}...")
    
    # Kiểm tra xem collection đã tồn tại chưa
    # Nếu tồn tại, có thể xóa và tạo lại để đảm bảo dữ liệu mới nhất
    if client.collection_exists(collection_name=QDRANT_COLLECTION_NAME):
        print(f"Collection '{QDRANT_COLLECTION_NAME}' đã tồn tại. Đang xóa và tạo lại...")
        client.delete_collection(collection_name=QDRANT_COLLECTION_NAME)
    
    # Tạo collection mới
    client.recreate_collection(
        collection_name=QDRANT_COLLECTION_NAME,
        vectors_config=models.VectorParams(size=EMBEDDING_DIMENSION, distance=models.Distance.COSINE),
    )
    print(f"Đã tạo collection '{QDRANT_COLLECTION_NAME}' mới.")

    # Chuyển đổi Documents thành Points cho Qdrant
    points = []
    for doc in documents:
        # Tạo embedding cho nội dung của Document
        vector = embeddings.embed_query(doc.page_content)
        
        # Payload sẽ là metadata của Document
        # Đảm bảo rằng 'content_text' đã được thêm vào metadata trong load_data_chunks
        payload = doc.metadata.copy() 

        points.append(models.PointStruct(
            id=payload.get("id", str(uuid.uuid4())), 
            vector=vector,
            payload=payload 
        ))
    
    # Tải các điểm lên Qdrant theo lô (batch) để hiệu quả hơn
    batch_size = 100 
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(
            collection_name=QDRANT_COLLECTION_NAME,
            points=batch,
            wait=True 
        )
        print(f"    > Đã tải {min(i + batch_size, len(points))}/{len(points)} points lên Qdrant.")

    # Lấy tổng số điểm sau khi tải lên
    total_points = client.count(collection_name=QDRANT_COLLECTION_NAME, exact=True).count
    print(f"Đã tải tất cả tài liệu lên Qdrant thành công! Tổng số điểm: {total_points}")

if __name__ == "__main__":
    print("--- BẮT ĐẦU QUÁ TRÌNH TẢI DỮ LIỆU LÊN QDRANT CLOUD ---")
    print("Vui lòng đảm bảo các biến môi trường sau đã được thiết lập trong file .env:")
    print("  - QDRANT_URL (URL đầy đủ cho Qdrant Cloud)")
    print("  - QDRANT_API_KEY")
    print("  - QDRANT_COLLECTION_NAME (Tùy chọn, mặc định là 'apec_chatbot_data')")
    print("\nVí dụ file .env:")
    print("QDRANT_URL=\"https://YOUR_CLUSTER_URL:6333\"")
    print("QDRANT_API_KEY=\"YOUR_API_KEY_HERE\"")
    print("QDRANT_COLLECTION_NAME=\"my_apec_data\"\n")

    # 1. Khởi tạo Embedding Model
    embeddings_model = initialize_embeddings_model()

    # 2. Kết nối tới Qdrant
    qdrant_client = get_qdrant_client()

    # 3. Tải dữ liệu chunks
    langchain_documents = load_data_chunks()

    if langchain_documents:
        # 4. Tạo embeddings và tải lên Qdrant
        upload_documents_to_qdrant(langchain_documents, embeddings_model, qdrant_client)
    else:
        print("Không có tài liệu nào để tải lên Qdrant. Quá trình dừng lại.")
    
    print("--- HOÀN TẤT QUÁ TRÌNH TẢI DỮ LIỆU LÊN QDRANT CLOUD ---")