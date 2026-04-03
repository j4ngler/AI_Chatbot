# Workflow & Operations Spec (Tuần 13-16)

## 1. Workflow vụ việc chuẩn
- `OPEN`: tạo vụ việc mới.
- `ASSIGNED`: phân công luật sư/phụ trách.
- `IN_PROGRESS`: đang xử lý.
- `WAITING_EXTERNAL`: chờ đối tác/tòa án/khách hàng.
- `REVIEW`: chờ rà soát nội bộ.
- `CLOSED`: hoàn tất.

## 2. Dữ liệu bắt buộc cho mỗi vụ việc
- `case_code`
- `client_name`
- `legal_domain`
- `assigned_to`
- `deadline_main`
- `status`
- `priority`
- `risk_level`

## 3. Deadline engine
- Tạo lịch nhắc theo 3 mốc:
  - T-7 ngày
  - T-3 ngày
  - T-1 ngày
- Quá hạn: gửi cảnh báo đỏ + escalte cho quản lý.

## 4. Notification channels
- Email (bắt buộc).
- Zalo hoặc Telegram (tùy hạ tầng khách hàng).
- Rule chống spam:
  - gộp thông báo trong cửa sổ 15 phút.
  - idempotency theo `case_code + deadline + channel`.

## 5. Lịch pháp lý
- Thực thể: `hearing_date`, `court_session`, `internal_meeting`.
- Mỗi lịch gắn với `case_code` và danh sách người liên quan.
- Hỗ trợ tạo/sửa/hủy + lưu lịch sử thay đổi.

## 6. Dashboard v1
- Tổng việc theo trạng thái.
- Việc đến hạn trong 7 ngày.
- Việc quá hạn theo cá nhân/nhóm.
- Tải công việc theo luật sư.
- Tỷ lệ cập nhật metadata đúng hạn.

## 7. Tiêu chí nghiệm thu
- Luồng tạo -> phân công -> cập nhật -> đóng vụ chạy ổn.
- Cảnh báo deadline gửi đúng mốc.
- Dashboard phản ánh đúng dữ liệu CSDL.
