(() => {
  const canvas = document.getElementById("bz-canvas");
  const ctx = canvas.getContext("2d");

  const alphaInput = document.getElementById("bz-alpha");
  const betaInput = document.getElementById("bz-beta");
  const gammaInput = document.getElementById("bz-gamma");
  const speedInput = document.getElementById("bz-speed");
  const paletteSelect = document.getElementById("bz-palette");
  const reseedButton = document.getElementById("bz-reseed");
  const pauseButton = document.getElementById("bz-pause");
  const hud = document.getElementById("bz-hud");

  const turboStops = [
    [48, 18, 59],
    [48, 70, 139],
    [38, 129, 198],
    [34, 181, 192],
    [40, 223, 140],
    [122, 245, 71],
    [211, 244, 45],
    [253, 196, 53],
    [241, 93, 34],
    [133, 16, 12],
  ].map((row) => row.map((v) => v / 255));

  const triad = [
    [29, 210, 168],
    [255, 120, 104],
    [250, 207, 90],
  ].map((row) => row.map((v) => v / 255));

  const state = {
    size: 180,
    a: new Float32Array(),
    b: new Float32Array(),
    c: new Float32Array(),
    aNext: new Float32Array(),
    bNext: new Float32Array(),
    cNext: new Float32Array(),
    alpha: 1.0,
    beta: 1.0,
    gamma: 1.0,
    running: true,
    speedMs: 70,
    palette: "soft",
    tick: 0,
  };
  let needsDraw = true;

  function clamp01(x) {
    return Math.min(1, Math.max(0, x));
  }

  function allocate() {
    const cells = state.size * state.size;
    state.a = new Float32Array(cells);
    state.b = new Float32Array(cells);
    state.c = new Float32Array(cells);
    state.aNext = new Float32Array(cells);
    state.bNext = new Float32Array(cells);
    state.cNext = new Float32Array(cells);
    canvas.width = state.size;
    canvas.height = state.size;
  }

  function reseed() {
    for (let i = 0; i < state.a.length; i += 1) {
      state.a[i] = Math.random();
      state.b[i] = Math.random();
      state.c[i] = Math.random();
    }
    state.tick = 0;
    scheduleDraw();
  }

  function stepOnce() {
    const { size, a, b, c, aNext, bNext, cNext, alpha, beta, gamma } = state;
    for (let y = 0; y < size; y += 1) {
      const yN = (y - 1 + size) % size;
      const yS = (y + 1) % size;
      const row = y * size;
      const rowN = yN * size;
      const rowS = yS * size;
      for (let x = 0; x < size; x += 1) {
        const xW = (x - 1 + size) % size;
        const xE = (x + 1) % size;

        const idx = row + x;
        const idxNW = rowN + xW;
        const idxN = rowN + x;
        const idxNE = rowN + xE;
        const idxW = row + xW;
        const idxE = row + xE;
        const idxSW = rowS + xW;
        const idxS = rowS + x;
        const idxSE = rowS + xE;

        const avgA =
          (a[idxNW] + a[idxN] + a[idxNE] + a[idxW] + a[idx] + a[idxE] + a[idxSW] + a[idxS] + a[idxSE]) / 9;
        const avgB =
          (b[idxNW] + b[idxN] + b[idxNE] + b[idxW] + b[idx] + b[idxE] + b[idxSW] + b[idxS] + b[idxSE]) / 9;
        const avgC =
          (c[idxNW] + c[idxN] + c[idxNE] + c[idxW] + c[idx] + c[idxE] + c[idxSW] + c[idxS] + c[idxSE]) / 9;

        aNext[idx] = clamp01(avgA + avgA * (alpha * avgB - gamma * avgC));
        bNext[idx] = clamp01(avgB + avgB * (beta * avgC - alpha * avgA));
        cNext[idx] = clamp01(avgC + avgC * (gamma * avgA - beta * avgB));
      }
    }

    const oldA = state.a;
    const oldB = state.b;
    const oldC = state.c;
    state.a = state.aNext;
    state.b = state.bNext;
    state.c = state.cNext;
    state.aNext = oldA;
    state.bNext = oldB;
    state.cNext = oldC;
    state.tick += 1;
  }

  function hsvToRgb(h, s, v) {
    const i = Math.floor(h * 6);
    const f = h * 6 - i;
    const p = v * (1 - s);
    const q = v * (1 - f * s);
    const t = v * (1 - (1 - f) * s);
    switch (i % 6) {
      case 0:
        return [v, t, p];
      case 1:
        return [q, v, p];
      case 2:
        return [p, v, t];
      case 3:
        return [p, q, v];
      case 4:
        return [t, p, v];
      case 5:
      default:
        return [v, p, q];
    }
  }

  function sampleGradient(stops, t) {
    const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    const i0 = Math.floor(x);
    const i1 = Math.min(stops.length - 1, i0 + 1);
    const frac = x - i0;
    const c0 = stops[i0];
    const c1 = stops[i1];
    return [
      c0[0] + (c1[0] - c0[0]) * frac,
      c0[1] + (c1[1] - c0[1]) * frac,
      c0[2] + (c1[2] - c0[2]) * frac,
    ];
  }

  function paletteSoft(a, b, c) {
    return [0.25 + 0.75 * a, 0.25 + 0.75 * c, 0.25 + 0.75 * b];
  }

  function paletteTriad(a, b, c) {
    const sum = a + b + c + 1e-6;
    const wa = a / sum;
    const wb = b / sum;
    const wc = c / sum;
    return [
      wa * triad[0][0] + wb * triad[1][0] + wc * triad[2][0],
      wa * triad[0][1] + wb * triad[1][1] + wc * triad[2][1],
      wa * triad[0][2] + wb * triad[1][2] + wc * triad[2][2],
    ];
  }

  function paletteTurbo(a, b, c) {
    const variance = Math.max(Math.abs(a - b), Math.abs(b - c), Math.abs(c - a));
    const level = clamp01(0.55 * (a + b + c) / 3 + 0.55 * variance);
    return sampleGradient(turboStops, level);
  }

  function paletteHue(a, b, c) {
    const hue = (Math.atan2(c - b, a - 0.5 * (b + c)) / (2 * Math.PI) + 1) % 1;
    const sat = Math.min(1, 1.2 * Math.max(Math.abs(a - b), Math.abs(b - c), Math.abs(c - a)));
    const val = clamp01(0.5 + 0.5 * (a + b + c) / 3);
    return hsvToRgb(hue, sat, val);
  }

  const paletteMap = {
    soft: paletteSoft,
    triad: paletteTriad,
    turbo: paletteTurbo,
    hue: paletteHue,
  };

  function draw() {
    const { size, a, b, c, palette } = state;
    const toRgb = paletteMap[palette] || paletteSoft;
    const image = ctx.createImageData(size, size);
    const data = image.data;
    for (let i = 0, p = 0; i < a.length; i += 1, p += 4) {
      const [r, g, bl] = toRgb(a[i], b[i], c[i]);
      data[p] = Math.floor(r * 255);
      data[p + 1] = Math.floor(g * 255);
      data[p + 2] = Math.floor(bl * 255);
      data[p + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
    hud.textContent = `Step ${state.tick} • α=${state.alpha.toFixed(2)} β=${state.beta.toFixed(2)} γ=${state.gamma.toFixed(2)} • Palette ${palette}`;
  }

  function toggleRunning(force) {
    if (typeof force === "boolean") {
      state.running = force;
    } else {
      state.running = !state.running;
    }
    pauseButton.textContent = state.running ? "Pause" : "Resume";
  }

  function scheduleDraw() {
    needsDraw = true;
  }

  function disturbAt(event) {
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor(((event.clientX - rect.left) / rect.width) * state.size);
    const y = Math.floor(((event.clientY - rect.top) / rect.height) * state.size);
    if (x < 0 || y < 0 || x >= state.size || y >= state.size) return;
    const radius = 6;
    for (let dy = -radius; dy <= radius; dy += 1) {
      const ny = (y + dy + state.size) % state.size;
      const row = ny * state.size;
      for (let dx = -radius; dx <= radius; dx += 1) {
        const nx = (x + dx + state.size) % state.size;
        const idx = row + nx;
        const fade = Math.max(0, 1 - Math.hypot(dx, dy) / radius);
        state.a[idx] = clamp01(state.a[idx] * 0.4 + 0.6 * Math.random() * fade);
        state.b[idx] = clamp01(state.b[idx] * 0.4 + 0.6 * Math.random() * fade);
        state.c[idx] = clamp01(state.c[idx] * 0.4 + 0.6 * Math.random() * fade);
      }
    }
    scheduleDraw();
  }

  let painting = false;
  canvas.addEventListener("pointerdown", (e) => {
    painting = true;
    disturbAt(e);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!painting) return;
    disturbAt(e);
  });
  canvas.addEventListener("pointerup", () => {
    painting = false;
  });
  canvas.addEventListener("pointerleave", () => {
    painting = false;
  });

  alphaInput.addEventListener("input", () => {
    state.alpha = Number(alphaInput.value);
    alphaInput.nextElementSibling.textContent = state.alpha.toFixed(2);
    scheduleDraw();
  });
  betaInput.addEventListener("input", () => {
    state.beta = Number(betaInput.value);
    betaInput.nextElementSibling.textContent = state.beta.toFixed(2);
    scheduleDraw();
  });
  gammaInput.addEventListener("input", () => {
    state.gamma = Number(gammaInput.value);
    gammaInput.nextElementSibling.textContent = state.gamma.toFixed(2);
    scheduleDraw();
  });
  speedInput.addEventListener("input", () => {
    state.speedMs = Number(speedInput.value);
    speedInput.nextElementSibling.textContent = `${state.speedMs} ms`;
    scheduleDraw();
  });
  paletteSelect.addEventListener("change", () => {
    state.palette = paletteSelect.value;
    scheduleDraw();
  });

  reseedButton.addEventListener("click", () => {
    reseed();
  });

  pauseButton.addEventListener("click", () => {
    toggleRunning();
  });

  let lastStep = 0;
  function loop(timestamp) {
    if (state.running && timestamp - lastStep >= state.speedMs) {
      stepOnce();
      lastStep = timestamp;
      needsDraw = true;
    }
    if (needsDraw) {
      draw();
      needsDraw = false;
    }
    requestAnimationFrame(loop);
  }

  // Initial setup.
  state.alpha = Number(alphaInput.value);
  state.beta = Number(betaInput.value);
  state.gamma = Number(gammaInput.value);
  state.speedMs = Number(speedInput.value);
  state.palette = paletteSelect.value;
  allocate();
  reseed();
  draw();
  requestAnimationFrame(loop);
})(); 
