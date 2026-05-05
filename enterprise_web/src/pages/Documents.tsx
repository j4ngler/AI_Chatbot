import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";

type Doc = {
  id: string;
  title: string;
  doc_type: string;
  external_url: string | null;
};
type Customer = { id: string; name: string };
type Contract = { id: string; title: string };

export default function Documents() {
  const [rows, setRows] = useState<Doc[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("tai_lieu");
  const [url, setUrl] = useState("");
  const [cust, setCust] = useState("");
  const [ctr, setCtr] = useState("");

  async function load() {
    const [d, c, ct] = await Promise.all([
      apiFetch("/api/erp/documents"),
      apiFetch("/api/erp/customers"),
      apiFetch("/api/erp/contracts"),
    ]);
    if (!d.ok || !c.ok || !ct.ok) throw new Error("Không tải được dữ liệu.");
    setRows(await d.json());
    setCustomers(await c.json());
    setContracts(await ct.json());
  }

  useEffect(() => {
    (async () => {
      try {
        await load();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const r = await apiFetch("/api/erp/documents", {
        method: "POST",
        body: JSON.stringify({
          title,
          doc_type: docType,
          external_url: url || null,
          customer_id: cust || null,
          contract_id: ctr || null,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      setTitle("");
      setUrl("");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Xóa tài liệu?")) return;
    setErr(null);
    try {
      const r = await apiFetch(`/api/erp/documents/${id}`, { method: "DELETE" });
      if (!r.ok) throw new Error(await r.text());
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Hồ sơ / tài liệu</h1>
          <div className="muted">Liên kết tùy chọn tới khách hàng hoặc hợp đồng.</div>
        </div>
      </div>
      {err ? <p className="error">{err}</p> : null}
      <div className="card">
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>Thêm tài liệu</h2>
        <form onSubmit={onCreate}>
          <div className="form-row">
            <label className="muted">Tiêu đề</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="form-row">
            <label className="muted">Loại</label>
            <select value={docType} onChange={(e) => setDocType(e.target.value)}>
              <option value="tai_lieu">Tài liệu</option>
              <option value="chung_cu">Chứng cứ / phụ lục</option>
              <option value="khac">Khác</option>
            </select>
          </div>
          <div className="form-row">
            <label className="muted">URL (Drive, v.v.)</label>
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
          </div>
          <div className="form-row">
            <label className="muted">Khách hàng</label>
            <select value={cust} onChange={(e) => setCust(e.target.value)}>
              <option value="">—</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label className="muted">Hợp đồng</label>
            <select value={ctr} onChange={(e) => setCtr(e.target.value)}>
              <option value="">—</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </div>
          <button type="submit">Lưu</button>
        </form>
      </div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Tiêu đề</th>
              <th>Loại</th>
              <th>Liên kết</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.title}</td>
                <td>{r.doc_type}</td>
                <td>
                  {r.external_url ? (
                    <a href={r.external_url} target="_blank" rel="noreferrer">
                      Mở
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  <button type="button" className="danger" onClick={() => onDelete(r.id)}>
                    Xóa
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
