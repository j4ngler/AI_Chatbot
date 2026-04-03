# Document Automation, Signing, Payment Spec (Tuần 17-20)

## 1. Mục tiêu
- Tạo biểu mẫu pháp lý tự động từ dữ liệu vụ việc.
- Xuất văn bản Word/PDF chuẩn định dạng tiếng Việt.
- Tích hợp ký số qua adapter.
- Đưa QR payment thành module có điều kiện, không chặn go-live phase 1.

## 2. Biểu mẫu tự động
- Công nghệ đề xuất: `docxtpl`.
- Bộ template v1:
  - Đơn khởi kiện.
  - Bản khai.
  - Báo cáo tiến độ vụ việc.
- Quy trình:
  1. Chọn template.
  2. Mapping dữ liệu từ `cases` + metadata.
  3. Render preview.
  4. Xuất Word/PDF.

## 3. Xuất văn bản
- Chuẩn font tiếng Việt, kiểm tra lỗi layout khi chuyển PDF.
- Lưu version đã xuất để truy vết.
- Kèm `generated_by`, `generated_at`, `case_code`.

## 4. Ký số adapter
- Thiết kế theo strategy pattern:
  - `MisaEsignAdapter`
  - `VnptCAAdapter`
  - `UsbTokenAdapter`
- Interface chuẩn:
  - `createSigningSession`
  - `signDocument`
  - `verifySignature`
- Fallback nếu nhà cung cấp lỗi:
  - queue retry
  - cảnh báo operator.

## 5. Thanh toán QR (optional gate)
- Điều kiện bật:
  - có nhu cầu nghiệp vụ thực sự.
  - có đối tác thanh toán/API hợp lệ.
- Nếu chưa sẵn sàng: chuyển sang phase tiếp theo, không chặn nghiệm thu phase 1.

## 6. Tiêu chí nghiệm thu GateD
- Sinh được tối thiểu 3 mẫu từ dữ liệu thật.
- Xuất Word/PDF đúng định dạng trên tập mẫu.
- Luồng ký số thử nghiệm thành công end-to-end.
