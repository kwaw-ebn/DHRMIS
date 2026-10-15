'use client';
import {useEffect,useState} from 'react';
type Unit={id:string;name:string;kind:string;parent_id?:string|null;category?:string|null};
export function unitPath(units:Unit[],id:string):Unit[]{
 const path:Unit[]=[],seen=new Set<string>();let current=units.find(u=>u.id===id);
 while(current&&!seen.has(current.id)){path.unshift(current);seen.add(current.id);current=units.find(u=>u.id===current?.parent_id)}return path;
}
function groupFor(units:Unit[],id:string){const path=unitPath(units,id);return path.find(u=>u.kind==='subdistrict')?.id||path.find(u=>u.category==='DHD')?.id||path.find(u=>u.kind==='district')?.id||''}
export function assignmentLabel(units:Unit[],id:string){return unitPath(units,id).filter(u=>['subdistrict','facility','department'].includes(u.kind)).map(u=>u.name).join(' · ')||units.find(u=>u.id===id)?.name||'—'}
export default function AssignmentPicker({units,value,onChange,label='Work location'}:{units:Unit[];value:string;onChange:(id:string)=>void;label?:string}){
 const [group,setGroup]=useState(()=>groupFor(units,value));
 useEffect(()=>{if(value)setGroup(groupFor(units,value))},[units,value]);
 const dhds=units.filter(u=>u.kind==='facility'&&u.category==='DHD');
 const districts=units.filter(u=>u.kind==='district'&&units.some(child=>child.parent_id===u.id&&['facility','department'].includes(child.kind)&&child.category!=='DHD'));
 const groups=[...dhds,...units.filter(u=>u.kind==='subdistrict').sort((a,b)=>a.name.localeCompare(b.name)),...districts];
 const selected=units.find(u=>u.id===value),selectedGroup=groups.find(u=>u.id===group);
 const path=unitPath(units,value);const facility=path.find(u=>u.kind==='facility');
 const options=units.filter(u=>u.parent_id===group&&['facility','department'].includes(u.kind)&&u.category!=='DHD').sort((a,b)=>a.name.localeCompare(b.name));
 const departments=facility?units.filter(u=>u.kind==='department'&&u.parent_id===facility.id).sort((a,b)=>a.name.localeCompare(b.name)):[];
 return <><label>{label}: sub-district / DHD<select required value={group} onChange={e=>{const id=e.target.value;setGroup(id);onChange(dhds.some(u=>u.id===id)?id:'')}}><option value="">Select sub-district or DHD</option>{groups.map(g=><option key={g.id} value={g.id}>{g.category==='DHD'?'DHD — '+g.name:g.name}</option>)}</select></label>
 {selectedGroup?.category==='DHD'?<label>Facility / office<input readOnly value={selectedGroup.name}/></label>:<label>Facility<select required disabled={!group} value={facility?.id||(selected?.parent_id===group?value:'')} onChange={e=>onChange(e.target.value)}><option value="">{group?'Select facility':'Select a sub-district first'}</option>{options.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label>}
 {!!departments.length&&<label>Department (optional)<select value={selected?.kind==='department'?value:''} onChange={e=>onChange(e.target.value||facility!.id)}><option value="">General — {facility?.name}</option>{departments.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
 </>;
}
