import test from 'node:test';
import assert from 'node:assert/strict';
import { selectVoronoiSites, voronoiPolygon, MAX_VORONOI_SITES }
  from '../dist/voronoi.js';

test('sparse Life patterns use their actual live cells as Voronoi seeds', () => {
  const sites = selectVoronoiSites(new Set(['0,0', '1,0', '2,1']), 
    { x: 0, y: 0, distance: 58 });
  assert.equal(sites.length, 3);
  assert.deepEqual(sites[2], { x: 2, y: 1 });
});

test('dense populations are capped and follow the camera', () => {
  const cells = new Set();
  for (let y = -60; y <= 60; y += 2)
    for (let x = -60; x <= 60; x += 2) cells.add(x + ',' + y);
  const camera = { x: 0, y: 0, distance: 58 };
  const sites = selectVoronoiSites(cells, camera);
  assert.equal(sites.length, MAX_VORONOI_SITES);
  assert.deepEqual(sites, selectVoronoiSites(cells, camera));
  assert.ok(sites.every(s => Number.isFinite(s.x) && Number.isFinite(s.y)));
});

test('Voronoi clipping finds the bisector between two sites', () => {
  const sites = [{ x: 0, y: 0 }, { x: 10, y: 0 }];
  const bounds = [-10, -10, 20, 10];
  const left = voronoiPolygon(sites, 0, bounds);
  const right = voronoiPolygon(sites, 1, bounds);
  assert.ok(left.length >= 3 && right.length >= 3);
  assert.ok(left.every(p => p[0] <= 5 + 1e-6));
  assert.ok(right.every(p => p[0] >= 5 - 1e-6));
  assert.ok(left.some(p => Math.abs(p[0] - 5) < 1e-6));
  assert.ok(right.some(p => Math.abs(p[0] - 5) < 1e-6));
});
