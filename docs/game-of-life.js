(() => {
  const canvas = document.getElementById("life-canvas");
  const ctx = canvas.getContext("2d");

  const runButton = document.getElementById("life-run");
  const stepButton = document.getElementById("life-step");
  const randomButton = document.getElementById("life-random");
  const clearButton = document.getElementById("life-clear");
  const speedInput = document.getElementById("life-speed");
  const densityInput = document.getElementById("life-density");
  const sizeInput = document.getElementById("life-size");
  const hud = document.getElementById("life-hud");

  const state = {
    rows: 140,
    cols: 140,
    grid: new Uint8Array(),
    buffer: new Uint8Array(),
    running: true,
    generation: 0,
    speedMs: 90,
    density: 0.18,
  };

  function allocate() {
    const cells = state.rows * state.cols;
    state.grid = new Uint8Array(cells);
    state.buffer = new Uint8Array(cells);
    canvas.width = state.cols;
    canvas.height = state.rows;
  }

  function randomize() {
    for (let i = 0; i < state.grid.length; i += 1) {
      state.grid[i] = Math.random() < state.density ? 1 : 0;
    }
    state.generation = 0;
    draw();
  }

  function clear() {
    state.grid.fill(0);
    state.generation = 0;
    draw();
  }

  function setGridSize(size) {
    state.rows = size;
    state.cols = size;
    allocate();
    randomize();
  }

  function stepOnce() {
    const { rows, cols, grid, buffer } = state;
    for (let y = 0; y < rows; y += 1) {
      const yNorth = (y - 1 + rows) % rows;
      const ySouth = (y + 1) % rows;
      for (let x = 0; x < cols; x += 1) {
        const xWest = (x - 1 + cols) % cols;
        const xEast = (x + 1) % cols;
        const idx = y * cols + x;
        let count =
          grid[yNorth * cols + xWest] +
          grid[yNorth * cols + x] +
          grid[yNorth * cols + xEast] +
          grid[y * cols + xWest] +
          grid[y * cols + xEast] +
          grid[ySouth * cols + xWest] +
          grid[ySouth * cols + x] +
          grid[ySouth * cols + xEast];

        const alive = grid[idx] === 1;
        buffer[idx] = alive ? (count === 2 || count === 3 ? 1 : 0) : count === 3 ? 1 : 0;
      }
    }
    state.generation += 1;
    state.grid = buffer;
    state.buffer = grid;
  }

  function draw() {
    const { rows, cols, grid } = state;
    const image = ctx.createImageData(cols, rows);
    const data = image.data;
    let live = 0;
    for (let i = 0, p = 0; i < grid.length; i += 1, p += 4) {
      const on = grid[i];
      live += on;
      const color = on ? [126, 237, 183] : [15, 20, 32];
      data[p] = color[0];
      data[p + 1] = color[1];
      data[p + 2] = color[2];
      data[p + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
    hud.textContent = `Generation ${state.generation} • Live cells ${live}`;
  }

  function toggleRunning(force) {
    if (typeof force === "boolean") {
      state.running = force;
    } else {
      state.running = !state.running;
    }
    runButton.textContent = state.running ? "Pause" : "Resume";
  }

  let paintLive = true;
  let painting = false;
  canvas.addEventListener("pointerdown", (e) => {
    painting = true;
    paintLive = e.button !== 2;
    setCellFromEvent(e, paintLive ? 1 : 0);
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!painting) return;
    setCellFromEvent(e, paintLive ? 1 : 0);
  });

  canvas.addEventListener("pointerup", () => {
    painting = false;
  });
  canvas.addEventListener("pointerleave", () => {
    painting = false;
  });
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());

  function setCellFromEvent(e, value) {
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * state.cols);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * state.rows);
    if (x < 0 || y < 0 || x >= state.cols || y >= state.rows) return;
    state.grid[y * state.cols + x] = value;
    draw();
  }

  let lastStep = 0;
  function loop(timestamp) {
    if (state.running && timestamp - lastStep >= state.speedMs) {
      stepOnce();
      lastStep = timestamp;
      draw();
    } else if (!state.running && painting) {
      draw();
    }
    requestAnimationFrame(loop);
  }

  runButton.addEventListener("click", () => toggleRunning());
  stepButton.addEventListener("click", () => {
    toggleRunning(false);
    stepOnce();
    draw();
  });
  randomButton.addEventListener("click", () => randomize());
  clearButton.addEventListener("click", () => clear());

  speedInput.addEventListener("input", () => {
    state.speedMs = Number(speedInput.value);
    speedInput.nextElementSibling.textContent = `${state.speedMs} ms`;
  });

  densityInput.addEventListener("input", () => {
    state.density = Number(densityInput.value);
    densityInput.nextElementSibling.textContent = `${(state.density * 100).toFixed(0)}%`;
  });

  sizeInput.addEventListener("input", () => {
    const val = Number(sizeInput.value);
    sizeInput.nextElementSibling.textContent = `${val} x ${val}`;
    setGridSize(val);
  });

  document.addEventListener("keydown", (e) => {
    if (e.code === "Space") {
      e.preventDefault();
      toggleRunning();
    } else if (e.key.toLowerCase() === "r") {
      randomize();
    } else if (e.key.toLowerCase() === "c") {
      clear();
    }
  });

  // Initial setup.
  state.speedMs = Number(speedInput.value);
  state.density = Number(densityInput.value);
  setGridSize(Number(sizeInput.value));
  toggleRunning(true);
  draw();
  requestAnimationFrame(loop);
})(); 
