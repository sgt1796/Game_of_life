import { WorkerLifeClient } from './life/client.js';

const $ = id => document.getElementById(id);
const canvas = $('life-canvas'), ctx = canvas.getContext('2d');
let client, runtimeReady = false, ready = false, running = true, revision = 0;
let pending = 0, stepPending = false, paintRequest = null, lastStep = 0;
let snapshot = { cells: [], generation: 0, population: 0, engine: 'auto', shape: [140, 140] };
const pendingPaint = new Map(), optimisticPaint = new Map();

function controls() {
  // Background steps must not dim or interrupt controls on every generation.
  for (const id of ['life-run', 'life-step', 'life-random', 'life-clear', 'life-engine']) {
    const control = $(id);
    if (control.disabled !== !ready) control.disabled = !ready;
  }
  $('life-size').disabled = !runtimeReady;
  const runLabel = running ? 'Pause' : 'Resume';
  if ($('life-run').textContent !== runLabel) $('life-run').textContent = runLabel;
}

function draw() {
  const [rows, cols] = snapshot.shape;
  if (canvas.width !== cols) canvas.width = cols;
  if (canvas.height !== rows) canvas.height = rows;
  const grid = new Uint8Array(rows * cols);
  for (const [x, y] of snapshot.cells) grid[y * cols + x] = 1;
  for (const [key, alive] of optimisticPaint) grid[key] = Number(alive);
  const image = ctx.createImageData(cols, rows);
  for (let i = 0; i < grid.length; i++) {
    const color = grid[i] ? [126, 237, 183] : [15, 20, 32];
    image.data.set([...color, 255], i * 4);
  }
  ctx.putImageData(image, 0, 0);
  $('life-hud').textContent = `Generation ${snapshot.generation} · Live cells ${snapshot.population}`;
}

function fail(error, requestRevision) {
  if (requestRevision !== revision) return;
  ready = false; runtimeReady = false; running = false;
  pendingPaint.clear(); optimisticPaint.clear();
  $('life-status').textContent = error.message;
  $('life-retry').hidden = false;
  controls();
}

async function execute(action, data, replace = false) {
  if (!runtimeReady) return;
  if (replace) {
    revision++; ready = false;
    if (action === 'reset') { pendingPaint.clear(); optimisticPaint.clear(); }
  }
  const requestRevision = revision;
  pending++; controls();
  try {
    const state = await client.command(action, data);
    if (requestRevision === revision) {
      snapshot = state; ready = true;
      if ($('life-engine').value !== state.engine) $('life-engine').value = state.engine;
      $('life-status').textContent = 'Python ready';
      draw();
    }
  } catch (error) { fail(error, requestRevision); }
  finally { pending--; controls(); }
}

function reset(clear = false) {
  return execute('reset', {
    size: Number($('life-size').value),
    density: clear ? 0 : Number($('life-density').value),
  }, true);
}

async function initialize() {
  const requestRevision = ++revision;
  client?.dispose(); ready = false; runtimeReady = false;
  pendingPaint.clear(); optimisticPaint.clear();
  $('life-retry').hidden = true;
  controls();
  try {
    client = new WorkerLifeClient({ mode: 'bounded', engine: $('life-engine').value,
      onStatus: text => { if (requestRevision === revision) $('life-status').textContent = text; } });
    await client.ready;
    if (requestRevision !== revision) return;
    runtimeReady = true;
    await reset();
  } catch (error) { fail(error, requestRevision); }
}

function flushPaint() {
  if (paintRequest) return paintRequest;
  if (!ready || !pendingPaint.size) return Promise.resolve();
  const batch = new Map(pendingPaint), requestRevision = revision;
  pendingPaint.clear();
  const cols = snapshot.shape[1];
  const cells = [...batch].map(([key, alive]) => [key % cols, Math.floor(key / cols), alive]);
  paintRequest = execute('paint', { cells }).then(() => {
    if (requestRevision !== revision) return;
    for (const key of batch.keys()) if (!pendingPaint.has(key)) optimisticPaint.delete(key);
    draw();
  }).finally(() => { paintRequest = null; });
  return paintRequest;
}

async function step() {
  if (!ready || stepPending || pending) return;
  stepPending = true;
  const requestRevision = revision;
  try {
    await flushPaint();
    if (requestRevision === revision && ready) await execute('step', { steps: 1 });
  } finally { stepPending = false; }
}

async function changeEngine() {
  const engine = $('life-engine').value;
  await flushPaint();
  if (ready) await execute('engine', { engine }, true);
}

let painting = false, paintAlive = true;
function paint(event) {
  if (!ready) return;
  const rect = canvas.getBoundingClientRect(), [rows, cols] = snapshot.shape;
  const x = Math.floor((event.clientX - rect.left) * cols / rect.width);
  const y = Math.floor((event.clientY - rect.top) * rows / rect.height);
  if (x < 0 || y < 0 || x >= cols || y >= rows) return;
  const key = y * cols + x;
  pendingPaint.set(key, paintAlive); optimisticPaint.set(key, paintAlive); draw();
}
canvas.onpointerdown = event => {
  canvas.setPointerCapture(event.pointerId);
  painting = true; paintAlive = event.button !== 2; paint(event);
};
canvas.onpointermove = event => { if (painting) paint(event); };
canvas.onpointerup = canvas.onpointercancel = () => { painting = false; };
canvas.oncontextmenu = event => event.preventDefault();
$('life-run').onclick = () => { running = !running; controls(); };
$('life-step').onclick = () => { running = false; controls(); step(); };
$('life-random').onclick = () => reset();
$('life-clear').onclick = () => reset(true);
$('life-engine').onchange = changeEngine;
$('life-retry').onclick = initialize;
for (const name of ['speed', 'density', 'size']) {
  $(`life-${name}`).oninput = event => {
    const value = Number(event.target.value);
    event.target.nextElementSibling.textContent = name === 'speed' ? `${value} ms`
      : name === 'density' ? `${Math.round(value * 100)}%` : `${value} x ${value}`;
    if (name === 'size' && runtimeReady) reset();
  };
}
document.onkeydown = event => {
  if (['INPUT', 'SELECT', 'BUTTON'].includes(document.activeElement.tagName) || !ready) return;
  if (event.code === 'Space') { event.preventDefault(); running = !running; controls(); }
  if (event.key.toLowerCase() === 'r') reset();
  if (event.key.toLowerCase() === 'c') reset(true);
};
function frame(now) {
  if (!pending && !stepPending) {
    if (pendingPaint.size) flushPaint();
    else if (running && now - lastStep >= Number($('life-speed').value)) { lastStep = now; step(); }
  }
  requestAnimationFrame(frame);
}
window.addEventListener('pagehide', () => client?.dispose());
draw(); initialize(); requestAnimationFrame(frame);
