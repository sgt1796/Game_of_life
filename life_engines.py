"""Binary Conway Life engines and a persistent finite-board QuickLife core.

All step functions accept and return dense matrices. QuickLifeEngine retains
packed slices, alternating buffers, and dirty tiles across generations. These
are independent NumPy implementations, not ports of Golly's sparse tree or
its HashLife time-skipping algorithm.
"""

from functools import lru_cache

import numpy as np


def _binary(grid):
    cells = np.asarray(grid)
    if cells.ndim != 2 or not all(cells.shape):
        raise ValueError("Life requires a nonempty 2D binary grid.")
    return cells.astype(np.uint8, copy=False)


def step_dense(grid, boundary="wrap"):
    """Separable 3x3 box sum in bytes, including the center cell."""
    cells = _binary(grid)
    padded = np.pad(cells, 1, mode="wrap" if boundary == "wrap" else "constant")
    horizontal = padded[:, :-2] + padded[:, 1:-1]
    horizontal += padded[:, 2:]
    total = horizontal[:-2] + horizontal[1:-1]
    total += horizontal[2:]
    # Inclusive totals: a live cell survives on 3/4, a dead one is born on 3.
    return ((total == 3) | ((total == 4) & (cells == 1))).astype(float)


@lru_cache(maxsize=1)
def block_lookup_table():
    """64 KiB: every binary 4x4 block maps to its next central 2x2."""
    indices = np.arange(1 << 16, dtype=np.uint32)
    table = np.zeros(1 << 16, dtype=np.uint8)
    for output_bit, (row, col) in enumerate(((1, 1), (1, 2), (2, 1), (2, 2))):
        count = np.zeros(1 << 16, dtype=np.uint8)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    count += ((indices >> ((row + dy) * 4 + col + dx)) & 1).astype(np.uint8)
        center = (indices >> (row * 4 + col)) & 1
        alive = (count == 3) | ((count == 2) & (center == 1))
        table |= alive.astype(np.uint8) << output_bit
    table.flags.writeable = False
    return table


def step_lookup(grid, boundary="wrap"):
    """Evaluate four output cells at a time through a 4x4 block lookup."""
    cells = _binary(grid)
    rows, cols = cells.shape
    block_rows, block_cols = (rows + 1) // 2, (cols + 1) // 2
    padded = np.pad(cells, ((1, 1 + rows % 2), (1, 1 + cols % 2)),
                    mode="wrap" if boundary == "wrap" else "constant")
    row_codes = padded[:, :2 * block_cols:2].astype(np.uint16)
    for col in range(1, 4):
        row_codes |= padded[:, col:col + 2 * block_cols:2].astype(np.uint16) << col
    codes = row_codes[:2 * block_rows:2].copy()
    for row in range(1, 4):
        codes |= row_codes[row:row + 2 * block_rows:2] << (row * 4)
    values = block_lookup_table()[codes]
    result = np.empty((2 * block_rows, 2 * block_cols), dtype=float)
    result[::2, ::2] = values & 1
    result[::2, 1::2] = (values >> 1) & 1
    result[1::2, ::2] = (values >> 2) & 1
    result[1::2, 1::2] = (values >> 3) & 1
    return np.ascontiguousarray(result[:rows, :cols])


def _add_three(a, b, c):
    """Bitwise carry-save addition: independent sums in each bit position."""
    xor = a ^ b
    return xor ^ c, (a & b) | (xor & c)


