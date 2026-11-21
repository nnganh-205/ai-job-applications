import React, { useEffect, useRef } from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import Icon from "../../components/ui/Icon.jsx";
const items = [
  ["/workspace", "Tổng quan", "grid", true],
  ["/workspace/assistant", "Trợ lý AI", "chat"],
  ["/workspace/interviews", "Luyện phỏng vấn", "chat"],
  ["/workspace/applications", "Theo dõi ứng tuyển", "briefcase"],
];
export default function WorkspaceNav() {
  const nav = useRef(null);
  const { pathname } = useLocation();
  useEffect(() => {
    const node = nav.current;
    if (!node) return;
    const reveal = () => {
      const active = node.querySelector('[aria-current="page"]');
      if (active && node.scrollWidth > node.clientWidth)
        node.scrollLeft = Math.max(
          0,
          active.offsetLeft - (node.clientWidth - active.clientWidth) / 2,
        );
    };
    reveal();
    const observer = new ResizeObserver(reveal);
    observer.observe(node);
    return () => observer.disconnect();
  }, [pathname]);
  return (
    <aside className="workspace-sidebar workspace-sidebar-card">
      <nav ref={nav} aria-label="Điều hướng workspace">
        {items.map(([to, label, icon, end]) => (
          <NavLink key={to} to={to} end={!!end}>
            <Icon name={icon} />
            {label}
          </NavLink>
        ))}
      </nav>
      <Link className="sidebar-explore" to="/jobs">
        <Icon name="search" size={17} /> Khám phá việc làm{" "}
        <Icon name="diagonal" size={15} />
      </Link>
    </aside>
  );
}
