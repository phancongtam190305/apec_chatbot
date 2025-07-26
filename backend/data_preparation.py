import requests
from bs4 import BeautifulSoup, Comment
import os
import re
import json
import uuid
import glob

# Thư viện LangChain cho preprocessing
from langchain_community.document_loaders import UnstructuredHTMLLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# --- Hàm hỗ trợ crawl: Lấy số trang tối đa ---
def get_max_page_number(soup):
    """
    Extracts the maximum page number from the pagination section of a BeautifulSoup object.
    """
    max_page = 1
    pagination_links = soup.select('.webtong-paging #numbering a')
    current_page_elem = soup.select_one('.webtong-paging #numbering em')
    
    if current_page_elem:
        try:
            max_page = max(max_page, int(current_page_elem.get_text(strip=True)))
        except ValueError:
            pass

    for link in pagination_links:
        if link.has_attr('onclick'):
            match = re.search(r'submitForm\(this,\s*"list",\s*(\d+)\);', link['onclick'])
            if match:
                page_num = int(match.group(1))
                max_page = max(max_page, page_num)
    
    last_btn = soup.select_one('.webtong-paging .last')
    if last_btn and last_btn.has_attr('onclick'):
        match = re.search(r'submitForm\(this,\s*"list",\s*(\d+)\);', last_btn['onclick'])
        if match:
            max_page = max(max_page, int(match.group(1)))
    return max_page

# --- Hàm hỗ trợ tiền xử lý: Trích xuất HTML nội dung chính (GIỮ NGUYÊN TỪ CRAWLER.IPYNB) ---
def extract_main_content_html(html_file_path):
    """
    Extracts the HTML content from the main content area of the page.
    Assumes main content is within <div id="contents">...</div>.
    """
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"Lỗi: File HTML không tìm thấy tại '{html_file_path}'")
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Tìm thẻ div có id="contents"
    main_contents_div = soup.find('div', id='contents')
    
    if main_contents_div:
        # Loại bỏ các thẻ không liên quan đến nội dung chính bên trong main_contents_div
        for tag in main_contents_div(['script', 'style', 'nav', 'form', 'img', 'svg', 'header', 'footer']):
            tag.decompose()
        
        # Trả về HTML đã được làm sạch của khu vực nội dung chính
        return str(main_contents_div)
    else:
        print(f"Cảnh báo: Không tìm thấy div #contents trong file {html_file_path}. Sẽ xử lý toàn bộ HTML.")
        return html_content # Trả về toàn bộ HTML nếu không tìm thấy khu vực chính

# --- Chức năng chính: Crawl và lưu HTML ---
def crawl_and_save_html(urls_to_crawl, output_dir="data/crawled_raw_html"):
    """
    Crawls HTML content from a list of URLs and saves each to a separate .html file.
    Includes special handling for paginated pages like 'Press Release' to combine them.
    """
    os.makedirs(output_dir, exist_ok=True)
    print(f"Thư mục '{output_dir}' đã sẵn sàng để lưu trữ HTML.")

    for name, base_url in urls_to_crawl.items():
        print(f"\n--- Đang xử lý: {name} từ {base_url} ---")
        
        file_path_to_save = os.path.join(output_dir, f"{name}.html")
        if name == "Press_Release":
            file_path_to_save = os.path.join(output_dir, f"{name}_combined.html")

        if os.path.exists(file_path_to_save):
            print(f"  File '{file_path_to_save}' đã tồn tại. Bỏ qua crawl cho {name}.")
            continue

        if name == "Press_Release":
            with open(file_path_to_save, "w", encoding="utf-8") as combined_file:
                combined_file.write("<!DOCTYPE html>\n<html><head><meta charset='utf-8'></head><body>\n")
                combined_file.write("<main>\n") 
                
                current_page = 1
                max_page_found = 1 

                while current_page <= max_page_found:
                    url = f"{base_url}&pageNum={current_page}" if current_page > 1 else base_url
                    print(f"  > Đang tải trang {current_page} của {name} từ {url}...")
                    try:
                        response = requests.get(url, timeout=20)
                        response.raise_for_status()
                        html_content = response.text
                        soup = BeautifulSoup(html_content, 'html.parser')

                        new_max_page = get_max_page_number(soup)
                        if new_max_page > max_page_found:
                            max_page_found = new_max_page
                            print(f"  > Cập nhật tổng số trang cho {name} thành: {max_page_found}")

                        article_list_items = soup.select('.board_list1 .event > li')
                        
                        if article_list_items:
                            for item in article_list_items:
                                combined_file.write(f"<article data-source-url='{url}' data-article-id='{str(uuid.uuid4())}'>\n")
                                combined_file.write(str(item) + "\n")
                                combined_file.write("</article>\n")
                            print(f"  + Đã thêm {len(article_list_items)} bài viết từ trang {current_page} (đã bọc <article>) vào file tổng.")
                        else:
                            print(f"  ! Không tìm thấy bài viết nào trên trang {current_page}. Dừng crawl {name}.")
                            break

                        current_page += 1

                        if current_page > max_page_found:
                            break

                    except requests.exceptions.RequestException as e:
                        print(f"  ! Lỗi khi tải trang {url}: {e}. Dừng crawl {name}.")
                        break
                    except Exception as e:
                        print(f"  ! Lỗi xử lý trang {url}: {e}. Dừng crawl {name}.")
                        break

                combined_file.write("</main>\n")
                combined_file.write("</body></html>\n")
                print(f"✅ Đã lưu tất cả nội dung Press Release vào: {file_path_to_save}")

        else: # Xử lý các trang không phân trang (HTML đơn)
            try:
                response = requests.get(base_url, timeout=20)
                response.raise_for_status()
                html_content = response.text

                with open(file_path_to_save, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"  Đã lưu: {file_path_to_save}")

            except requests.exceptions.RequestException as e:
                print(f"  ! Lỗi khi tải trang {base_url}: {e}")
            except Exception as e:
                print(f"  ! Lỗi xử lý trang {base_url}: {e}")

    print("\n--- ✅ Hoàn tất quá trình crawl và lưu HTML ---\n")

