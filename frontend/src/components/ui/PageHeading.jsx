import React from 'react';
export default function PageHeading({eyebrow, title, children, action}) {
  return <header className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{children && <p className="page-description">{children}</p>}</div>{action && <div className="page-heading-action">{action}</div>}</header>;
}
