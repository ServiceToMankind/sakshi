import { defineConfig } from 'vite';

// Sakshi frontend build configuration.
//
// GitHub Pages project pages are served from https://<user>.github.io/<repo>/,
// so the base path must match the repository name. For this repository the
// site lives under /sakshi/. If you fork or rename, update `base` accordingly.
// For a user/organization page (served from the domain root) set base to '/'.
export default defineConfig({
  base: '/sakshi/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
});
