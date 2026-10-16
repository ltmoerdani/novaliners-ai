/* P1-04 witness: a causal endpoint resolves ONLY to its exact visible canonical location. A hidden
   RouteNode yields NO point — never the path terminal — so a declared cross-route relation can never
   be drawn to the wrong node. Run: node evals/test_maps_causal_endpoints.mjs */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, '..', 'app', 'static', 'js', 'maps-topology.js'), 'utf8');
new Function(src)();
const TOPO = globalThis.TOPO;

let failed = 0;
const check = (name, cond, detail) => {
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && detail ? ' | ' + detail : ''));
  if (!cond) failed += 1;
};

const visible = {
  nodes: [{ pathId: 'p1', id: 'n1', x: 10, y: 20, r: 3 }],
  here: { x: 0, y: 0, r: 9 }, goal: { x: 99, y: 0, r: 8 },
  lanes: [{ pathId: 'p1', terminal: { x: 55, y: 55 } }]
};

check('visible RouteNode resolves to itself',
  JSON.stringify(TOPO.causalVisiblePoint({ pathId: 'p1', nodeId: 'n1' }, visible))
    === JSON.stringify({ x: 10, y: 20, r: 3 }));
check('HIDDEN RouteNode -> null, no terminal substitution',
  TOPO.causalVisiblePoint({ pathId: 'p1', nodeId: 'n2' }, visible) === null);
check('path-only endpoint -> null, never the terminal',
  TOPO.causalVisiblePoint({ pathId: 'p1' }, visible) === null);
check('HERE resolves to the anchor', !!TOPO.causalVisiblePoint({ kind: 'HERE' }, visible));
check('GOAL resolves to the landmark', !!TOPO.causalVisiblePoint({ kind: 'GOAL' }, visible));
check('null endpoint -> null', TOPO.causalVisiblePoint(null, visible) === null);
check('missing lookup -> null (never throws)',
  TOPO.causalVisiblePoint({ pathId: 'p1', nodeId: 'n1' }, null) === null);

console.log();
if (failed) {
  console.log('FAIL - maps causal endpoints (' + failed + ' FAIL)');
  process.exit(1);
}
console.log('PASS - maps causal endpoints (7 checks)');
