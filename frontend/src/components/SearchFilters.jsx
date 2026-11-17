import React from 'react';
import Icon from './ui/Icon.jsx';
export default function SearchFilters({ filters, options, onChange, onReset, syncing, onSync }) {
  const advanced = ['employment_type','workplace_type','industry','experience_level','salary_min'];
  const activeCount = advanced.filter(k=>filters[k]).length;
  const choice = (key,label) => <label key={key}>{label}<select name={key} value={filters[key]} onChange={e=>onChange(key,e.target.value)}><option value="">Tất cả</option>{(options[key] || []).map(value=><option key={value} value={value}>{value}</option>)}</select></label>;
  return <section className="search-filters" aria-label="Tìm kiếm và bộ lọc">
    <div className="search-primary">
      <label className="search-input"><span>Từ khóa tìm kiếm</span><div className="search-field"><Icon name="search"/><input name="q" type="search" placeholder="Vị trí, kỹ năng hoặc công ty bạn quan tâm…" value={filters.q} onChange={e=>onChange('q',e.target.value)}/></div></label>
      {choice('location','Địa điểm')}{choice('source_name','Nguồn tuyển dụng')}
    </div>
    <div className="filter-toolbar"><label className="saved-filter"><input name="saved" type="checkbox" checked={filters.saved} onChange={e=>onChange('saved',e.target.checked)}/><Icon name="bookmark" size={15}/> Việc đã lưu</label><span className="filter-live-note">Kết quả cập nhật khi bạn thay đổi bộ lọc</span><button type="button" className="text-button" onClick={onReset}>Đặt lại</button><button className="secondary-button refresh-button" disabled={syncing} onClick={onSync}><Icon name="refresh" size={15}/>{syncing?'Đang cập nhật…':'Cập nhật tin'}</button></div>
    <details className="advanced-filters" open={activeCount ? true : undefined}>
      <summary><Icon name="filter" size={16}/> Bộ lọc chi tiết {activeCount>0&&<span className="filter-count">{activeCount}</span>}</summary>
      <div className="advanced-filter-fields">{choice('employment_type','Hình thức làm việc')}{choice('workplace_type','Môi trường làm việc')}{choice('industry','Ngành nghề')}{choice('experience_level','Kinh nghiệm')}
        <label>Lương công bố từ<input name="salary_min" type="number" min="0" step="any" placeholder="Không giới hạn" value={filters.salary_min} onChange={e=>onChange('salary_min',e.target.value)}/></label>
        <label>Tiền tệ<select name="salary_currency" value={filters.salary_currency} onChange={e=>onChange('salary_currency',e.target.value)}>{['VND','USD','EUR','GBP','SGD','AUD','CAD','JPY'].map(c=><option key={c}>{c}</option>)}</select></label>
        <label>Kỳ lương<select name="salary_period" value={filters.salary_period} onChange={e=>onChange('salary_period',e.target.value)}>{[['month','Tháng'],['year','Năm'],['hour','Giờ'],['day','Ngày'],['week','Tuần']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
      </div><p className="filter-note">Ngành, kinh nghiệm và lương dùng thông tin nguồn công bố. Lương chỉ so sánh cùng tiền tệ và kỳ lương; tin thiếu dữ liệu sẽ không khớp bộ lọc đó.</p>
    </details>
  </section>;
}
