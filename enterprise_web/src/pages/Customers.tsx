import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";

type Row = {
  id: string;
  name: string;
  tax_id: string | null;
  email: string | null;
  phone: string | null;
  status: string;
};

export default function Customers() {
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  async function load() {
    const r = await apiFetch("/api/erp/customers");
    if (!r.ok) throw new Error(await r.text());
    setRows(await r.json());
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
      const r = await apiFetch("/api/erp/customers", {
        method: "POST",
        body: JSON.stringify({ name, email: email || null, phone: phone || null }),
      });
      if (!r.ok) throw new Error(await r.text());
      setName("");
      setEmail("");
      setPhone("");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Xóa khách hàng này?")) return;
    setErr(null);
    try {
      const r = await apiFetch(`/api/erp/customers/${id}`, { method: "DELETE" });
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
          <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Khách hàng / doanh nghiệp</h1>
          <div className="muted">CRUD tối thiểu cho demo.</div>
        </div>
      </div>
      {err ? <p className="error">{err}</p> : null}
      <div className="card">
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>Thêm nhanh</h2>
        <form onSubmit={onCreate}>
          <div className="form-row">
            <label className="muted">Tên</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="form-row">
            <label className="muted">Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
          </div>
          <div className="form-row">
            <label className="muted">Điện thoại</label>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <button type="submit">Lưu</button>
        </form>
      </div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Tên</th>
              <th>Email</th>
              <th>Điện thoại</th>
              <th>Trạng thái</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>{r.email || "—"}</td>
                <td>{r.phone || "—"}</td>
                <td>{r.status}</td>
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
