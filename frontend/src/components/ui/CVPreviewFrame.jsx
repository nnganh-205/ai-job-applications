import React,{useEffect,useRef,useState} from 'react';
/** Show the unchanged renderer at A4 width, scaling the frame rather than reflowing CV text. */
export default function CVPreviewFrame({title,src,srcDoc,decorative=false}){
  const container=useRef(null),[scale,setScale]=useState(1);
  useEffect(()=>{const element=container.current;if(!element)return;const update=()=>setScale(Math.min(1,element.clientWidth/794));update();const observer=new ResizeObserver(update);observer.observe(element);return()=>observer.disconnect();},[]);
  return <div className="a4-preview-container" ref={container} style={{height:1123*scale}}><iframe className="a4-preview-frame" title={title} tabIndex={decorative?-1:undefined} aria-hidden={decorative||undefined} loading="lazy" src={src} srcDoc={srcDoc} sandbox="" style={{transform:`scale(${scale})`}}/></div>;
}
