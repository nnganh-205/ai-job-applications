import ResumeChat from "./features/resumes/ResumeChat.jsx";
import ResumeNew, { LegacyResumeForm } from "./features/resumes/ResumeNew.jsx";
import React, { useState, useEffect } from "react";
import {
  createBrowserRouter,
  RouterProvider,
  Routes,
  Route,
  Link,
  useNavigate,
  useLocation,
  Navigate,
} from "react-router-dom";
import Icon from "./components/ui/Icon.jsx";
import WorkspaceNav from "./app/layouts/WorkspaceNav.jsx";
import SiteHeader from "./app/layouts/SiteHeader.jsx";
import AssistantPage from "./features/assistant/AssistantPage.jsx";
import Dashboard from "./features/jobs/Dashboard.jsx";
import WorkspacePage, {
  CVGenerationPage,
} from "./features/workspace/WorkspacePage.jsx";
import InterviewPage from "./features/interviews/InterviewPage.jsx";
import ApplicationsPage from "./features/applications/ApplicationsPage.jsx";
import HomePage from "./features/home/HomePage.jsx";
import AdminPage from "./features/admin/AdminPage.jsx";
import TemplateGallery from "./features/templates/TemplateGallery.jsx";
import ResumeEditor from "./features/resumes/ResumeEditor.jsx";
import ProfileEditor from "./features/profile/ProfileEditor.jsx";
import ProfileConversation from "./features/profile/ProfileConversation.jsx";
import ImportProfile from "./features/profile/ImportProfile.jsx";
import AuthPage from "./features/auth/AuthPage.jsx";
import { AuthProvider, useAuth } from "./features/auth/AuthContext.jsx";
import { accountStorage } from "./lib/accountStorage.js";

function AccountGate({ children }) {
  const { user, ready, error, requiresLogin, refresh } = useAuth();
  const location = useLocation();
  const adminPage = /^\/admin(\/|$)/.test(location.pathname);
  const privatePage = location.pathname.startsWith('/workspace') || adminPage;
  const authPage = ['/login', '/register'].includes(location.pathname);
  if ((privatePage && !ready) || (privatePage && error)) return <main className="auth-loading" aria-live="polite"><Icon name="shield" size={28} /><p>{error || 'Đang mở không gian của bạn…'}</p>{error && <button type="button" onClick={() => refresh()}>Thử lại</button>}</main>;
  if ((privatePage && !user) || (requiresLogin && !authPage)) {
    return <Navigate replace to={`/login?next=${encodeURIComponent(location.pathname + location.search + location.hash)}`} />;
  }
  if (adminPage && user?.role !== 'admin') return <main className="auth-loading"><Icon name="shield" size={28} /><h1>Không có quyền truy cập</h1><p>Trang này chỉ dành cho quản trị viên.</p><Link to="/workspace">Về không gian của tôi</Link></main>;
  return children;
}

function AccountWorkspace() {
  const { user } = useAuth();
  return <WorkspaceApp key={user?.user_id || 'guest'} />;
}

