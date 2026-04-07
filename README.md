# Chatbot RAG — tra cứu văn bản pháp luật (demo)

Ứng dụng demo: **truy vấn ngôn ngữ tự nhiên** trên kho văn bản luật đã index (TF‑IDF + embedding **hybrid**), sinh câu trả lời bằng **Ollama**, kèm giao diện web và tùy chọn tra cứu **EU CoSIng** (hóa chất mỹ phẩm).

> Demo mang tính minh họa; không thay thế tư vấn pháp lý chính thức. Luôn đối chiếu văn bản gốc và văn sửa đổi.

---

## Yêu cầu

- **Python 3.11+** (khuyến nghị; đã thử trên 3.12/3.14 tùy máy).
- **Ollama** cài trên máy, đã `pull` model trong `.env` (mặc định `qwen2.5:3b-instruct`).
- RAM/ổ đủ cho `sentence-transformers` + `torch` (CPU) nếu dùng hybrid.
- **CoSIng (tùy chọn):** Chrome hoặc Edge + bật `COSING_ENABLED=true` (Selenium).

---

## Cài đặt nhanh

```powershell
cd đường_dẫn_tới\AI_Chatbot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Sao chép cấu hình môi trường:

```powershell
copy .env.example .env
```

Chỉnh trong `.env` ít nhất **`OLLAMA_BASE_URL`** và **`OLLAMA_MODEL`** cho khớp Ollama của bạn.

---

## Chuẩn bị dữ liệu & vector store

Văn bản nguồn khai báo trong `data/raw_laws/manifest.json`. Sau khi có PDF/RTF trong `data/raw_laws/`:

```powershell
# Trích text + chunk (theo từng doc_id trong manifest)
python tools/extract_text.py --doc-id law_35_2024_qh15 --force
python tools/legal_chunker.py --doc-id law_35_2024_qh15 --force
# (lặp cho các luật khác, hoặc viết vòng lặp theo nhu cầu)

# TF‑IDF + metadata
python tools/build_embeddings_file_based.py --rebuild

# Dense (cho hybrid) — lần đầu tải model Sentence Transformers
python tools/build_dense_embeddings.py --rebuild
```

Kỳ vọng thư mục `data/vector_db/file_based_demo/` có: `vectorizer.joblib`, `tfidf_matrix.joblib`, `metadatas.jsonl`, và thường kèm `dense_matrix.npy`.

Chi tiết checklist tay: **`tests/MANUAL_STAGING.md`** (M1–M6).

---

## Chạy web (API + giao diện)

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Mở trình duyệt:

| Mục | URL |
|-----|-----|
| **Giao diện chat + tab CoSIng** | http://127.0.0.1:8000/ |
| **Swagger / thử API** | http://127.0.0.1:8000/docs |

- Tab **Pháp luật:** gửi câu hỏi → `POST /chat` (RAG + Ollama).
- Tab **CoSIng:** `POST /api/cosing/lookup` — chỉ hoạt động khi **`COSING_ENABLED=true`**; lần đầu có thể **30–120 giây** (Selenium).

**Lưu ý:** Phải mở qua `http://...` (không mở file HTML kiểu `file://`).

---

## Câu hỏi mẫu để demo chatbot

Đã tách sang file riêng để README gọn hơn:
- Xem tại: `demo_questions.md`

---

## API chính

### `POST /chat`

Body JSON:

```json
{
  "question": "Giấy phép lái xe các hạng?",
  "top_k": 3
}
```

Trả về: `answer`, `citations`, `sources` (luật / điều).

### `POST /api/cosing/lookup`

Body JSON:

```json
{
  "query": "Salicylic Acid",
  "query_type": "NAME_OR_INCI",
  "request_id": "REQ-tùy-chọn"
}
```

`request_id` có thể bỏ trống (server tự sinh). Cần bật CoSIng trong `.env`.

---

## Biến môi trường (tóm tắt)

Xem đầy đủ trong **`.env.example`**.

