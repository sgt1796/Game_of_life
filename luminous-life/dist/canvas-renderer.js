// The same perspective scene, drawn with Canvas for browsers without WebGL.
export function createCanvasRenderer(canvas){
 const ctx=canvas.getContext('2d',{alpha:false});
 const sprites=[0,1].map(v=>{
  const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d');
  const rgb=v?'141,123,255':'71,222,255';
  const halo=g.createRadialGradient(64,64,5,64,64,64);halo.addColorStop(0,`rgba(${rgb},.60)`);halo.addColorStop(.30,`rgba(${rgb},.28)`);halo.addColorStop(.65,`rgba(${rgb},.07)`);halo.addColorStop(1,`rgba(${rgb},0)`);
  g.fillStyle=halo;g.fillRect(0,0,128,128);
  g.filter='blur(2px)';g.shadowBlur=24;g.shadowColor=`rgb(${rgb})`;g.fillStyle=v?'#b9b5ff':'#a5f4ff';g.fillRect(53,53,22,22);
  g.shadowBlur=0;g.filter='blur(2.5px)';g.fillStyle=v?'#dfd9ff':'#d0fdff';g.fillRect(55,55,18,18);return c;
 });
 return ({now,cells,ghosts,camera,basis:b,glow,showGrid,planePoint})=>{
  const dpr=Math.min(devicePixelRatio||1,1.5),w=innerWidth,h=innerHeight;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
  const bg=ctx.createLinearGradient(0,0,0,h);bg.addColorStop(0,'#040a17');bg.addColorStop(.65,'#061424');bg.addColorStop(1,'#030b14');ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
  const focal=h/(2*Math.tan(26*Math.PI/180));
  const space=(x,y)=>{const r=[x-b.eye[0],-b.eye[1],y-b.eye[2]];return [r[0]*b.right[0]+r[2]*b.right[2],r[0]*b.up[0]+r[1]*b.up[1]+r[2]*b.up[2],r[0]*b.forward[0]+r[1]*b.forward[1]+r[2]*b.forward[2]];};
  const project=q=>[w/2+q[0]*focal/q[2],h/2-q[1]*focal/q[2],q[2]];
  const screen=(x,y)=>project(space(x,y));
  if(showGrid){
   const corners=[[0,0],[w,0],[0,h],[w,h]].map(([x,y])=>planePoint(x,y));
   const minX=Math.floor(Math.min(...corners.map(p=>p[0])))-2,maxX=Math.ceil(Math.max(...corners.map(p=>p[0])))+2;
   const minY=Math.floor(Math.min(...corners.map(p=>p[1])))-2,maxY=Math.ceil(Math.max(...corners.map(p=>p[1])))+2;
   ctx.lineWidth=.65;
   const line=(x1,y1,x2,y2,bold)=>{
    let a=space(x1,y1),z=space(x2,y2);if(a[2]<1&&z[2]<1)return;
    if(a[2]<1){const t=(1-a[2])/(z[2]-a[2]);a=a.map((v,i)=>v+(z[i]-v)*t);}
    if(z[2]<1){const t=(1-z[2])/(a[2]-z[2]);z=z.map((v,i)=>v+(a[i]-v)*t);}
    const p=project(a),q=project(z);ctx.strokeStyle=bold?'rgba(37,116,153,.29)':'rgba(26,94,132,.22)';ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.stroke();
   };
   for(let x=minX;x<=maxX;x++)line(x+.5,minY,x+.5,maxY,x%10===0);
   for(let y=minY;y<=maxY;y++)line(minX,y+.5,maxX,y+.5,y%10===0);
  }
  ctx.globalCompositeOperation='lighter';
  const tile=(cell,opacity)=>{
   const comma=cell.indexOf(','),x=Number(cell.slice(0,comma)),y=Number(cell.slice(comma+1));
   const center=screen(x,y);if(center[2]<2||center[0]<-100||center[0]>w+100||center[1]<-100||center[1]>h+100)return;
   const a=screen(x-2.3,y-2.3),r=screen(x+2.3,y-2.3),u=screen(x-2.3,y+2.3);
   const fade=Math.exp(-Math.max(center[2]-15,0)*.007)*opacity;
   const tint=Math.sin(x*.033+y*.027)>.75?1:0;
   ctx.globalAlpha=fade*(.5+glow*.65);ctx.setTransform(dpr*(r[0]-a[0])/128,dpr*(r[1]-a[1])/128,dpr*(u[0]-a[0])/128,dpr*(u[1]-a[1])/128,a[0]*dpr,a[1]*dpr);ctx.drawImage(sprites[tint],0,0);
  };
  for(const c of cells)tile(c,1);
  for(const [c,death] of ghosts){const fade=1-(now-death)/230;if(fade<=0||cells.has(c))ghosts.delete(c);else tile(c,fade*.55);}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';
  const fog=ctx.createLinearGradient(0,0,0,h*.65);fog.addColorStop(0,'#030913e6');fog.addColorStop(.45,'#03091355');fog.addColorStop(1,'#03091300');ctx.fillStyle=fog;ctx.fillRect(0,0,w,h*.65);
 };
}
