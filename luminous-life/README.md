# LIFE

A luminous, unbounded Conway's Game of Life with a perspective camera, connected to the Python core in `Game_of_Life.py`. The frontend uses buildless HTML, CSS and JavaScript.

From the repository root, run `python Game_of_Life.py webui`. The local server opens `http://127.0.0.1:8000` automatically. Add `--life-engine quicklife` to use the persistent packed engine, `--port 8001` to use another port, or `--no-browser` to open the page yourself. Run `python Game_of_Life.py webui --help` for web UI options. Stop the server with Ctrl+C. Python and NumPy are required; Matplotlib and diffusion packages are optional for the other views. This local mode computes in native Python and needs no Pyodide assets.

The [GitHub Pages version](https://sgt1796.github.io/Game_of_life/luminous-life/) uses the same Python core through Pyodide in a module worker. From the repository root, run `python docs/build_site.py`, then `python -m http.server 8000 --directory _site` to preview the packaged site at `http://localhost:8000/luminous-life/`. The Pages source and packager live together in `docs/`. All simulation assets are self-hosted. `runtime-config.js` explicitly selects native HTTP in the source frontend; the build writes worker configuration into the staged artifact. Keep editing this frontend in `luminous-life/dist/`, which is the single source for both modes.

`life-core.js` contains pattern seeds and coordinate keys. `life-client.js` serializes reset, generation, painting, and engine commands through either native HTTP or the shared worker client; both call `life_protocol.py`, `Game_of_Life.py`, and `life_engines.py`. `app.js` owns controls, request timing, camera, and WebGL 2 rendering. `canvas-renderer.js` supplies a perspective Canvas fallback when WebGL 2 is unavailable. Only one animation request runs at a time, and reset responses supersede earlier requests. Python and NumPy load before simulation controls are enabled; Retry rebuilds the browser worker after a failure.

The default living-field camera distance is 58 (previously 82), making cells appear about 41% larger at the same viewport size. Reset and recenter use the closer default. Both renderers use broader halos and softer luminous cell edges.

## Controls

- Drag to pan; scroll to zoom around the cursor.
- Space plays/pauses, N steps, R resets, H recenters.
- V selects pan; D selects drawing and pauses the simulation.
- Draw mode: left drag adds cells; right drag erases.
- Appearance controls adjust bloom, camera angle and grid visibility.
- Appearance also contains the Python engine selector: Auto, Dense, Packed, Lookup, and QuickLife. Changes keep the field and generation. Pages starts with Auto; the local view starts with the CLI-selected engine.
- Presets include a living field, Gosper glider gun, pulsar, glider, R-pentomino and empty canvas.

The lattice has no wrapping or simulated boundary. An initially finite population evolves on integer coordinates. The Python core adds empty space before cells reach a board edge, subject to its existing allocation limit. The surface is rendered across the camera's view; the initial populated field is finite. Each local server owns one simulation, shared across its browser tabs. On Pages each tab owns its own Python worker and simulation.
