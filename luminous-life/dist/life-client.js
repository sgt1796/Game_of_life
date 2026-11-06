import { runtimeConfig } from './runtime-config.js';

// Explicit transport configuration: native HTTP locally, Python worker on Pages.
export class LifeClient {
  constructor(base = '', { onStatus = () => {} } = {}) {
    this.base = base;
    this.queue = Promise.resolve();
    if (runtimeConfig.transport === 'worker') {
      this.ready = import(runtimeConfig.clientURL).then(({ WorkerLifeClient }) => {
        if (this.closed) throw new Error('Simulation replaced.');
        this.worker = new WorkerLifeClient({ mode: 'unbounded', onStatus });
        return this.worker.ready;
      });
    } else {
      onStatus('Connecting to Python…');
      this.ready = fetch(`${base}/api/state`, { signal: AbortSignal.timeout(15000) }).then(async response => {
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
          throw new Error('Start the local simulation with python Game_of_Life.py webui.');
        }
        return response.json();
      });
    }
    this.ready.catch(() => {});
  }

  command(action, data) {
    const request = this.queue.then(async () => {
      await this.ready;
      if (this.closed) throw new Error('Simulation replaced.');
      if (this.worker) return this.worker.command(action, data);
      let response;
      try {
        response = await fetch(`${this.base}/api/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(15000),
        });
      } catch {
        throw new Error('Cannot reach Python. Start python Game_of_Life.py webui, then retry.');
      }
      if (!response.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Start this page with python Game_of_Life.py webui to connect the simulation.');
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
  setEngine(engine) { return this.command('engine', { engine }); }
  dispose() { this.closed = true; this.worker?.dispose(); }
}