# --- Chức năng chính: Tiền xử lý HTML thành chunks JSON (GIỮ NGUYÊN TỪ CRAWLER.IPYNB) ---
def process_html_files_to_chunks_smartly(html_dir="data/crawled_raw_html", output_json_path="data/json_chunks/apec_all_chunks.json"):
    all_chunks_data = []
    
    output_data_dir = os.path.dirname(output_json_path)
    os.makedirs(output_data_dir, exist_ok=True)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        add_start_index=True
    )

    html_files = glob.glob(os.path.join(html_dir, "*.html"))
    if not html_files:
        print(f"Không tìm thấy file HTML nào trong thư mục '{html_dir}'. Vui lòng crawl dữ liệu trước.")
        return

    print(f"Tìm thấy {len(html_files)} file HTML để xử lý.")

    for html_file in html_files:
        file_name = os.path.basename(html_file)
        print(f"Đang xử lý file: {file_name}")

        try:
            # Bước mới: Chỉ lấy phần HTML của khu vực nội dung chính
            main_content_html = extract_main_content_html(html_file)
            
            if main_content_html:
                # Tạo một file tạm thời chỉ chứa nội dung chính để UnstructuredHTMLLoader đọc
                temp_html_path = f"{html_file}.temp.html"
                with open(temp_html_path, "w", encoding="utf-8") as temp_f:
                    temp_f.write(main_content_html)

                loader = UnstructuredHTMLLoader(temp_html_path)
                documents = loader.load() 
                
                # Xóa file tạm sau khi đã load
                os.remove(temp_html_path)

                chunks = text_splitter.split_documents(documents)

                for chunk in chunks:
                    topic_from_filename = file_name.replace(".html", "").replace("_page_", " Page ").replace("_", " ")
                    
                    # Cố gắng lấy topic/sub_topic từ metadata của UnstructuredHTMLLoader nếu có
                    cleaned_content = ' '.join(chunk.page_content.split()) 
                    
                    chunk_data = {
                        "id": str(uuid.uuid4()),
                        "topic": chunk.metadata.get("category", topic_from_filename), 
                        "sub_topic": chunk.metadata.get("title", chunk.metadata.get("header", "N/A")), 
                        "content": cleaned_content, 
                        "source_file": file_name,
                        # "source_url": "URL_GOC_CUA_TRANG_NAY" # Bạn cần một cách để ánh xạ filename về URL gốc
                    }
                    all_chunks_data.append(chunk_data)
            else:
                # Dòng này sẽ chỉ xuất hiện nếu extract_main_content_html trả về None
                # Trong phiên bản của crawler.ipynb, extract_main_content_html KHÔNG bao giờ trả về None
                # nếu file tồn tại, nên dòng này hiếm khi xuất hiện
                print(f"Không tìm thấy nội dung chính để xử lý từ file: {file_name}. Bỏ qua file này.")

        except Exception as e:
            print(f"Lỗi khi xử lý file '{html_file}': {e}")
            
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(all_chunks_data, f, ensure_ascii=False, indent=4)

    print(f"\n--- Đã xử lý {len(html_files)} file HTML và lưu {len(all_chunks_data)} chunks vào '{output_json_path}' ---")
    
    if all_chunks_data:
        print("\n--- Chunk mẫu đầu tiên sau khi cải thiện ---")
        print(json.dumps(all_chunks_data[0], ensure_ascii=False, indent=4))
        # Không in chunk mẫu từ Press Release cụ thể nếu không có logic cụ thể cho nó như trong data_preparation.py
        # Điều này là để giữ cho nó giống hệt crawler.ipynb

