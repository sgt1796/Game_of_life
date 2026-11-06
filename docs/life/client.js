export class WorkerLifeClient {
  constructor({ mode = 'unbounded', engine = 'auto', onStatus = () => {} } = {}) {
    this.pending = new Map();
    this.nextId = 0;
    this.queue = Promise.resolve();
    this.worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    this.worker.onmessage = ({ data }) => {
      if (data.status) { onStatus(data.status); return; }
      const pending = this.pending.get(data.id);
      if (!pending) return;
      this.pending.delete(data.id);
      if (data.error) pending.reject(new Error(data.error));
      else pending.resolve(data.state);
    };
    this.worker.onerror = event => {
      event.preventDefault();
      this.dispose(new Error(event.message || 'The Python worker stopped. Retry loading the simulation.'));
    };
    this.worker.onmessageerror = () => this.dispose(new Error('Could not read the Python response.'));
    this.ready = this.command('init', { mode, engine });
    // The consumer awaits ready; attaching a handler also covers early disposal.
    this.ready.catch(() => {});
  }

  command(action, data = {}) {
    const request = this.queue.then(() => {
      if (this.closed) throw this.closed;
      return new Promise((resolve, reject) => {
        const id = ++this.nextId;
        this.pending.set(id, { resolve, reject });
        this.worker.postMessage({ id, action, data });
      });
    });
    this.queue = request.catch(() => {});
    return request;
  }

  dispose(error = new Error('Simulation replaced.')) {
    this.closed = error;
    this.worker.terminate();
    for (const { reject } of this.pending.values()) reject(error);
    this.pending.clear();
  }
}
