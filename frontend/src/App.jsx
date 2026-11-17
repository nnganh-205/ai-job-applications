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
import Dashboard from "./pages/Dashboard.jsx";
import WorkspacePage, {
  CVGenerationPage,
} from "./features/workspace/WorkspacePage.jsx";
import InterviewPage from "./features/interviews/InterviewPage.jsx";
import ApplicationsPage from "./features/applications/ApplicationsPage.jsx";
import HomePage from "./features/home/HomePage.jsx";
import EventsPage from "./features/events/EventsPage.jsx";
import TemplateGallery from "./features/templates/TemplateGallery.jsx";
import ResumeLibrary from "./features/resumes/ResumeLibrary.jsx";
import ResumeEditor from "./features/resumes/ResumeEditor.jsx";
import ProfileEditor from "./features/profile/ProfileEditor.jsx";
import ProfileConversation from "./features/profile/ProfileConversation.jsx";
import ImportProfile from "./features/profile/ImportProfile.jsx";

function WorkspaceApp() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isWorkspace = pathname.startsWith("/workspace");
  const isHome = pathname === "/";
  const hasAurora = /^\/(jobs|templates|events)(\/|$)/.test(pathname) || isWorkspace;
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname]);
  const [profileId, setProfileId] = useState(() => {
    try {
      return localStorage.getItem("kltn.confirmedProfileId") || null;
    } catch {
      return null;
    }
  });
  function confirmed(id) {
    setProfileId(id);
    try {
      localStorage.setItem("kltn.confirmedProfileId", id);
    } catch {}
  }
  return (
    <div className={isHome ? "landing-shell" : hasAurora ? "aurora-shell" : undefined}>
      {(isHome || hasAurora) && <div className="aurora-backdrop" aria-hidden="true" />}
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
          <Routes>
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
            <Route path="/events" element={<EventsPage />} />
            <Route
              path="/jobs"
              element={
                <main className="dashboard-shell">
                  <Dashboard
                    confirmedProfileId={profileId}
                    onOpenProfile={() => navigate("/workspace/resumes")}
                    onProfileConfirmed={confirmed}
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
                    onOpenProfile={() => navigate("/workspace/resumes")}
                    onProfileConfirmed={confirmed}
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
              element={<Navigate replace to="/workspace/resumes" />}
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
            <Route path="/workspace/resumes" element={<ResumeLibrary />} />
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
          </Routes>
        </div>
      </div>
      {!isWorkspace && <footer className="site-footer">
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
                <Link to="/events">Sự kiện nghề nghiệp</Link>
              </div>
              <div>
                <strong>Không gian của bạn</strong>
                <Link to="/workspace/resumes">Thư viện CV</Link>
                <Link to="/workspace/resumes">CV của tôi</Link>
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
const router = createBrowserRouter([{ path: "*", element: <WorkspaceApp /> }]);
export default function App() {
  return <RouterProvider router={router} />;
}
