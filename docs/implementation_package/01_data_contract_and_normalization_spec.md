# Data Contract & Normalization Spec

## 1. Quy tắc heading pháp lý bắt buộc

### 1.1 Tài liệu Quyết định
- `Heading 1`: tiêu đề quyết định.
- `Heading 2`: các Điều (`Điều 1`, `Điều 2`, ...).

### 1.2 Tài liệu Quy định
- `Heading 1`: tiêu đề quy định.
- `Heading 2`: tên Chương.
- `Heading 3`: các Điều và thông tin quyết định ban hành kèm (nếu có).

### 1.3 Tài liệu Nhiệm vụ
- `Heading 1`: Lĩnh vực.
- `Heading 2`: Tên công việc/Trích yếu.
- Các trường còn lại là nội dung, không đánh heading.

### 1.4 Tài liệu Lịch làm việc
- `Heading 1`: Thứ/Ngày/Tháng/Năm.
- `Heading 2`: Buổi + Thứ/Ngày/Tháng/Năm.

## 2. Metadata bắt buộc theo loại tài liệu

### 2.1 Trường bắt buộc chung
- `document_id`
- `title`
- `document_type`
- `source_file_name`
- `folder_path`
- `uploaded_by`
- `uploaded_at`
- `priority`

### 2.2 Trường bắt buộc theo nghiệp vụ pháp lý
- `case_code`
- `legal_domain`
- `issued_by` (nếu là văn bản pháp quy)
- `decision_no` (nếu áp dụng)
- `effective_date` (nếu áp dụng)
- `security_level`

## 3. Vòng đời trạng thái tài liệu
- `NEW_UPLOAD`: mới tải lên, chưa xử lý.
- `PROCESSING`: hệ thống đang chuẩn hóa/OCR/index.
- `ERROR_NEEDS_REPROCESS`: xử lý lỗi, cần xử lý lại.
- `READY`: đã xử lý hợp lệ, sẵn sàng truy vấn.
- `ARCHIVED`: ngừng dùng nhưng giữ lịch sử.

## 4. Quy tắc validation
- Cấm nhảy cấp heading (ví dụ H1 -> H3 mà không có H2).
- Heading path phải nhất quán trong từng phân đoạn nội dung.
- Thiếu metadata bắt buộc => không cho qua bước index.
- Tài liệu ảnh/sơ đồ bắt buộc có đoạn mô tả text đính kèm.

## 5. Checklist uploader trước khi nạp
- Có đủ file gốc và (nếu có) file đã chuẩn hóa.
- Heading trong docx đã kiểm tra bằng Navigation Pane.
- Metadata bắt buộc đã điền đủ.
- Tài liệu được gán đúng thư mục/partition.
- Đã khai báo mức ưu tiên và quyền truy cập.

## 6. Data contract dạng JSON mẫu
```json
{
  "document_id": "DOC-2026-0001",
  "title": "Quy định nội bộ về quy trình tố tụng",
  "document_type": "QUY_DINH",
  "source_file_name": "quy_dinh_to_tung_2026.docx",
  "folder_path": "/phap-che/noi-bo",
  "uploaded_by": "uploader01",
  "uploaded_at": "2026-04-01T10:15:00+07:00",
  "priority": "HIGH",
  "case_code": "CASE-2026-015",
  "legal_domain": "TO_TUNG_DAN_SU",
  "issued_by": "Cong ty Luat Mai Trang",
  "decision_no": "QD-139/2026",
  "effective_date": "2026-04-10",
  "security_level": "INTERNAL"
}
```