| Nhóm | Biến | Ý nghĩa |
|------|------|---------|
| LLM | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TEMPERATURE` | Endpoint và model Ollama |
| RAG | `RAG_MODE`, `HYBRID_ALPHA`, `RETRIEVE_K`, `TOP_K_DEFAULT`, `MIN_RETRIEVAL_SCORE`, `VECTOR_STORE_DIR`, `DENSE_MODEL_NAME` | Chế độ hybrid / ngưỡng / đường dẫn store |
| Hành vi | `ROUTER_ENABLED`, `REFLECTION_ENABLED` | Chào hỏi không RAG; kiểm tra bám context sau LLM |
| Tối ưu tốc độ/chất lượng | `FAST_ACCURATE_MODE`, `ANSWER_CACHE_ENABLED`, `ANSWER_CACHE_TTL_SECONDS`, `ANSWER_CACHE_MAX_ITEMS` | Adaptive retrieval + nén context + cache trả lời |
| Web | `CORS_ALLOW_ORIGINS` | CORS cho demo |
| CoSIng | `COSING_ENABLED`, `COSING_CACHE_DIR`, `COSING_BROWSER`, `COSING_HEADLESS`, `COSING_ENRICH_DETAIL` | Tab tra cứu EU + mở rộng dữ liệu chi tiết |

---

## Cấu hình tăng tốc (giữ độ chính xác)

Mặc định đã hỗ trợ cơ chế tối ưu:
- Adaptive retrieval (câu đơn giản dùng pool nhỏ hơn).
- Nén context theo từ khóa câu hỏi trước khi gửi LLM.
- Cache câu trả lời theo TTL cho câu hỏi lặp.

### Bật chế độ tối ưu (khuyến nghị)

```env
FAST_ACCURATE_MODE=true
ANSWER_CACHE_ENABLED=true
ANSWER_CACHE_TTL_SECONDS=300
ANSWER_CACHE_MAX_ITEMS=300
```

Sau khi đổi `.env`, khởi động lại API:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

---

## Docker

```powershell
copy .env.example .env
# Chỉnh OLLAMA_BASE_URL nếu Ollama chạy trên máy host (Windows): thường dùng http://host.docker.internal:11434
docker compose up --build
```

Giao diện: http://localhost:8000/

Image đã copy sẵn `data/` trong Dockerfile; nếu index nằm ngoài image, có thể bật `volumes` trong `docker-compose.yml` (xem comment trong file).

---

## Kiểm thử

```powershell
python -m pytest tests/ -v
```

Smoke RAG (TF‑IDF) / suite mẫu:

```powershell
python tools/smoke_test_rag_llm.py --suite --rag-only --top-k 2
```

---

## Cấu trúc thư mục (rút gọn)

```
api/main.py              # FastAPI: /chat, /api/cosing/lookup, static demo_web
demo_web/index.html      # Giao diện: Pháp luật + CoSIng
tools/                   # extract, chunk, build index, hybrid retrieval, LLM helpers
tools/cosing_adapter/    # Tra cứu CoSIng (Selenium + cache)
data/raw_laws/           # PDF/RTF + manifest.json
data/processed/          # text JSON + chunk jsonl
data/vector_db/          # vectorizer, matrix, metas, dense .npy
tests/                   # Pytest + MANUAL_STAGING.md
docs/                    # Tài liệu bổ sung (CoSIng, implementation package)
```

---

## Xử lý sự cố thường gặp

- **API báo thiếu vector store:** chạy lại `build_embeddings_file_based.py` (và đảm bảo đường dẫn `VECTOR_STORE_DIR`).
- **Không có câu trả lời LLM, chỉ thấy trích context:** Ollama chưa chạy hoặc sai URL/model — kiểm tra `ollama list` và `OLLAMA_BASE_URL`.
- **Hybrid / T3 pytest lỗi thiếu gói:** `pip install sentence-transformers` (và torch).
- **CoSIng 503:** đặt `COSING_ENABLED=true` và đảm bảo Chrome/Edge + driver (webdriver-manager thường tự tải).
- **Windows + cache Hugging Face cảnh báo symlink:** có thể bật Developer Mode hoặc bỏ qua nếu vẫn chạy được.

---

## Giấy phép & nguồn dữ liệu

Văn bản luật do người dùng đặt trong `data/raw_laws/` theo quy định sở hữu bản quyền nguồn. CoSIng: dữ liệu từ trang EU Commission — tuân thủ điều khoản sử dụng của trang nguồn.
