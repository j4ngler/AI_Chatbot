import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { getToken } from "./api";
import Layout from "./Layout";
import Chatbot from "./pages/Chatbot";
import Contracts from "./pages/Contracts";
import Customers from "./pages/Customers";
import Dashboard from "./pages/Dashboard";
import Documents from "./pages/Documents";
import Login from "./pages/Login";
import Notifications from "./pages/Notifications";

function ProtectedLayout() {
  const loc = useLocation();
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<ProtectedLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="customers" element={<Customers />} />
        <Route path="contracts" element={<Contracts />} />
        <Route path="documents" element={<Documents />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="chatbot" element={<Chatbot />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
