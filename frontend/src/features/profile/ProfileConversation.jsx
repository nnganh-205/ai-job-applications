import React,{useEffect,useState} from 'react';
import {useParams,Link} from 'react-router-dom';
import {request} from '../../lib/api.js';
import ProfileSessionPanel from '../../components/ProfileSessionPanel.jsx';
export default function ProfileConversation({onConfirmed}){
  const {id}=useParams();const [data,setData]=useState(null),[profile,setProfile]=useState(null),[error,setError]=useState('');
  useEffect(()=>{const c=new AbortController();setData(null);setError('');request('/api/profile-sessions/'+id,{signal:c.signal}).then(async s=>{if(c.signal.aborted)return;setData(s);if(s.profile_id){const p=await request('/api/profiles/'+s.profile_id,{signal:c.signal});if(!c.signal.aborted)setProfile(p.profile);}}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>c.abort();},[id]);
  return <main><h1>Kể rõ hơn về kinh nghiệm của bạn.</h1><Link to="/workspace/assistant">← Trợ lý AI</Link>{error&&<p className="error" role="alert">{error}</p>}{!data&&!error&&<p role="status">Đang mở phiên bổ sung…</p>}{data&&<ProfileSessionPanel key={id} mode={data.mode} profileId={data.profile_id} postingId={data.posting_id} profile={profile} initialSessionId={id} onProfileConfirmed={onConfirmed}/>}</main>;
}
