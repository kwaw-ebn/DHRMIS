import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata={title:'GHS StaffHub | District HR Management',description:'Agona East District Health Directorate — HR pilot',robots:{index:false,follow:false}};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