# --- Khối main để chạy các chức năng ---
if __name__ == "__main__":
    # 1. Định nghĩa các URL để crawl
    urls_and_names = {
        "Information_of_Apec": "https://apec2025.kr/?menuno=89",
        "Introduction_About_Apec_Korea_2025": "https://apec2025.kr/?menuno=91",
        "Emblem_and_Theme": "https://apec2025.kr/?menuno=92",
        "Meetings": "https://apec2025.kr/?menuno=93",
        "Side_Events": "https://apec2025.kr/?menuno=94",
        "Documents_HRDDM": "https://apec2025.kr/?menuno=148",
        "Documents_AEMM": "http://apec2025.kr/?menuno=149", 
        "Documents_MRT": "https://apec2025.kr/?menuno=150",
        "Notices": "https://apec2025.kr/?menuno=15",
        "Press_Release": "https://apec2025.kr/?menuno=16", 
        "Korea_in_Brief": "https://apec2025.kr/?menuno=18",
        "Practical_Information": "https://apec2025.kr/?menuno=22",
        "About_Gyeongju": "https://apec2025.kr/?menuno=102",
        "Transportation_of_Gyeongju": "https://apec2025.kr/?menuno=137",
        "Heritage_Gyeongju": "https://apec2025.kr/?menuno=108",
        "Attraction_of_Gyeongju": "https://apec2025.kr/?menuno=138",
        "About_Jeju": "https://apec2025.kr/?menuno=103",
        "Transportation_Jeju": "https://apec2025.kr/?menuno=141",
        "Nature_Culture_Jeju": "https://apec2025.kr/?menuno=114",
        "Themed_Travel_Jeju": "https://apec2025.kr/?menuno=115",
        "About_Incheon": "https://apec2025.kr/?menuno=104",
        "Attractions_Incheon": "https://apec2025.kr/?menuno=117",
        "Local_Eateries_Incheon": "https://apec2025.kr/?menuno=118",
        "About_Busan": "https://apec2025.kr/?menuno=106",
        "About_Seoul": "https://apec2025.kr/?menuno=24",
    }
    
    # 2. Định nghĩa các đường dẫn input/output
    # Lưu ý: crawler.ipynb mặc định lưu vào "data/crawled_raw_html"
    # và "data/json_chunks/apec_all_chunks.json"
    html_raw_output_dir = "backend/data/crawled_raw_html" 
    json_chunks_output_path = "backend/data/json_chunks/apec_all_chunks.json"

    # 3. Chạy quá trình crawl
    print("--- BẮT ĐẦU QUÁ TRÌNH CRAWL HTML ---")
    crawl_and_save_html(urls_and_names, output_dir=html_raw_output_dir)
    print("--- HOÀN TẤT QUÁ TRÌNH CRAWL HTML ---\n")

    # 4. Chạy quá trình tiền xử lý HTML thành chunks JSON
    print("--- BẮT ĐẦU QUÁ TRÌNH TIỀN XỬ LÝ HTML THÀNH CHUNKS JSON ---")
    process_html_files_to_chunks_smartly(html_dir=html_raw_output_dir, output_json_path=json_chunks_output_path)
    print("--- HOÀN TẤT QUÁ TRÌNH TIỀN XỬ LÝ HTML THÀNH CHUNKS JSON ---")