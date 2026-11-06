// Pointer Events share one gesture path across mouse, pen, and touch.
// Callbacks keep camera and simulation state outside this input adapter.
export function installGestures(surface, { mode, pan, pinch, paint, endStroke }) {
  const pointers = new Map();
  let previousPair = null, pendingTap = null, navigating = false, erase = false;
  const point = event => {
    const rect = surface.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };
  const pair = () => {
    const [a, b] = [...pointers.values()];
    return { center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, distance: Math.max(1, Math.hypot(b.x - a.x, b.y - a.y)) };
  };
  const down = event => {
    if (event.pointerType === 'mouse' && event.button !== 0 && event.button !== 2) return;
    surface.setPointerCapture(event.pointerId);
    const p = point(event);
    pointers.set(event.pointerId, p);
    if (pointers.size > 1) {
      navigating = true; pendingTap = null; endStroke(); previousPair = pair();
    } else {
      erase = mode() === 'erase' || event.button === 2;
      if (mode() !== 'pan') {
        // Delay touch ink so placing the second finger does not leave a dot.
        if (event.pointerType === 'touch') pendingTap = p;
        else paint(p, erase);
      }
    }
  };
  const move = event => {
    if (!pointers.has(event.pointerId)) return;
    const before = pointers.get(event.pointerId), after = point(event);
    pointers.set(event.pointerId, after);
    if (pointers.size > 1) {
      const next = pair();
      if (previousPair) pinch(previousPair.center, next.center, previousPair.distance / next.distance);
      previousPair = next;
    } else if (mode() === 'pan' || navigating) {
      pan(before, after);
    } else {
      if (pendingTap) {
        if (Math.hypot(after.x - pendingTap.x, after.y - pendingTap.y) < 4) return;
        paint(pendingTap, erase); pendingTap = null;
      }
      paint(after, erase);
    }
  };
  const finish = event => {
    if (!pointers.has(event.pointerId)) return;
    if (event.type === 'pointerup' && pendingTap && !navigating) paint(pendingTap, erase);
    pointers.delete(event.pointerId); pendingTap = null; previousPair = null; endStroke();
    if (!pointers.size) navigating = false;
  };
  const listeners = { pointerdown: down, pointermove: move, pointerup: finish, pointercancel: finish, lostpointercapture: finish };
  for (const [name, handler] of Object.entries(listeners)) surface.addEventListener(name, handler);
  return () => { for (const [name, handler] of Object.entries(listeners)) surface.removeEventListener(name, handler); };
}
