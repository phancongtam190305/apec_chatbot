import streamlit as st
import requests
import json
import time

# --- Cấu hình API Backend ---
BACKEND_API_URL = "http://localhost:8000/chat" 

st.set_page_config(
    page_title="APEC 2025 Chatbot | Trợ lý AI",
    page_icon="🤖", 
    layout="centered", 
    initial_sidebar_state="auto" 
)

# --- NÂNG CẤP: CSS được tinh chỉnh để hiện đại và mượt mà hơn ---
st.markdown("""
<style>
    /* Sử dụng biến CSS để dễ dàng thay đổi theme */
    :root {
        --primary-color: #005A9E; /* Màu xanh APEC chính */
        --secondary-color: #E0F2F7; /* Màu nền tin nhắn người dùng */
        --background-color: #F0F2F6;
        --text-color: #333333;
        --light-gray: #f7f7f7;
        --white: #ffffff;
        --border-radius-lg: 18px;
        --border-radius-sm: 10px;
    }

    /* Tổng thể ứng dụng */
    .stApp {
        /* THAY ĐỔI Ở ĐÂY: Thêm background-image */
        background-image: url("https://drive.google.com/file/d/1BiDEkdBWPn1k9eKUeEtqaNKWj71Xj3iM/view?usp=drive_link"); /* Thay bằng đường dẫn file ảnh của bạn */
        background-size: cover; 
        background-position: center; 
        background-repeat: no-repeat; 
        background-attachment: fixed; 
        color: var(--text-color);
        backdrop-filter: blur(3px) brightness(90%); 
    }
    
    /* Vùng nội dung chính của Streamlit App để tạo lớp phủ nền nhẹ */
    .main .block-container {
        background-color: rgba(255, 255, 255, 0.7); 
        backdrop-filter: blur(5px); 
        border-radius: var(--border-radius-lg);
        padding: 2rem;
        box-shadow: 0 8px 30px rgba(0,0,0,0.2);
    }

    /* Tiêu đề chính */
    h1 {
        color: var(--primary-color);
        text-align: center;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 700;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.05);
    }

    /* Mô tả dưới tiêu đề */
    .st-emotion-cache-1yy083x p { 
        text-align: center;
        font-size: 1.1em;
        color: #555;
        margin-bottom: 2rem;
    }

    /* Animation cho tin nhắn mới xuất hiện */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* Khung chứa tin nhắn */
    .stChatMessage {
        background-color: var(--white);
        border-radius: var(--border-radius-lg);
        padding: 16px 22px;
        margin-bottom: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border: 1px solid #EAEAEA;
        animation: fadeIn 0.3s ease-out;
    }
    
    /* Tin nhắn của người dùng (bên phải) */
    .stChatMessage[data-testid="stChatMessage"]:has(div[data-testid="stAvatarIcon-user"]) {
        background-color: var(--secondary-color);
        border-bottom-right-radius: 2px; 
    }

    /* Tin nhắn của bot (bên trái) */
    .stChatMessage[data-testid="stChatMessage"]:has(div[data-testid="stAvatarIcon-assistant"]) {
        background-color: var(--white);
        border-bottom-left-radius: 2px;
    }

    /* Ô nhập liệu */
    .stTextInput div[data-baseweb="input"] {
        border-radius: 25px;
        border: 1px solid #CDCDCD;
        padding: 8px 18px;
        background-color: var(--white);
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .stTextInput div[data-baseweb="input"]:focus-within {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 3px rgba(0, 90, 158, 0.2);
    }

    /* Các nút gợi ý nhanh */
    .stButton > button {
        border-radius: 20px;
        border: 1px solid #B0C4DE;
        color: #334E68;
        background-color: rgba(255, 255, 255, 0.7); 
        backdrop-filter: blur(5px); 
        padding: 8px 16px;
        margin: 4px;
        transition: all 0.2s ease;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: var(--primary-color);
        color: var(--white);
        border-color: var(--primary-color);
        box-shadow: 0 4px 10px rgba(0,90,158,0.25);
        transform: translateY(-2px);
    }
    .stButton > button:active {
        transform: translateY(0);
        box-shadow: 0 2px 5px rgba(0,90,158,0.2);
    }

    /* Điều chỉnh sidebar */
    .st-emotion-cache-vk330y { 
        background-color: rgba(255, 255, 255, 0.85); 
        backdrop-filter: blur(10px);
        box-shadow: 2px 0 15px rgba(0,0,0,0.1);
    }

</style>
""", unsafe_allow_html=True)


# --- Tiêu đề và mô tả chính ---
st.title("🤖 APEC 2025 Chatbot")
st.markdown(
    "Chào mừng bạn đến với trợ lý AI chính thức của **APEC 2025**! "
    "Hỏi tôi bất cứ điều gì về sự kiện, lịch trình, địa điểm, thủ tục nhập cảnh, văn hóa và nhiều hơn nữa."
)

