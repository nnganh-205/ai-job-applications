import React,{useEffect,useMemo,useState} from 'react';
import Icon from '../../components/ui/Icon.jsx';
const names={candidate_pass:'Qua kiểm tra tự động · chưa duyệt',needs_review:'Cần đối chiếu',rejected:'Bị loại theo kiểm tra'};
function DiffText({parts,side}){return <p className="dr-diff-text">{parts.map((p,i)=>p.op==='equal'?<React.Fragment key={i}>{p[side]}</React.Fragment>:p[side]?<mark key={i} className={side==='original'?'removed':'added'}>{p[side]}</mark>:null)}</p>}

export default function ProposalReview({packet,annotation,onChange,checkPair,busy}){
  const [filter,setFilter]=useState('safe_rewrite'),[page,setPage]=useState(0),[checks,setChecks]=useState({}),[working,setWorking]=useState(''),[error,setError]=useState('');
  const pairs=packet.cleaning.pairs,decisions=annotation.pair_decisions||{},catalog=packet.catalog;
  const selected=annotation.cv_plan.selected_refs,items=annotation.cv_plan.review.items;
  const done=p=>['accept','keep','discard'].includes(decisions[p.id]?.action);
  const visible=useMemo(()=>pairs.filter(p=>filter==='all'||filter==='safe_rewrite'&&p.status==='candidate_pass'&&p.proposed_text!==p.original_text||filter==='pending'&&!done(p)&&p.origin!=='source_keep'||filter==='rewrite'&&p.origin!=='source_keep'&&p.proposed_text!==p.original_text||filter==='keep'&&(p.origin==='source_keep'||p.proposed_text===p.original_text)||p.status===filter),[pairs,filter,decisions]);
  useEffect(()=>setPage(p=>Math.min(p,Math.max(0,Math.ceil(visible.length/12)-1))),[visible.length]);
  const rows=visible.slice(page*12,page*12+12);
  function draft(pair){return {source_ref:pair.source_ref||'',proposed_text:pair.proposed_text,reason:pair.reason,semantic_review_confirmed:false,...decisions[pair.id]}}
  function update(pair,patch){const next={...draft(pair),...patch,action:'edit',semantic_review_confirmed:patch.semantic_review_confirmed??false};const ref=decisions[pair.id]?.source_ref||pair.source_ref;const review=['accept','keep'].includes(decisions[pair.id]?.action)?items.filter(i=>i.source_ref!==ref):items;onChange({...annotation,pair_decisions:{...decisions,[pair.id]:next},cv_plan:{...annotation.cv_plan,review:{...annotation.cv_plan.review,items:review}}});setChecks(c=>{const a={...c};delete a[pair.id];return a})}
  function choose(pair,action,data){
    const ref=data.source_ref||pair.source_ref,next={...decisions};
    let review=[...items],keep=[...selected];
    if(action!=='discard'){
      for(const p of pairs){if(p.id!==pair.id&&(p.source_ref===ref||decisions[p.id]?.source_ref===ref))next[p.id]={action:'discard',reason:'Reviewer chọn phương án khác cho cùng bullet nguồn.'}}
      next[pair.id]={...data,source_ref:ref,action};if(!keep.includes(ref))keep.push(ref);
      review=review.filter(i=>i.source_ref!==ref);
      if(action==='accept'&&data.proposed_text!==catalog[ref])review.push({source_ref:ref,original_text:catalog[ref],proposed_text:data.proposed_text,reason:data.reason,severity:(checks[pair.id]?.assessment||pair.assessment).status==='candidate_pass'?'info':'warning'});
    }else{
      next[pair.id]={...data,action:'discard'};
      if(['accept','keep'].includes(decisions[pair.id]?.action))review=review.filter(i=>i.source_ref!==ref);
    }
    onChange({...annotation,pair_decisions:next,cv_plan:{...annotation.cv_plan,selected_refs:keep,review:{...annotation.cv_plan.review,items:review}}});setError('');
  }
  async function verify(pair,accept=false){
    const data=draft(pair);setWorking(pair.id);setError('');
    try{
      const result=await checkPair({proposal_id:pair.id,source_ref:data.source_ref||'',proposed_text:data.proposed_text,reason:data.reason});setChecks(c=>({...c,[pair.id]:result}));
      if(accept){
        if(!data.source_ref)throw Error('Chọn đúng bullet trong entry nguồn trước khi chấp nhận.');
        if(result.runtime_guard_pass===false)throw Error('Bộ kiểm tra runtime chưa chấp nhận câu sửa. Hãy đối chiếu lỗi/cảnh báo và chỉnh lại.');
        if(data.proposed_text!==catalog[data.source_ref]&&!items.some(i=>i.source_ref===data.source_ref)&&items.length>=5)throw Error('Plan đã có 5 câu sửa. Giữ nguyên hoặc bỏ một câu sửa trước khi thêm.');
        if(result.assessment.status==='rejected')throw Error('Còn lỗi dữ kiện hoặc nguồn. Sửa lại, giữ nguyên nguồn hoặc bỏ đề xuất.');
        if(result.assessment.status==='needs_review'&&!data.semantic_review_confirmed)throw Error('Cần bạn kiểm tra ý nghĩa và đánh dấu xác nhận ngữ nghĩa.');
        choose(pair,'accept',data);
      }
    }catch(e){setError(e.message)}finally{setWorking('')}
  }
  const unresolved=pairs.filter(p=>p.origin!=='source_keep'&&!done(p)).length;
  return <section className="dr-proposals"><div className="dr-section-heading"><div><h3>Đối chiếu câu gốc và câu sửa</h3><p>{pairs.length} mục · {unresolved} đề xuất chưa quyết định. candidate_pass chưa phải human-approved.</p></div><span className="dr-chip">{packet.cleaning.version} · {packet.cleaning.guard_version}</span></div>
    <div className="dr-alert">Plan bắt đầu trống. Chọn nội dung theo JD sau khi đối chiếu. Chọn một phương án sẽ bỏ các phương án khác đã gắn cùng bullet; câu chưa gắn chắc nguồn cần quyết định riêng. Mỗi plan có tối đa 5 câu sửa, có thể giữ nguyên các bullet khác.</div>
    <details className="dr-inline-context"><summary>Xem JD trong lúc duyệt câu</summary><p>{packet.job.description}</p></details>
    <div className="dr-proposal-filters"><label>Lọc đề xuất<select value={filter} onChange={e=>{setFilter(e.target.value);setPage(0)}}><option value="safe_rewrite">Câu sửa qua kiểm tra tự động</option><option value="pending">Chưa quyết định (câu đích / gợi ý sửa)</option><option value="rewrite">Câu sửa</option><option value="keep">Giữ nguyên</option><option value="candidate_pass">candidate_pass</option><option value="needs_review">needs_review</option><option value="rejected">rejected</option><option value="all">Tất cả</option></select></label><button disabled={busy||!!working} onClick={()=>{const next={...decisions};for(const p of pairs)if(!done(p))next[p.id]={action:'discard',reason:'Reviewer bỏ các đề xuất còn lại qua thao tác hàng loạt.'};onChange({...annotation,pair_decisions:next})}}>Bỏ các đề xuất còn chưa quyết định trong mẫu</button></div>
    {error&&<div className="dr-alert error" role="alert">{error}</div>}
    {!rows.length&&<p>Không còn mục trong bộ lọc này. Bạn vẫn có thể xem tất cả hoặc chọn bullet trong phần bên dưới.</p>}
    {rows.map(pair=>{const data=draft(pair),result=checks[pair.id],assessment=result?.assessment||pair.assessment,ref=data.source_ref||pair.source_ref,original=catalog[ref]||pair.comparison_original_text||'',diff=result?.diff||pair.diff,context=pair.source_context;
      return <article key={pair.id} className={'dr-proposal-card '+pair.status}><header><strong>{pair.origin==='dataset_target'?'Output dataset':pair.origin==='rule_generated'?'Gợi ý theo quy tắc':'Giữ nguyên nguồn'}</strong><span className="dr-chip">{names[assessment.status]}</span><span className="dr-chip">{done(pair)?({accept:'Đã chọn câu sửa · nháp',keep:'Đã chọn giữ nguyên · nháp',discard:'Đã bỏ đề xuất'}[decisions[pair.id].action]):'Chưa quyết định'}</span></header>
      {context&&<p className="dr-entry-context"><strong>{context.title}</strong>{context.subtitle&&<> · {context.subtitle}</>}{context.period&&<> · {context.period}</>}<small>{context.entry_id}</small></p>}
      {pair.source_ref?<p className="dr-source-ref">Nguồn: <code>{pair.source_ref}</code></p>:<label>Gắn nguồn thủ công trong cùng entry (chưa tự xác nhận)<select value={data.source_ref||''} disabled={!pair.allowed_source_refs.length||busy||!!working} onChange={e=>update(pair,{source_ref:e.target.value})}><option value="">Chưa gắn chắc nguồn</option>{pair.allowed_source_refs.map(r=><option key={r} value={r}>{r} · {catalog[r].slice(0,100)}</option>)}</select></label>}
      {!ref&&<p className="dr-unbound">Đối chiếu tạm, chưa có source_ref được xác nhận. Các kiểm tra dưới đây chỉ có giá trị theo đoạn nguồn đang so sánh.</p>}
      <div className="dr-pair-columns"><section><h4>{ref?'Câu nguồn · nguyên văn':'Đoạn nguồn đang so sánh'}</h4><p className="dr-pair-original">{original||'Chưa xác định được nguồn. Hãy bỏ đề xuất hoặc viết từ bullet nguồn.'}</p><DiffText parts={diff} side="original"/></section><section><h4>Câu sửa đề xuất</h4><textarea id={'proposal-'+pair.id} rows={4} value={data.proposed_text} onChange={e=>update(pair,{proposed_text:e.target.value})} aria-label="Câu sửa đề xuất"/><DiffText parts={diff} side="proposed"/></section></div>
      {!result&&data.action==='edit'&&<p>Phần tô khác biệt bên trên thuộc bản kiểm tra gần nhất. Bấm “Kiểm tra câu sửa” để cập nhật.</p>}
      <label>Lý do<textarea rows={2} value={data.reason||''} onChange={e=>update(pair,{reason:e.target.value})}/></label>
      <details className="dr-pair-checks"><summary>Kiểm tra: {assessment.checks.filter(c=>c.status==='pass').length} qua · {assessment.reason_codes.length} cảnh báo/lỗi</summary><ul>{assessment.checks.map((c,i)=><li key={i} className={c.status}><b>{c.status==='pass'?'✓':c.status==='fail'?'×':'!'} {c.name}</b>{c.status!=='pass'&&<pre>{JSON.stringify(c.details)}</pre>}</li>)}</ul>{assessment.binding_unconfirmed&&<p>Chưa gắn nguồn: lỗi/cảnh báo nội dung là so sánh có điều kiện, chưa kết luận chắc câu đích sai.</p>}</details>
      <label className="dr-check"><input type="checkbox" checked={!!data.semantic_review_confirmed} onChange={e=>update(pair,{semantic_review_confirmed:e.target.checked})}/>Tôi đã đối chiếu ý nghĩa, chủ thể và mức độ khẳng định của câu sửa chưa chắc chắn.</label>
      <div className="dr-actions"><button disabled={busy||!!working} onClick={()=>document.getElementById('proposal-'+pair.id)?.focus()}>Sửa lại</button><button disabled={busy||!!working} onClick={()=>verify(pair)}>Kiểm tra câu sửa</button><button disabled={busy||!!working||!ref} onClick={()=>choose(pair,'keep',{...data,proposed_text:catalog[ref],reason:data.reason||'Reviewer giữ nguyên câu nguồn.'})}>Giữ nguyên</button><button disabled={busy||!!working||!ref} onClick={()=>verify(pair,true)}><Icon name="check" size={15}/> Chấp nhận câu sửa (nháp)</button><button disabled={busy||!!working} onClick={()=>choose(pair,'discard',data)}>Bỏ đề xuất</button></div>
      </article>})}
    <div className="dr-pagination"><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>← Trước</button><span>{visible.length?`${page+1} / ${Math.ceil(visible.length/12)}`:'0 mục'}</span><button disabled={(page+1)*12>=visible.length} onClick={()=>setPage(p=>p+1)}>Tiếp →</button></div>
    <p className="dr-proposal-limit">Đây là plan bullet một phần. Summary, thông tin liên hệ và thay đổi metadata của output gốc không được âm thầm chuyển thành câu sửa CV.</p>
  </section>
}
