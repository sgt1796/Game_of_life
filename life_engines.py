"""Binary Conway Life engines with the same dense-matrix interface.

The block lookup and packed-bit engines apply techniques used by fast Life
implementations. They are independent implementations, not ports of Golly's
sparse QuickLife tree or its HashLife time-skipping algorithm.
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


def next_generation(grid, boundary="wrap", method="auto"):
    if method == "auto":
        # Local matrix-in/out benchmarks put packed bits ahead by 256x256.
        # Narrow boards have too few useful bits per word to benefit as much.
        method = "packed" if grid.size >= 256 * 256 and grid.shape[1] >= 128 else "dense"
    engines = {"dense": step_dense, "packed": step_packed, "lookup": step_lookup}
    try:
        engine = engines[method]
    except KeyError:
        raise ValueError(f"Unknown Life engine: {method}") from None
    return engine(grid, boundary)
