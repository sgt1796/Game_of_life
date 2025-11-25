(() => {
  const canvas = document.getElementById("bz-canvas");
  const ctx = canvas.getContext("2d");
  const chartCanvas = document.getElementById("bz-chart");
  const chartCtx = chartCanvas.getContext("2d");

  const alphaInput = document.getElementById("bz-alpha");
  const betaInput = document.getElementById("bz-beta");
  const gammaInput = document.getElementById("bz-gamma");
  const speedInput = document.getElementById("bz-speed");
  const reseedButton = document.getElementById("bz-reseed");
  const pauseButton = document.getElementById("bz-pause");
  const hud = document.getElementById("bz-hud");
  const paletteRow = document.getElementById("bz-palette-row");
  const boundaryRow = document.getElementById("bz-boundary-row");
  const maskRow = document.getElementById("bz-mask-row");
  const boundaryNote = document.getElementById("bz-boundary-note");

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

  const plasmaStops = [
    [13, 8, 135],
    [75, 3, 161],
    [125, 3, 168],
    [168, 34, 150],
    [203, 70, 121],
    [229, 107, 93],
    [248, 148, 65],
    [253, 195, 40],
    [240, 249, 33],
  ].map((row) => row.map((v) => v / 255));

  const history = {
    max: 360,
    steps: [],
    a: [],
    b: [],
    c: [],
  };

  const state = {
    size: 200,
    a: new Float32Array(),
    b: new Float32Array(),
    c: new Float32Array(),
    aNext: new Float32Array(),
    bNext: new Float32Array(),
    cNext: new Float32Array(),
    domainMask: new Float32Array(),
    alpha: 1.0,
    beta: 1.0,
    gamma: 1.0,
    running: true,
    speedMs: 70,
    palette: "relief",
    boundary: "wrap",
    maskMode: "full",
    tick: 0,
  };

  let needsDraw = true;
  let painting = false;

  function clamp01(x) {
    return Math.min(1, Math.max(0, x));
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

  function allocate() {
    const cells = state.size * state.size;
    state.a = new Float32Array(cells);
    state.b = new Float32Array(cells);
    state.c = new Float32Array(cells);
    state.aNext = new Float32Array(cells);
    state.bNext = new Float32Array(cells);
    state.cNext = new Float32Array(cells);
    state.domainMask = new Float32Array(cells);
    canvas.width = state.size;
    canvas.height = state.size;
    buildRoundMask();
  }

  function buildRoundMask() {
    const { size, domainMask } = state;
    const center = (size - 1) / 2;
    const radius = size * 0.48;
    const radius2 = radius * radius;
    for (let y = 0; y < size; y += 1) {
      const dy = y - center;
      for (let x = 0; x < size; x += 1) {
        const dx = x - center;
        const idx = y * size + x;
        domainMask[idx] = dx * dx + dy * dy <= radius2 ? 1 : 0;
      }
    }
  }

  function reseed() {
    for (let i = 0; i < state.a.length; i += 1) {
      state.a[i] = Math.random();
      state.b[i] = Math.random();
      state.c[i] = Math.random();
      if (state.maskMode === "round" && state.domainMask[i] === 0) {
        state.a[i] = 0;
        state.b[i] = 0;
        state.c[i] = 0;
      }
    }
    state.tick = 0;
    history.steps = [];
    history.a = [];
    history.b = [];
    history.c = [];
    recordHistory();
    scheduleDraw();
  }

  function toggleRunning(force) {
    if (typeof force === "boolean") {
      state.running = force;
    } else {
      state.running = !state.running;
    }
    pauseButton.textContent = state.running ? "Pause" : "Resume";
  }

  function recordHistory() {
    let sumA = 0;
    let sumB = 0;
    let sumC = 0;
    for (let i = 0; i < state.a.length; i += 1) {
      sumA += state.a[i];
      sumB += state.b[i];
      sumC += state.c[i];
    }
    const meanA = sumA / state.a.length;
    const meanB = sumB / state.b.length;
    const meanC = sumC / state.c.length;
    history.steps.push(state.tick);
    history.a.push(meanA);
    history.b.push(meanB);
    history.c.push(meanC);
    if (history.steps.length > history.max) {
      history.steps.shift();
      history.a.shift();
      history.b.shift();
      history.c.shift();
    }
  }

  function stepOnce() {
    const { size, a, b, c, aNext, bNext, cNext, alpha, beta, gamma, boundary, maskMode, domainMask } = state;
    const maskActive = maskMode === "round";
    const needsCountNorm = boundary === "open" || maskActive;

    for (let y = 0; y < size; y += 1) {
      const yNorth = y - 1;
      const ySouth = y + 1;
      for (let x = 0; x < size; x += 1) {
        const xWest = x - 1;
        const xEast = x + 1;
        let sumA = needsCountNorm ? 0 : 0;
        let sumB = needsCountNorm ? 0 : 0;
        let sumC = needsCountNorm ? 0 : 0;
        let count = needsCountNorm ? 0 : 9;

        for (let dy = -1; dy <= 1; dy += 1) {
          let ny = y + dy;
          let validY = ny >= 0 && ny < size;
          if (boundary === "wrap") {
            ny = (ny + size) % size;
            validY = true;
          }
          for (let dx = -1; dx <= 1; dx += 1) {
            let nx = x + dx;
            let validX = nx >= 0 && nx < size;
            if (boundary === "wrap") {
              nx = (nx + size) % size;
              validX = true;
            }

            if (needsCountNorm) {
              if ((boundary === "open" && (!validX || !validY)) || !validX || !validY) {
                continue;
              }
              const nIdx = ny * size + nx;
              if (maskActive) {
                const maskVal = domainMask[nIdx];
                if (maskVal <= 0) continue;
                sumA += a[nIdx] * maskVal;
                sumB += b[nIdx] * maskVal;
                sumC += c[nIdx] * maskVal;
                count += maskVal;
              } else {
                sumA += a[nIdx];
                sumB += b[nIdx];
                sumC += c[nIdx];
                count += 1;
              }
            } else {
              if (!validX || !validY) {
                continue;
              }
              const nIdx = ny * size + nx;
              sumA += a[nIdx];
              sumB += b[nIdx];
              sumC += c[nIdx];
            }
          }
        }

        const idx = y * size + x;
        const divisor = needsCountNorm ? Math.max(1, count) : 9;
        const avgA = sumA / divisor;
        const avgB = sumB / divisor;
        const avgC = sumC / divisor;

        let nextA = clamp01(avgA + avgA * (alpha * avgB - gamma * avgC));
        let nextB = clamp01(avgB + avgB * (beta * avgC - alpha * avgA));
        let nextC = clamp01(avgC + avgC * (gamma * avgA - beta * avgB));

        if (maskActive && domainMask[idx] === 0) {
          nextA = 0;
          nextB = 0;
          nextC = 0;
        }

        aNext[idx] = nextA;
        bNext[idx] = nextB;
        cNext[idx] = nextC;
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
    recordHistory();
    scheduleDraw();
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

  function paletteRelief(x, y, idx) {
    const { size, a, b, c } = state;
    const idxN = ((y - 1 + size) % size) * size + x;
    const idxS = ((y + 1) % size) * size + x;
    const idxW = y * size + ((x - 1 + size) % size);
    const idxE = y * size + ((x + 1) % size);

    const field = 0.55 * a[idx] + 0.35 * b[idx] + 0.1 * c[idx];
    const fieldN = 0.55 * a[idxN] + 0.35 * b[idxN] + 0.1 * c[idxN];
    const fieldS = 0.55 * a[idxS] + 0.35 * b[idxS] + 0.1 * c[idxS];
    const fieldW = 0.55 * a[idxW] + 0.35 * b[idxW] + 0.1 * c[idxW];
    const fieldE = 0.55 * a[idxE] + 0.35 * b[idxE] + 0.1 * c[idxE];

    const gradX = fieldE - fieldW;
    const gradY = fieldS - fieldN;
    const edge = Math.sqrt(gradX * gradX + gradY * gradY);
    const height = clamp01(field + 0.45 * edge);
    const level = Math.pow(height, 0.7);
    return sampleGradient(plasmaStops, level);
  }

  const paletteMap = {
    soft: (a, b, c, x, y, idx) => paletteSoft(a, b, c),
    triad: (a, b, c, x, y, idx) => paletteTriad(a, b, c),
    turbo: (a, b, c, x, y, idx) => paletteTurbo(a, b, c),
    hue: (a, b, c, x, y, idx) => paletteHue(a, b, c),
    relief: (a, b, c, x, y, idx) => paletteRelief(x, y, idx),
  };

  function drawField() {
    const { size, a, b, c, palette } = state;
    const toRgb = paletteMap[palette] || paletteMap.relief;
    const image = ctx.createImageData(size, size);
    const data = image.data;
    let p = 0;
    for (let y = 0; y < size; y += 1) {
      const row = y * size;
      for (let x = 0; x < size; x += 1, p += 4) {
        const idx = row + x;
        const [r, g, bl] = toRgb(a[idx], b[idx], c[idx], x, y, idx);
        data[p] = Math.floor(r * 255);
        data[p + 1] = Math.floor(g * 255);
        data[p + 2] = Math.floor(bl * 255);
        data[p + 3] = 255;
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  function drawChart() {
    const rect = chartCanvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(200, Math.floor(rect.width * dpr));
    const height = Math.floor(chartCanvas.clientHeight * dpr || 200 * dpr);
    if (chartCanvas.width !== width || chartCanvas.height !== height) {
      chartCanvas.width = width;
      chartCanvas.height = height;
    }
    const w = chartCanvas.width;
    const h = chartCanvas.height;
    chartCtx.clearRect(0, 0, w, h);
    chartCtx.fillStyle = "#0b111c";
    chartCtx.fillRect(0, 0, w, h);

    chartCtx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    chartCtx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = (h / 4) * i;
      chartCtx.beginPath();
      chartCtx.moveTo(0, y + 0.5);
      chartCtx.lineTo(w, y + 0.5);
      chartCtx.stroke();
    }

    if (!history.steps.length) return;
    const xStep = history.steps.length > 1 ? w / (history.steps.length - 1) : 0;
    const datasets = [
      { data: history.a, color: "#ff5c5c" },
      { data: history.b, color: "#4db5ff" },
      { data: history.c, color: "#7bd88f" },
    ];

    datasets.forEach(({ data, color }) => {
      chartCtx.beginPath();
      chartCtx.strokeStyle = color;
      chartCtx.lineWidth = 2;
      data.forEach((v, i) => {
        const x = xStep * i;
        const y = h - v * (h - 8) - 4;
        if (i === 0) {
          chartCtx.moveTo(x, y);
        } else {
          chartCtx.lineTo(x, y);
        }
      });
      chartCtx.stroke();
    });
  }

  function drawHud() {
    const paletteLabel =
      paletteRow.querySelector(`.chip-btn[data-palette="${state.palette}"]`)?.textContent?.trim() || state.palette;
    const boundaryLabel =
      boundaryRow.querySelector(`.chip-btn[data-boundary="${state.boundary}"]`)?.textContent?.trim() ||
      state.boundary;
    const maskLabel = maskRow.querySelector(`.chip-btn[data-mask="${state.maskMode}"]`)?.textContent?.trim() || "";
    hud.textContent = `Step ${state.tick} • α=${state.alpha.toFixed(2)} β=${state.beta.toFixed(
      2,
    )} γ=${state.gamma.toFixed(2)} • ${boundaryLabel} | ${maskLabel} | ${paletteLabel}`;
  }

  function scheduleDraw() {
    needsDraw = true;
  }

  function disturbAt(event) {
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor(((event.clientX - rect.left) / rect.width) * state.size);
    const y = Math.floor(((event.clientY - rect.top) / rect.height) * state.size);
    if (x < 0 || y < 0 || x >= state.size || y >= state.size) return;

    const radius = 7;
    const maskActive = state.maskMode === "round";
    for (let dy = -radius; dy <= radius; dy += 1) {
      let ny = y + dy;
      let validY = ny >= 0 && ny < state.size;
      if (state.boundary === "wrap") {
        ny = (ny + state.size) % state.size;
        validY = true;
      }
      if (!validY) continue;
      const row = ny * state.size;
      for (let dx = -radius; dx <= radius; dx += 1) {
        let nx = x + dx;
        let validX = nx >= 0 && nx < state.size;
        if (state.boundary === "wrap") {
          nx = (nx + state.size) % state.size;
          validX = true;
        }
        if (!validX) continue;
        const idx = row + nx;
        if (maskActive && state.domainMask[idx] === 0) continue;
        const fade = Math.max(0, 1 - Math.hypot(dx, dy) / radius);
        const noise = (Math.random() * 2 - 1) * 0.6 * fade;
        state.a[idx] = clamp01(state.a[idx] + noise * 0.65);
        state.b[idx] = clamp01(state.b[idx] + noise * 0.65);
        state.c[idx] = clamp01(state.c[idx] + noise * 0.65);
      }
    }
    scheduleDraw();
  }

  function applyMaskChange() {
    if (state.maskMode === "round") {
      for (let i = 0; i < state.a.length; i += 1) {
        if (state.domainMask[i] === 0) {
          state.a[i] = 0;
          state.b[i] = 0;
          state.c[i] = 0;
        }
      }
      if (state.boundary === "wrap") {
        setBoundary("open");
      }
      boundaryRow.querySelector('[data-boundary="wrap"]').classList.add("disabled");
    } else {
      boundaryRow.querySelector('[data-boundary="wrap"]').classList.remove("disabled");
    }
    recordHistory();
    scheduleDraw();
  }

  function clearActive(row, selector) {
    row.querySelectorAll(selector).forEach((btn) => btn.classList.remove("active"));
  }

  function setPalette(palette) {
    state.palette = palette;
    clearActive(paletteRow, ".chip-btn");
    const btn = paletteRow.querySelector(`[data-palette="${palette}"]`);
    if (btn) btn.classList.add("active");
    scheduleDraw();
  }

  function setBoundary(boundary) {
    if (state.maskMode === "round" && boundary === "wrap") {
      return;
    }
    state.boundary = boundary;
    clearActive(boundaryRow, ".chip-btn");
    const btn = boundaryRow.querySelector(`[data-boundary="${boundary}"]`);
    if (btn) btn.classList.add("active");
    boundaryNote.textContent =
      boundary === "wrap"
        ? "Edges wrap — patterns keep circulating."
        : boundary === "open"
        ? "Open edges absorb waves; wrap is disabled when the round mask is active."
        : "Edges are clamped to zero, softening outward motion.";
    scheduleDraw();
  }

  function setMask(maskMode) {
    state.maskMode = maskMode;
    clearActive(maskRow, ".chip-btn");
    const btn = maskRow.querySelector(`[data-mask="${maskMode}"]`);
    if (btn) btn.classList.add("active");
    applyMaskChange();
  }

  canvas.addEventListener("pointerdown", (e) => {
    painting = true;
    disturbAt(e);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (painting) disturbAt(e);
  });
  ["pointerup", "pointerleave", "pointercancel"].forEach((evt) =>
    canvas.addEventListener(evt, () => {
      painting = false;
    }),
  );

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
  });

  paletteRow.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => setPalette(btn.dataset.palette));
  });

  boundaryRow.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => setBoundary(btn.dataset.boundary));
  });

  maskRow.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => setMask(btn.dataset.mask));
  });

  reseedButton.addEventListener("click", () => reseed());
  pauseButton.addEventListener("click", () => toggleRunning());

  let lastStep = 0;
  function loop(timestamp) {
    if (state.running && (timestamp - lastStep >= state.speedMs || !lastStep)) {
      stepOnce();
      lastStep = timestamp;
    }
    if (needsDraw) {
      drawField();
      drawChart();
      drawHud();
      needsDraw = false;
    }
    requestAnimationFrame(loop);
  }

  function bootstrap() {
    state.alpha = Number(alphaInput.value);
    state.beta = Number(betaInput.value);
    state.gamma = Number(gammaInput.value);
    state.speedMs = Number(speedInput.value);
    allocate();
    setPalette(state.palette);
    setBoundary(state.boundary);
    setMask(state.maskMode);
    reseed();
    drawField();
    drawChart();
    drawHud();
    requestAnimationFrame(loop);
  }

  window.addEventListener("resize", () => {
    scheduleDraw();
  });

  bootstrap();
})();
