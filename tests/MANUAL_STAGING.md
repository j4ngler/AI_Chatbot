# Checklist thủ công / staging (M1–M5)

Chạy sau khi cài dependency: `pip install -r requirements.txt`.

## M1 — Extract + chunk luật 26/2001 (RTF)

```powershell
cd <repo>
python tools/extract_text.py --doc-id law_26_2001_qh10 --force
python tools/legal_chunker.py --doc-id law_26_2001_qh10 --force
```

Kỳ vọng: `data/processed/text/law_26_2001_qh10.json` và `data/processed/chunks/law_26_2001_qh10.jsonl` có tiếng Việt đọc được (không chuỗi kiểu `LÖnh`).

## M2 — Build TF-IDF + dense

```powershell
python tools/build_embeddings_file_based.py --rebuild
python tools/build_dense_embeddings.py --rebuild
```

Kỳ vọng: `data/vector_db/file_based_demo/` có `vectorizer.joblib`, `tfidf_matrix.joblib`, `metadatas.jsonl`, `dense_matrix.npy`.

## M3 — API chat

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

`POST http://127.0.0.1:8000/chat` body JSON: `{"question":"giấy phép lái xe các hạng","top_k":2}`  
Kỳ vọng: `sources` khớp luật (ví dụ 23/2008), `answer` tiếng Việt ngắn.

## M4 — Ngưỡng retrieval

Đặt trong `.env`: `MIN_RETRIEVAL_SCORE=0.95`, hỏi câu ngoài phạm vi.  
Kỳ vọng: trả lời kiểu không đủ căn cứ trong văn bản đã index, `sources` rỗng.

## M5 — Reflection

Đặt `REFLECTION_ENABLED=true` và **Ollama** đang chạy (reflection dùng cùng model Ollama).  
Hỏi câu hợp lệ; quan sát latency. (Kiểm tra chặn ảo giác cần bối cảnh kiểm soát — chủ yếu smoke.)

## M6 — CoSIng trên demo web (tùy chọn)

Đặt `COSING_ENABLED=true`, cài Chrome/Edge; chạy API như M3. Mở trang chủ demo → tab **CoSIng** → tra cứu (có thể rất lâu).

## Hồi quy nhanh

```powershell
python tools/smoke_test_rag_llm.py --suite --rag-only --top-k 2
```

## Biến môi trường (tùy chọn)

| Biến | Ý nghĩa |
|------|---------|
| `RAG_MODE` | Để trống = tự bật hybrid nếu có `dense_matrix.npy`; `tfidf` = chỉ TF-IDF; `hybrid` = bắt buộc hybrid khi có file dense |
| `HYBRID_ALPHA` | Trọng số dense (0–1), mặc định `0.5` |
| `RETRIEVE_K` | Số ứng viên sau bước pool (trước `top_k`), mặc định `20` |
| `MIN_RETRIEVAL_SCORE` | Ngưỡng điểm hybrid trên pool (sau min-max); điểm max dưới ngưỡng → từ chối trả lời |
| `DENSE_MODEL_NAME` | Model sentence-transformers khi build/query hybrid |
| `DENSE_MATRIX_FILENAME` | Tên file `.npy` trong thư mục vector store |
| `ROUTER_ENABLED` | `true`/`false` — chào hỏi không qua RAG |
| `REFLECTION_ENABLED` | `true`/`false` — tự kiểm YES/NO sau câu trả lời LLM |
