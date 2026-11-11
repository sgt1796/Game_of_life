// Voronoi sites follow the live Life population, without changing the simulation.
// Sparse patterns use every living cell. Dense fields use centroids of spatial
// buckets so a full-screen shader can draw a bounded number of territories.
export const MAX_VORONOI_SITES = 24;

export function selectVoronoiSites(cells, camera, maxSites = MAX_VORONOI_SITES) {
  const samples = [];
  const clusters = new Map();
  const reach = Math.max(110, camera.distance * 6);
  const bucketWidth = 14;
  for (const cell of cells) {
    const comma = cell.indexOf(',');
    if (comma < 0) continue;
    const x = Number(cell.slice(0, comma));
    const y = Number(cell.slice(comma + 1));
    if (!Number.isFinite(x) || !Number.isFinite(y)
      || Math.abs(x - camera.x) > reach || Math.abs(y - camera.y) > reach) continue;
    samples.push({ x, y });
    const bx = Math.floor(x / bucketWidth), by = Math.floor(y / bucketWidth);
    const id = bx + ',' + by;
    let cluster = clusters.get(id);
    if (!cluster) { cluster = { x: 0, y: 0, count: 0, id }; clusters.set(id, cluster); }
    cluster.x += x;
    cluster.y += y;
    cluster.count++;
  }
  if (samples.length <= maxSites) return samples;
  const candidates = [...clusters.values()].map(c => ({
    x: c.x / c.count, y: c.y / c.count, count: c.count, id: c.id
  }));
  // A tiny, tightly packed pattern may occupy only one or two buckets.
  // Spread a small representative sample rather than collapsing it to one site.
  if (candidates.length < 3) {
    const stride = Math.max(1, Math.ceil(samples.length / maxSites));
    return samples.filter((_, i) => i % stride === 0).slice(0, maxSites);
  }
  return candidates.sort((a, b) => {
    const da = ((a.x - camera.x) ** 2 + (a.y - camera.y) ** 2)
      / (1 + Math.log2(a.count) * .15);
    const db = ((b.x - camera.x) ** 2 + (b.y - camera.y) ** 2)
      / (1 + Math.log2(b.count) * .15);
    return da - db || a.id.localeCompare(b.id);
  }).slice(0, maxSites);
}

// Clip a 2D polygon against the half-plane normal · point <= threshold.
function clipHalfPlane(points, nx, ny, threshold) {
  const result = [];
  for (let i = 0; i < points.length; i++) {
    const a = points[i], b = points[(i + 1) % points.length];
    const da = a[0] * nx + a[1] * ny - threshold;
    const db = b[0] * nx + b[1] * ny - threshold;
    const insideA = da <= 1e-7, insideB = db <= 1e-7;
    if (insideA) result.push(a);
    if (insideA !== insideB) {
      const t = da / (da - db);
      result.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
    }
  }
  return result;
}

// The exact finite Voronoi polygon for one site, clipped to a world rectangle.
// Used by the Canvas 2D fallback (WebGL uses an analytic distance shader).
export function voronoiPolygon(sites, index, bounds) {
  const [minX, minY, maxX, maxY] = bounds;
  let polygon = [[minX, minY], [maxX, minY], [maxX, maxY], [minX, maxY]];
  const site = sites[index];
  for (let j = 0; j < sites.length && polygon.length; j++) {
    if (j === index) continue;
    const other = sites[j], nx = other.x - site.x, ny = other.y - site.y;
    if (nx === 0 && ny === 0) continue;
    const threshold = (other.x * other.x + other.y * other.y
      - site.x * site.x - site.y * site.y) * .5;
    polygon = clipHalfPlane(polygon, nx, ny, threshold);
  }
  return polygon;
}
