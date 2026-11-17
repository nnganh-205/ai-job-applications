export function formatSalary(job) {
  const low=job.salary_min,high=job.salary_max;
  if(job.salary_currency&&job.salary_period&&(low!=null||high!=null)) {
    const number=value=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:20}).format(value);
    const bounds=low!=null&&high!=null ? low===high?number(low):`${number(low)} – ${number(high)}` : low!=null?`Từ ${number(low)}`:`Đến ${number(high)}`;
    const period={hour:'giờ',day:'ngày',week:'tuần',month:'tháng',year:'năm'}[job.salary_period]||job.salary_period;
    return `${bounds} ${job.salary_currency==='VND'?'₫':job.salary_currency} / ${period}`;
  }
  if (/th[oỏ][aả]\s*thuận/i.test(job.salary || '')) return 'Thỏa thuận';
  return job.salary||'Lương chưa công bố';
}

export function employmentLabel(value) {
  return ({'full-time':'Toàn thời gian','FULL_TIME':'Toàn thời gian','Full-time':'Toàn thời gian','part-time':'Bán thời gian','internship':'Thực tập','contract':'Hợp đồng'})[value] || value || 'Chưa công bố hình thức';
}
