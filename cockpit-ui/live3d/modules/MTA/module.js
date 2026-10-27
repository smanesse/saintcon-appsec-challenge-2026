/* SAINTCON 2026 — PER-MODULE CLOSE-UP TEMPLATE.
 *
 * Everything above the "MODULE WORK STARTS HERE" line is generic and has been
 * verified end to end (live3d/CONVERSION_BRIEF.md step 9).  Copy it VERBATIM.
 * If you find yourself editing it, either you have found a bug -- say so, it
 * affects all nine modules -- or you are solving a module problem in the wrong
 * place.
 *
 * Everything below that line is yours.  The TODOs are the whole job.
 *
 * The worked example with real props, real interaction and a real session
 * model is live3d/app.js (KVS).  Read it beside this file.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import { CSS3DLayer } from '../../css3d.js';
import { OcclusionSplit, attachForeground, makePlateFront } from '../../occlusion.js';
/* THE TWO REFIT FITTINGS.  Both are shared, module-agnostic frontends: every
 * anchor, size, part name, pivot and hotspot they use comes out of this
 * module's own `scene.json -> refit` / `-> mast`, which
 * live3d/pipeline/refit_port.py and live3d/pipeline/status_mast.py wrote.
 * live3d/design/FIX_UPLOAD.md and live3d/design/STATUS_AT_A_GLANCE.md are the
 * designs; MTA's build record is section 9 of this module's NOTES.md. */
import { mountRefit } from '../../refit.js';
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'MTA';                     // Subspace Comms Relay / SMTP
const A = '../../assets/' + CODE + '/';

const W = 1280, H = 720, D2R = Math.PI / 180;
const $ = id => document.getElementById(id);

function fail(msg) {
  const e = $('err');
  e.style.display = 'block';
  e.textContent = msg;
  throw new Error(msg);
}
addEventListener('error', ev => {
  const e = $('err'); e.style.display = 'block';
  e.textContent = 'PAGE ERROR: ' + ev.message;
});
async function getJSON(u) {
  const r = await fetch(u);
  if (!r.ok) fail('cannot fetch ' + u + ' (HTTP ' + r.status + ')\n\n' +
    'Serve the REPO ROOT, not this folder:\n' +
    '    cd <repo>/2026 && python3 -m http.server 8777');
  return r.json();
}

/* ===================================================================== 1 */
/* LOAD                                                                    */
const [S, MJ] = await Promise.all([getJSON(A + 'scene.json'),
                                   getJSON(A + 'materials.json')]);
const depth = new Float32Array(
  await (await fetch(A + S.depth.file)).arrayBuffer());
if (depth.length !== W * H)
  fail('depth.bin is ' + depth.length + ' floats, expected ' + W * H);
$('plate').src = A + 'plate.png';

/* ===================================================================== 2 */
/* RENDERER / CAMERA / LIGHTS — all from scene.json, nothing hardcoded      */
const renderer = new THREE.WebGLRenderer({
  canvas: $('gl'), alpha: true, antialias: true,
  premultipliedAlpha: true, preserveDrawingBuffer: true });
renderer.setClearAlpha(0);
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.AgXToneMapping;     // Blender's view transform
renderer.toneMappingExposure = 1.0;
RectAreaLightUniformsLib.init();
const scene = new THREE.Scene();

/* fov_y_deg comes from angle_x and the render aspect.  NEVER cam.data.angle_y:
 * it derives from sensor_HEIGHT and reports 26.99 where the truth is 22.895 --
 * a 49 px error.  The exporter writes it only under a name saying DO NOT USE. */
const camera = new THREE.PerspectiveCamera(
  S.camera.fov_y_deg, W / H, S.camera.clip[0], S.camera.clip[1]);
{
  const f = new THREE.Vector3().fromArray(S.camera.forward);
  const u = new THREE.Vector3().fromArray(S.camera.up);
  const z = f.clone().negate().normalize();
  const x = new THREE.Vector3().crossVectors(u, z).normalize();
  const y = new THREE.Vector3().crossVectors(z, x);
  camera.position.fromArray(S.camera.pos);
  camera.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
  camera.updateMatrixWorld();
}

/* Blender area lights are WATTS over a size x size square; L = P/(A*pi) is the
 * physically-right relative balance and light_gain is the single global scalar
 * reconciling watts with three's nits.  0.65 is the measured optimum for
 * RAYTRACED close plates (measurements.txt section 3). */
let GAIN = S.light_gain;
const lights = [];
for (const L of S.lights) {
  const Ar = Math.max(1e-6, L.size * L.size);
  const rl = new THREE.RectAreaLight(
    new THREE.Color().setRGB(...L.color, THREE.LinearSRGBColorSpace),
    (L.energy / (Ar * Math.PI)) * GAIN, L.size, L.size);
  rl.position.fromArray(L.pos);
  rl.lookAt(rl.position.x + L.dir[0], rl.position.y + L.dir[1],
            rl.position.z + L.dir[2]);
  rl.userData.base = L.energy / (Ar * Math.PI);
  scene.add(rl); lights.push(rl);
}
function setGain(g) { GAIN = g; for (const l of lights) l.intensity = l.userData.base * g; }
scene.add(new THREE.AmbientLight(new THREE.Color().setRGB(
  ...S.world_bg.slice(0, 3), THREE.LinearSRGBColorSpace), 1.0));

/* ===================================================================== 3 */
/* DEPTH COMPOSITING — hard discard against the baked linear depth pass     */
const dTex = new THREE.DataTexture(depth, W, H, THREE.RedFormat, THREE.FloatType);
dTex.minFilter = dTex.magFilter = THREE.NearestFilter;
dTex.needsUpdate = true;
const DU = {
  uDepth: { value: dTex },
  /* DRAWING-BUFFER size, never the 1280x720 stage size.  gl_FragCoord.xy is in
   * drawing-buffer pixels; pinning this shears the lookup by (pixelRatio - 1)
   * across the frame and the composite fails outright at 2.  README 16.5. */
  uRes: { value: new THREE.Vector2(W, H) },
  /* PER MODULE, AND MEASURED -- `scene.json -> ubias_m`.  This page shipped a
   * hardcoded 0.002 here, which is the old template's FLEET default and is
   * nobody's measurement: `if (vLinDepth > baked - uBias) discard` silently
   * deletes any live fragment standing less proud of the baked surface behind
   * it than uBias, with no error and a clean auditScene().  It cost PKT 5.7
   * rms and a 208 x 20 px emissive strip, and it cost IPM 8.58.  The value now
   * comes out of scene.json like every other module's; see
   * live3d/pipeline/live_depth.py for how it was derived for this one and
   * RESULTS.md for the sweep that confirms it. */
  uBias: { value: (typeof S.ubias_m === 'number') ? S.ubias_m : 0.0005 },
  uEnable: { value: 1 },
};
if (typeof S.ubias_m !== 'number')
  console.warn('scene.json has no `ubias_m`: the depth composite is running '
    + 'on a 0.5 mm guess.  A prop thinner than this is silently discarded '
    + 'into the plate.');