def step_packed(grid, boundary="wrap"):
    """Pack 64 adjacent cells per uint64; count neighbors with Boolean logic.

    Packing and unpacking are included on every call so callers can keep using
    and editing an ordinary matrix. Nonmultiples of 64 wrap at the actual edge,
    not at the padding bits in the final machine word.
    """
    cells = _binary(grid)
    rows, cols = cells.shape
    word_count = (cols + 63) // 64
    packed_bytes = np.zeros((rows, word_count * 8), dtype=np.uint8)
    bits = np.packbits(cells, axis=1, bitorder="little")
    packed_bytes[:, :bits.shape[1]] = bits
    packed = packed_bytes.view("<u8")
    padded = np.pad(packed, ((1, 1), (0, 0)),
                    mode="wrap" if boundary == "wrap" else "constant")
    west = np.empty_like(padded)
    east = np.empty_like(padded)
    west[:, 1:] = (padded[:, 1:] << 1) | (padded[:, :-1] >> 63)
    east[:, :-1] = (padded[:, :-1] >> 1) | (padded[:, 1:] << 63)
    last_bit = (cols - 1) % 64
    west[:, 0] = padded[:, 0] << 1
    east[:, -1] = padded[:, -1] >> 1
    if boundary == "wrap":
        west[:, 0] |= (padded[:, -1] >> last_bit) & 1
        east[:, -1] |= (padded[:, 0] & 1) << last_bit

    # Add the eight neighbors as bit planes. Only counts 2 and 3 matter, so
    # a single high plane records counts >= 4, including the all-eight case.
    low_a, carry_a = _add_three(west[:-2], padded[:-2], east[:-2])
    low_b, carry_b = _add_three(west[1:-1], east[1:-1], west[2:])
    low_c = padded[2:] ^ east[2:]
    carry_c = padded[2:] & east[2:]
    ones, carry_d = _add_three(low_a, low_b, low_c)
    partial_twos, partial_fours = _add_three(carry_a, carry_b, carry_c)
    twos = partial_twos ^ carry_d
    high = partial_fours | (partial_twos & carry_d)
    result = ~high & twos & (ones | packed)
    if last_bit != 63:
        result[:, -1] &= np.uint64((1 << (last_bit + 1)) - 1)
    unpacked = np.unpackbits(result.astype("<u8", copy=False).view(np.uint8),
                             axis=1, count=cols, bitorder="little")
    return unpacked.astype(float)


