# Master brief: fluid, atmospheric workspaces

Use this as the enduring product brief. Append one focused prompt from the library for each pass. Replace the inputs with real project facts; keep unknowns explicit. This is a design and engineering specification, not a request to install every library mentioned in the research.

## Inputs

- Product and audience: [name, users, environment]
- Primary job: [what the user is trying to accomplish]
- Existing application: [repository or runnable preview, if available]
- Essential capabilities: [routes, workflows, permissions, data operations]
- Content examples: [realistic names, long text, dense states]
- Devices and browsers: [actual targets]
- Delivery for this pass: [concept, implementation, review or validation]
- Constraints: [existing stack, time, accessibility, device performance]

If a codebase is available, inspect it before choosing implementation details. If only reference images are available, produce a design proposal and label assumptions. Do not invent performance results, working features or source-code findings.

## Intended experience

Create an original workspace that feels clear, tactile and immediately responsive. The visual direction combines an architectural or landscape background with a sense of depth, a quiet working surface, selectively translucent controls, restrained metallic details and coherent icons. Use proportion, light and continuity to create character.

The user's action should produce feedback immediately. Visual settling may continue while the interface remains usable. Remote work must have an honest pending state. An animation should help the user understand a change, locate an object or recognise feedback. It must not become an additional step before the task can proceed.

Use the reference images to understand atmosphere and layering. Do not reproduce their brand, dashboard metrics, greeting layout, card arrangement or content. Derive the new layout from this product's primary work. Avoid decorative analytics and stock feature cards unless their information is genuinely needed.

## Information architecture and feature preservation

Inventory existing destinations and actions. Record each capability's current location, proposed location, access path and relevant permission. Identify frequent navigation, infrequent settings, object-specific tools, global actions, destructive operations and status information.

Preserve functionality while reducing visible clutter. Every moved feature must retain a discoverable route. Keep high-frequency work available with few steps and identify tasks that need visible controls. A command palette can accelerate navigation but cannot be the only discoverable entry to essential functionality.

Produce two shell compositions before committing: one with a bottom-centred dock and one with a bottom-leading or edge-aligned navigation arrangement. Compare their effect on content, pointer travel, reading order and small screens. Choose based on the task. Explain why the placement helps; novelty alone is not sufficient.

Use a stable primary dock where it fits. Keep destinations in predictable positions and distinguish navigation from creation, account and settings. Never move the control under a user's pointer merely to make a hover effect attractive. Reserve space around the dock so it cannot cover final rows, form actions or timeline transport.

Use the top-right region for a compact, comprehensible utility cluster and workspace picker when appropriate. Long workspace names need truncation plus an accessible full name. Do not turn every utility into an unidentified icon. Keep critical state such as unsaved work, connection health or a live recording visible in the working context.

## Atmosphere and materials

Design a background with intentional composition: a recognisable foreground, quiet middle distance, clear depth and a protected area for controls. A static rendered scene is an acceptable starting point. A background with a 3D feeling does not require a live 3D renderer.

Use atmosphere most strongly on entry, browsing or personal home views. During focused work, strengthen the content surface or reduce the background's prominence. Preserve neutrality around colour-sensitive content, scientific colour maps and visual editing tools. Allow a plain background mode.

Define semantic materials rather than a universal glass card: background atmosphere, reading surface, navigation glass, transient overlay, metallic active control and solid fallback. Describe each material's role, opacity, edge, shadow and intended contrast. Keep the number of treatments small.

Metal should suggest controlled directional light and a finished surface. It should not become a rainbow or bright chrome gradient behind labels. A pointer-responsive highlight is optional and limited to a small region; do not run a perpetual shimmer. Prefer a simple pseudo-element with measured transform/opacity behaviour before considering shaders.

Glass may need a scrim or tint to remain legible. Test against the brightest and busiest background crop. Provide an opaque fallback and a reduced-transparency preference if the product uses substantial translucent surfaces. Avoid nested full-screen blur layers.

Define a compact palette and typography hierarchy using real content. Use spacing and alignment to group related work before adding more containers. Keep text readable at practical sizes. Include long labels, empty states and error text in the composition; they are part of the interface, not later additions.

## Motion contract

For each interaction, specify trigger, immediate feedback, state update, moving element, stable anchors, settling behaviour, interruption, reverse behaviour and reduced-motion alternative. Use this contract to choose implementation rather than starting with an effect catalog.

Use short easing transitions for simple colour or opacity feedback. Use springs where continuous movement and retargeting are useful. Prefer restrained settling; spring motion need not visibly bounce. During dragging, the manipulated object should track input directly. Apply settling after release only when appropriate.

Keep navigation and persistent utilities stable while the affected region changes. Preserve the identity of an object when opening its detail view, using shared-element movement where it clarifies the relationship. A straightforward state change or crossfade is appropriate when there is no meaningful shared geometry.

Treat timing as a starting hypothesis. Try roughly 80–140 ms for finishing small hover changes, 120–200 ms for anchored menus, 160–240 ms for a dock indicator and 200–320 ms for object expansion. Immediate acknowledgement is separate from these settling times. Tune based on distance, device and repetition; do not claim these are official platform specifications.

New input must take precedence over obsolete presentation. Rapid navigation A → B → C must converge to C. A closing panel must be reopenable without waiting. Avoid routing application logic through animation-complete callbacks. Motion cleanup must not leave invisible overlays intercepting input or hidden content in the focus order.

