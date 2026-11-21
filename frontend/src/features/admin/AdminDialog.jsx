import React, { useEffect, useRef } from 'react';
import Icon from '../../components/ui/Icon.jsx';

export default function AdminDialog({ title, children, onClose, busy, className = '' }) {
  const dialog = useRef(null);
  useEffect(() => { const element = dialog.current; element.showModal(); return () => element.close(); }, []);
  return <dialog className={'crm-dialog ' + className} ref={dialog} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} aria-labelledby="crm-modal-title">
    <div className="crm-dialog-heading"><h2 id="crm-modal-title">{title}</h2><button className="crm-icon-button" type="button" aria-label="Đóng" onClick={onClose} disabled={busy}><Icon name="close" /></button></div>{children}
  </dialog>;
}
