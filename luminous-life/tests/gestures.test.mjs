import test from 'node:test';
import assert from 'node:assert/strict';
import { installGestures } from '../dist/gestures.js';

function fixture(initialMode = 'pan') {
  const handlers = {}, calls = { pan: [], pinch: [], paint: [], end: 0 };
  const surface = {
    getBoundingClientRect: () => ({ left: 10, top: 20 }),
    setPointerCapture() {},
    addEventListener: (name, handler) => { handlers[name] = handler; },
    removeEventListener: name => { delete handlers[name]; },
  };
  const dispose = installGestures(surface, {
    mode: () => initialMode,
    pan: (...args) => calls.pan.push(args),
    pinch: (...args) => calls.pinch.push(args),
    paint: (...args) => calls.paint.push(args),
    endStroke: () => { calls.end++; },
  });
  const event = (type, id, x, y, extra = {}) => handlers[type]?.({ type, pointerId: id, clientX: x + 10, clientY: y + 20, pointerType: 'touch', button: 0, ...extra });
  return { calls, event, dispose, handlers };
}

test('one finger pans using canvas-relative coordinates', () => {
  const { event, calls } = fixture();
  event('pointerdown', 1, 20, 30); event('pointermove', 1, 50, 60); event('pointerup', 1, 50, 60);
  assert.deepEqual(calls.pan, [[{ x: 20, y: 30 }, { x: 50, y: 60 }]]);
  assert.equal(calls.paint.length, 0);
});

test('pinch changes distance around its moving midpoint', () => {
  const { event, calls } = fixture();
  event('pointerdown', 1, 50, 100); event('pointerdown', 2, 150, 100);
  event('pointermove', 2, 250, 100);
  assert.deepEqual(calls.pinch, [[{ x: 100, y: 100 }, { x: 150, y: 100 }, .5]]);
});

test('touch tap draws once and eraser taps remove cells', () => {
  for (const mode of ['draw', 'erase']) {
    const { event, calls } = fixture(mode);
    event('pointerdown', 1, 30, 40); assert.equal(calls.paint.length, 0);
    event('pointerup', 1, 30, 40);
    assert.deepEqual(calls.paint, [[{ x: 30, y: 40 }, mode === 'erase']]);
  }
});

test('two-finger navigation in drawing mode leaves no dots or connecting stroke', () => {
  const { event, calls } = fixture('draw');
  event('pointerdown', 1, 20, 20); event('pointerdown', 2, 80, 20);
  event('pointermove', 2, 100, 20); event('pointerup', 2, 100, 20);
  event('pointermove', 1, 40, 40); event('pointerup', 1, 40, 40);
  assert.equal(calls.paint.length, 0); assert.equal(calls.pan.length, 1);
  event('pointerdown', 3, 60, 60); event('pointerup', 3, 60, 60);
  assert.equal(calls.paint.length, 1);
});

test('drawing starts after touch slop and includes the initial point', () => {
  const { event, calls } = fixture('draw');
  event('pointerdown', 1, 10, 10); event('pointermove', 1, 11, 11);
  assert.equal(calls.paint.length, 0);
  event('pointermove', 1, 30, 30); event('pointerup', 1, 30, 30);
  assert.deepEqual(calls.paint, [[{ x: 10, y: 10 }, false], [{ x: 30, y: 30 }, false]]);
});

test('cancel and lost capture do not paint pending taps or leave gestures stuck', () => {
  const { event, calls, dispose, handlers } = fixture('draw');
  event('pointerdown', 1, 10, 10); event('pointercancel', 1, 10, 10);
  event('pointerdown', 2, 20, 20); event('lostpointercapture', 2, 20, 20);
  assert.equal(calls.paint.length, 0);
  event('pointerdown', 3, 30, 30); event('pointerup', 3, 30, 30);
  assert.equal(calls.paint.length, 1); dispose(); assert.equal(Object.keys(handlers).length, 0);
});

test('desktop drawing and right-button erasing remain immediate', () => {
  const { event, calls } = fixture('draw');
  event('pointerdown', 1, 10, 10, { pointerType: 'mouse' });
  event('pointerup', 1, 10, 10, { pointerType: 'mouse' });
  event('pointerdown', 2, 20, 20, { pointerType: 'mouse', button: 2 });
  assert.deepEqual(calls.paint, [[{ x: 10, y: 10 }, false], [{ x: 20, y: 20 }, true]]);
});
