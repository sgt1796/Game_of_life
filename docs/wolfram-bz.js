(() => {
  const canvas = document.getElementById("wolfram-canvas");
  const ctx = canvas.getContext("2d");
  const chartCanvas = document.getElementById("wolfram-chart");
  const chartCtx = chartCanvas.getContext("2d");

  const ruleInput = document.getElementById("wolfram-rule");
  const speedInput = document.getElementById("wolfram-speed");
  const reseedButton = document.getElementById("wolfram-reseed");
  const pauseButton = document.getElementById("wolfram-pause");
  const hud = document.getElementById("wolfram-hud");
  const paletteRow = document.getElementById("wolfram-palette-row");
  const boundaryRow = document.getElementById("wolfram-boundary-row");
  const maskRow = document.getElementById("wolfram-mask-row");
  const boundaryNote = document.getElementById("wolfram-boundary-note");
  const ruleTableEl = document.getElementById("wolfram-rule-table");

  const STATE_COUNT = 20;
  const MAX_SUM = 171; // 9 cells * max state 19

  const emberStops = [
    [5, 5, 15],
    [68, 25, 78],
    [140, 36, 84],
    [214, 85, 52],
    [243, 140, 69],
    [255, 215, 131],
  ].map((row) => row.map((v) => v / 255));

  const marineStops = [
    [3, 10, 30],
    [19, 46, 99],
    [40, 115, 155],
    [93, 201, 189],
    [178, 248, 219],
  ].map((row) => row.map((v) => v / 255));

  const iceStops = [
    [9, 7, 38],
    [34, 31, 88],
    [70, 86, 150],
    [133, 181, 196],
    [217, 240, 245],
  ].map((row) => row.map((v) => v / 255));

  const spectrumStops = [
    [28, 31, 101],
    [72, 12, 132],
    [168, 0, 121],
    [236, 66, 32],
    [255, 176, 0],
    [120, 219, 87],
    [34, 189, 215],
  ].map((row) => row.map((v) => v / 255));

  // Soft cyclic BZ colormap (20 stops) - anti-flash version.
  const bzCyclicStops = [
    [0.15, 0.1, 0.18],
    [0.18, 0.12, 0.22],
    [0.21, 0.15, 0.26],
    [0.25, 0.18, 0.3],
    [0.3, 0.22, 0.35],
    [0.35, 0.26, 0.4],
    [0.4, 0.31, 0.45],
    [0.45, 0.35, 0.5],
    [0.5, 0.4, 0.55],
    [0.55, 0.45, 0.6],
    [0.6, 0.5, 0.6],
    [0.55, 0.45, 0.55],
    [0.5, 0.4, 0.5],
    [0.45, 0.35, 0.45],
    [0.4, 0.31, 0.4],
    [0.35, 0.26, 0.36],
    [0.3, 0.23, 0.33],
    [0.25, 0.2, 0.3],
    [0.2, 0.16, 0.26],
    [0.17, 0.13, 0.22],
  ];

  const history = {
    max: 360,
    steps: [],
    mean: [],
    active: [],
    entropy: [],
  };

  const state = {
    size: 220,
    cells: new Uint8Array(),
    cellsNext: new Uint8Array(),
    domainMask: new Float32Array(),
    ruleNumber: "1350851716507335422",
    ruleTable: new Uint8Array(MAX_SUM + 1),
    boundary: "wrap",
    maskMode: "full",
    running: true,
    speedMs: 70,
    palette: "ember",
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

  function decodeRule(raw) {
    let n;
    try {
      n = BigInt(raw.trim());
    } catch (err) {
      return null;
    }
    if (n < 0n) n = -n;
    const base = 20n;
    const table = new Uint8Array(MAX_SUM + 1);
    for (let i = 0; i <= MAX_SUM; i += 1) {
      table[i] = Number(n % base);
      n /= base;
    }
    return table;
  }

  function allocate() {
    const cells = state.size * state.size;
    state.cells = new Uint8Array(cells);
    state.cellsNext = new Uint8Array(cells);
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
    for (let i = 0; i < state.cells.length; i += 1) {
      const value = Math.floor(Math.random() * STATE_COUNT);
      state.cells[i] = value;
      state.cellsNext[i] = 0;
      if (state.maskMode === "round" && state.domainMask[i] === 0) {
        state.cells[i] = 0;
      }
    }
    state.tick = 0;
    history.steps = [];
    history.mean = [];
    history.active = [];
    history.entropy = [];
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
    let sum = 0;
    let active = 0;
    const counts = new Array(STATE_COUNT).fill(0);
    const total = state.cells.length;
    for (let i = 0; i < total; i += 1) {
      const v = state.cells[i];
      sum += v;
      if (v > 0) active += 1;
      counts[v] += 1;
    }
    let entropy = 0;
    for (let i = 0; i < STATE_COUNT; i += 1) {
      if (!counts[i]) continue;
      const p = counts[i] / total;
      entropy -= p * Math.log(p);
    }
    const maxEntropy = Math.log(STATE_COUNT);
    history.steps.push(state.tick);
    history.mean.push(sum / (total * (STATE_COUNT - 1)));
    history.active.push(active / total);
    history.entropy.push(maxEntropy > 0 ? entropy / maxEntropy : 0);
    if (history.steps.length > history.max) {
      history.steps.shift();
      history.mean.shift();
      history.active.shift();
      history.entropy.shift();
    }
  }

  function stepOnce() {
    const { size, cells, cellsNext, boundary, maskMode, domainMask, ruleTable } = state;
    const maskActive = maskMode === "round";

    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        const centerIdx = y * size + x;
        let sum = 0;

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

            if (!validX || !validY) {
              if (boundary === "fill") {
                sum += cells[centerIdx];
              }
              continue;
            }

            const nIdx = ny * size + nx;
            if (maskActive && domainMask[nIdx] === 0) {
              if (boundary === "fill") {
                sum += cells[centerIdx];
              }
              continue;
            }
            sum += cells[nIdx];
          }
        }

        let nextVal = ruleTable[Math.min(MAX_SUM, sum)];
        if (maskActive && domainMask[centerIdx] === 0) {
          nextVal = 0;
        }
        cellsNext[centerIdx] = nextVal;
      }
    }

    const tmp = state.cells;
    state.cells = state.cellsNext;
    state.cellsNext = tmp;

    state.tick += 1;
    recordHistory();
    scheduleDraw();
  }

  function paletteValue(level, x, y, idx) {
    const t = clamp01(level / (STATE_COUNT - 1));
    switch (state.palette) {
      case "cyclic": {
        const k = Math.floor(t * (bzCyclicStops.length - 1));
        return bzCyclicStops[k];
      }
      case "marine":
        return sampleGradient(marineStops, t);
      case "ice":
        return sampleGradient(iceStops, t);
      case "spectrum":
        // Slight rotation across rows for more motion.
        return sampleGradient(spectrumStops, clamp01(t * 0.9 + (y % 32) / (state.size * 1.1)));
      case "ember":
      default:
        return sampleGradient(emberStops, t);
    }
  }

  function drawField() {
    const { size, cells } = state;
    const image = ctx.createImageData(size, size);
    const data = image.data;
    let p = 0;
    for (let y = 0; y < size; y += 1) {
      const row = y * size;
      for (let x = 0; x < size; x += 1, p += 4) {
        const idx = row + x;
        const [r, g, b] = paletteValue(cells[idx], x, y, idx);
        data[p] = Math.floor(r * 255);
        data[p + 1] = Math.floor(g * 255);
        data[p + 2] = Math.floor(b * 255);
        data[p + 3] = 255;
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  function drawChart() {
    const rect = chartCanvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(200, Math.floor(rect.width * dpr));
    const height = Math.floor((chartCanvas.clientHeight || 200) * dpr);
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
      const y = (h / 4) * i + 0.5;
      chartCtx.beginPath();
      chartCtx.moveTo(0, y);
      chartCtx.lineTo(w, y);
      chartCtx.stroke();
    }

    if (!history.steps.length) return;
    const xStep = history.steps.length > 1 ? w / (history.steps.length - 1) : 0;
    const datasets = [
      { data: history.mean, color: "#ffd166" },
      { data: history.active, color: "#4ae1ff" },
      { data: history.entropy, color: "#c792ff" },
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
      boundaryRow.querySelector(`.chip-btn[data-boundary="${state.boundary}"]`)?.textContent?.trim() || state.boundary;
    const maskLabel = maskRow.querySelector(`.chip-btn[data-mask="${state.maskMode}"]`)?.textContent?.trim() || "";
    hud.textContent = `Step ${state.tick} | Rule ${state.ruleNumber} | ${boundaryLabel} | ${maskLabel} | ${paletteLabel}`;
  }

  function renderRuleTable(table) {
    if (!ruleTableEl || !table) return;
    const entries = [];
    const lines = [];
    for (let i = 0; i < table.length; i += 1) {
      entries.push(`${String(i).padStart(3, " ")}:${String(table[i]).padStart(2, " ")}`);
      if (entries.length === 12) {
        lines.push(entries.join("  "));
        entries.length = 0;
      }
    }
    if (entries.length) {
      lines.push(entries.join("  "));
    }
    ruleTableEl.textContent = lines.join("\n");
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
        const jitter = Math.floor(Math.random() * STATE_COUNT);
        const mix = clamp01(fade * 0.7 + 0.3 * Math.random());
        const blended =
          clamp01((state.cells[idx] / (STATE_COUNT - 1)) * (1 - mix) + (jitter / (STATE_COUNT - 1)) * mix) *
          (STATE_COUNT - 1);
        state.cells[idx] = Math.floor(blended);
      }
    }
    scheduleDraw();
  }

  function applyMaskChange() {
    if (state.maskMode === "round") {
      for (let i = 0; i < state.cells.length; i += 1) {
        if (state.domainMask[i] === 0) {
          state.cells[i] = 0;
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
        ? "Edges wrap - patterns keep circulating."
        : boundary === "open"
        ? "Open edges absorb waves; wrap is disabled when the round mask is active."
        : "Edges are clamped to the nearest interior value.";
    scheduleDraw();
  }

  function setMask(maskMode) {
    state.maskMode = maskMode;
    clearActive(maskRow, ".chip-btn");
    const btn = maskRow.querySelector(`[data-mask="${maskMode}"]`);
    if (btn) btn.classList.add("active");
    applyMaskChange();
  }

  function setRuleFromInput() {
    const rule = ruleInput.value.trim();
    const table = decodeRule(rule);
    const status = ruleInput.nextElementSibling;
    if (!table) {
      status.textContent = "Invalid integer; keeping previous rule.";
      ruleInput.value = state.ruleNumber;
      return;
    }
    state.ruleTable = table;
    state.ruleNumber = rule;
    status.textContent = "Rule applied (base-20 encoded).";
    renderRuleTable(table);
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

  ruleInput.addEventListener("change", setRuleFromInput);
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
    state.speedMs = Number(speedInput.value);
    allocate();
    const defaultTable = decodeRule(state.ruleNumber);
    if (defaultTable) {
      state.ruleTable = defaultTable;
      renderRuleTable(defaultTable);
    }
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
