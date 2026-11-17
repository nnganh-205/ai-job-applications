import React from 'react';
import Icon from './Icon.jsx';
export function EmptyState({ title, children, action, icon='file' }) {
  return <div className="empty-state"><span className="empty-state-icon"><Icon name={icon} size={28}/></span><h2>{title}</h2><p>{children}</p>{action}</div>;
}
export function JobSkeletons() {
  return <div role="status" aria-label="Đang tải công việc" className="job-skeletons">{Array.from({length:4},(_,i)=><div className="skeleton-card" key={i} aria-hidden="true"><div className="skeleton-line wide"/><div className="skeleton-line"/><div className="skeleton-line short"/></div>)}</div>;
}
