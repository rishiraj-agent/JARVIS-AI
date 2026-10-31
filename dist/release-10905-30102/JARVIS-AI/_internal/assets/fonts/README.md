# Fonts

The app and theme use the operating system's installed interface fonts instead
of bundling font binaries.

- Native Windows UI: Segoe UI.
- Browser theme: Segoe UI, Inter, system UI, then generic sans-serif.
- CSS alias: `font-stack.css`.

This keeps the package small and avoids redistributing fonts with separate
licence terms. If using the theme on a platform without Segoe UI or Inter, the
browser automatically falls back to its system sans-serif.
