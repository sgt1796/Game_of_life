// Serialize commands so drawing, reset, and animation cannot overtake one another.
export class LifeClient {
  constructor(base = '') {
    this.base = base;
    this.queue = Promise.resolve();
  }

  command(action, data) {
    const request = this.queue.then(async () => {
      let response;
      try {
        response = await fetch(`${this.base}/api/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(15000),
        });
      } catch {
        throw new Error('Cannot reach the Life server. Start python Game_of_Life.py --webui, then reset the field.');
      }
      if (!response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Start this page with python Game_of_Life.py --webui to connect the simulation.');
      }
      const state = await response.json();
      if (!response.ok) throw new Error(state.error || 'The Life command failed.');
      return state;
    });
    this.queue = request.catch(() => {});
    return request;
  }

  reset(cells, warmup = 0) { return this.command('reset', { cells, warmup }); }
  step(steps = 1) { return this.command('step', { steps }); }
  paint(cells) { return this.command('paint', { cells }); }
}
