# OCR Foundation Spec (Tuần 5-8)

## 1. Mục tiêu
- Chọn OCR engine phù hợp tiếng Việt cho hồ sơ pháp lý.
- Xây pipeline OCR batch theo thư mục.
- Giảm lỗi trên scan xấu bằng tiền xử lý ảnh.
- Thiết lập human-in-the-loop (HITL) cho hồ sơ nhạy cảm.

## 2. Bộ benchmark OCR
- **Nhóm tài liệu**: hợp đồng, đơn từ, quyết định tòa, văn bản scan cũ.
- **Mức chất lượng ảnh**: tốt, trung bình, kém (mờ/nghiêng/nhiễu).
- **Chỉ số đo**:
  - Character Error Rate (CER)
  - Word Error Rate (WER)
  - Field Extraction Accuracy (tên đương sự, số hồ sơ, ngày, điều khoản)

## 3. Pipeline OCR v1
1. Nhận file từ hàng đợi.
2. Tiền xử lý ảnh (`deskew`, `denoise`, `contrast normalize`).
3. OCR text extraction.
4. Trích xuất trường chính bằng rule + NLP.
5. Gắn confidence score.
6. Lưu text + field + log lỗi.
7. Đồng bộ sang kho tra cứu vụ việc.

## 4. Quy tắc HITL
- Hồ sơ vào hàng chờ kiểm duyệt khi:
  - confidence thấp hơn ngưỡng vận hành.
  - chứa trường pháp lý nhạy cảm.
  - scan xấu vượt ngưỡng nhiễu.
- Reviewer có quyền sửa text và field.
- Lưu lịch sử chỉnh sửa để tái huấn luyện quy tắc.

## 5. Cấu trúc output chuẩn
```json
{
  "document_id": "DOC-2026-0001",
  "ocr_text_uri": "s3://ocr-results/DOC-2026-0001.txt",
  "fields": {
    "party_name": "Nguyen Van A",
    "case_code": "CASE-2026-015",
    "decision_no": "QD-139/2026",
    "document_date": "2026-05-01"
  },
  "confidence": 0.93,
  "needs_review": false,
  "processed_at": "2026-05-10T14:30:00+07:00"
}
```

## 6. Tiêu chí nghiệm thu GateB
- Pipeline OCR chạy batch ổn định trên tập mẫu.
- Có dashboard theo dõi lỗi OCR theo loại tài liệu.
- Có quy trình HITL vận hành được.
- Đồng bộ OCR -> CSDL tra cứu pass trên dữ liệu thật.