function syncDepthRes() { renderer.getDrawingBufferSize(DU.uRes.value); }
function attachDepthTest(mat) {
  mat.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, DU);
    sh.vertexShader = 'varying float vLinDepth;\n' + sh.vertexShader.replace(
      '#include <project_vertex>',
      '#include <project_vertex>\n  vLinDepth = -mvPosition.z;');
    sh.fragmentShader = `
uniform sampler2D uDepth; uniform vec2 uRes;
uniform float uBias; uniform float uEnable;
varying float vLinDepth;
` + sh.fragmentShader.replace('void main() {', `void main() {
  if (uEnable > 0.5) {
    vec2 duv = gl_FragCoord.xy / uRes;
    float baked = texture2D(uDepth, vec2(duv.x, 1.0 - duv.y)).r;
    // HARD discard.  A 1px feather measured strictly WORSE (75 -> 113 wrong
    // edge pixels): one depth sample per pixel carries no coverage, so there
    // is nothing to reconstruct.  measurements.txt section 2.
    if (vLinDepth > baked - uBias) discard;
  }`);
  };
  mat.needsUpdate = true;
}

/* ===================================================================== 4 */
/* THE MATERIAL SIDE CHANNEL                                               */
/* Blender's glTF exporter omits roughnessFactor/metallicFactor whenever the
 * Principled input is node-driven, and since the texture pass landed that is
 * essentially every material.  Skipping this measures rms 8.212 against 4.832
 * and everything looks flat for no visible reason. */
let matFixOn = true;
const patched = [];
/* every mesh dress() has handled, so facingAudit() below can ask which of them
 * FrontSide is silently deleting.  MTA shipped without this hook
 * (live3d/RESULTS.md item 11) and the two fittings are exactly the geometry
 * trap 21 names -- a vane and an iris leaf are a flag and a single triangle --
 * so it is added here rather than assumed away. */
const dressed = [];
function dress(mesh) {
  const m = mesh.material.clone();          // per-mesh: state swaps act alone
  mesh.material = m;
  const rec = MJ[m.name];
  const raw = { rough: m.roughness, metal: m.metalness };
  if (rec) {
    m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                   THREE.LinearSRGBColorSpace);
    if (rec.emit > 0) {
      m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                        THREE.LinearSRGBColorSpace);
      m.emissiveIntensity = rec.emit;
    }
  }
  m.side = THREE.FrontSide;
  m.envMapIntensity = 0;   // measured optimum, monotonically
  dressed.push(mesh);
  patched.push({ m, rec, raw });
  /* ORDER MATTERS.  attachDepthTest ASSIGNS onBeforeCompile; attachForeground
   * CHAINS onto whatever is there.  Swap them and the depth composite is gone,
   * silently. */
  attachDepthTest(m);
  attachForeground(m);
  return m;
}
function applyMatFix() {
  for (const p of patched) {
    if (!p.rec) continue;
    p.m.roughness = matFixOn ? p.rec.rough : p.raw.rough;
    p.m.metalness = matFixOn ? p.rec.metallic : p.raw.metal;
  }
}
/* TRAP 21.  `dress()` above forces THREE.FrontSide, and EEVEE does not
 * backface-cull while three does: a one-sided Blender surface is deleted with
 * no error and with split.auditScene() still []. OTA lost 14 single-triangle
 * chevrons that way.  This is the ONLY check that finds it.  Area-weighted
 * over world-space triangle normals, so a merely oblique mesh does not
 * register.  Reported to the console and to window.__mta.facing(); it is
 * deliberately NOT part of __occ.audit(), which the fleet harness asserts is
 * [] and which means something else. */
function facingAudit(camera) {
  const out = [];
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const n = new THREE.Vector3(), e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  for (const mesh of dressed) {
    if (mesh.material.side !== THREE.FrontSide) continue;
    const g = mesh.geometry, pos = g.attributes.position;
    if (!pos) continue;
    const idx = g.index;
    const tri = (idx ? idx.count : pos.count) / 3 | 0;
    let away = 0, tot = 0;
    for (let t = 0; t < tri; t += Math.max(1, (tri / 64) | 0)) {
      const i0 = idx ? idx.getX(t * 3) : t * 3;
      const i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1;
      const i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
      a.fromBufferAttribute(pos, i0).applyMatrix4(mesh.matrixWorld);
      b.fromBufferAttribute(pos, i1).applyMatrix4(mesh.matrixWorld);
      c.fromBufferAttribute(pos, i2).applyMatrix4(mesh.matrixWorld);
      n.copy(e1.subVectors(b, a)).cross(e2.subVectors(c, a));
      const area = n.length();
      if (area < 1e-12) continue;
      n.divideScalar(area);
      tot += area;
      if (n.dot(e1.subVectors(camera.position, a)) < 0) away += area;
    }
    if (tot > 0 && away / tot > 0.95)
      out.push(mesh.name || '(unnamed)');
  }
  if (out.length)
    console.warn('facingAudit: these dressed meshes face AWAY from the camera '
      + 'and FrontSide is discarding them -- set m.side = THREE.DoubleSide: '
      + out.join(', '));
  return out;
}
const loader = new GLTFLoader();
const load = url => new Promise((ok, no) => loader.load(url, ok, undefined, no));
/* every glb is exported in WORLD coordinates, so a prop is "pivot at the hub,
 * child translated back by the hub" and nothing else has to be reconciled. */
function pivotAt(hubArr) {
  const pivot = new THREE.Object3D();
  const inner = new THREE.Object3D();
  pivot.position.fromArray(hubArr);
  inner.position.fromArray(hubArr).multiplyScalar(-1);
  pivot.add(inner); scene.add(pivot);
  return { pivot, inner };
}

/* ===================================================================== 5 */
/* THE SPLIT + THE READOUT PLANES                                          */
const split = new OcclusionSplit({ canvas: $('glFront'), scene, camera, W, H });
{
  const tex = new THREE.TextureLoader().load(A + 'plate.png');
  /* NO colorSpace tag and flipY=false.  The plate-front quad is a
   * RawShaderMaterial, so three injects no sRGB decode/encode pair; tagging the
   * texture sRGB makes the GPU decode to linear and the raw shader then writes
   * linear values into an sRGB target -- the redrawn pixels come out visibly
   * darker than the <img> underneath them. */
  tex.flipY = false;
  tex.minFilter = tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  split.setPlateFront(makePlateFront({
    plateTex: tex, depthTex: dTex, W, H,
    fovYdeg: S.camera.fov_y_deg, near: S.camera.clip[0], far: S.camera.clip[1] }));
}

/* Content text is DOM, hung on the exporter's own plane frame by the same
 * projection the WebGL camera uses, so it lies ON the panel and stays sharp at
 * any window size (the browser rasterises AFTER the transform). */
const css3d = new CSS3DLayer($('css3d'), W, H);
const MPP = 0.0002;                 // metres per CSS pixel of the element
const readouts = [];                // { tp, plane, el, lines[], paint() }

