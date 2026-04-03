# Kiến trúc tổng thể + lộ trình 24 tuần (bản triển khai)

## 1. Mục tiêu triển khai
- Thiết lập hệ thống chatbot pháp lý phục vụ Công ty Luật Mai Trang theo hướng `RAG-first`.
- Chuẩn hóa tài liệu pháp lý theo quy tắc heading trước khi index.
- Hỗ trợ số hóa hồ sơ (OCR), hỏi đáp có dẫn chiếu, quản trị vụ việc, và vận hành nội bộ.
- Giữ khả năng mở rộng cho ký số, thanh toán QR, biểu mẫu tự động, tra cứu hóa chất CoSIng.

## 2. Kiến trúc tổng thể

### 2.1 Các lớp hệ thống
- **Presentation Layer**: cổng người dùng chat, cổng uploader/admin.
- **Application Layer**: API Gateway, Chat Orchestrator, Case Service, Doc Service, Notification Service.
- **AI Layer**: OCR pipeline, embedding/indexing, retriever, reranker, LLM gateway, policy guard.
- **Data Layer**: object storage, metadata DB (PostgreSQL), vector DB, audit log.
- **Integration Layer**: ký số, thanh toán, email/zalo/telegram, Selenium CoSIng adapter.

### 2.2 Luồng dữ liệu cốt lõi
1. Uploader đưa file gốc + metadata.
2. Normalization chuẩn hóa về cấu trúc heading pháp lý.
3. Validation kiểm tra tính hợp lệ heading/metadata.
4. Indexing tạo chunk + embedding + metadata.
5. Chat query đi qua retrieval -> rerank -> LLM.
6. Policy guard ép trả lời có citation hoặc từ chối an toàn.
7. Kết quả và truy vết được ghi log phục vụ kiểm toán.

### 2.3 Mô hình triển khai khuyến nghị
- **Mặc định**: Hybrid.
- Dữ liệu pháp lý và chỉ mục đặt trong hạ tầng nội bộ/on-prem.
- LLM gateway có thể trỏ private model hoặc cloud model theo policy.

## 3. Phân rã lộ trình 24 tuần

### Pha 0 (Tuần 1-2): Scope & kiến trúc
- Chốt phase 1/2 scope, RACI, deployment, backlog.
- Ban hành data contract và checklist nhập liệu.

### Pha 1 (Tuần 3-4): Nền tảng dữ liệu
- Kho lưu trữ, phân quyền, backup.
- CSDL vụ việc v0.1 + audit logging.

### Pha 2 (Tuần 5-8): OCR & số hóa
- Benchmark OCR và pipeline OCR v1.
- Tối ưu scan xấu, đồng bộ OCR vào CSDL.

### Pha 3 (Tuần 9-12): RAG pháp lý
- Chuẩn hóa tri thức pháp lý và index pipeline.
- Chatbot pháp lý v1 có dẫn chiếu bắt buộc.
- Đánh giá chất lượng retrieval + grounded answer.

### Pha 4 (Tuần 13-16): Workflow vận hành
- Workflow vụ việc, nhắc hạn, lịch pháp lý.
- Dashboard quản trị deadline và tải công việc.

### Pha 5 (Tuần 17-20): Tự động hóa hồ sơ
- Ký số adapter, template biểu mẫu, xuất Word/PDF.
- QR payment là hạng mục có điều kiện theo readiness.

### Pha 6 (Tuần 21-24): UAT -> Go-live
- UAT đa phòng ban, fix P1/P2, hardening.
- Đào tạo theo vai trò, bàn giao SOP, go-live + SLA.

## 4. Stage Gates
- **GateA (Tuần 4)**: data contract + hạ tầng + CSDL tối thiểu.
- **GateB (Tuần 8)**: OCR pipeline ổn định + QA tay cho hồ sơ nhạy cảm.
- **GateC (Tuần 12)**: RAG đạt ngưỡng citation và từ chối an toàn.
- **GateD (Tuần 20)**: biểu mẫu + xuất văn bản vận hành được.
- **GateE (Tuần 24)**: UAT pass + SOP + SLA ký.

## 5. KPI điều hành tối thiểu
- OCR accuracy.
- Citation valid rate.
- Hallucination rejection accuracy.
- Case cycle time.
- Overdue reduction.
- User adoption theo vai trò.