function WorkspaceApp() {
  const navigate = useNavigate();
  const { pathname, search, hash } = useLocation();
  const isWorkspace = pathname.startsWith("/workspace");
  const isHome = pathname === "/";
  const isAuth = pathname === '/register' || pathname === '/login';
  const hasAurora = /^\/(jobs|templates)(\/|$)/.test(pathname) || isWorkspace;
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    if (!isAuth && !/^\/admin(\/|$)/.test(pathname)) document.title = 'CV & Cơ hội nghề nghiệp';
  }, [pathname]);
  const [profileId, setProfileId] = useState(() => {
    try {
      return accountStorage.getItem("kltn.confirmedProfileId") || null;
    } catch {
      return null;
    }
  });
  function confirmed(id) {
    setProfileId(id);
    try {
      accountStorage.setItem("kltn.confirmedProfileId", id);
    } catch {}
  }
  if (/^\/admin(\/|$)/.test(pathname)) return <AccountGate><AdminPage /></AccountGate>;
  return (
    <div className={isAuth ? 'landing-shell auth-shell' : isHome ? "landing-shell" : hasAurora ? "aurora-shell" : undefined}>
      {(isHome || isAuth || hasAurora) && <div className="aurora-backdrop" aria-hidden="true" />}
      <a className="skip-link" href="#page-content">
        Đến nội dung chính
      </a>
      <SiteHeader />
      <div className={isWorkspace ? "workspace-layout" : "site-content"}>
        {isWorkspace && <WorkspaceNav />}
        <div
          id="page-content"
          tabIndex={-1}
          className={isWorkspace ? "workspace-content" : "public-content"}
        >
          <AccountGate><Routes>
            <Route path="/register" element={<AuthPage mode="register" />} />
            <Route path="/login" element={<AuthPage mode="login" />} />
            <Route path="/workspace/data-review" element={<Navigate replace to="/workspace/assistant" />} />
            <Route path="/workspace/assistant" element={<AssistantPage />} />
            <Route
              path="/workspace/assistant/:id"
              element={<AssistantPage />}
            />
            <Route path="/workspace/interviews" element={<InterviewPage />} />
            <Route
              path="/workspace/interviews/:id"
              element={<InterviewPage />}
            />
            <Route
              path="/workspace/applications"
              element={<ApplicationsPage />}
            />
            <Route path="/templates" element={<TemplateGallery />} />
            <Route path="/" element={<HomePage />} />
            <Route path="/events" element={<Navigate replace to="/" />} />
            <Route
              path="/jobs"
              element={
                <main className="dashboard-shell">
                  <Dashboard
                    confirmedProfileId={profileId}
                  />
                </main>
              }
            />
            <Route
              path="/jobs/:id"
              element={
                <main className="dashboard-shell">
                  <Dashboard
                    confirmedProfileId={profileId}
                  />
                </main>
              }
            />
            <Route
              path="/workspace/profile/conversation/:id"
              element={<ProfileConversation onConfirmed={confirmed} />}
            />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route
              path="/workspace/profile"
              element={<Navigate replace to="/workspace" />}
            />
            <Route
              path="/workspace/profile/:id/:section"
              element={<LegacyResumeForm />}
            />
            <Route
              path="/workspace/import"
              element={<ImportProfile onConfirmed={confirmed} />}
            />
            <Route
              path="/workspace/resumes/generate"
              element={<CVGenerationPage />}
            />
            <Route
              path="/workspace/resumes/chat"
              element={<ResumeChat onConfirmed={confirmed} />}
            />
            <Route path="/workspace/resumes/new" element={<ResumeNew />} />
            <Route
              path="/workspace/resumes/new/:id"
              element={<ProfileEditor onConfirmed={confirmed} />}
            />
            <Route path="/workspace/resumes" element={<Navigate replace to={{ pathname: "/workspace", search, hash }} />} />
            <Route
              path="/workspace/resumes/:id/edit"
              element={<ResumeEditor />}
            />
            <Route
              path="*"
              element={
                <main>
                  <h1>Không tìm thấy trang</h1>
                  <Link to="/">Về trang chủ</Link>
                </main>
              }
            />
          </Routes></AccountGate>
        </div>
      </div>
      {!isAuth && !isWorkspace && !pathname.startsWith("/jobs") && <footer className="site-footer">
        {isWorkspace ? (
          null
        ) : (
          <>
            <div className="footer-top">
              <div>
                <p>
                  Một không gian cho hành trình nghề nghiệp.
                  <br />
                  Bắt đầu từ những điều bạn đã làm.
                </p>
              </div>
              <div>
                <strong>Khám phá</strong>
                <Link to="/jobs">Tìm việc làm</Link>
                <Link to="/templates">Thư viện mẫu CV</Link>
              </div>
              <div>
                <strong>Không gian của bạn</strong>
                <Link to="/workspace">CV của tôi</Link>
                <Link to="/workspace/assistant">Trợ lý AI</Link>
              </div>
            </div>
            <div className="footer-bottom">
              <span>Thông tin thật. Lựa chọn của bạn.</span>
            </div>
          </>
        )}
      </footer>}
    </div>
  );
}
const router = createBrowserRouter([{ path: "*", element: <AccountWorkspace /> }]);
export default function App() {
  return <AuthProvider><RouterProvider router={router} /></AuthProvider>;
}
