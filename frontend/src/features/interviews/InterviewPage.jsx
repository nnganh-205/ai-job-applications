import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Icon from '../../components/ui/Icon.jsx';
import PageHeading from '../../components/ui/PageHeading.jsx';
import {EmptyState} from '../../components/ui/PageState.jsx';
import { request } from '../../services/api.js';
import { getTask, retryTask, taskLabel } from '../../services/tasks.js';

const labels = { relevance: 'Đúng trọng tâm', clarity: 'Diễn đạt rõ ràng', specificity: 'Ví dụ cụ thể', technical_accuracy: 'Độ chính xác chuyên môn' };
function Feedback({ value }) {
  return <div className="practice-feedback"><h3>Nhận xét luyện tập</h3><div className="practice-rubric">{value.rubric.map(r => <article key={r.dimension}><strong>{labels[r.dimension]} · {r.score === null ? 'Chưa chấm' : `${r.score}/4`}</strong><p>{r.reason}</p></article>)}</div>
    {value.strengths.length > 0 && <><h4>Điểm tốt</h4><ul>{value.strengths.map((s,i) => <li key={i}>{s}</li>)}</ul></>}
    <h4>Có thể cải thiện</h4><ul>{value.improvements.map((s,i) => <li key={i}>{s}</li>)}</ul><p><strong>Gợi ý cách triển khai:</strong> {value.suggested_approach}</p>
    <details><summary>Đoạn câu trả lời dùng để nhận xét</summary>{value.answer_quotes.map((q,i) => <blockquote key={i}>{q}</blockquote>)}</details></div>;
}

export default function InterviewRoute() {
  const { id } = useParams();
  return <InterviewPage key={id || "new"} />;
}

