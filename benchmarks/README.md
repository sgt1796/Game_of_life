# Life engine benchmarks and Golly investigation

Measured locally on 2026-11-05 with Python 3.12.13, NumPy 2.5.1, and SciPy 1.18.1.
These are CPU timings for one generation on a fixed binary float64 matrix with
20% live cells. Every call includes input conversion, padding, output allocation,
and conversion back to float64. GUI drawing, fading trails, RGB conditioning,
and diffusion inference are excluded. Methods receive the same input; this is
a dense-matrix update benchmark, not a sparse-pattern or evolving-world benchmark.

Each method is warmed up, and lookup-table construction is excluded. Reported
values are medians of five samples (three at 8192); each sample batches enough
calls to approach 80 ms where practical. Timings vary with cache and machine load.
Both wrap and open boundaries were tested through 4096; 8192 uses wrap only.
Every measured method's output was checked against the previous NumPy engine.

## Wrap boundary, milliseconds per generation

| Grid | Previous NumPy float | Original SciPy signal | SciPy ndimage uint8 | New NumPy byte sums | New block lookup | New packed bits |
|---|---:|---:|---:|---:|---:|---:|
| 64 x 64 | 0.042 | 0.069 | 0.034 | 0.025 | 0.043 | 0.036 |
| 150 x 150 | 0.098 | 0.341 | 0.138 | 0.059 | 0.105 | 0.063 |
| 512 x 512 | 4.866 | 4.655 | 1.850 | 0.763 | 1.160 | 0.546 |
| 1024 x 1024 | 21.416 | 20.523 | 8.281 | 4.474 | 6.388 | 2.495 |
| 2048 x 2048 | 93.879 | 83.614 | 33.749 | 18.102 | 30.621 | 11.822 |
| 4096 x 4096 | 389.152 | 332.574 | 130.727 | 72.394 | 122.646 | 48.889 |
| 8192 x 8192 | 1457.347 | 1365.663 | 539.976 | 298.268 | 511.212 | 209.648 |

The original `scipy.signal.convolve2d` kernel overtakes the previous float-based
NumPy implementation at larger sizes. A byte-based `scipy.ndimage.convolve` is
considerably faster still. However, reducing memory traffic and packing binary
cells produces the largest improvements here. Packed bits are about 6.8x faster
than the original SciPy method at 4096 and 6.5x faster at 8192.

The packed engine includes packing and unpacking on every call. Keeping state
packed between generations could remove those costs, but the existing drawing
and rendering code needs dense matrices. The reported times do not promise the
same speedup for the complete application, which also updates trails and images.

Additional 192, 256, and 384 tests put packed bits ahead of byte sums. `auto`
conservatively switches at 256 x 256 equivalent cell count, with at least 128
columns; narrow boards waste most bits in each packed word. This heuristic is
based on this machine and can be overridden with `--life-engine`.

The full measurements include a seventh method, byte-based signal convolution:
[main results](results.json), [8192 results](large-results.json),
[crossover results](crossover.json).

## How Golly makes Life fast

Golly's author's [QuickLife source comments](https://raw.githubusercontent.com/rokicki/lifealg/master/qlifealgo.h)
describe packed cell storage, a lookup from 4-by-4 neighborhoods to central
2-by-2 results, and a hierarchy of bricks, 32-by-32 tiles, and larger regions.
Change flags track which regions need recalculation. Its
[generation code](https://raw.githubusercontent.com/rokicki/lifealg/master/qlifealgo.cpp)
uses those flags to avoid unchanged work and traverses adjacent tiles to improve
cache locality. These sources are the author's benchmark adaptation of Golly,
not a claim that the installed 5.0 executable is byte-identical to that code.

Our `lookup` engine implements the same 4-by-4 to 2-by-2 local mapping idea with
an independently generated table. Our `packed` engine packs horizontal rows into
64-bit words and uses Boolean neighbor-count planes instead of table lookups.
It won these dense NumPy benchmarks. A pure NumPy lookup lacks QuickLife's
persistent packed tile representation and skipping of unchanged regions.

Golly also offers [HashLife](https://golly.sourceforge.io/Help/Algorithms/HashLife.html),
which excels on patterns with repeated structure in space or time; Golly warns
that chaotic patterns can perform poorly. Rokicki's
[Life algorithms paper](https://www.gathering4gardner.org/g4g13gift/math/RokickiTomas-GiftExchange-LifeAlgorithms-G4G13.pdf)
explains how HashLife caches hierarchical results and advances many generations
at once. That is useful for far-future pattern
exploration, while this application needs individual generations for editing,
trail updates, and live rendering. A full sparse QuickLife/HashLife port would
require a stateful world engine and integration with those dense consumers.
The current implementation adopts compact local computation while keeping the
existing matrix API; it does not claim Golly-equivalent performance.

## Reproduce

Run in an environment containing NumPy and SciPy:

```powershell
python benchmarks/benchmark_life.py
python benchmarks/benchmark_life.py --sizes 8192 --boundaries wrap --repeats 3 --target-seconds 0.05 --output benchmarks/large-results.json
```

SciPy is optional: if unavailable, its three methods are omitted. To use an
existing extracted SciPy wheel, pass `--scipy-path` pointing at the directory
containing `scipy/` and its associated libraries. No package is installed or
downloaded by the harness. The benchmark baseline retains both earlier functions
so the comparison remains reproducible after `next_gen` is optimized.
