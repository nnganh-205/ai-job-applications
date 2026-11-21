import React from 'react';
export default function PageHeading({title, children, action}) {
  return <header className="page-heading"><div><h1>{title}</h1>{children && <p className="page-description">{children}</p>}</div>{action && <div className="page-heading-action">{action}</div>}</header>;
}