function addReadout(tp) {
  const el = document.createElement('div');
  el.className = 'readout';
  el.style.width = (2 * tp.half_w / MPP) + 'px';
  el.style.height = (2 * tp.half_h / MPP) + 'px';
  const lines = document.createElement('div');
  lines.className = 'lines';
  el.appendChild(lines);
  const rec = css3d.add(el);
  const plane = split.addPlane(tp);
  const r = { tp, plane, el, lines, els: [], rec };
  /* type metrics: the ADVANCE is measured off Blender's own render in metres
   * per character, and the font size is solved from it.  Blender's FONT.size is
   * NOT an em (KVS: size 0.031 advances 0.0100 m, a ratio of 0.32). */
  if (tp.type) {
    const em = measureEmAdvance(lines);          // e.g. 0.600 for Courier New
    lines.style.fontSize = (tp.type.adv_m / em / MPP).toFixed(2) + 'px';
    lines.style.lineHeight = (tp.type.lead_m / MPP).toFixed(2) + 'px';
    lines.style.left = ((tp.half_w + tp.type.left_m) / MPP).toFixed(2) + 'px';
    lines.style.top =
      (((tp.half_h - tp.type.top_m) / MPP) - (tp.type.lead_m / MPP) / 2
       + (tp.type.base_adj || 0)).toFixed(2) + 'px';
    for (let i = 0; i < tp.type.n_lines; i++) {
      const d = document.createElement('div');
      lines.appendChild(d);
      r.els.push(d);
    }
  }
  r.paint = (arr) => {
    for (let i = 0; i < r.els.length; i++)
      r.els[i].textContent = arr && arr[i] !== undefined ? arr[i] : '';
  };
  r.place = (o, u, v, n) => {
    r.plane.o.copy(o); r.plane.u.copy(u); r.plane.v.copy(v); r.plane.n.copy(n);
    rec.matrix = new THREE.Matrix4().makeBasis(
      u.clone().multiplyScalar(MPP), v.clone().multiplyScalar(MPP), n)
      .setPosition(o);
  };
  r.place(new THREE.Vector3().fromArray(tp.origin),
          new THREE.Vector3().fromArray(tp.u),
          new THREE.Vector3().fromArray(tp.v),
          new THREE.Vector3().fromArray(tp.n));
  readouts.push(r);
  return r;
}

/* Measure the face's real advance rather than trusting a nominal em.  Doing
 * this before document.fonts.load() returns the FALLBACK's metrics and lays
 * the type out 21% wide -- that bug is recorded in TEXT_OCCLUSION.md. */
function measureEmAdvance(host) {
  const probe = document.createElement('div');
  probe.style.cssText =
    'position:absolute;visibility:hidden;white-space:pre;font-size:100px';
  probe.textContent = 'M'.repeat(40);
  host.appendChild(probe);
  const em = probe.offsetWidth / 40 / 100;
  probe.remove();
  return em;
}
await document.fonts.ready;

/* Declare every readout the module has.  The exporter writes them as
 * scene.json -> text_planes (a LIST).  KVS's original single `text_plane` is
 * accepted so the reference export keeps working. */
const PLANES = S.text_planes || [S.text_plane];
for (const tp of PLANES) addReadout(tp);

/* Debug: draw the declared rects, so a plane that is in the wrong place is
 * visible rather than merely wrong.  Hidden from the FRONT pass -- a wireframe
 * with depthTest off carries no occCull and would otherwise double-draw. */
const planeViz = new THREE.Group();
planeViz.visible = false;
for (const tp of PLANES) {
  const o = new THREE.Vector3().fromArray(tp.origin);
  const u = new THREE.Vector3().fromArray(tp.u).multiplyScalar(tp.half_w);
  const v = new THREE.Vector3().fromArray(tp.v).multiplyScalar(tp.half_h);
  const pts = [[-1, 1], [1, 1], [1, -1], [-1, -1], [-1, 1]].map(([a, b]) =>
    o.clone().addScaledVector(u, a).addScaledVector(v, b));
  const g = new THREE.BufferGeometry().setFromPoints(pts);
  const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xff30ff }));
  l.material.toneMapped = false; l.material.depthTest = false;
  planeViz.add(l);
}
scene.add(planeViz);
split.hideInFront.push(planeViz);

/* ===================================================================== 6 */
/* LAYOUT + LOOP.  One entry point for the pixel ratio, both renderers.     */
function setBothPR(r) {
  renderer.setPixelRatio(r);
  renderer.setSize(W, H, false);
  syncDepthRes();
  split.setPixelRatio(r);
}
function layout() {
  const b = $('viewport').getBoundingClientRect();
  const k = Math.min(b.width / W, b.height / H);
  $('stage').style.transform =
    `translate(${(b.width - W * k) / 2}px,${(b.height - H * k) / 2}px) scale(${k})`;
  setBothPR(Math.min(3, Math.max(1, (devicePixelRatio || 1) * k)));
}
addEventListener('resize', layout);

let t0 = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - t0) / 1000); t0 = now;
  onFrame(dt, now);
  /* ONE call, in the one order that is correct: upload the plane frames from
   * this frame's camera, draw the background half, lay the DOM on it, then
   * redraw the foreground half on top. */
  split.renderFrame(renderer, css3d);
  requestAnimationFrame(frame);
}

/* ===================================================================== 7 */
/* THE FLEET-STANDARD HOOK.  check/shoot_occlusion.mjs drives only this.    */
window.__occ = {
  code: CODE,
  pose: () => poseForCapture(),
  setText: (arr) => { (arr || []).forEach((lines, i) =>
                        readouts[i] && readouts[i].paint(lines)); },
  enable: v => { split.enabled = !!v; $('bOcc').classList.toggle('on', !!v); },
  info: () => ({ enabled: split.enabled, planes: split.planes.length,
                 pr: renderer.getPixelRatio(),
                 depthRes: [DU.uRes.value.x, DU.uRes.value.y],
                 frontRes: split.renderer
                   .getDrawingBufferSize(new THREE.Vector2()).toArray() }),
  audit: () => split.auditScene(),
  planes: () => readouts.map((r, i) => {
    const c = r.tp.corners_px;
    if (!c) return { max_err_px: 0, note: 'no corners_px exported' };
    const want = [[c.tl.x, c.tl.y], [c.tr.x, c.tr.y],
                  [c.br.x, c.br.y], [c.bl.x, c.bl.y]];
    const got = split.cornersPx(r.plane);
    return { i, max_err_px: Math.max(...want.map((w, j) =>
      Math.max(Math.abs(w[0] - got[j][0]), Math.abs(w[1] - got[j][1])))) };
  }),
  shotBoth: (pr) => {
    const old = renderer.getPixelRatio();
    if (pr) setBothPR(pr);
    split.renderFrame(renderer, css3d);
    const out = { back: renderer.domElement.toDataURL('image/png'),
                  front: $('glFront').toDataURL('image/png'),
                  pr: renderer.getPixelRatio(),
                  buf: [DU.uRes.value.x, DU.uRes.value.y] };
    if (pr) setBothPR(old);
    return out;
  },
  /* THE THREE MEASURED KNOBS, added at integration time so this module can be
   * swept by check/sweep_knob.mjs like the other eight.  `light_gain` and
   * `ubias_m` are per-module MEASUREMENTS and both shipped as fleet constants
   * that were wrong; the only way to measure one is to move it on the real
   * page and score the grab.  Getters with no argument.  CONVERSION_BRIEF
   * 5.2a. */
  gain: (g) => { if (g !== undefined) setGain(+g); return GAIN; },
  ubias: (v) => { if (v !== undefined) DU.uBias.value = +v;
                  return DU.uBias.value; },
  matfix: (v) => { if (v !== undefined) { matFixOn = !!v; applyMatFix(); }
                   return matFixOn; },
  stage: () => { const r = $('stage').getBoundingClientRect();
                 return { x: r.left, y: r.top, width: r.width, height: r.height }; },
};

