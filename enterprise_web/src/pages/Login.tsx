import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setToken } from "../api";

export default function Login() {
  const nav = useNavigate();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [db, setDb] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      if (typeof window !== "undefined" && db.trim()) {
        sessionStorage.setItem("luat_maitrang_odoo_db_hint", db.trim());
      }
      const r = await fetch("/api/erp/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: login.trim(), password }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error((data as { detail?: string }).detail || "Đăng nhập thất bại.");
      }
      setToken((data as { access_token: string }).access_token);
      nav("/", { replace: true });
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1 style={{ margin: "0 0 0.35rem", fontSize: "1.15rem" }}>Đăng nhập</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Xác thực qua Odoo (JSON-RPC). Dev không Odoo: bật ERP_DEMO_AUTH_BYPASS trong .env.
        </p>
        <form onSubmit={onSubmit}>
          <div className="form-row">
            <label className="muted">Tên đăng nhập Odoo</label>
            <input value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" required />
          </div>
          <div className="form-row">
            <label className="muted">Mật khẩu</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <div className="form-row">
            <label className="muted">Gợi ý DB Odoo (chỉ hiển thị — cấu hình thật ở ODOO_DB server)</label>
            <input value={db} onChange={(e) => setDb(e.target.value)} placeholder="vd: mycompany" />
          </div>
          {err ? <p className="error">{err}</p> : null}
          <div className="form-actions">
            <button type="submit" disabled={loading}>
              {loading ? "Đang đăng nhập…" : "Đăng nhập"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
