// Python owns the numerical state. This module worker never touches the DOM.
let command;
let queue = Promise.resolve();

async function initialize({ mode = 'unbounded', engine = 'auto' }) {
  const status = message => self.postMessage({ status: message });
  const runtime = new URL('./runtime/314.0.7/', import.meta.url).href;
  status('Loading Python…');
  const { loadPyodide } = await import(`${runtime}pyodide.mjs`);
  const pyodide = await loadPyodide({
    indexURL: runtime,
    lockFileURL: `${runtime}pyodide-lock.json`,
    packageBaseUrl: runtime,
  });
  status('Loading NumPy…');
  await pyodide.loadPackage('numpy');
  status('Loading Life engine…');
  for (const name of ['life_engines.py', 'Game_of_Life.py', 'life_protocol.py']) {
    const response = await fetch(new URL(`./python/${name}`, import.meta.url));
    if (!response.ok) throw new Error(`Could not load ${name} (${response.status}).`);
    pyodide.FS.writeFile(`/home/pyodide/${name}`, await response.text());
  }
  const module = pyodide.pyimport('life_protocol');
  const factory = module.LifeSession;
  try {
    const session = factory(mode, engine);
    try { command = session.command_json.copy(); }
    finally { session.destroy(); }
  } finally {
    factory.destroy();
    module.destroy();
  }
  status('Ready');
}

self.onmessage = ({ data: { id, action, data = {} } }) => {
  queue = queue.then(async () => {
    try {
      if (action === 'init') await initialize(data);
      if (!command) throw new Error('Python is not ready. Retry loading the simulation.');
      const state = JSON.parse(command(action === 'init' ? 'state' : action, JSON.stringify(data)));
      self.postMessage({ id, state });
    } catch (error) {
      self.postMessage({ id, error: error.message || String(error) });
    }
  });
};