$('bOcc').addEventListener('click', function () {
  window.__occ.enable(!split.enabled);
  this.textContent = split.enabled ? 'occlusion split' : 'split: OFF';
});
$('bText').addEventListener('click', function () {
  const off = document.body.classList.toggle('notext');
  this.classList.toggle('on', !off);
  this.textContent = off ? 'dom text: off' : 'dom text';
});
$('bPlanes').addEventListener('click', function () {
  planeViz.visible = !planeViz.visible;
  this.classList.toggle('on', planeViz.visible);
});
$('bDbg').addEventListener('click', function () {
  this.classList.toggle('on', document.body.classList.toggle('debug'));
});

/* =========================================================================
 * ======================  MODULE WORK STARTS HERE  ========================
 * =========================================================================
 *
 * MTA — "Subspace Comms Relay / Message Torpedo Room".  An SMTP relay.
 *
 * LIVE (four glbs, 89 meshes, 19,128 tris — the page counts it at runtime out
 * of the loaded index accessors, below):
 *   capsule.glb    the pneumatic message capsule.  The module SHIPS this as a
 *                  `frames` control — seven baked stills along the tube — and
 *                  frames are a baked approximation of movement, so it becomes
 *                  ONE live capsule that rides the rail continuously and swings
 *                  nose-out of the bell.  BRIEF step 2, rule 1.
 *   envelopes.glb  ten queued envelopes, card + flap + wax seal.  They appear
 *                  and disappear with queue depth: a state change, rule 3.
 *   wheel.glb      the STARTTLS scrambler, rotating about the panel normal.
 *                  Its twelve rotor letters are STAMPED lettering and stay
 *                  geometry — they have to turn with the wheel.
 *   handset.glb    the comms handset, hinging on its cradle.
 *
 * BAKED: everything else, all 85 static objects plus the shell.  The plate
 * carries correct pixels BEHIND every live object (the pigeonhole recesses,
 * the tube bed, the wheel well, the cradle).
 *
 * DOM (seven readout planes): the ten pigeonhole message IDs (one plane per
 * COLUMN, two rows of IDs each), the queue-depth odometer, and the slip on
 * the message pad.  Those are the three content readouts the occlusion audit
 * names, and they are values that come off the wire — so textContent only,
 * never innerHTML, anywhere in this file.
 */

const P = S.props;

/* ------------------------------------------------------------ TODO 1: PROPS */
const [gCap, gEnv, gWheel, gHand] = await Promise.all(
  [P.capsule.glb, P.queue.glb, P.scrambler.glb, P.handset.glb]
    .map(f => load(A + f)));
let liveTris = 0, liveMeshes = 0;
for (const g of [gCap, gEnv, gWheel, gHand])
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    dress(o);
    liveMeshes++;
    const ix = o.geometry.index;
    liveTris += (ix ? ix.count : o.geometry.attributes.position.count) / 3;
  });
applyMatFix();

const capsule = pivotAt(P.capsule.hub);
capsule.inner.add(gCap.scene);
/* the envelopes are already in world coordinates and never move, they only
 * appear and disappear, so they need no pivot at all. */
scene.add(gEnv.scene);
const envGroups = P.queue.groups.map(
  names => names.map(n => gEnv.scene.getObjectByName(n)).filter(Boolean));
const wheel = pivotAt(P.scrambler.hub);
wheel.inner.add(gWheel.scene);
const handset = pivotAt(P.handset.hinge);
handset.inner.add(gHand.scene);

const V = a => new THREE.Vector3().fromArray(a);
const CAP_HUB = V(P.capsule.hub), CAP_AX = V(P.capsule.axis).normalize(),
      CAP_OUT = V(P.capsule.out_axis).normalize(),
      CAP_SW = V(P.capsule.swing_axis).normalize();
const WHEEL_AX = V(P.scrambler.axis).normalize();
const HAND_AX = V(P.handset.axis).normalize();
const RAIL0 = P.capsule.stops_m[0];
const RAIL1 = P.capsule.stops_m[P.capsule.stops_m.length - 1];

/* the three measured ink colours, and centred lines: every FONT object in this
 * module is align_x='CENTER', so the DOM lines centre in the rect the same way
 * rather than being laid out from a left margin. */
readouts.forEach((r, i) => {
  const tp = PLANES[i];
  if (tp.ink) r.el.style.color = 'rgb(' + tp.ink.join(',') + ')';
  r.lines.style.left = '0px';
  r.lines.style.width = (2 * tp.half_w / MPP) + 'px';
  r.lines.style.textAlign = 'center';
  /* the slip's third line ("ops@fleet") is set at a smaller FONT.size in
   * build.py than the two above it, so it gets its own measured advance. */
  const per = tp.type && tp.type.line_adv_m;
  if (per) {
    const em = measureEmAdvance(r.lines);
    r.els.forEach((el, k) => {
      el.style.fontSize = (per[k] / em / MPP).toFixed(2) + 'px';
    });
  }
});

$('note').textContent =
  liveTris + ' tris · ' + liveMeshes + ' live meshes · ' +
  S.lights.length + ' area lights · ' + PLANES.length + ' readout planes';

/* ------------------------------------------------- TODO 2: THE SESSION MODEL
 * MTA speaks SMTP.  The pigeonholes and the odometer are the relay's own queue
 * (the admin `queue` listing) once it has answered; until then, and offline,
 * they are the canned q5 rest state.  pose() restores canned q5 so RESULTS.md
 * still matches.
 *
 * Track 01 owns the shared /api/* client and remaps cockpit MTA → catalog MAIL
 * before POST.  This close-up has no api.js: it fetch()es {code:'MTA'}.  Until
 * 01 remaps at catalog lookup, a standalone MAIL POST still hits mail_send
 * because this copy's interactors.dispatch accepts MAIL and MTA.
 *
 * EVERY value below reaches the readout through textContent (the template's
 * r.paint() -> els[i].textContent).  There is no innerHTML in this file and
 * there must never be one: a recipient address, a message ID, and a queue
 * URL are bytes off the wire in the real product. */
const REST_N = P.queue.states.find(s => s[0] === P.queue.rest)[1];
const HEX = '0123456789abcdef';
let queue = [];                     // {id, name, to, local}, oldest first
let queueTotal = null;              // the relay's count; null = canned
/* the slip on the pad: the id the relay gave the last post.  The capture
 * pose paints scene.json's own rest text instead. */
let slip = null;
let opCount = 0;
let starttlsArmed = false;
let sending = false;

function mintId() {
  const b = new Uint8Array(6);
  crypto.getRandomValues(b);
  let h = '';
  for (const v of b) h += HEX[(v >> 4) & 15] + HEX[v & 15];
  return h.slice(0, 6);            // the 6 the pigeonhole slip shows
}
function shortQueuedId(queuedAs) {
  const s = String(queuedAs || '');
  const m = /\.([0-9a-fA-F]{6,})\.eml$/i.exec(s);
  if (m) return m[1].slice(0, 6).toLowerCase();
  const hex = s.replace(/[^0-9a-fA-F]/g, '');
  return (hex.slice(0, 6) || mintId()).toLowerCase();
}
function readDraft() {
  return {
    from: $('mtaFrom').value,
    to: $('mtaTo').value,
    subject: $('mtaSubj').value,
    body: $('mtaBody').value,
  };
}
function writeDraft(d) {
  $('mtaFrom').value = d.from || '';
  $('mtaTo').value = d.to || '';
  $('mtaSubj').value = d.subject || '';
  $('mtaBody').value = d.body || '';
}
function hasDraft() {
  const d = readDraft();
  return !!(d.from || d.to || d.subject || d.body);
}
function readStamp() {
  return {
    user: $('mtaUser').value,
    pass: $('mtaPass').value,
    mech: $('mtaMech').value || 'PLAIN',
  };
}
/* ---- what the player is told.  The dev #note is page chrome; this line on
 * the form is the station's own answer. */
