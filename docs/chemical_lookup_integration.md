# Chemical Lookup (CoSIng) - Integration Notes

Module này triển khai tra cứu hóa chất từ CoSIng bằng Selenium (adapter theo spec `07_chemical_lookup_cosing_spec.md`), đồng thời chuẩn hóa output để dùng được cho RAG/LLM về sau.

## 1) Kiến trúc & thành phần chính
- `ChemicalLookupService` (`tools/cosing_adapter/chemical_lookup_service.py`): service entrypoint, cache-first.
- `CosingSeleniumWorker` (`tools/cosing_adapter/cosing_worker_selenium.py`): worker chạy Selenium, gồm timeout/retry, dismiss cookie banner, snapshot artifacts.
- `parse_cosing_results_table` (`tools/cosing_adapter/parser.py`): parser HTML table -> `substances[]`.
- `ChemicalCacheStore` (`tools/cosing_adapter/cache_store.py`): cache file TTL 24 giờ theo `query + query_type`.
- `cli.py` (`tools/cosing_adapter/cli.py`): CLI chạy để test nhanh.

## 2) Input contract (theo spec)
```json
{
  "query": "Salicylic Acid",
  "query_type": "NAME_OR_INCI",
  "request_id": "REQ-2026-0001"
}
```

`query_type` hiện hỗ trợ: `NAME_OR_INCI`.

## 3) Output contract (theo spec)
Ví dụ output:
```json
{
  "request_id": "REQ-2026-0001",
  "source": "EU_COSING",
  "substances": [
    {
      "substance_name": "Salicylic Acid",
      "inci_name": "SALICYLIC ACID",
      "cas": "69-72-7",
      "function": "Preservative",
      "restrictions": "See Annex ...",
      "reference_url": "https://ec.europa.eu/growth/tools-databases/cosing/advanced",
      "fetched_at": "2026-06-01T10:30:00+07:00"
    }
  ],
  "status": "OK"
}
```

Trường hợp không có kết quả: adapter trả `substances: []` và `status: OK` (không coi là lỗi worker).

## 4) Cách chạy CLI (test nhanh)

Chạy trong `venv`:
```powershell
.\venv\Scripts\python.exe -m tools.cosing_adapter.cli `
  --request-id "REQ-smoke-001" `
  --query "Salicylic Acid" `
  --query-type NAME_OR_INCI `
  --cache-dir "data\cache\cosing_tmp" `
  --browser chrome
```

Gợi ý:
- Dùng cache-dir riêng khi bạn muốn tránh cache cũ ảnh hưởng test.
- Nếu cần thấy browser, dùng `--no-headless`.

## 5) Vị trí debug artifacts
Khi Selenium/parse gặp lỗi hoặc DOM thay đổi:
- Worker sẽ ghi screenshot + HTML snapshot theo `request_id`
- Thư mục: `data\artifacts\cosing\<request_id>\`
- Ví dụ file: `attempt1_fail_<timestamp>.png|.html`

## 6) Cách tích hợp vào chatbot

**HTTP (demo):** `POST /api/cosing/lookup` với body JSON giống input contract; cần `COSING_ENABLED=true` trong `.env`. Giao diện `demo_web` có tab CoSIng gọi endpoint này.

Khi chatbot nhận biết query thuộc nhóm “tra cứu hóa chất”, có thể gọi service trực tiếp theo contract:

```python
from pathlib import Path
from tools.cosing_adapter.cache_store import ChemicalCacheStore
from tools.cosing_adapter.cosing_worker_selenium import CosingSeleniumWorker, WorkerConfig
from tools.cosing_adapter.chemical_lookup_service import ChemicalLookupService

cache_store = ChemicalCacheStore(cache_dir=Path("data/cache/cosing"), ttl_hours=24)
worker = CosingSeleniumWorker(WorkerConfig(headless=True, browser="chrome"))
service = ChemicalLookupService(cache_store=cache_store, worker=worker)

payload = {
  "query": "Salicylic Acid",
  "query_type": "NAME_OR_INCI",
  "request_id": "REQ-2026-0001"
}

out = service.lookup_payload(payload)
result_dict = out.to_dict()
```

`result_dict` có sẵn `reference_url` và `fetched_at` để đưa vào phần “citation/grounding” khi bạn kết nối RAG/LLM.

## 7) Lưu ý vận hành ban đầu
- CoSIng có cookie consent overlay: worker đã xử lý “Accept cookies” tự động.
- Cache TTL = 24h giúp giảm truy vấn lặp.
- Nếu CoSIng thay đổi DOM, parser/selector có thể cần chỉnh; khi đó xem artifacts theo `request_id`.