Reduce nonessential spatial motion when requested. Preserve understandable state changes using immediate updates and restrained nonspatial feedback. Do not replace a large movement with the same movement played faster. Test the product with motion completely disabled to expose logic accidentally coupled to animation.

## State and data architecture

Separate durable application state, server/cache state, transient interaction state and presentation values. Selection, current workspace, pending edits and navigation should remain correct even if effects fail or are disabled. Avoid a global store for every hover, pointer position or animated value.

Give local input the shortest possible update path. Keep search text and pressed feedback independent of expensive filtering or remote requests. Preserve useful content while loading the next region. Use skeletons only when they communicate a meaningful stable layout; avoid replacing the entire screen for a small operation.

Use optimistic updates only where a credible rollback and conflict strategy exist. Distinguish pending from saved, submitted, paid, dispatched or completed. Preserve drafts on error. A request finishing late must not overwrite newer intent. Use cancellation or stale-response guards where appropriate, while recognising that cancelling UI presentation does not necessarily cancel committed server work.

Preserve context across navigation: scroll position, cursor, selection, active filters, camera, timeline position and undo history as relevant. Use stable identities for objects and rendering keys. Prevent resizes and pane changes from reconstructing expensive editors or resetting in-progress work.

Start with a small architecture: reusable semantic tokens, accessible controls, a navigation shell, a few interaction primitives and domain features. Introduce abstractions when repeated behaviour justifies them. Do not create a large motion framework, generic event bus or plugin layer merely to display a handful of transitions.

## Implementation choices

Inspect the installed framework and versions first. Reuse appropriate existing dependencies. CSS is sufficient for many hover, pressed and visibility changes. For a React application needing layout/gesture continuity, evaluate Motion as the primary engine. React Spring is an alternative for suitable physics-oriented work, not an automatic additional dependency.

Evaluate browser View Transitions for specific view changes. Verify feature support and input handling in the target browser set. Preserve a normal DOM-update fallback. Do not assume snapshot-based transitions, component layout animation and every wrapper's interruption behaviour are equivalent.

Treat Aceternity UI, React Bits, Animate UI and Magic UI as sources of individual patterns to inspect. Read component code, dependencies, accessibility behaviour and current license before adoption. Adapt styling and state handling to the product. Remove demo delays, fake success, unnecessary loops and unrelated presentation features.

Use actual live 3D where it supports the task. Establish a fallback, resource budget, cleanup and inactive-state behaviour. Keep essential controls as accessible UI rather than embedding them only in a scene. Avoid adding a full 3D dependency solely to reproduce a static architectural background.

## SVG and interaction details

Define an icon family with consistent optical size, stroke weight and corner treatment. Use familiar silhouettes for navigation and expressive details for a few signature actions. Label unfamiliar controls. Accessible names and selected states must not depend on the appearance of the SVG.

Prefer simple transformations when they describe state: rotating a plus into a close mark, moving a small indicator or changing a stroke. Use path morphing only when compatible geometry and meaning justify it. Keep path complexity modest and test actual rendered sizes, not only enlarged artboards.

Provide hover, focus, pressed, active, loading, disabled and error states where relevant. The states must remain distinguishable without animation. Use normal button/link semantics; hover polish is not a substitute for keyboard interaction. Trigger the action through the appropriate activation event, while pressed feedback can begin on contact.

Menus and dialogs need meaningful focus entry, Escape handling, dismissal and focus restoration. Do not hide controls behind hover alone. Preserve touch usability and prevent decorative layers from stealing pointer events. Larger comfortable hit areas can surround visually small icons.

## Performance and validation

Define representative devices, display rates, browsers, network conditions and content sizes. Record input acknowledgement separately from animation completion and data completion. Measure field responsiveness when available, and use local traces for reproducible interactions and frame pacing. Do not treat a single desktop recording as proof across devices.

Prefer measured transform/opacity approaches for movement and fading. Inspect layout, paint, image decoding, layer count, memory and main-thread work when effects stutter. Filters, clipping and shadows need contextual evaluation. Do not add `will-change` to every element or continuously update component state for pointer decoration.

Use a repeatable stress path: switch destinations rapidly, reverse an opening panel, type while results load, drag while an inspector updates, resize with work in progress, navigate back, lose the network, retry and enable reduced effects. Test bright and dark backgrounds, keyboard-only use, long text and mobile keyboard occlusion.

Maintain a task-level feature map. Verify that every capability remains reachable and that permissions, undo, drafts and data operations still behave correctly. Evaluate accessibility in the full composition: contrast, focus visibility, names, logical reading order and target sizes.

## Deliverables and reporting

For a concept pass, deliver the chosen composition, believable content, a small state storyboard and a precise image prompt. Identify what the still cannot demonstrate. For implementation, deliver the working vertical slice plus focused evidence. For review, cite actual observed states or code. For validation, separate passed, failed and untested cases.

Report material limitations plainly. Do not claim 120fps, native parity, production readiness, preserved functionality or accessibility conformance without supporting evidence. Do not install competing libraries or rewrite working architecture without a concrete reason.

The finished experience should make the next action obvious, respond as soon as the user acts, and preserve context as the workspace changes. Its personality comes from the product's content, a coherent spatial composition, and a small number of carefully executed material and motion decisions.