function setStatus(text, kind) {
  const el = $('formReply');
  el.textContent = text || '';
  el.className = kind || '';
  el.title = text || '';
}
function report(res, okText) {
  if (res.ok) setStatus(res.result.summary || okText || '', 'ok');
  else setStatus((res.result && res.result.summary) || res.error
                 || 'no answer from the station', 'err');
}

/* ---- the printout at the foot of the form: the SMTP session the relay just
 * held, the queue listing, or one queued message.  `cls(line)` tags a line;
 * every line is painted with textContent only. */
let printout = null;                // {title, note, lines[], cls}
function setPrintout(title, note, lines, cls, top) {
  printout = { title, note: note || '',
               lines: (lines || []).map(m => String(m == null ? '' : m)), cls, top };
  renderPrintout();
}
function renderPrintout() {
  const pr = printout;
  const pre = $('formLines');
  $('formTitle').textContent = pr ? pr.title : 'Message form';
  $('formSize').textContent = pr ? pr.note : '';
  pre.textContent = '';
  if (!pr || !pr.lines.length) {
    const e = document.createElement('span');
    e.className = 'empty';
    e.textContent = pr ? '(nothing printed)'
      : 'Post the message, or click a pigeonhole to read what is queued.';
    pre.appendChild(e);
    return;
  }
  for (const line of pr.lines) {
    const e = document.createElement('div');
    const c = pr.cls && pr.cls(line);
    if (c) e.className = c;
    e.textContent = line;
    pre.appendChild(e);
  }
  pre.scrollTop = pr.top ? 0 : pre.scrollHeight;   // a session reads to its foot
}
/* client lines are "> ..."; a reply that is not 2xx/3xx is the relay saying no */
const smtpCls = l => /^> /.test(l) ? 'sent' : (/^[45]\d\d[ -]/.test(l) ? 'bad' : '');
function paintTls() {
  const el = $('mtaTls');
  el.textContent = starttlsArmed ? 'STARTTLS armed' : 'STARTTLS idle';
  el.className = 'tls' + (starttlsArmed ? ' on' : '');
  const cb = $('mtaStarttls');
  if (cb) cb.checked = !!starttlsArmed;
}
function armStarttls(v) {
  starttlsArmed = !!v;
  paintTls();
}
function playDefaults() {
  writeDraft({
    from: 'bridge@auditor-7.ship',
    to: 'ops@station.example',
    subject: 'Bridge console test',
    body: 'Subspace relay check.',
  });
}

/* POST /api/interact with cockpit code MTA.  Track 01 must remap MTA→MAIL at
 * catalog lookup; this file does not import api.js.  Errors and offline land
 * on the form via textContent — never innerHTML (AUTH PLAIN is base64). */
async function interact(action, params) {
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'MTA', action, params }),
    });
    let data = {};
    try { data = await r.json(); } catch { data = {}; }
    const res = data.result || data;
    if (!r.ok)
      return { ok: false, error: data.error || res.error || ('HTTP ' + r.status),
               result: res };
    return { ok: !!res.ok, error: res.error, result: res };
  } catch (e) {
    return { ok: false, error: 'coordinator unreachable', result: {}, offline: true };
  }
}

async function commitSend() {
  if (sending) return;
  const draft = readDraft();
  const stamp = readStamp();
  /* No client-side stamp gate: the service accepts or rejects. */
  const params = {
    from: draft.from, to: draft.to,
    subject: draft.subject, body: draft.body,
  };
  if (stamp.user) params.user = stamp.user;
  if (stamp.pass) params.pass = stamp.pass;
  if (stamp.user && stamp.pass) params.mech = stamp.mech || 'PLAIN';
  if (starttlsArmed) params.starttls = 'true';
  sending = true;
  $('formPost').disabled = true;
  setStatus('posting…', 'busy');
  const out = await interact('send', params);
  sending = false;
  $('formPost').disabled = false;
  report(out, 'posted');
  /* the session the relay held, line for line, pass or fail */
  const tr = (out.result && out.result.transcript) || [];
  const qid = out.result && out.result.queued_as;
  if (tr.length || out.ok)
    setPrintout(out.ok ? 'Posted' : 'Not posted',
                qid ? 'queued as ' + shortQueuedId(qid) : '',
                tr.join('\n').split(/\r?\n/), smtpCls);
  if (!out.ok) return;
  slip = ['LAST POST', 'QUEUED AS', shortQueuedId(qid)];
  armStarttls(false);
  /* re-read the rack from the relay, so the new envelope is the real one */
  if (!(await pullQueue(true))) {
    enqueue(shortQueuedId(qid), draft.to, { local: false, name: qid });
    paintAll();
  }
}

/* The relay's queue onto the rack: the newest ten in the pigeonholes, oldest
 * first, and the whole count on the odometer.  Offline the rack keeps what it
 * had: never invent mail. */
async function pullQueue(quiet) {
  const res = await interact('queue', {});
  if (!quiet) report(res);
  if (!res.ok || frozen) return null;
  const entries = (Array.isArray(res.result.entries) ? res.result.entries : [])
    .slice().sort((a, b) => String(a.receivedAt || '').localeCompare(String(b.receivedAt || '')));
  queueTotal = entries.length;
  queue = entries.slice(-10).map(e => ({
    id: shortQueuedId(e.name), name: e.name, to: e.to, local: false }));
  paintAll();
  return entries;
}
async function printQueue() {
  setStatus('reading the queue…', 'busy');
  const entries = await pullQueue(false);
  if (!entries) return;
  const n = entries.length;
  setPrintout('Queue', n + ' queued', entries.slice().reverse().map(e =>
    shortQueuedId(e.name) + '  ' + (e.to || '?') + '  ' + (e.subject || '')),
    null, true);
}
async function printMessage(m) {
  setStatus('reading ' + m.id + '…', 'busy');
  const res = await interact('queue', { name: m.name });
  report(res, 'queue ' + m.id);
  if (!res.ok) return;
  const raw = String(res.result.raw || '');
  const e = res.result.entry || {};
  setPrintout('Pigeonhole ' + m.id, (e.size != null ? e.size + ' bytes' : ''),
              [(e.from || '?') + ' -> ' + (e.to || '?'), ''].concat(raw.split(/\r?\n/)),
              null, true);
}

function rsetEnvelope() {
  writeDraft({ from: '', to: '', subject: '', body: '' });
  setStatus('RSET: envelope cleared');
}

