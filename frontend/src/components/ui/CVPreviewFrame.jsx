import React,{useEffect,useRef,useState} from 'react';
/** Show the unchanged renderer at A4 width, scaling the frame rather than reflowing CV text. */
export default function CVPreviewFrame({title,src,srcDoc,decorative=false,pageWidth=794,pageHeight=1123}){
  const container=useRef(null),[scale,setScale]=useState(1);
  useEffect(()=>{const element=container.current;if(!element)return;const update=()=>setScale(Math.min(1,element.clientWidth/pageWidth));update();const observer=new ResizeObserver(update);observer.observe(element);return()=>observer.disconnect();},[pageWidth]);
  return <div className="a4-preview-container" ref={container} style={{height:pageHeight*scale}}><iframe className="a4-preview-frame" title={title} tabIndex={decorative?-1:undefined} aria-hidden={decorative||undefined} loading="lazy" src={src} srcDoc={srcDoc} sandbox="" style={{width:pageWidth,height:pageHeight,transform:`scale(${scale})`}}/></div>;
}
