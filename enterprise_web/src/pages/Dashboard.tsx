import { useEffect, useState } from "react";
import { apiFetch } from "../api";

type Dash = {
  counts: Record<string, number>;
  unread_notifications: number;
  recent_customers: { id: string; name: string }[];
  recent_contracts: { id: string; title: string }[];
};

export default function Dashboard() {
  const [data, setData] = useState<Dash | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await apiFetch("/api/erp/dashboard");
        if (!r.ok) throw new Error(await r.text());
        setData(await r.json());
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  async function download(path: string, name: string) {
    const r = await apiFetch(path);
    if (!r.ok) {
      alert(await r.text());
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Tổng quan</h1>
          <div className="muted">Dashboard phong cách gọn — dữ liệu lưu PostgreSQL (demo).</div>
        </div>
        <div className="form-actions" style={{ margin: 0 }}>
          <button type="button" className="secondary" onClick={() => download("/api/erp/export/customers.xlsx", "khach-hang.xlsx")}>
            Xuất Excel (KH)
          </button>
          <button type="button" className="secondary" onClick={() => download("/api/erp/export/dashboard.pdf", "dashboard.pdf")}>
            Xuất PDF
          </button>
        </div>
      </div>
      {err ? <p className="error">{err}</p> : null}
      {!data ? (
        <p className="muted">Đang tải…</p>
      ) : (
        <>
          <div className="grid">
            {Object.entries(data.counts).map(([k, v]) => (
              <div key={k} className="stat">
                <span className="muted" style={{ fontSize: "0.78rem" }}>
                  {k}
                </span>
                <b>{v}</b>
              </div>
            ))}
            <div className="stat">
              <span className="muted" style={{ fontSize: "0.78rem" }}>
                Thông báo chưa đọc
              </span>
              <b>{data.unread_notifications}</b>
            </div>
          </div>
          <div className="card" style={{ marginTop: "0.85rem" }}>
            <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>Khách hàng gần đây</h2>
            <table>
              <thead>
                <tr>
                  <th>Tên</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_customers.length === 0 ? (
                  <tr>
                    <td className="muted">Chưa có dữ liệu</td>
                  </tr>
                ) : (
                  data.recent_customers.map((c) => (
                    <tr key={c.id}>
                      <td>{c.name}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="card">
            <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>Hợp đồng gần đây</h2>
            <table>
              <thead>
                <tr>
                  <th>Tiêu đề</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_contracts.length === 0 ? (
                  <tr>
                    <td className="muted">Chưa có dữ liệu</td>
                  </tr>
                ) : (
                  data.recent_contracts.map((c) => (
                    <tr key={c.id}>
                      <td>{c.title}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