function resetSession() {
  queue = [];
  queueTotal = null;
  for (let i = 0; i < REST_N; i++)
    queue.push({ id: P.queue.ids[i], to: P.queue.to[i], local: false });
  slip = null;
  opCount = 0;
  sending = false;
  writeDraft({ from: '', to: '', subject: '', body: '' });
  $('mtaUser').value = '';
  $('mtaPass').value = '';
  $('mtaMech').value = 'PLAIN';
  setStatus('');
  printout = null;
  renderPrintout();
  armStarttls(false);
}
function enqueue(id, to, rec) {
  if (queue.length >= 10) return false;
  queue.push({ id: id || mintId(),
               to: to || P.queue.to[(opCount++) % P.queue.to.length],
               name: rec && rec.name, local: !!(rec && rec.local) });
  if (queueTotal != null) queueTotal++;
  return true;
}
function paintAll() {
  for (let c = 0; c < 5; c++)
    readouts[c].paint([queue[c] ? queue[c].id : '',
                       queue[c + 5] ? queue[c + 5].id : '']);
  const n = queueTotal != null ? Math.min(99, queueTotal) : queue.length;
  readouts[5].paint([('0' + n).slice(-2)]);
  readouts[6].paint(slip || ['LAST POST', 'QUEUED AS', '------']);
  for (let i = 0; i < envGroups.length; i++)
    for (const o of envGroups[i]) o.visible = i < queue.length;
}

/* ------------------------------------------------------- TODO 3: ANIMATION */
let frozen = false;                 // set by pose(): the capture must be still
/* THE REFIT PORT and THE TELLTALE MAST.  Mounted at the bottom of this file,
 * after the hotspot helper exists; declared here because onFrame() and
 * poseForCapture() both reach them and both are defined before the mount. */
let refit = null;
let mast = null;
let capT = -1;                      // -1 = parked at the exported rest stop
let wheelAng = 0, wheelVel = 0, dragging = null;
let handAng = P.handset.angles.cradled, handWant = handAng;

function applyCapsule() {
  let along = 0, out = 0, swing = 0;
  if (capT >= 0) {
    if (capT < 0.78) {              // down the rail, inside the tube
      const u = capT / 0.78;
      along = RAIL0 + (RAIL1 - RAIL0) * u;
    } else {                        // elbow: swings nose-out of the bell mouth
      const u = (capT - 0.78) / 0.22;
      const e = u * u * (3 - 2 * u);
      along = RAIL1 + (P.capsule.bell.along_m - RAIL1) * e;
      out = P.capsule.bell.out_m * e;
      swing = P.capsule.bell.swing_deg * e;
    }
  }
  capsule.pivot.position.copy(CAP_HUB)
    .addScaledVector(CAP_AX, along).addScaledVector(CAP_OUT, out);
  capsule.pivot.quaternion.setFromAxisAngle(CAP_SW, swing * D2R);
}
function applyControls() {
  wheel.pivot.quaternion.setFromAxisAngle(WHEEL_AX, wheelAng * D2R);
  handset.pivot.quaternion.setFromAxisAngle(HAND_AX, handAng * D2R);
  applyCapsule();
}