function InterviewPage() {
  const { id } = useParams(), navigate = useNavigate();
  const [choices,setChoices] = useState(null), [history,setHistory] = useState([]), [session,setSession] = useState(null), [task,setTask] = useState(null);
  const [cv,setCV] = useState(''), [job,setJob] = useState(''), [language,setLanguage] = useState('vi'), [count,setCount] = useState('3');
  const [answer,setAnswer] = useState(''), [busy,setBusy] = useState(false), [error,setError] = useState(''), [reload,setReload] = useState(0);
  const [startEvent,setStartEvent] = useState(() => crypto.randomUUID());
  const [answerEvent,setAnswerEvent] = useState(() => crypto.randomUUID());
  useEffect(() => { setStartEvent(crypto.randomUUID()); }, [cv,job,language,count]);
  useEffect(() => { setAnswerEvent(crypto.randomUUID()); }, [answer]);
  useEffect(() => {
    const c = new AbortController(); setError('');
    Promise.all([request('/api/resumes/published',{signal:c.signal}),request('/api/dashboard',{signal:c.signal}),request('/api/interviews',{signal:c.signal})])
      .then(([cvs,jobs,sessions]) => { if (!c.signal.aborted) { setChoices({cvs,jobs:jobs.jobs});setHistory(sessions); } })
      .catch(e => { if(e.name!=='AbortError')setError(e.message); });
    return () => c.abort();
  },[reload]);
  useEffect(() => {
    const c = new AbortController(); let timer; setSession(null);setTask(null);setAnswer('');setBusy(false);setError('');
    if (!id) return () => c.abort();
    async function load() {
      try {
        const s = await request('/api/interviews/'+id,{signal:c.signal});
        if(c.signal.aborted)return;
        setSession(s);
        if(s.pending) {
          const t = await getTask(s.pending.task_id,c.signal);
          if(c.signal.aborted)return;
          setTask(t);
          if(t.status==='queued'||t.status==='running'||t.status==='completed')timer=setTimeout(load,1500);
        } else setTask(null);
      } catch(e) { if(e.name!=='AbortError')setError(e.message); }
    }
    load();return () => {c.abort();clearTimeout(timer);};
  },[id,reload]);
  async function start(e) {
    e.preventDefault();setBusy(true);setError('');
    try {
      const s = await request('/api/interviews',{method:'POST',body:JSON.stringify({cv_id:cv,posting_id:job,language,question_count:Number(count),event_id:startEvent}),headers:{'Content-Type':'application/json'}});
      navigate('/workspace/interviews/'+s.session_id);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function send(e) {
    e.preventDefault();const scope=id;setBusy(true);setError('');
    try {
      await request('/api/interviews/'+scope+'/answers',{method:'POST',body:JSON.stringify({expected_version:session.version,event_id:answerEvent,answer}),headers:{'Content-Type':'application/json'}});
      setReload(n=>n+1);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function retry() {
    setBusy(true);setError('');try{await retryTask(task.task_id);setReload(n=>n+1);}catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <main className="interview-page"><PageHeading eyebrow="LUYỆN TẬP ĐỂ TỰ TIN HƠN" title="Kể câu chuyện của bạn, rõ ràng hơn.">Luyện trả lời qua văn bản với câu hỏi từ CV và công việc bạn chọn. Nhận phản hồi và tiếp tục cải thiện ở lần sau.</PageHeading>
    <div className="form-actions"><Link to="/workspace">Workspace</Link>{id && <Link to="/workspace/interviews">Tạo phiên khác / lịch sử</Link>}</div>
    {error && <p className="error" role="alert">{error} <button onClick={()=>setReload(n=>n+1)}>Tải lại</button></p>}
    {!id && <><section className="interview-setup-card"><div className="interview-setup-title"><span className="surface-icon"><Icon name="chat" size={24}/></span><div><h2>Chuẩn bị một buổi luyện tập</h2><p>Chọn nội dung, bắt đầu trả lời và nhận góp ý từng câu.</p></div></div>{!choices ? <p role="status">Đang tải CV và việc làm…</p> : !choices.cvs.length || !choices.jobs.length ? <div className="interview-prerequisites"><Link to="/workspace/resumes"><Icon name="file" size={23}/><strong>Chuẩn bị CV của bạn</strong><span>Lưu và xác nhận một bản CV để câu hỏi sát với kinh nghiệm của bạn.</span><small>Mở thư viện CV →</small></Link><Link to="/jobs"><Icon name="briefcase" size={23}/><strong>Chọn vị trí mục tiêu</strong><span>Khám phá yêu cầu của công việc bạn muốn luyện phỏng vấn.</span><small>Khám phá việc làm →</small></Link></div> : <form onSubmit={start} className="practice-setup">
      <label>CV đã xác nhận<select name="cv_id" required value={cv} onChange={e=>setCV(e.target.value)}><option value="">Chọn phiên bản CV</option>{choices.cvs.map(c=><option value={c.cv_id} key={c.cv_id}>{c.title||'CV đã xác nhận'} · {c.created_at ? new Date(c.created_at).toLocaleString('vi-VN') : c.cv_id.slice(-8)}</option>)}</select></label>
      <label>Vị trí luyện tập<select name="posting_id" required value={job} onChange={e=>setJob(e.target.value)}><option value="">Chọn JD</option>{choices.jobs.map(j=><option value={j.posting_id} key={j.posting_id}>{j.title} · {j.company||j.source_name}</option>)}</select></label>
      <label>Ngôn ngữ<select name="language" value={language} onChange={e=>setLanguage(e.target.value)}><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
      <label>Số câu hỏi<select name="question_count" value={count} onChange={e=>setCount(e.target.value)}>{[2,3,4,5,6,7,8].map(n=><option key={n}>{n}</option>)}</select></label>
      <button disabled={busy||!cv||!job}>{busy?'Đang tạo…':'Bắt đầu luyện tập'}</button></form>}</section>
      <section><h2>Lịch sử luyện tập</h2>{history.length ? history.map(s=><article className="workspace-row" key={s.session_id}><div><h3>{s.job_title}</h3><p>{s.answered}/{s.question_count} câu · {s.language==='vi'?'Tiếng Việt':'English'} · {s.status==='completed'?'Hoàn tất':'Đang luyện tập'}</p></div><Link to={'/workspace/interviews/'+s.session_id}>Mở lại →</Link></article>) : <div className="quiet-empty"><Icon name="clock" size={24}/><div><strong>Lần luyện tập đầu tiên bắt đầu từ đây</strong><p>Lịch sử câu trả lời và nhận xét được lưu để bạn mở lại.</p></div></div>}</section></>}
    {id && !session && !error && <p role="status">Đang tải phiên…</p>}
    {session && <><section className="practice-source"><h2>{session.job_title}</h2><p>CV version {session.cv_id.slice(-8)} · JD snapshot {session.job_content_hash.slice(0,8)} · {session.question_count} câu</p><p>Phiên giữ nguyên CV/JD đã chọn lúc bắt đầu, kể cả khi bạn sửa CV sau đó.</p>{session.warnings.map((w,i)=><p key={i} className="muted">{w}</p>)}</section>
      {session.turns.map((turn,i)=><article className="practice-turn" key={i}><p className="eyebrow">Câu {i+1} · {turn.question.kind==='technical'?'Chuyên môn':'Hành vi'}</p><h2>{turn.question.text}</h2><details><summary>Căn cứ từ CV / JD</summary>{turn.question.evidence.map((e,j)=><blockquote key={j}><strong>{e.source.toUpperCase()}</strong>: {e.quote}</blockquote>)}</details>
        {turn.answer!==null && <><h3>Câu trả lời của bạn</h3><p className="practice-answer">{turn.answer}</p></>}{turn.feedback && <Feedback value={turn.feedback}/>}</article>)}
      {session.pending && <section role="status"><p>{task ? taskLabel(task) : 'Đang tải tác vụ…'} Bạn có thể rời trang rồi mở lại phiên.</p>{session.pending.answer && <><h3>Câu trả lời đã gửi</h3><p className="practice-answer">{session.pending.answer}</p></>}{task?.status==='failed' && <><p className="error">{task.error}</p><button disabled={busy} onClick={retry}>Thử lại lượt này</button></>}</section>}
      {session.status==='awaiting_answer' && <form onSubmit={send} className="practice-turn"><label htmlFor="practice-answer">Câu trả lời của bạn</label><textarea id="practice-answer" required maxLength={6000} rows={7} value={answer} onChange={e=>setAnswer(e.target.value)} placeholder={session.language==='vi'?'Trả lời bằng lời của bạn…':'Answer in your own words…'}/><p className="muted">{answer.length}/6000 ký tự. Bản gõ chưa gửi chỉ giữ trong trang này.</p><button disabled={busy||!answer.trim()}>{busy?'Đang gửi…':'Gửi và nhận xét'}</button></form>}
      {session.report && <section className="practice-turn"><h2>Báo cáo luyện tập</h2><p>{session.report.notice}</p><p>Đã trả lời {session.report.answered} câu. Điểm trung bình chỉ tính lượt có thể chấm.</p><div className="practice-rubric">{Object.entries(session.report.rubric).map(([key,r])=><article key={key}><h3>{labels[key]}</h3><p>{r.average===null?'Chưa đủ căn cứ':`${r.average}/4`} · {r.rated_answers} lượt</p></article>)}</div><h3>Điểm tốt</h3><ul>{session.report.strengths.map((s,i)=><li key={i}>{s}</li>)}</ul><h3>Ưu tiên luyện tiếp</h3><ul>{session.report.improvements.map((s,i)=><li key={i}>{s}</li>)}</ul></section>}
    </>}
  </main>;
}
