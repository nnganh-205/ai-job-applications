import React from 'react';

export default function SearchFilters({ filters, options, onChange, syncing, onSync }) {
  return <div className="search-filters">
    <label className="search-input">Tìm công việc<input type="search" placeholder="Tên công việc, kỹ năng hoặc công ty…" value={filters.q} onChange={event => onChange('q', event.target.value)} /></label>
    {[
      ['location', 'Địa điểm'], ['employment_type', 'Hình thức làm việc'], ['workplace_type', 'Nơi làm việc'],
      ['source_name', 'Nguồn tuyển dụng'],
    ].map(([key, label]) => <label key={key}>{label}<select value={filters[key]} onChange={event => onChange(key, event.target.value)}><option value="">Tất cả</option>{(options[key] || []).map(value => <option key={value} value={value}>{value}</option>)}</select></label>)}
    <button className="refresh-button" disabled={syncing} onClick={onSync}>{syncing ? 'Đang đồng bộ…' : '↻ Refresh tin tuyển dụng'}</button>
    <label className="saved-filter"><input type="checkbox" checked={filters.saved} onChange={event => onChange('saved', event.target.checked)} /> Chỉ việc đã lưu</label>
    <p className="muted filter-note">Tìm kiếm trên dữ liệu đã nhập, gồm nội dung JD. Lương và kinh nghiệm không được tự suy đoán để lọc.</p>
  </div>;
}
