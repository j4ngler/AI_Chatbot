# Roadmap 24 Tuần (Đã chỉnh sửa để bao phủ đầy đủ)

## Tuần 1-4
- **T1**: Kickoff, chốt MVP, chốt kiến trúc hybrid, thống nhất phase 1/2.
- **T2**: Chuẩn hóa dữ liệu + metadata contract + checklist uploader.
- **T3**: Kho lưu trữ, phân quyền, backup baseline.
- **T4**: CSDL vụ việc v0.1 + audit log + GateA.

## Tuần 5-8
- **T5**: OCR benchmark set + tiêu chí đo.
- **T6**: OCR pipeline v1.
- **T7**: Tối ưu scan xấu + HITL cho hồ sơ nhạy cảm.
- **T8**: Đồng bộ OCR vào tra cứu nội bộ + GateB.

## Tuần 9-12
- **T9**: Chuẩn hóa kho tri thức pháp lý (heading/chunk/tag).
- **T10**: Retriever + vector index + kết nối LLM.
- **T11**: Chatbot pháp lý v1, citation bắt buộc, no-source rejection.
- **T12**: Đánh giá chất lượng RAG + tinh chỉnh + GateC.

## Tuần 13-16
- **T13**: Chuẩn hóa workflow mở vụ -> đóng vụ.
- **T14**: Deadline engine + nhắc việc đa kênh.
- **T15**: Lịch pháp lý.
- **T16**: Dashboard quản trị deadline/tải công việc.

## Tuần 17-20
- **T17**: Tích hợp ký số (mock/real adapter theo readiness).
- **T18**: Thanh toán QR (tùy chọn, không chặn nghiệm thu phase 1).
- **T19**: Template biểu mẫu pháp lý tự động.
- **T20**: Xuất Word/PDF + kiểm tra định dạng + GateD.

## Tuần 21-24
- **T21**: UAT theo phòng ban + phân loại lỗi P1/P2.
- **T22**: Hardening bảo mật/hiệu năng + regression.
- **T23**: Đào tạo theo vai trò + SOP.
- **T24**: Go-live phase 1 + SLA + GateE.

## Hạng mục bổ sung bao phủ dự án
- Evaluation harness OCR/RAG chạy theo tháng.
- DR drill backup/restore định kỳ.
- Hypercare sau go-live 2-4 tuần.
- CoSIng selenium adapter cho tra cứu hóa chất.
