'use client';
import {useEffect,useState} from 'react';
type Api=(path:string,options?:RequestInit)=>Promise<any>;
export function Portrait({id,name,api}:{id:string;name:string;api:Api}){
 const [src,setSrc]=useState('');
 useEffect(()=>{let active=true;api('/employees/'+id+'/photo/meta').then(m=>{if(active&&m.exists)setSrc('/api/employees/'+id+'/photo?v='+m.version)}).catch(()=>{});return()=>{active=false}},[id,api]);
 return src?<img className="passport-portrait" src={src} alt={'Passport photograph of '+name} onError={()=>setSrc('')}/>:<span className="avatar large" aria-label="No passport photograph">{name.split(' ').map(s=>s[0]).slice(0,2).join('')}</span>;
}
export default function PassportPhoto({id,file,api,onChange}:{id?:string;file:File|null;api:Api;onChange:(file:File|null,version:number)=>void}){
 const [selection,setSelection]=useState(0);
 const [version,setVersion]=useState(0),[ready,setReady]=useState(!id),[existing,setExisting]=useState(''),[preview,setPreview]=useState(''),[error,setError]=useState('');
 useEffect(()=>{let active=true;setReady(!id);setError('');setExisting('');setVersion(0);if(id)api('/employees/'+id+'/photo/meta').then(m=>{if(active){setVersion(m.version);setExisting(m.exists?'/api/employees/'+id+'/photo?v='+m.version:'');setReady(true)}}).catch(()=>{if(active)setError('Photo information could not be loaded. Reopen this form before replacing the photo.')});return()=>{active=false}},[id,api]);
 useEffect(()=>{if(!file){setPreview('');return}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url)},[file]);
 return <section className="passport-upload span-two"><div className="passport-preview">{preview||existing?<img src={preview||existing} alt={file?'Selected passport photograph preview':'Current passport photograph'} onError={()=>{setExisting('');setError('This photograph could not be displayed. Choose a valid JPEG or PNG.')}}/>:<span>No photo</span>}</div><div><label>Passport photograph (optional)<input key={selection} type="file" accept="image/jpeg,image/png" disabled={!ready} onChange={e=>{const selected=e.target.files?.[0]||null;setError('');if(selected&&(selected.size>2*1024*1024||!['image/jpeg','image/png'].includes(selected.type))){setError('Choose a JPEG or PNG up to 2 MB.');e.target.value='';onChange(null,version);return}onChange(selected,version)}}/></label><small>A clear head-and-shoulders photograph. JPEG or PNG, up to 2 MB. Photos are stored privately; location and camera metadata are removed.</small>{file&&<button type="button" className="link-button" onClick={()=>{setSelection(n=>n+1);onChange(null,version)}}>Clear selected photo</button>}{!ready&&!error&&<small>Loading current photograph…</small>}{error&&<p role="alert" className="message error">{error}</p>}</div></section>;
}
