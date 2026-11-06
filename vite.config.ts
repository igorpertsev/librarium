import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'


function figmaAssetResolver() {
  return {
    name: 'figma-asset-resolver',
    resolveId(id) {
      if (id.startsWith('figma:asset/')) {
        const filename = id.replace('figma:asset/', '')
        return path.resolve(__dirname, 'src/assets', filename)
      }
    },
  }
}

export default defineConfig({
  plugins: [
    figmaAssetResolver(),
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],

  build: {
    rollupOptions: {
      output: {
        // React and i18next change less often than the app: their own files stay cached across
        // releases. Everything else is split by Rollup along the lazily loaded pages.
        manualChunks(id) {
          if (/[\\/]node_modules[\\/](\.pnpm[\\/])?(react|react-dom|react-router|scheduler)[@\\/]/.test(id)) return 'react'
          if (/[\\/]node_modules[\\/](\.pnpm[\\/])?(i18next|react-i18next)[@\\/]/.test(id)) return 'i18n'
          return undefined
        },
      },
    },
  },
})