# --- Sidebar với các chức năng bổ sung ---
with st.sidebar:
    st.header("Tùy chọn")
    if st.button("🗑️ Xóa cuộc trò chuyện", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_suggestions = [] 
        st.session_state.temp_user_input = "" # Đảm bảo xóa input tạm thời
        st.rerun()
        
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; font-size: 0.85em; color: #888;'>"
        "APEC 2025 Chatbot<br>"
        "&copy; 2025. Phát triển bởi Hekate - công ty AI hàng đầu Việt Nam."
        "</div>",
        unsafe_allow_html=True
    )

# --- Khởi tạo session state ---
if "messages" not in st.session_state:
    st.session_state.messages = [] 
if "last_suggestions" not in st.session_state:
    st.session_state.last_suggestions = []
if "temp_user_input" not in st.session_state: 
    st.session_state.temp_user_input = ""

# --- Hàm gửi tin nhắn đến Backend API ---
def send_message_to_backend(message: str, chat_history: list):
    """
    Gửi tin nhắn của người dùng và lịch sử chat đến API backend
    và nhận câu trả lời.
    """
    print(f"Người dùng gửi: {message}")
    
    try:
        with st.spinner("Bot đang suy nghĩ..."): 
            response = requests.post(
                BACKEND_API_URL,
                json={"message": message}, 
                timeout=180 
            )
            response.raise_for_status() 

            data = response.json()
            return data["answer"], data.get("lang", "?"), data.get("suggestions", []) 
    except requests.exceptions.ConnectionError:
        st.error("Lỗi kết nối: Không thể kết nối tới API backend. Đảm bảo backend đang chạy tại " + BACKEND_API_URL)
    except requests.exceptions.Timeout:
        st.error("Lỗi timeout: API backend không phản hồi kịp thời. Vui lòng thử lại.")
    except requests.exceptions.RequestException as e:
        st.error(f"Lỗi yêu cầu API: {e}. Vui lòng kiểm tra log backend.")
    except json.JSONDecodeError:
        st.error("Lỗi phân tích phản hồi JSON từ API backend.")
    except Exception as e:
        st.error(f"Một lỗi không mong muốn đã xảy ra: {e}")
    return None, "?", [] 

# --- Hiển thị lịch sử cuộc trò chuyện ---
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="🙋‍♂️" if message["role"] == "user" else "🤖"):
        st.markdown(message["content"])

# --- Xử lý input từ người dùng (text input) ---
if prompt := st.chat_input("Gõ câu hỏi của bạn ở đây...", key="main_chat_input"):
    st.session_state.temp_user_input = prompt 

# --- Xử lý khi có input (từ chat_input hoặc quick reply) ---
if st.session_state.temp_user_input:
    user_message = st.session_state.temp_user_input
    st.session_state.temp_user_input = "" # Xóa tạm để tránh lặp
    
    st.session_state.messages.append({"role": "user", "content": user_message})
    with st.chat_message("user", avatar="🙋‍♂️"):
        st.markdown(user_message)

    current_chat_history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    
    answer, lang, suggestions = send_message_to_backend(user_message, current_chat_history)
    
    if answer: 
        st.session_state.messages.append({"role": "assistant", "content": answer, "lang": lang})
        st.session_state.last_suggestions = suggestions
    
    st.rerun() 

# --- Hiển thị các câu hỏi gợi ý nhanh ---
# Chỉ hiển thị quick replies nếu không có tin nhắn nào trong lịch sử HOẶC có gợi ý từ tin nhắn gần nhất
if not st.session_state.messages or st.session_state.last_suggestions:
    st.markdown("---") 
    suggestions_container = st.container()
    with suggestions_container:
        st.markdown("<p style='text-align: center; font-weight: 500;'>Hoặc thử một trong các câu hỏi sau:</p>", unsafe_allow_html=True)
        
        suggestions_to_display = []
        if st.session_state.last_suggestions: 
            suggestions_to_display = st.session_state.last_suggestions
        elif not st.session_state.messages: 
            suggestions_to_display = [
                "APEC 2025 tổ chức ở đâu?",
                "Lịch trình chính của hội nghị?",
                "Các chủ đề thảo luận chính là gì?",
                "Giới thiệu về văn hóa Việt Nam ở Phú Quốc?", 
                "Thông tin về các thành viên APEC?"
            ]
        
        if suggestions_to_display:
            # Sửa đổi logic tạo cột và phân phối nút
            num_suggestions = len(suggestions_to_display)
            # Giới hạn số cột hiển thị trên một hàng để tránh quá nhỏ, ví dụ max 3 cột
            max_cols_per_row = 3
            num_rows = (num_suggestions + max_cols_per_row - 1) // max_cols_per_row # Tính số hàng cần thiết

            for row in range(num_rows):
                # Tạo số cột bằng max_cols_per_row
                cols = st.columns(max_cols_per_row)
                for col_idx in range(max_cols_per_row):
                    sug_idx = row * max_cols_per_row + col_idx
                    if sug_idx < num_suggestions:
                        sug = suggestions_to_display[sug_idx]
                        with cols[col_idx]:
                            if st.button(sug, key=f"sug_btn_{sug_idx}", use_container_width=True): 
                                st.session_state.temp_user_input = sug 
                                st.rerun()