def _pack_slices(cells):
    """Bit (4*y+x) represents local cell (y,x) in each 4x8 slice."""
    rows, cols = cells.shape
    packed_rows = np.packbits(cells, axis=1, bitorder="little")
    nibbles = np.empty((rows, cols // 4), dtype=np.uint8)
    nibbles[:, ::2] = packed_rows & 15
    nibbles[:, 1::2] = packed_rows >> 4
    nibbles = nibbles.reshape(rows // 8, 8, cols // 4)
    word_bytes = (nibbles[:, ::2] | (nibbles[:, 1::2] << 4)).transpose(0, 2, 1).copy()
    return word_bytes.view("<u4").reshape(rows // 8, cols // 4)


def _unpack_slices(words):
    rows, cols = words.shape
    word_bytes = words.astype("<u4", copy=False).view(np.uint8).reshape(rows, cols, 4)
    nibbles = np.empty((rows, 8, cols), dtype=np.uint8)
    nibbles[:, ::2] = (word_bytes & 15).transpose(0, 2, 1)
    nibbles[:, 1::2] = (word_bytes >> 4).transpose(0, 2, 1)
    nibbles = nibbles.reshape(rows * 8, cols)
    packed_rows = nibbles[:, ::2] | (nibbles[:, 1::2] << 4)
    return np.unpackbits(packed_rows, axis=1, bitorder="little")


class QuickLifeEngine:
    """Own the packed state across steps; export dense matrices only on demand.

    Coordinates are x=column, y=row. Public matrices always have the original
    shape, including boards that are odd-sized or not tile-aligned. Halo bits
    implement boundaries at that true shape, not at the padded storage edge.
    """

    def __init__(self, grid, boundary="wrap"):
        self.boundary = self._check_boundary(boundary)
        self.lookup = block_lookup_table()
        # Spread four table result bits into two rows of a four-column word.
        values = np.arange(16, dtype=np.uint32)
        self._spread = (values & 3) | ((values & 12) << 2)
        self.load(grid)

    @staticmethod
    def _check_boundary(boundary):
        if boundary not in ("wrap", "open", "fill"):
            raise ValueError("Boundary must be wrap, open, or fill.")
        return boundary

    def load(self, grid):
        cells = np.asarray(grid)
        if cells.ndim != 2 or not all(cells.shape):
            raise ValueError("QuickLife requires a nonempty 2D binary board.")
        if not np.all((cells == 0) | (cells == 1)):
            raise ValueError("QuickLife cells must be zero or one.")
        self.shape = cells.shape
        # Four extra cells leave room for two halo cells on either side.
        self.storage_shape = tuple(((n + 4 + 31) // 32) * 32 for n in self.shape)
        physical = np.zeros(self.storage_shape, dtype=np.uint8)
        physical[:self.shape[0], :self.shape[1]] = cells
        initial = _pack_slices(physical)
        self._buffers = [initial, np.zeros_like(initial)]
        valid = np.zeros(self.storage_shape, dtype=np.uint8)
        valid[:self.shape[0], :self.shape[1]] = 1
        self._valid = [_pack_slices(valid), _pack_slices(np.roll(valid, (-1, -1), axis=(0, 1)))]
        self._dirty = np.ones(initial.shape, dtype=bool)
        self._forced = [np.zeros(initial.shape, dtype=bool), np.zeros(initial.shape, dtype=bool)]
        self.phase = 0
        self.generation = 0
        self._cold_steps = 2
        self.last_stats = self._stats(0, 0, 0)

    @property
    def packed_state_bytes(self):
        """The two cell-state buffers, excluding masks, flags, and the LUT."""
        return sum(buffer.nbytes for buffer in self._buffers)

    def _stats(self, tiles, slices, changed):
        total = (self.storage_shape[0] // 32) * (self.storage_shape[1] // 32)
        return {"generation": self.generation, "tiles_total": total,
                "tiles_updated": int(tiles), "slices_updated": int(slices),
                "slices_changed": int(changed), "phase": self.phase}

    def to_numpy(self, dtype=float):
        cells = _unpack_slices(self._buffers[self.phase])
        if self.phase:
            cells = np.roll(cells, (1, 1), axis=(0, 1))
        return np.array(cells[:self.shape[0], :self.shape[1]], dtype=dtype, copy=True, order="C")

    def set_boundary(self, boundary):
        boundary = self._check_boundary(boundary)
        if boundary != self.boundary:
            self.boundary = boundary
            self._dirty.fill(True)
            self._cold_steps = 2

    def set_cell(self, x, y, alive=True):
        if not (0 <= y < self.shape[0] and 0 <= x < self.shape[1]):
            raise IndexError("Cell coordinates are outside the board.")
        physical_y = (y - self.phase) % self.storage_shape[0]
        physical_x = (x - self.phase) % self.storage_shape[1]
        row, col = physical_y // 8, physical_x // 4
        bit = np.uint32(1 << ((physical_y % 8) * 4 + physical_x % 4))
        words = self._buffers[self.phase]
        before = words[row, col]
        after = before | bit if alive else before & ~bit
        if before != after:
            words[row, col] = after
            self._dirty[row, col] = True
            # This buffer was manually altered. It must also be recomputed
            # when it becomes the destination, even if the edit dies out.
            self._forced[self.phase][row, col] = True

    def _refresh_halo(self):
        words = self._buffers[self.phase]
        physical_rows, physical_cols = self.storage_shape
        rows, cols = self.shape
        for world_y in (-2, -1, rows, rows + 1):
            target = (world_y - self.phase) % physical_rows
            row, offset = target // 8, (target % 8) * 4
            before = words[row].copy()
            nibble = np.zeros(words.shape[1], dtype=np.uint32)
            if self.boundary == "wrap":
                source = (world_y % rows - self.phase) % physical_rows
                nibble = (words[source // 8] >> ((source % 8) * 4)) & 15
            mask = np.uint32(15 << offset)
            words[row] = (before & ~mask) | (nibble << offset)
            self._dirty[row] |= before != words[row]
        # Refresh columns after rows so the four corner halos are consistent.
        for world_x in (-2, -1, cols, cols + 1):
            target = (world_x - self.phase) % physical_cols
            col, offset = target // 4, target % 4
            before = words[:, col].copy()
            column = np.zeros(words.shape[0], dtype=np.uint32)
            if self.boundary == "wrap":
                source = (world_x % cols - self.phase) % physical_cols
                column = (words[:, source // 4] >> (source % 4)) & np.uint32(0x11111111)
            mask = np.uint32(0x11111111 << offset)
            words[:, col] = (before & ~mask) | (column << offset)
            self._dirty[:, col] |= before != words[:, col]

    def _lookup_slice_batch(self, current, neighbor, below, diagonal, forward):
        """Eight lookups produce each packed 32-cell destination slice.

        The forward phase uses the current/right/below/diagonal slices; the
        backward phase uses current/left/above/diagonal. No dense expansion.
        """
        if forward:
            side = ((current & np.uint32(0xcccccccc)) >> 2) | ((neighbor & np.uint32(0x33333333)) << 2)
            side_below = ((below & np.uint32(0xcccccccc)) >> 2) | ((diagonal & np.uint32(0x33333333)) << 2)
            windows = [current, side]
            edges = [below, side_below]
        else:
            side = ((neighbor & np.uint32(0xcccccccc)) >> 2) | ((current & np.uint32(0x33333333)) << 2)
            side_above = ((diagonal & np.uint32(0xcccccccc)) >> 2) | ((below & np.uint32(0x33333333)) << 2)
            windows = [side, current]
            edges = [side_above, below]
        result = np.zeros_like(current)
        for horizontal in range(2):
            source, edge = windows[horizontal], edges[horizontal]
            for vertical in range(4):
                if forward:
                    code = ((source >> (8 * vertical)) & 65535) if vertical < 3 else (
                        (source >> 24) | ((edge & 255) << 8))
                else:
                    code = ((edge >> 24) | ((source & 255) << 8)) if vertical == 0 else (
                        (source >> (8 * (vertical - 1))) & 65535)
                result |= self._spread[self.lookup[code]] << (vertical * 8 + horizontal * 2)
        return result

    def _step_once(self):
        destination_phase = 1 - self.phase
        forced = self._forced[destination_phase]
        if self._cold_steps == 0 and not self._dirty.any() and not forced.any():
            # Both phases already represent the correct period-one/two cycle.
            self.phase = destination_phase
            self.generation += 1
            self.last_stats = self._stats(0, 0, 0)
            return
        self._refresh_halo()
        direction = -1 if self.phase == 0 else 1
        dirty = self._dirty
        required = dirty | np.roll(dirty, direction, axis=0)
        required |= np.roll(required, direction, axis=1)
        required |= forced
        if self._cold_steps:
            required.fill(True)
        word_rows, word_cols = required.shape
        tiles = required.reshape(word_rows // 4, 4, word_cols // 8, 8).any(axis=(1, 3))
        active = np.repeat(np.repeat(tiles, 4, axis=0), 8, axis=1)
        y, x = np.nonzero(active)
        source = self._buffers[self.phase]
        destination = self._buffers[destination_phase]
        neighbor_y = (y + (1 if self.phase == 0 else -1)) % word_rows
        neighbor_x = (x + (1 if self.phase == 0 else -1)) % word_cols
        result = self._lookup_slice_batch(source[y, x], source[y, neighbor_x],
                                          source[neighbor_y, x], source[neighbor_y, neighbor_x],
                                          self.phase == 0)
        valid = self._valid[destination_phase][y, x]
        result &= valid
        changed = result != (destination[y, x] & valid)
        destination[y, x] = result
        self._dirty = np.zeros_like(dirty)
        self._dirty[y, x] = changed
        forced.fill(False)
        self.phase = destination_phase
        self.generation += 1
        self._cold_steps = max(0, self._cold_steps - 1)
        self.last_stats = self._stats(tiles.sum(), len(y), changed.sum())

    def step(self, generations=1):
        """Advance in place, retaining packed state; return update statistics."""
        if not isinstance(generations, (int, np.integer)) or generations < 0:
            raise ValueError("generations must be a nonnegative integer.")
        for _ in range(generations):
            self._step_once()
        return dict(self.last_stats)


def step_quicklife(grid, boundary="wrap"):
    """Stateless compatibility wrapper; use QuickLifeEngine to retain state."""
    engine = QuickLifeEngine(grid, boundary)
    engine.step()
    return engine.to_numpy()


def next_generation(grid, boundary="wrap", method="auto"):
    if method == "auto":
        # Local matrix-in/out benchmarks put packed bits ahead by 256x256.
        # Narrow boards have too few useful bits per word to benefit as much.
        method = "packed" if grid.size >= 256 * 256 and grid.shape[1] >= 128 else "dense"
    engines = {"dense": step_dense, "packed": step_packed, "lookup": step_lookup,
               "quicklife": step_quicklife}
    try:
        engine = engines[method]
    except KeyError:
        raise ValueError(f"Unknown Life engine: {method}") from None
    return engine(grid, boundary)