function onFrame(dt, now) {
  /* BOTH FITTINGS TICK BEFORE THE `frozen` GATE, and that is deliberate.
   * `frozen` is this module's capture latch -- it stops the capsule, the
   * scrambler's momentum and the drain timer so a screenshot is still.  The
   * port and the mast are not this module's state: they own NO timer of their
   * own (README 16.8 is a module that failed a byte-identical capture for a
   * 520 ms setInterval nobody cleared), and every animation they have runs off
   * these two calls.  Gate them behind `frozen` and the iris would stop
   * half-open the moment anything posed the page.  pose() HIDES them instead,
   * which is FIX_UPLOAD section 0 decision 3 and the reason every number in
   * this module's NOTES reproduces byte-identically. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  if (frozen) return;
  if (capT >= 0) {
    capT += dt * 0.42;
    if (capT >= 1.45) capT = -1;    // arrived, held, then the tube swallows it
  }
  if (!dragging) {                  // momentum, then a pull to the nearest detent
    wheelAng += wheelVel * dt;
    wheelVel *= Math.pow(0.16, dt);
    if (Math.abs(wheelVel) < 8) {
      const d = P.scrambler.detent;
      const snap = Math.round(wheelAng / d) * d;
      wheelAng += (snap - wheelAng) * Math.min(1, dt * 8);
      wheelVel *= 0.5;
    }
  }
  handAng += (handWant - handAng) * Math.min(1, dt * 9);
  applyControls();
  tickHeld(dt);
}

/* ----------------------------------------------------- TODO 4: INTERACTION */
function stagePt(ev) {
  const b = $('stage').getBoundingClientRect();
  return { x: (ev.clientX - b.left) * W / b.width,
           y: (ev.clientY - b.top) * H / b.height };
}
function hotspot(rect, title, onDown) {
  const d = document.createElement('div');
  d.className = 'hot';
  d.style.left = rect.x + 'px'; d.style.top = rect.y + 'px';
  d.style.width = rect.w + 'px'; d.style.height = rect.h + 'px';
  d.title = title;                       // textContent-safe: no markup
  d.addEventListener('pointerdown', ev => {
    frozen = false; onDown(ev, d);
  });
  $('hots').appendChild(d);
  return d;
}
/* THE SHARED FITTINGS WANT A DIFFERENT HOTSPOT SIGNATURE, and this is fleet
 * convention drift, not an MTA quirk -- README section 7's own subject.
 * `refit.js` and `mast.js` call `o.hotspot(rect, label, el => {...})`: the
 * third argument is a WIRER that is handed the element once, at creation, and
 * attaches its own listeners (KVS, MQB and OTA are written that way).  MTA,
 * PKT, IPM, FMM and DNSM instead take a HANDLER that is called on every
 * pointerdown.  Passing this module's `hotspot` straight to mountRefit()
 * silently mis-wires it: the "wirer" is invoked with (ev, el) on the first
 * press and `h.addEventListener` throws on a PointerEvent.
 * So the fittings get their own creator, in the convention they document.  It
 * deliberately does NOT clear `frozen`: unfreezing the module because someone
 * opened the port would restart this module's own easing as a side effect,
 * and the fittings tick outside that gate anyway (see onFrame). */
function wireHotspot(rect, label, wire) {
  const d = document.createElement('div');
  d.className = 'hot';
  d.style.left = rect.x + 'px'; d.style.top = rect.y + 'px';
  d.style.width = rect.w + 'px'; d.style.height = rect.h + 'px';
  d.title = label;                       // textContent-safe: no markup
  $('hots').appendChild(d);
  wire(d);
  return d;
}

/* ---- HELD PAPER.  The message form is DOM in a second CSS3D layer, laid on
 * the panel's face basis.  Its `k` runs 0..1: 0 is the top form of the white
 * pad, 1 is the form held up toward the camera over the left bulkhead.
 * onFrame() eases k toward `want`; no timers. */
const FACE_U = V(S.panel.u), FACE_V = V(S.panel.v), FACE_N = V(S.panel.n);
const held = new CSS3DLayer($('held'), W, H);
const FORM = { el: $('mtaForm'), w: 560, h: 700, k: 0, want: 0,
               at: { x: 192, y: 366, w: 318 } };
FORM.rec = held.add(FORM.el);
/* THE PAD is the white card the slip is printed on.  scene.json
 * declares only the slip, so the card's own size is measured off plate.png
 * (593..725 x 601..667) and carried onto the face at the slip's scale. */
const SLIP = PLANES[6];                // the slip is the seventh readout
const PAD = { x: 593, y: 601, w: 132, h: 66 };
const PAD_REST = (() => {
  const c = SLIP.corners_px;
  const mpp = 2 * SLIP.half_w / (c.tr.x - c.tl.x);
  const sy = (c.tl.y + c.bl.y) / 2, sx = (c.tl.x + c.tr.x) / 2;
  const o = V(SLIP.origin)
    .addScaledVector(FACE_U, (PAD.x + PAD.w / 2 - sx) * mpp)
    .addScaledVector(FACE_V, (sy - (PAD.y + PAD.h / 2)) * mpp);
  return { o, mx: PAD.w * mpp / FORM.w, my: PAD.h * mpp / FORM.h };
})();
/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the pad's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = camera.position.distanceTo(PAD_REST.o) * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  const m = at.w * perPx / elW;
  return { o, mx: m, my: m };
}
const FORM_UP = heldPose(FORM.at, FORM.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function basis(o, mx, my) {
  return new THREE.Matrix4().makeBasis(FACE_U.clone().multiplyScalar(mx),
    FACE_V.clone().multiplyScalar(my), FACE_N).setPosition(o);
}
function tickHeld(dt) {
  if (FORM.k !== FORM.want) {
    const step = dt * 4;
    FORM.k = FORM.want > FORM.k ? Math.min(FORM.want, FORM.k + step)
                                : Math.max(FORM.want, FORM.k - step);
    if (FORM.k === 0) FORM.el.hidden = true;
  }
  if (!FORM.el.hidden) {
    const e = ease(FORM.k);
    FORM.rec.matrix = basis(PAD_REST.o.clone().lerp(FORM_UP.o, e),
      PAD_REST.mx + (FORM_UP.mx - PAD_REST.mx) * e,
      PAD_REST.my + (FORM_UP.my - PAD_REST.my) * e);
  }
  held.render(camera);
}

/* FOCUS WITHOUT MOVING THE SCENE.  #viewport is overflow:hidden, which is
 * still a scroll container: focus without scrolling, then put the clipping
 * ancestors back at 0 in case anything scrolled them anyway. */
function resetClipScroll() {
  const vp = $('viewport');
  vp.scrollLeft = 0; vp.scrollTop = 0;
  const de = document.documentElement;
  de.scrollLeft = 0; de.scrollTop = 0;
  document.body.scrollLeft = 0; document.body.scrollTop = 0;
}
function focusStill(el) {
  if (!el) return;
  try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
  resetClipScroll();
}
$('viewport').addEventListener('scroll', resetClipScroll);
addEventListener('scroll', resetClipScroll);

/* ---- the form: tear it off the pad / lay it back, and where focus goes
 * back to. */
let formOpener = null;
let padHot = null;
function openForm(then) {
  const el = FORM.el;
  const wasDown = el.hidden || FORM.want === 0;
  if (wasDown) {
    const a = document.activeElement;
    formOpener = (a && a !== document.body && a !== document.documentElement
                  && !el.contains(a)) ? a : null;
  }
  frozen = false;
  el.hidden = false;
  FORM.want = 1;
  /* Keyboard users land on the form; Tab leaves it freely and Escape or the
   * X always put it down. */
  if (wasDown) focusStill(then || $('mtaFormCard'));
}
function closeForm() {
  const el = FORM.el;
  const wasUp = FORM.want === 1;
  const a = document.activeElement;
  const focusWasHere = !a || a === document.body || a === document.documentElement
    || el.contains(a);
  FORM.want = 0;
  if (wasUp && focusWasHere) {
    const back = (formOpener && formOpener.isConnected && !el.contains(formOpener))
      ? formOpener : padHot;
    formOpener = null;
    focusStill(back);
  }
}
function formUp() { return FORM.want > 0; }

/* the tube fetches the queue: the capsule runs while the relay answers */
hotspot(P.capsule.hotspot, P.capsule.label + ' — fetch the queue', () => {
  if (capT < 0) capT = 0;
  pullQueue(!formUp()).then(() => { if (formUp()) printQueue(); });
});
/* the rack reads: a click on a pigeonhole prints that message off the relay,
 * a click on an empty one prints the queue listing */
function pigeonholeAt(pt) {
  let col = 0, best = Infinity;
  for (let c = 0; c < 5; c++) {
    const k = PLANES[c].corners_px;
    const d = Math.abs(pt.x - (k.tl.x + k.tr.x + k.bl.x + k.br.x) / 4);
    if (d < best) { best = d; col = c; }
  }
  const k = PLANES[col].corners_px;
  const row = pt.y < (k.tl.y + k.bl.y) / 2 ? 0 : 1;
  return col + 5 * row;
}
hotspot(P.queue.hotspot, P.queue.label + ' — read a queued message', ev => {
  const m = queue[pigeonholeAt(stagePt(ev))];
  openForm();
  if (m && m.name) printMessage(m);
  else printQueue();
});
hotspot(P.handset.hotspot, P.handset.label + ' — lift / cradle', () => {
  const cradled = P.handset.angles.cradled;
  if (handWant === cradled) {
    handWant = P.handset.angles.lifted;
    return;
  }
  /* cradling it posts what is on the form, so the form comes up to answer */
  openForm();
  if (hasDraft()) commitSend();
  else rsetEnvelope();
  handWant = cradled;
});
hotspot(P.scrambler.hotspot, P.scrambler.label + ' — throw', (ev, el) => {
  /* angular drag about the wheel's PROJECTED hub, with momentum, the same
   * shape as app.js section 9.  Screen y runs down, so a clockwise drag is a
   * positive screen angle and a negative rotation about the panel normal
   * (which points out of the screen at the pilot). */
  const hub = P.scrambler.pivot_px;
  const ang = pt => Math.atan2(pt.y - hub.y, pt.x - hub.x) / D2R;
  let last = ang(stagePt(ev)), lastT = performance.now();
  const ang0 = wheelAng;
  dragging = true; wheelVel = 0;
  el.setPointerCapture(ev.pointerId);
  const move = e2 => {
    const now = performance.now();
    let a = ang(stagePt(e2)), d = a - last;
    while (d > 180) d -= 360;
    while (d < -180) d += 360;
    wheelAng -= d;
    const dt = Math.max(1, now - lastT) / 1000;
    wheelVel = -d / dt;
    last = a; lastT = now;
    applyControls();
  };
  const up = () => {
    dragging = null;
    if (Math.abs(wheelAng - ang0) >= P.scrambler.detent)
      armStarttls(true);
    else paintTls();
    el.removeEventListener('pointermove', move);
    el.removeEventListener('pointerup', up);
    el.removeEventListener('pointercancel', up);
  };
  el.addEventListener('pointermove', move);
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', up);
});
/* The pad.  Its rect is the white card, measured above. */
padHot = hotspot(PAD, 'MESSAGE FORM — tear off a form to write and post', () => {});
padHot.tabIndex = 0;
padHot.setAttribute('role', 'button');
padHot.addEventListener('click', () => openForm());
padHot.addEventListener('keydown', ev => {
  if (ev.key !== 'Enter' && ev.key !== ' ') return;
  ev.preventDefault();
  openForm();
});
{
  const on = (el, ev, fn) => el.addEventListener(ev, fn);
  on($('formClose'), 'click', () => closeForm());
  on($('formPost'), 'click', () => commitSend());
  on($('formRset'), 'click', () => rsetEnvelope());
  on($('mtaStarttls'), 'change', () => armStarttls($('mtaStarttls').checked));
  /* Ctrl/Cmd+Enter posts from anywhere on the form; Enter in a one-line field
   * moves to the next one, never on key-repeat. */
  const fields = ['mtaFrom', 'mtaTo', 'mtaSubj', 'mtaBody'].map($);
  on($('mtaFormCard'), 'keydown', ev => {
    if (ev.key !== 'Enter' || ev.repeat) return;
    if (ev.ctrlKey || ev.metaKey) { ev.preventDefault(); commitSend(); return; }
    const i = fields.indexOf(ev.target);
    if (i >= 0 && ev.target.tagName === 'INPUT') {
      ev.preventDefault();
      focusStill(fields[i + 1]);
    }
  });
  /* Escape lays the form back on the pad.  Stopped here so nothing else in
   * this page (the refit docket's own Escape) also reacts.  The cockpit's
   * Escape lives on its own window and never sees keys typed in this iframe. */
  const closeTop = () => {
    if (FORM.want) { closeForm(); return true; }
    return false;
  };
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !FORM.want) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTop();
  });
  /* exposed so the shell can ask "did the module use this Escape?" first */
  window.__closeOverlay = closeTop;
}

