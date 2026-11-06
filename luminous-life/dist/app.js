import { createCanvasRenderer } from './canvas-renderer.js';
import { installGestures } from './gestures.js';
import { key, patterns } from './life-core.js';
import { LifeClient } from './life-client.js';
import { runtimeConfig } from './runtime-config.js';
const $ = id => document.getElementById(id);
const canvas = $('world');
const touchInput = matchMedia('(pointer: coarse)');
const compactView = matchMedia('(max-width: 700px)');
const phoneViewport = matchMedia('(max-width: 1000px) and (max-height: 500px)');
const viewport = () => ({ width: canvas.clientWidth, height: canvas.clientHeight });
const gl = canvas.getContext('webgl2', { alpha: false, antialias: false, powerPreference: 'high-performance' });
const fallback = gl ? null : createCanvasRenderer(canvas);
let gridProgram, cellsProgram, buffer, gridU, cellU;
if (gl) {
const shader = (type, source) => {
  const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
};
const program = (vs, fs) => {
  const p = gl.createProgram(); gl.attachShader(p, shader(gl.VERTEX_SHADER, vs)); gl.attachShader(p, shader(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  return p;
};
const common = `uniform vec3 eye, rightV, upV, forwardV; uniform float aspect, lens;`;
gridProgram = program(`#version 300 es
precision highp float;
out vec2 uv;
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p*2.-1.;gl_Position=vec4(uv,0,1);}`, `#version 300 es
precision highp float;
in vec2 uv; out vec4 color;
${common}
uniform float showGrid;
void main(){
 vec3 ray=normalize(forwardV+rightV*uv.x*lens*aspect+upV*uv.y*lens);
 float t=-eye.y/min(ray.y,-.001);vec3 p=eye+ray*t;
 vec2 coord=p.xz;vec2 d=max(fwidth(coord),vec2(.0001));
 vec2 lines=abs(fract(coord)-.5)/d;
 float line=1.-smoothstep(.1,.95,min(lines.x,lines.y));
 float fade=exp(-t*.010);float horizon=exp(-t*.018);
 vec3 base=mix(vec3(.009,.020,.043),vec3(.013,.034,.061),horizon);
 vec2 major=abs(fract(coord/10.)-.5)/max(fwidth(coord/10.),vec2(.0001));
 float bold=(1.-smoothstep(.1,.9,min(major.x,major.y)))*.18;
 base+=vec3(.025,.17,.23)*(line*.38+bold)*fade*showGrid;
 float center=exp(-length(coord-eye.xz)*.014);
 base+=vec3(.001,.008,.014)*center;
 color=vec4(base,1);
}`);
cellsProgram = program(`#version 300 es
precision highp float;
layout(location=0) in vec3 cell;
${common}
out vec2 local;out float opacity;out float depthFade;out float tint;
void main(){
 vec2 corners[6]=vec2[6](vec2(-1,-1),vec2(1,-1),vec2(-1,1),vec2(-1,1),vec2(1,-1),vec2(1,1));
 local=corners[gl_VertexID]*2.3;
 vec3 world=vec3(cell.x+local.x,0.,cell.y+local.y);
 vec3 relative=world-eye;
 vec3 q=vec3(dot(relative,rightV),dot(relative,upV),dot(relative,forwardV));
 gl_Position=vec4(q.x/(lens*aspect),q.y/lens,q.z-.2,q.z);
 opacity=cell.z;depthFade=exp(-max(q.z-15.,0.)*.007);
 tint=smoothstep(.55,.95,sin(cell.x*.033+cell.y*.027));
}`, `#version 300 es
precision highp float;
in vec2 local;in float opacity;in float depthFade;in float tint;out vec4 color;
uniform float bloom;
void main(){
 float sd=max(abs(local.x),abs(local.y))-.405;
 float aa=max(fwidth(sd),.075);
 float core=1.-smoothstep(-aa,aa*1.8,sd);
 float halo=exp(-max(sd,0.)*3.2)*(.29*bloom);
 float outer=exp(-dot(local,local)*.65)*.10*bloom;
 vec3 hue=mix(vec3(.12,.82,1.),vec3(.48,.28,1.),tint*.7);
 vec3 light=hue*(core*.68+halo+outer)+vec3(.30,.36,.36)*core;
 color=vec4(light*opacity*depthFade,1);
}`);
const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0,3,gl.FLOAT,false,12,0);gl.vertexAttribDivisor(0,1);
const uniforms = p => Object.fromEntries(['eye','rightV','upV','forwardV','aspect','lens','bloom','showGrid'].map(n=>[n,gl.getUniformLocation(p,n)]));
gridU=uniforms(gridProgram); cellU=uniforms(cellsProgram);
}
let cells=new Set(), ghosts=new Map(), generation=0, population=0, running=true, mode='pan', selected='field';
const DEFAULT_FIELD_DISTANCE = 58;
let camera={x:0,y:0,distance:DEFAULT_FIELD_DISTANCE,angle:45,yaw:.20};
let speed=8, glow=.7, showGrid=1, lastTime=0, accumulator=0, toastTimer;
let backend, backendReady=false, enginePending=false, paintTask=null;
let loadingStatus='Loading Python…';
let ready=false, resetPending=false, stepPending=false, paintPending=false, revision=0, connectionError=false;
const pendingPaint=new Map(), optimisticPaint=new Map();
const stamp=(set,pattern,x,y)=>pattern.forEach(([a,b])=>set.add(key(a+x,b+y)));
const seededRandom = () => { let n=13713; return () => {n=(n*1664525+1013904223)>>>0; return n/4294967296;}; };
function field(){
 const set=new Set(), random=seededRandom();
 for(let i=0;i<150;i++){
  const cx=Math.floor((random()-.5)*360),cy=Math.floor((random()-.5)*360);
  for(let y=0;y<10;y++)for(let x=0;x<12;x++)if(random()<.28)set.add(key(cx+x,cy+y));
 }
 for(let y=-20;y<19;y++)for(let x=-28;x<29;x++)if(random()<.30)set.add(key(x,y));
 stamp(set,patterns.gun,-52,-15);stamp(set,patterns.pulsar,40,15);
 // Python settles the initial field for twelve generations when loading it.
 return set;
}
function updateStats(){ $('generation').textContent=String(generation).padStart(5,'0');$('population').textContent=population.toLocaleString(); }
function toast(message,duration=2300){$('toast').textContent=message;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),duration);}
function gateControls(){
 for(const id of ['play','step','reset','pattern','engine'])$(id).disabled=!ready||resetPending||enginePending;
}
function setRunning(value){running=value;accumulator=0;$('playText').textContent=value?'Pause':'Play';$('playIcon').innerHTML=value?'<path d="M6 4v12M14 4v12"/>':'<path d="m6 3 10 7-10 7V3Z"/>';$('status').textContent=connectionError?'ERROR':!ready?loadingStatus:value?'EVOLVING':'PAUSED';$('loading').textContent=ready?'':loadingStatus;gateControls();}
function applySnapshot(state,{reset=false,edit=false}={}){
 const next=new Set(state.cells.map(([x,y])=>key(x,y))),now=performance.now();
 for(const [cell,alive] of optimisticPaint){if(alive)next.add(cell);else next.delete(cell);}
 if(reset)ghosts.clear();
 else if(!edit)for(const cell of cells)if(!next.has(cell))ghosts.set(cell,now);
 cells=next;generation=state.generation;population=next.size;$('engine').value=state.engine;updateStats();
}
function fail(error,requestRevision){
 if(requestRevision!==revision)return;
 ready=false;connectionError=true;pendingPaint.clear();optimisticPaint.clear();setRunning(false);
 $('error').textContent=error.message;$('error').hidden=false;$('retry').hidden=false;
 $('loading').textContent='Simulation paused';toast('Simulation stopped. Use Retry to reconnect.',6000);
}
async function step(count=1){
 if(!ready||resetPending||stepPending||enginePending)return;
 stepPending=true;
 const requestRevision=revision;
 try{
  await flushPaint();
  if(pendingPaint.size)await flushPaint();
  if(requestRevision!==revision||!ready)return;
  const state=await backend.step(count);if(requestRevision===revision)applySnapshot(state);
 }
 catch(error){fail(error,requestRevision);}
 finally{stepPending=false;}
}
async function reset(){
 if(!backendReady)return;
 const requestRevision=++revision;
 ready=false;resetPending=true;enginePending=false;connectionError=false;pendingPaint.clear();optimisticPaint.clear();lastPaint=null;
 $('error').hidden=true;setRunning(running);
 cells=new Set();ghosts.clear();generation=0;population=0;camera.x=0;camera.y=0;
 if(selected==='field'){cells=field();camera.distance=DEFAULT_FIELD_DISTANCE;}
 else if(patterns[selected]){const p=patterns[selected];const center=selected==='gun'?[-18,-4]:selected==='pulsar'?[0,0]:[-1,-1];stamp(cells,p,...center);camera.distance=selected==='gun'?48:selected==='pulsar'?32:18;}
 else {camera.distance=45;setRunning(false);setMode('draw');}
 $('sceneName').textContent=({field:'THE LIVING FIELD',gun:'GOSPER’S GLIDER GUN',pulsar:'THE PULSAR',glider:'THE GLIDER',rpentomino:'THE R-PENTOMINO',empty:'YOUR NEXT UNIVERSE'})[selected];
 accumulator=0;updateStats();
 try{
  const coordinates=[...cells].map(cell=>cell.split(',').map(Number));
  const state=await backend.reset(coordinates,selected==='field'?12:0);
  if(requestRevision!==revision)return;
  applySnapshot(state,{reset:true});ready=true;setRunning(running);
 }catch(error){fail(error,requestRevision);}
 finally{if(requestRevision===revision){resetPending=false;gateControls();}}
}
async function connect(){
 const requestRevision=++revision;
 backend?.dispose();backendReady=false;ready=false;resetPending=false;enginePending=false;
 connectionError=false;$('error').hidden=true;$('retry').hidden=true;setRunning(running);
 backend=new LifeClient('',{onStatus:message=>{if(requestRevision===revision){loadingStatus=message;setRunning(running);}}});
 try{
  const state=await backend.ready;
  if(requestRevision!==revision)return;
  $('engine').value=state.engine;backendReady=true;await reset();
 }catch(error){fail(error,requestRevision);}
}
async function changeEngine(){
 if(!ready||enginePending)return;
 const engine=$('engine').value,previousRevision=revision;
 enginePending=true;gateControls();
 await flushPaint();
 if(pendingPaint.size)await flushPaint();
 if(previousRevision!==revision||!ready){enginePending=false;gateControls();return;}
 const requestRevision=++revision;ready=false;loadingStatus='Changing engine…';setRunning(running);
 try{
  const state=await backend.setEngine(engine);
  if(requestRevision===revision){applySnapshot(state,{edit:true});ready=true;setRunning(running);}
 }catch(error){fail(error,requestRevision);}
 finally{if(requestRevision===revision){enginePending=false;gateControls();}}
}
function updateHint(){
 const touch=touchInput.matches||compactView.matches||phoneViewport.matches;
 $('hint').innerHTML=mode==='pan'?(touch?'DRAG TO PAN <b>·</b> PINCH TO ZOOM':'DRAG TO PAN <b>·</b> SCROLL TO ZOOM'):
  mode==='erase'?(touch?'DRAG TO ERASE <b>·</b> PINCH TO ZOOM':'DRAG TO ERASE <b>·</b> SCROLL TO ZOOM'):
  (touch?'DRAG TO DRAW <b>·</b> PINCH TO ZOOM':'DRAG TO DRAW <b>·</b> RIGHT CLICK TO ERASE');
 canvas.setAttribute('aria-label',touch?'Interactive Game of Life grid. Drag to pan, pinch to zoom. Select Draw or Erase to edit cells.':'Interactive Game of Life grid. Drag to pan, scroll to zoom. Select Draw or Erase to edit cells.');
}
for(const media of [touchInput,compactView,phoneViewport])media.addEventListener('change',updateHint);
function setMode(value){lastPaint=null;mode=value;for(const m of ['pan','draw','erase']){$(m).classList.toggle('active',m===value);$(m).setAttribute('aria-pressed',m===value);}
 canvas.classList.toggle('drawing',value!=='pan');updateHint();if(value!=='pan')setRunning(false);
}
function basis(){
 const a=camera.angle*Math.PI/180,c=Math.cos(camera.yaw),s=Math.sin(camera.yaw),ca=Math.cos(a),sa=Math.sin(a);
 return {right:[c,0,-s],up:[-s*sa,ca,-c*sa],forward:[-s*ca,-sa,-c*ca],eye:[camera.x+s*camera.distance*ca,camera.distance*sa,camera.y+c*camera.distance*ca]};
}
function planePoint(x,y){
 const {width,height}=viewport();
 const b=basis(),aspect=width/height,lens=Math.tan(26*Math.PI/180),nx=(2*x/width-1)*lens*aspect,ny=(1-2*y/height)*lens;
 const ray=b.forward.map((v,i)=>v+b.right[i]*nx+b.up[i]*ny),t=-b.eye[1]/ray[1];
 return [b.eye[0]+ray[0]*t,b.eye[2]+ray[2]*t];
}
function uploadCamera(p,u,b){gl.useProgram(p);gl.uniform3fv(u.eye,b.eye);gl.uniform3fv(u.rightV,b.right);gl.uniform3fv(u.upV,b.up);gl.uniform3fv(u.forwardV,b.forward);gl.uniform1f(u.aspect,canvas.width/canvas.height);gl.uniform1f(u.lens,Math.tan(26*Math.PI/180));}
let instanceData=new Float32Array(40000);
function draw(now){
 if(fallback){fallback({now,cells,ghosts,camera,basis:basis(),glow,showGrid,planePoint});$('cameraInfo').textContent=`${camera.angle}° PERSPECTIVE   /   ${Math.round(camera.x)}, ${Math.round(camera.y)}`;return;}
 const {width,height}=viewport();
 const dpr=Math.min(devicePixelRatio||1,touchInput.matches?1.4:1.6),w=Math.round(width*dpr),h=Math.round(height*dpr);
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}
 const b=basis();gl.disable(gl.BLEND);uploadCamera(gridProgram,gridU,b);gl.uniform1f(gridU.showGrid,showGrid);gl.drawArrays(gl.TRIANGLES,0,3);
 const total=(cells.size+ghosts.size)*3;if(instanceData.length<total)instanceData=new Float32Array(total*2);
 let n=0;for(const cell of cells){const comma=cell.indexOf(',');instanceData[n++]=Number(cell.slice(0,comma));instanceData[n++]=Number(cell.slice(comma+1));instanceData[n++]=1;}
 for(const [cell,death] of ghosts){const fade=1-(now-death)/230;if(fade<=0||cells.has(cell)){ghosts.delete(cell);continue;}const comma=cell.indexOf(',');instanceData[n++]=Number(cell.slice(0,comma));instanceData[n++]=Number(cell.slice(comma+1));instanceData[n++]=fade*.55;}
 gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,instanceData.subarray(0,n),gl.DYNAMIC_DRAW);
 gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);uploadCamera(cellsProgram,cellU,b);gl.uniform1f(cellU.bloom,glow*2);gl.drawArraysInstanced(gl.TRIANGLES,0,6,n/3);
 $('cameraInfo').textContent=`${camera.angle}° PERSPECTIVE   /   ${Math.round(camera.x)}, ${Math.round(camera.y)}`;
}
function frame(now){
 if(touchInput.matches&&now-lastTime<1000/30){requestAnimationFrame(frame);return;}
 const delta=Math.min(now-lastTime,200);lastTime=now;
 if(!stepPending&&!enginePending)flushPaint();
 if(running&&ready&&!resetPending&&!enginePending){
  const interval=1000/speed;accumulator=Math.min(accumulator+delta,interval*3);
  if(!stepPending&&accumulator>=interval){const count=Math.min(3,Math.floor(accumulator/interval));accumulator-=count*interval;step(count);}
 }
 draw(now);requestAnimationFrame(frame);
}
$('play').onclick=()=>setRunning(!running);
$('step').onclick=()=>{setRunning(false);step();};
$('reset').onclick=()=>{reset();toast('Field reset to its original seed');};
$('engine').onchange=changeEngine;
$('retry').onclick=connect;
$('speed').oninput=e=>{speed=Number(e.target.value);$('speedValue').value=`${speed}/s`;};
$('glow').oninput=e=>{glow=Number(e.target.value)/100;$('glowValue').value=`${e.target.value}%`;};
$('angle').oninput=e=>{camera.angle=Number(e.target.value);$('angleValue').value=`${camera.angle}°`;};
$('grid').onchange=e=>{showGrid=Number(e.target.checked);};
$('pan').onclick=()=>setMode('pan');$('draw').onclick=()=>{setMode('draw');toast('Draw live cells. Select the eraser to remove them.');};
$('erase').onclick=()=>{setMode('erase');toast('Tap or drag over cells to erase them.');};
$('home').onclick=()=>{camera={x:0,y:0,distance:selected==='field'?DEFAULT_FIELD_DISTANCE:45,angle:45,yaw:.20};$('angle').value=45;$('angleValue').value='45°';toast('Camera recentered');};
$('settingsButton').onclick=()=>{$('settings').hidden=!$('settings').hidden;$('settingsButton').setAttribute('aria-expanded',!$('settings').hidden);};
$('closeSettings').onclick=()=>{$('settings').hidden=true;$('settingsButton').setAttribute('aria-expanded','false');$('settingsButton').focus();};
$('pattern').onchange=e=>{selected=e.target.value;setMode('pan');reset();if(selected!=='empty')setRunning(true);toast(selected==='empty'?'Draw your own starting pattern':'Pattern loaded');};
let lastPaint=null;
function paint(point,erase){
 if(!ready||resetPending||enginePending)return;
 const [a,b]=planePoint(point.x,point.y),target=[Math.round(a),Math.round(b)];
 if(lastPaint&&lastPaint[0]===target[0]&&lastPaint[1]===target[1])return;
 let [x,y]=lastPaint||target;
 const dx=Math.abs(target[0]-x),dy=-Math.abs(target[1]-y),sx=x<target[0]?1:-1,sy=y<target[1]?1:-1;let err=dx+dy;
 // Fill cells between pointer events so fast finger strokes stay continuous.
 while(true){
  const cell=key(x,y),alive=!erase;
  pendingPaint.set(cell,alive);optimisticPaint.set(cell,alive);
  if(alive)cells.add(cell);else cells.delete(cell);
  ghosts.delete(cell);
  if(x===target[0]&&y===target[1])break;
  const twice=2*err;if(twice>=dy){err+=dy;x+=sx;}if(twice<=dx){err+=dx;y+=sy;}
 }
 lastPaint=target;population=cells.size;updateStats();
}
function flushPaint(){
 if(paintPending)return paintTask;
 if(!ready||resetPending||!pendingPaint.size)return Promise.resolve();
 const batch=new Map(pendingPaint),requestRevision=revision;pendingPaint.clear();paintPending=true;
 const changes=[...batch].map(([cell,alive])=>[...cell.split(',').map(Number),alive]);
 paintTask=(async()=>{
 try{
  const state=await backend.paint(changes);
  if(requestRevision!==revision)return;
  for(const cell of batch.keys())if(!pendingPaint.has(cell))optimisticPaint.delete(cell);
  applySnapshot(state,{edit:true});
 }catch(error){fail(error,requestRevision);}
 finally{paintPending=false;paintTask=null;}
 })();
 return paintTask;
}
function moveCamera(from,to,ratio=1){
 const before=planePoint(from.x,from.y);camera.distance=Math.max(9,Math.min(250,camera.distance*ratio));const after=planePoint(to.x,to.y);camera.x+=before[0]-after[0];camera.y+=before[1]-after[1];
}
installGestures(canvas,{mode:()=>mode,pan:moveCamera,pinch:moveCamera,paint,endStroke:()=>{lastPaint=null;}});
canvas.oncontextmenu=e=>e.preventDefault();
canvas.addEventListener('wheel',e=>{e.preventDefault();const r=canvas.getBoundingClientRect(),p={x:e.clientX-r.left,y:e.clientY-r.top};moveCamera(p,p,Math.exp(e.deltaY*.001));},{passive:false});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('settings').hidden){$('closeSettings').click();return;}if(['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName))return;if(e.code==='Space'){e.preventDefault();setRunning(!running);}if(e.key.toLowerCase()==='n'){setRunning(false);step();}if(e.key.toLowerCase()==='r')reset();if(e.key.toLowerCase()==='d')setMode('draw');if(e.key.toLowerCase()==='e')setMode('erase');if(e.key.toLowerCase()==='v')setMode('pan');if(e.key.toLowerCase()==='h')$('home').click();});
if(runtimeConfig.demosURL){$('demos').href=runtimeConfig.demosURL;$('demos').hidden=false;}
updateHint();connect();requestAnimationFrame(frame);
window.addEventListener('pagehide',()=>backend?.dispose());
