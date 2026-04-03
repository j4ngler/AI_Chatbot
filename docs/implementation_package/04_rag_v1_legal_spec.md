# RAG Pháp Lý v1 Spec (Tuần 9-12)

## 1. Nguyên tắc
- RAG trước, LLM sau.
- Chỉ trả lời trên ngữ liệu đã truy hồi.
- Bắt buộc citation hợp lệ hoặc từ chối có kiểm soát.

## 2. Pipeline truy vấn
1. Query normalization (sửa lỗi chính tả nhẹ, chuẩn hóa thuật ngữ).
2. Query rewrite (tạo truy vấn retrieval tốt hơn).
3. Hybrid retrieval:
   - BM25 keyword search.
   - Vector semantic search.
4. Metadata filter (`legal_domain`, `effective_date`, `security_level`).
5. Rerank top-k.
6. Context pack.
7. LLM answer generation với prompt guardrail.
8. Citation validator.

## 3. Chunking strategy
- Chunk theo đơn vị pháp lý: Chương/Điều/Khoản.
- Không chunk ngẫu nhiên theo số token thuần.
- Mỗi chunk giữ:
  - `document_id`, `section_code`, `heading_path`, `page_ref`, `effective_date`.

## 4. Chính sách trả lời
- Nếu có nguồn đủ mạnh: trả lời + dẫn chiếu.
- Nếu nguồn yếu/không đủ: trả lời từ chối an toàn, gợi ý câu hỏi cụ thể hơn.
- Cấm trả lời kiểu suy đoán pháp lý không có căn cứ tài liệu.

## 5. Prompt contract rút gọn
- System prompt bắt buộc:
  - Chỉ dùng context được cung cấp.
  - Trả citation cuối mỗi luận điểm.
  - Nếu không đủ dữ liệu thì nói rõ không đủ.

## 6. API contract đề xuất
- `POST /chat/query`
  - Input: `session_id`, `question`, `user_context`.
  - Output: `answer`, `citations[]`, `confidence`, `rejection_reason`.

- `POST /rag/evaluate`
  - Input: test set.
  - Output: `citation_valid_rate`, `grounded_rate`, `latency_p95`.

## 7. Bộ đánh giá
- Test set nội bộ tối thiểu 200 câu:
  - factual legal QA,
  - cross-document QA,
  - no-answer required.
- Ngưỡng vận hành ban đầu:
  - citation valid rate >= 0.9
  - grounded rate >= 0.85
  - latency p95 theo SLA nội bộ.

## 8. Tiêu chí nghiệm thu GateC
- 100% câu trả lời thử nghiệm có citation hoặc từ chối đúng.
- Truy xuất được nguồn theo `document_id + section_code`.
- Có dashboard theo dõi chất lượng RAG theo tuần.