/* ---- THE REFIT PORT -------------------------------------------------------
 * Nine lines, and none of them is MTA-specific: the anchor, the size, the part
 * names, the leaf pivots and the hotspot all come out of `scene.json -> refit`,
 * which `pipeline/refit_port.py` wrote.  It bolts to the SHIP STRUCTURE beside
 * the instrument -- the left bulkhead -- never to the faceplate, so no control
 * moves and no readout plane moves.  It declares NO readout plane: all of its
 * text is the screen-space docket, so MTA still reports SEVEN planes.
 * Passing `dress` is what chains attachDepthTest and then attachForeground onto
 * the port's materials; skip it and split.auditScene() correctly reports
 * double-blending. */
refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is MTA-specific either.
 *
 * IT IS NOT ON THE PORT'S SERVICE RAIL, and that is measured, not preferred.
 * STATUS_AT_A_GLANCE 11.2 mounts this fitting on the port's rail at 1.5 W and
 * tells the implementer to "solve the rail first and then confirm my 260 x 92
 * footprint lands on it".  On MTA it does not and cannot: the port's carrier
 * is a 265 px-wide strip of left bulkhead, and the rail runs off the far edge
 * of it 40 px past the port's own claimed half.  Solved on the rail, even a
 * 60 px mast overhangs the panel's left frame rail and `solve_mast()` answers
 * with a 24.2 mm lift -- 58.5 x ubias_m against KVS's 16.0 -- climbing to
 * 49.1 mm at 190 px.  That is a shelf floating in front of the instrument, not
 * a fitting bolted to it.  So this module takes `status_mast.py`'s second,
 * documented route: `--at PX,PY`, a sub-plate bolted to the panel, which is
 * STATUS_AT_A_GLANCE 6.1's ORIGINAL design and 6.2 rule 4's permitted home.
 * The numbers and the whole argument are in section 9 of this module's NOTES.
 *
 * It declares NO readout plane.  Its words are the screen-space caption in
 * live3d/mast.css, so check_occlusion.py's question 5, the dial-face rule and
 * check_text.py are not engaged by it.  `readouts.length` is still 7. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot: wireHotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

/* the toolbar line, re-stated now that both fittings are on the page.  It is
 * set once above, before the mount, because `liveTris` is this module's own
 * count and must stay quotable on its own. */
$('note').textContent =
  liveTris + ' tris + ' + (refit ? refit.tris : 0) + ' refit + ' + mast.tris + ' mast · '
  + liveMeshes + ' live meshes · ' + S.lights.length + ' area lights · '
  + PLANES.length + ' readout planes · uBias '
  + (DU.uBias.value * 1000).toFixed(3) + ' mm';

/* ------------------------------------------------- TODO 5: THE CAPTURE POSE
 * DETERMINISTIC, and it must be the state export_mta.py rendered
 * gt_full_read.png in, or check/compare.py measures the mismatch instead of
 * the renderer: queue q5 (five envelopes, top row), capsule parked at stop 3,
 * scrambler at 0, handset cradled.  Nothing animating. */
function poseForCapture() {
  /* HIDE BOTH FITTINGS.  Every number in live3d/RESULTS.md and sections 1-5 of
   * this module's NOTES was captured from pose() against Blender renders that
   * contain neither of them; hiding them reproduces all of it unchanged and
   * re-renders nothing.  FIX_UPLOAD section 0 decision 3.  The fittings' own
   * behaviour is measured with them SHOWN --
   * `window.__refit.show(true);window.__mast.show(true)` -- which is a separate
   * capture, and that report is byte-identical to this one. */
  if (refit) refit.pose();
  if (mast) mast.pose();
  frozen = true;
  capT = -1;
  wheelAng = 0; wheelVel = 0; dragging = null;
  handAng = handWant = P.handset.angles.cradled;
  FORM.want = FORM.k = 0;
  FORM.el.hidden = true;
  resetSession();
  slip = S.readout_text[6];
  paintAll();
  applyControls();
}

/* A module-private capture hook, ALONGSIDE the fleet-standard window.__occ and
 * never instead of it: check/shoot_occlusion.mjs drives only __occ, and this
 * exists so the two comparisons that are not part of that contract can be shot
 * from the real page rather than argued about.
 *   matfix(v)   the materials.json A/B (BRIEF 5.2: "materials.json on beats
 *               raw glTF off").  The template has no toolbar switch for it and
 *               `matFixOn` is module scope, so this is the only way to measure
 *               it without editing above the line.
 *   capsule(t)  park the live capsule at a chosen point of its travel.  At
 *               t = 1 it is nose-out of the bell mouth, which is the one pose
 *               where LIVE geometry crosses a declared readout rect. */
window.__mta = {
  matfix: v => { matFixOn = !!v; applyMatFix(); },
  capsule: t => { frozen = true; capT = t; applyControls(); },
  queue: n => { resetSession(); while (queue.length > n) queue.pop();
                while (queue.length < n) enqueue(); paintAll(); },
  handset: v => { frozen = true; handAng = handWant =
    P.handset.angles[v ? 'lifted' : 'cradled']; applyControls(); },
  form: v => { if (v !== undefined) { if (v) openForm(); else closeForm(); }
               return { want: FORM.want, k: FORM.k, printout }; },
  state: () => ({ queue: queue.map(m => m.id), queueTotal, slip,
                  capT, wheelAng, handAng, matFixOn,
                  draft: readDraft(), starttlsArmed,
                  authUser: $('mtaUser').value }),
  /* trap 21's only real check, now that this page carries a vane and six iris
   * leaves.  Expect []. */
  facing: () => facingAudit(camera),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
};

resetSession();
playDefaults();
paintAll();
applyControls();
pullQueue(true);                    // the rack shows the relay's queue once it answers
/* pose() hides both fittings; the page a human opens must SHOW them, or the
 * page they open is not the page this file describes.  check_occlusion.py's
 * section 0 reports the difference between the as-loaded and posed frames and
 * that section is REPORTED, NOT FAILED ON, for exactly this case (NOTES 9). */
if (refit) refit.show(true);
mast.show(true);
layout();
facingAudit(camera);
requestAnimationFrame(frame);
window.__loaded = true;
