import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";

type Customer = { id: string; name: string };
type Contract = {
  id: string;
  title: string;
  contract_type: string;
  status: string;
  amount: string | null;
};

export default function Contracts() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState("");
  const [title, setTitle] = useState("");
  const [ctype, setCtype] = useState("soan_thao");
  const [status, setStatus] = useState("nhap");

  async function load() {
    const [rc, rct] = await Promise.all([apiFetch("/api/erp/customers"), apiFetch("/api/erp/contracts")]);
    if (!rc.ok || !rct.ok) throw new Error("Không tải được dữ liệu.");
    setCustomers(await rc.json());
    setContracts(await rct.json());
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
      const r = await apiFetch("/api/erp/contracts", {
        method: "POST",
        body: JSON.stringify({
          customer_id: customerId,
          title,
          contract_type: ctype,
          status,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      setTitle("");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Xóa hợp đồng?")) return;
    setErr(null);
    try {
      const r = await apiFetch(`/api/erp/contracts/${id}`, { method: "DELETE" });
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
          <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Hợp đồng & soạn thảo</h1>
          <div className="muted">Gắn với khách hàng trong demo.</div>
        </div>
      </div>
      {err ? <p className="error">{err}</p> : null}
      <div className="card">
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>Tạo hợp đồng</h2>
        <form onSubmit={onCreate}>
          <div className="form-row">
            <label className="muted">Khách hàng</label>
            <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} required>
              <option value="">— Chọn —</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label className="muted">Tiêu đề</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="form-row">
            <label className="muted">Loại</label>
            <select value={ctype} onChange={(e) => setCtype(e.target.value)}>
              <option value="soan_thao">Soạn thảo</option>
              <option value="tu_van">Tư vấn</option>
              <option value="khac">Khác</option>
            </select>
          </div>
          <div className="form-row">
            <label className="muted">Trạng thái</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="nhap">Nháp</option>
              <option value="trinh_ky">Trình ký</option>
              <option value="hieu_luc">Hiệu lực</option>
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
              <th>Trạng thái</th>
              <th>Giá trị</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {contracts.map((c) => (
              <tr key={c.id}>
                <td>{c.title}</td>
                <td>{c.contract_type}</td>
                <td>{c.status}</td>
                <td>{c.amount || "—"}</td>
                <td>
                  <button type="button" className="danger" onClick={() => onDelete(c.id)}>
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
