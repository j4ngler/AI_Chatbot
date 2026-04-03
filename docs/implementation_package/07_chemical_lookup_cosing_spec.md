# Chemical Lookup Spec (Selenium + CoSIng)

## 1. Mục tiêu
- Tra cứu thông tin chất hóa học từ CoSIng bằng mô phỏng trình duyệt.
- Chuẩn hóa dữ liệu để dùng cho RAG/LLM.
- Hạn chế truy vấn lặp bằng cache.

## 2. Nguồn truy vấn
- URL: `https://ec.europa.eu/growth/tools-databases/cosing/advanced`

## 3. Kiến trúc adapter
- `ChemicalLookupService` nhận query từ chatbot.
- `CosingSeleniumWorker` chạy Selenium.
- `ChemicalCacheStore` lưu kết quả theo khóa query.
- `Parser` bóc tách bảng kết quả -> JSON chuẩn.

## 4. Input contract
```json
{
  "query": "Salicylic Acid",
  "query_type": "NAME_OR_INCI",
  "request_id": "REQ-2026-0001"
}
```

## 5. Output contract
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

## 6. Pseudocode Selenium
```python
def fetch_cosing(query):
    if cache.exists(query):
        return cache.get(query)

    driver.get(COSING_URL)
    wait_for_page_ready()
    input_box = find_input_for_substance()
    input_box.clear()
    input_box.send_keys(query)
    click_search_button()
    wait_result_table()
    rows = parse_result_table()
    data = normalize_rows(rows)
    cache.set(query, data, ttl_hours=24)
    return data
```

## 7. Cơ chế an toàn và ổn định
- Timeout từng bước.
- Retry có backoff (tối đa 3 lần).
- Chụp screenshot khi parse thất bại.
- Monitoring thay đổi DOM selector.
- Circuit breaker nếu nguồn ngoài lỗi liên tục.

## 8. Tích hợp với chatbot
- Nếu query nhận diện là chất hóa học:
  - gọi `ChemicalLookupService`.
  - trả kết quả có nguồn CoSIng.
  - nếu không có dữ liệu, chatbot báo không tìm thấy và gợi ý từ khóa khác.
