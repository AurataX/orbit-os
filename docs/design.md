# Dashboard design

Goal: a clear, calm control room where a lab audience sees *what the OS is doing* and *which policy won*. Information first, decoration second.

## Reference
The implemented console uses an edge-aligned sidebar, tinted status cards, a response chart and a distinct plum-to-peach topology panel. Keeping navigation on the edge leaves the bottom of the workspace available for the timeline and terminal. The phone layout puts navigation behind a menu.

## Layout
- **Sidebar**: Dashboard, Resources (memory and storage), Compare, Runs, Scenarios, Lab guide (including deadlock), and ORBIT Shell. Settings and theme controls sit at the bottom.
- **Controls**: seed and active policies, Run / Pause / Step, Checkpoint, speed, and a comparison shortcut. The timeline contains Rewind and Replay with…
- **Row 1 stat cards** (pastel): Tick, Tasks done, CPU util, Crisis status.
- **Row 2**: Hero card "Machine" (CPU, GPU, RAM, VRAM, Disk as linked blocks, cascade arrows light up when pressure propagates) + line chart "Interactive response over time" with checkpoint marker.
- **Row 3**: RAM/VRAM gauges, CPU/GPU queue lists, Disk queue, Event feed.
- **Compare page**: policy table (sortable) + before/after rewind chart; best value per column highlighted.

## Interaction model
- Every control change appends a line to the **What you did** panel (right rail): time, action, and a measured effect (before/after of one metric), see `system.md` section 10b.
- Inject buttons (AI burst, compile storm, swap storm) sit in a "Stress" group; resize sliders for RAM/VRAM in "Machine".
- Timeline scrubber under the main chart: checkpoints are dots, the crisis tick is a coral flag, dragging rewinds, "Replay with..." opens the policy picker.
- Challenge mode: pick a winner before running, show the result card (right/wrong + why).
- Select a PID to open its process card with workload class, placement reason, work remaining, priority and recent events.

## Tokens
- Surfaces: `--bg #EEF1F4`, `--card #FFFFFF`, pastel accents lavender `#D9D6F7`, mint `#D6E9E4`, butter `#EEF0B8`, sky `#D5E8F3`.
- Text: `--ink #1D2433`, `--muted #6B7385`. Radius 20px cards, 12px controls.
- Workload colours (fixed everywhere): interactive = lavender/violet, AI = sky/blue, dev = butter/olive, background = grey. Status: ok mint, warn amber, crisis coral.
- Dark mode: same tokens redefined, never inverted images.
- Type: one sans family (Inter), 3 sizes for data, tabular numbers for metrics.
- Icons: one stroke family (Lucide), consistent weight, labels on unfamiliar ones.

## Motion contract (from the Fluid-UI brief, trimmed)
- Immediate acknowledgement on click; settling 120–240 ms; no perpetual shimmer.
- Charts and gauges update by transform/opacity or SVG attribute changes; no per-tick React re-render of the whole tree (batch frames, update only changed cards).
- Honour `prefers-reduced-motion`: values update instantly, no travelling highlights.
- Rapid scenario/policy switching must converge on the last choice (ignore stale responses).
- Rewind/replay shows an honest pending state; late responses never overwrite newer intent.

## Materials
Few: page background, card surface, hero gradient, overlay (menus). Glass only on the top bar if contrast is verified; solid fallback.

## Accessibility
Colour never the only signal (add icon/label for crisis). Visible focus rings, real buttons/links, keyboard operable run controls, contrast >= 4.5:1 for text, tables with proper headers, long labels truncate with full accessible name.

## What not to build
Decorative analytics, fake patients/revenue widgets, greeting banners. Every card must show simulator data.

## Reference files

The [Fluid UI master brief](design/reference/fluid-master-brief.md) and [visual direction](design/reference/fluid-visual-direction.md) are checked into the project. Motion uses CSS and respects reduced-motion preferences.
