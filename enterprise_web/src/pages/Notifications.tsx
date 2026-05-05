import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";

type Row = {
  id: string;
  title: string;
  body: string | null;
  due_at: string | null;
  priority: string;
  is_read: boolean;
};

export default function Notifications() {
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState("normal");

  async function load() {
    const r = await apiFetch("/api/erp/notifications");
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
      const r = await apiFetch("/api/erp/notifications", {
        method: "POST",
        body: JSON.stringify({ title, body: body || null, priority }),
      });
      if (!r.ok) throw new Error(await r.text());
      setTitle("");
      setBody("");
      await load();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    }
  }

  async function markRead(id: string) {
    setErr(null);
    try {
      const r = await apiFetch(`/api/erp/notifications/${id}/read`, { method: "PATCH" });
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
          <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Nhắc việc / thông báo</h1>
          <div className="muted">Theo dõi việc cần làm trong demo.</div>
        </div>
      </div>
      {err ? <p className="error">{err}</p> : null}
      <div className="card">
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>Tạo nhắc việc</h2>
        <form onSubmit={onCreate}>
          <div className="form-row">
            <label className="muted">Tiêu đề</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="form-row">
            <label className="muted">Nội dung</label>
            <textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
          <div className="form-row">
            <label className="muted">Ưu tiên</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="low">Thấp</option>
              <option value="normal">Bình thường</option>
              <option value="high">Cao</option>
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
              <th>Ưu tiên</th>
              <th>Trạng thái</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <div>{r.title}</div>
                  {r.body ? (
                    <div className="muted" style={{ marginTop: 4 }}>
                      {r.body}
                    </div>
                  ) : null}
                </td>
                <td>{r.priority}</td>
                <td>{r.is_read ? "Đã đọc" : "Chưa đọc"}</td>
                <td>
                  {!r.is_read ? (
                    <button type="button" className="secondary" onClick={() => markRead(r.id)}>
                      Đánh dấu đọc
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
