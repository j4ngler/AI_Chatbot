import { NavLink, Outlet } from "react-router-dom";
import { setToken } from "./api";

const links = [
  { to: "/", label: "Tổng quan", end: true },
  { to: "/customers", label: "Khách hàng" },
  { to: "/contracts", label: "Hợp đồng" },
  { to: "/documents", label: "Hồ sơ / tài liệu" },
  { to: "/notifications", label: "Nhắc việc" },
  { to: "/chatbot", label: "Chatbot pháp luật" },
];

export default function Layout() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          Luật Mai Trang
          <div className="muted" style={{ fontWeight: 400, fontSize: "0.78rem", marginTop: 4 }}>
            Demo quản trị
          </div>
        </div>
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => "nav-item" + (isActive ? " active" : "")}>
            <span className="nav-label">{l.label}</span>
          </NavLink>
        ))}
        <div style={{ flex: 1 }} />
        <button
          type="button"
          className="secondary"
          style={{ margin: "0.35rem" }}
          onClick={() => {
            setToken(null);
            window.location.hash = "#/login";
          }}
        >
          Đăng xuất
        </button>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
