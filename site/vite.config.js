import { defineConfig } from 'vite';

// Sakshi frontend build configuration.
//
// RELATIVE base so the same build works at BOTH mount points without rebuilding:
//   - GitHub project pages:  https://servicetomankind.github.io/sakshi/
//   - Custom domain (root):  https://sakshi.stmorg.in/
// A hardcoded '/sakshi/' base 404s every asset on the custom domain root; './'
// resolves assets relative to index.html, which is correct in both places. The
// app is hash-routed, so no path ever diverges from the document root.
export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
});
