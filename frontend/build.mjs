import { build, context } from 'esbuild';
const options = {
  entryPoints: ['frontend/react-bits.jsx'],
  bundle: true,
  outfile: 'static/dist/react-bits.js',
  jsx: 'automatic',
  format: 'iife',
  target: ['es2020'],
  minify: true,
  legalComments: 'linked',
  define: { 'process.env.NODE_ENV': '"production"' },
};
if (process.argv.includes('--watch')) {
  const watcher = await context(options);
  await watcher.watch();
  console.log('Watching React components…');
} else {
  await build(options);
  console.log('Built local React bundle and styles in static/dist/');
}
