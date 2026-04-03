# UAT, Hardening, Go-live Spec (Tuần 21-24)

## 1. UAT framework
- Phân nhóm kịch bản:
  - Uploader: upload, normalize, reprocess.
  - Lawyer: hỏi đáp pháp lý có citation.
  - Admin: phân quyền, log, báo cáo.
  - Vận hành: deadline, nhắc việc, dashboard.
- Mỗi test case có:
  - precondition
  - test steps
  - expected result
  - severity (P1/P2/P3)

## 2. Hardening checklist
- Bảo mật:
  - rà soát quyền truy cập theo role.
  - kiểm thử lộ dữ liệu chéo partition.
  - kiểm tra mã hóa in-transit.
- Hiệu năng:
  - stress test query đồng thời.
  - đo latency p95 cho OCR/RAG/chat API.
- Độ ổn định:
  - retry policy.
  - queue backlog handling.
  - backup-restore drill.

## 3. Điều kiện release candidate
- Không còn lỗi P1 mở.
- Lỗi P2 có kế hoạch xử lý rõ ràng.
- KPI cốt lõi đạt ngưỡng tối thiểu.
- Tài liệu vận hành và SOP đã hoàn thiện.

## 4. Đào tạo và bàn giao SOP
- Đào tạo theo vai trò:
  - luật sư
  - trợ lý pháp lý
  - uploader
  - admin hệ thống
- Bộ tài liệu bàn giao:
  - SOP nạp dữ liệu mới.
  - SOP xử lý lỗi OCR/RAG.
  - Runbook sự cố và escalation matrix.

## 5. Go-live và hypercare
- Go-live tuần 24.
- Hypercare 2-4 tuần đầu:
  - war room hàng ngày.
  - theo dõi KPI real-time.
  - ưu tiên xử lý sự cố P1 trong SLA cam kết.

## 6. SLA đề xuất khởi điểm
- P1: phản hồi <= 30 phút, workaround <= 4 giờ.
- P2: phản hồi <= 4 giờ làm việc, xử lý <= 2 ngày.
- P3: xử lý theo backlog sprint kế tiếp.

## 7. Điều kiện GateE
- UAT pass theo checklist.
- SOP và vận hành sau go-live đã ký nhận.
- SLA hỗ trợ đã được thống nhất chính thức.
