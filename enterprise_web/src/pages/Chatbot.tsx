import { FormEvent, useState } from "react";
import { apiFetch } from "../api";

type ChatResp = {
  answer: string;
  citations: string[];
  sources: { law_number?: string; article_ref?: string }[];
};

export default function Chatbot() {
  const [q, setQ] = useState("");
  const [out, setOut] = useState<ChatResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setOut(null);
    setLoading(true);
    try {
      const r = await apiFetch("/api/erp/chat", {
        method: "POST",
        body: JSON.stringify({ question: q }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error((data as { detail?: string }).detail || JSON.stringify(data));
      }
      setOut(data as ChatResp);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="topbar">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.25rem" }}>Chatbot pháp luật</h1>
          <div className="muted">Trang riêng — gửi kèm ngữ cảnh công ty / người dùng (theo Odoo + JWT).</div>
        </div>
      </div>
      <div className="card">
        <form onSubmit={onSubmit}>
          <div className="form-row">
            <label className="muted">Câu hỏi</label>
            <textarea rows={4} value={q} onChange={(e) => setQ(e.target.value)} required />
          </div>
          <button type="submit" disabled={loading}>
            {loading ? "Đang trả lời…" : "Gửi"}
          </button>
        </form>
      </div>
      {err ? <p className="error">{err}</p> : null}
      {out ? (
        <div className="card">
          <div className="chat-box">{out.answer}</div>
          {out.citations?.length ? (
            <div className="citations">
              <strong>Trích dẫn:</strong> {out.citations.join(" · ")}
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
