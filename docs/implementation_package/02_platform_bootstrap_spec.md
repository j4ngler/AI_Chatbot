# Platform Bootstrap Spec (Tuần 3-4)

## 1. Mục tiêu
- Có hạ tầng lưu trữ trung tâm ổn định.
- Có phân quyền truy cập theo vai trò và dữ liệu.
- Có CSDL vận hành vụ việc tối thiểu.
- Có cơ chế backup/restore và audit log.

## 2. Hạ tầng tối thiểu
- **Object Storage**: NAS hoặc S3-compatible private.
- **Metadata DB**: PostgreSQL.
- **Vector DB**: Qdrant/pgvector (tùy hạ tầng).
- **Queue**: Redis/RabbitMQ cho job OCR/indexing.
- **Observability**: Prometheus + Grafana + log aggregation.

## 3. RBAC/ABAC đề xuất
- Vai trò: `Admin`, `Uploader`, `Lawyer`, `Paralegal`, `Auditor`.
- Rule tối thiểu:
  - Uploader: upload/preview/reprocess theo partition được cấp.
  - Lawyer: truy vấn và xem tài liệu trong domain được cấp.
  - Auditor: chỉ đọc log và báo cáo.
- ABAC:
  - Ràng buộc theo `security_level`, `legal_domain`, `organization_unit`.

## 4. Lược đồ CSDL tối thiểu
- `users(id, username, role, org_unit, is_active, created_at)`
- `documents(id, title, type, status, folder_id, priority, created_by, created_at)`
- `document_versions(id, document_id, raw_uri, normalized_uri, checksum, processed_at)`
- `cases(id, case_code, client_name, assignee_id, stage, due_date, risk_level, updated_at)`
- `audit_logs(id, actor, action, target_type, target_id, payload, created_at)`

## 5. Chính sách backup
- Backup DB: incremental hàng ngày, full hàng tuần.
- Backup object storage metadata index hàng ngày.
- Giữ bản backup 30/90 ngày theo cấp độ.
- Drill khôi phục: tối thiểu 1 lần/tháng.

## 6. Audit log bắt buộc
- Log sự kiện upload/update/delete/reprocess.
- Log sự kiện chat query và nguồn trả lời.
- Log thay đổi quyền truy cập.
- Không cho chỉnh sửa ngược log bởi user nghiệp vụ.

## 7. Tiêu chí nghiệm thu GateA
- Tạo/sửa/tra cứu hồ sơ vụ việc hoạt động ổn định.
- Phân quyền test pass cho các vai trò chính.
- Backup job chạy thành công và restore mẫu pass.
- Có dashboard giám sát trạng thái dịch vụ.
