# Design System: CAD Automation Delivery Workbench

## 1. Visual theme and atmosphere

The intended feel is a quiet engineering control room: density 7/10, variation 4/10, motion 2/10.

Mechanical engineers should find the interface dependable, clear, and suitable for repeated use. Place project status, parameter completeness, P0 review, and delivery outputs where they can be understood immediately. The overall appearance should resemble a precision instrument panel: stable, restrained, and orderly.

## 2. Color palette and roles

- **Drafting Canvas** (#EDEEEA): primary background, resembling engineering drawing paper without a yellow tint.
- **Instrument Surface** (#FAFAF7): forms, review areas, and main content panels.
- **Charcoal Console** (#141B1F): side navigation and bottom status area; do not use pure black.
- **Ink Primary** (#182024): headings, labels, and main content.
- **Steel Text** (#56636B): supporting explanations, paths, and status descriptions.
- **Hairline Border** (#D8DDD7): 1px structural lines and input borders.
- **Copper Accent** (#B87333): the sole accent color, for primary buttons, selection, and key gate states.

Do not use purple/blue neon, pure black, glowing shadows, or highly saturated gradients.

## 3. Typography

- **Display:** Segoe UI Semibold; use restrained sizes and establish hierarchy through weight.
- **Body:** Segoe UI; use comfortable line height and at least 13px in forms. Fonts must support Turkish characters.
- **Mono:** Cascadia Mono / Consolas for logs, paths, and numeric lists.
- **Avoid:** serif fonts, extensive negative letter spacing, and oversized marketing headings.

## 4. Components

- **Buttons:** flat with visible boundaries; primary buttons use Copper Accent, with a darker pressed state and no outer glow.
- **Panels:** reserve panels for functional areas. Use radii below 10px, clear borders, and avoid nested cards.
- **Inputs:** left-aligned labels, consistent input height, and border-color changes on focus.
- **Tables:** pale gray headers, clear numeric columns, and compact engineering density.
- **Status:** communicate P0/P1 results with text and color, without decorative icon clusters.
- **Empty states:** state the next action, for example, “Save parameters to create the project directory.”

## 5. Layout

- Navigation and product identity on the left, working parameters in the center, review and outputs on the right.
- Keep a command bar at the top, with the main action always at the upper right.
- The summary bar shows four facts: local execution, GB/T style, P0 gate, and mock status.
- Avoid three-column marketing cards and decorative visual noise.
- Display all text in full; button width must not truncate labels.

## 6. Motion and interaction

The desktop prototype uses no complex animation. Feedback comes from hover, pressed and focus states, and status text. For long CAD executions, use stage progress and streaming logs rather than a spinner.

## 7. Anti-patterns

- Pure black, purple/blue neon gradients, or decorative glow.
- Marketing language or emoji.
- Buttons that squeeze or truncate text.
- Large, mostly empty demonstration forms.
- Review results hidden only in JSON: show key issues directly in the interface.
