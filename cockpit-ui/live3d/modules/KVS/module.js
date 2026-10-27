/* SAINTCON 2026 — KVS close-up.  Key/Value Store: the CORE BANK.
 *
 * THIS IS THE PORT OF live3d/app.js's KVS HALF onto the shared template, made
 * at integration time.  app.js was both the reference module AND the cockpit
 * shell; it is the shell only now, and KVS is a standalone page like the other
 * eight.  Above the "MODULE WORK STARTS HERE" line this file is
 * modules/_TEMPLATE/module.js verbatim -- which is itself derived from the
 * app.js code this replaces, so the port is a re-parenting, not a rewrite.
 *
 * WHAT CHANGED, AND WHY IT MATTERS:
 *   * KVS now exposes the fleet-standard `window.__occ` including `gain()`,
 *     `ubias()` and `matfix()`.  It did not before -- CONVERSION_BRIEF
 *     correction 20 records that "KVS could not be swept because its page is
 *     app.js and has no hook", which is why its light_gain was still 0.65 and
 *     its scene.json still had no ubias_m.  Both are measurable now.
 *   * `uBias` comes from `scene.json -> ubias_m` like every other module.
 *     app.js hardcoded 0.002 -- the fleet default that cost PKT 5.7 rms.
 *   * The two screen-space HUD panels and the banner moved from
 *     live3d/index.html into this page's own #chrome.  They are HUD, not
 *     instrument content, and are deliberately not declared readout planes.
 *
 * WHAT DID NOT CHANGE: the scene.json, the camera, the ten area lights, the
 * depth composite, the split, the one readout plane on the raked console face,
 * the type metrics, the session model and every string it paints.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import { CSS3DLayer, layoutType } from '../../css3d.js';
import { OcclusionSplit, attachForeground, makePlateFront } from '../../occlusion.js';
import { applyColour } from '../../grade.js';
import { mountRefit } from '../../refit.js';
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'KVS';
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
/* premultipliedAlpha: TRUE -- three's own default, and what three's blending
 * actually writes.  `false` puts `a*rgb` in the buffer and then tells the
 * browser to multiply by alpha again, which is 32 levels too dark over a
 * 19%-covered fragment.  LOG NOTES 8.1 measured it; occlusion.js's front
 * renderer carries the same flag and the two MUST agree. */
renderer.setClearAlpha(0);
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.AgXToneMapping;     // Blender's view transform
/* toneMappingExposure and the Blender LOOK are set together by grade.js, from
 * scene.json -> colour, once the split exists (section 5).  Do NOT pin the
 * exposure here: `colour` is emitted for all nine modules and was read by none
 * of them, and on FMM -- the one module with a close_grade() -- that put every
 * live pixel 9..26 levels brighter than its own baked panel.  grade.js. */
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
  /* PER MODULE, AND MEASURED.  This is the stand-off tolerance in the depth
   * composite (`if (vLinDepth > baked - uBias) discard`): live geometry
   * within uBias of the baked surface behind it is DISCARDED INTO THE PLATE,
   * silently -- no error, no console warning, auditScene() clean.
   *
   * The template used to ship 0.002 for everyone.  2 mm is too big for a real
   * module: PKT's lit verdict header stands 1.15 mm proud of its baked frame,
   * so the default deleted a 208 x 20 px emissive strip and compare.py read
   * rms 15.905 against 10.177 at the right value.  A 5.7 rms error that looked
   * like "the header bar is a bit dark".  MQB swept the same knob and got
   * 5.418 at every value, so it does not always bite -- which is exactly why
   * nobody looked.
   *
   * DERIVE IT, DO NOT PICK IT: uBias = 0.7 x the SMALLEST stand-off between
   * any LIVE object and the BAKED surface behind it, which the exporter
   * measures by rendering the depth pass a second time with the live objects
   * VISIBLE.  USE `live3d/pipeline/ubias.py`, do not retype the one-liner:
   * min(baked - live) over EVERY pixel lands on a SILHOUETTE pixel, which is a
   * partial-coverage artefact and not a stand-off -- on IPM that is 0.090 mm
   * against a real 1.001 mm, 11x too small.  ubias.py erodes the live-nearer
   * mask by one pixel first, prints the distribution, and names FMM's converse
   * case (a prop EMERGING through its baked seat, where the gap sweeps through
   * zero and the minimum is a rim artefact).  Emit it as `scene.json ->
   * ubias_m`.  CONVERSION_BRIEF step 3.  Too small only risks z-fighting on a
   * genuinely coplanar prop, which is visible and noisy; too big deletes
   * geometry and is silent.  When in doubt go small. */
  uBias: { value: (typeof S.ubias_m === 'number') ? S.ubias_m : 0.0005 },
  uEnable: { value: 1 },
};
if (typeof S.ubias_m !== 'number')
  console.warn('scene.json has no `ubias_m`: the depth composite is running ' +
    'on a 0.5 mm guess.  Measure the smallest live stand-off and emit it -- ' +
    'a prop thinner than this is silently discarded into the plate.');
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
  /* FRONTSIDE DELETES ONE-SIDED BLENDER GEOMETRY, SILENTLY.  EEVEE does not
   * backface-cull; three does.  MQB's phosphor trace is a ribbon swept along a
   * waveform whose winding puts the front face AWAY from the camera: Blender
   * renders it, three renders nothing, there is no error and auditScene() has
   * no complaint because the material is attached correctly.  If a prop is
   * missing and everything else checks out, this is the first thing to try:
   *     m.side = THREE.DoubleSide;    // after dress() returns it
   * A swept ribbon, a flag, a paper tape, a curtain or a single-quad label are
   * all candidates.  facingAudit() below finds them for you. */
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
/* Which dressed meshes face AWAY from the camera in their entirety?  Those are
 * the ones FrontSide has just deleted.  Area-weighted over world-space triangle
 * normals, so a mesh that is merely oblique does not register.  Reported to the
 * console and to the toolbar; it is deliberately NOT part of `__occ.audit()`,
 * which the fleet harness asserts is [] and which means something else. */
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

function applyMatFix() {
  for (const p of patched) {
    if (!p.rec) continue;
    p.m.roughness = matFixOn ? p.rec.rough : p.raw.rough;
    p.m.metalness = matFixOn ? p.rec.metallic : p.raw.metal;
  }
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
/* THE MODULE'S OWN COLOUR MANAGEMENT.  Exposure onto BOTH renderers (they are
 * two halves of one partition and must agree), plus the measured transfer for
 * Blender's LOOK where the module declares one.  A no-op on the eight modules
 * whose look is 'None' and whose exposure is 0; on FMM it is worth 5.645 -> 4.241
 * rms and the difference between a gain sweep that has a minimum and one that
 * does not.  It must run BEFORE the first material compiles.  grade.js. */
const COLOUR = applyColour(S, renderer, split);
console.info('colour:', COLOUR.note);
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

async function addReadout(tp) {
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
  /* TYPE METRICS -- all of them MEASURED, none of them fudged.  The exporter
   * emits Blender's own advance, lead and BASELINE in metres on the plane
   * (pipeline/typemetrics.py); css3d.js's layoutType() solves the font-size
   * from the resolved face's own em and puts the baseline where Blender's is,
   * using the browser's real baseline offset rather than a model of it.
   * `base_adj` is 0 on every module and is not yours to invent: if the type
   * lands wrong, the plane or the exported metric is wrong.
   * Handles `align: "center"` and per-line `line_adv_m` too; see css3d.js. */
  if (tp.type) {
    for (let i = 0; i < tp.type.n_lines; i++) {
      const d = document.createElement('div');
      lines.appendChild(d);
      r.els.push(d);
    }
    r.layout = await layoutType(lines, tp, MPP, r.els);
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


/* Declare every readout the module has.  The exporter writes them as
 * scene.json -> text_planes (a LIST).  KVS's original single `text_plane` is
 * accepted so the reference export keeps working. */
const PLANES = S.text_planes || [S.text_plane];
for (const tp of PLANES) await addReadout(tp);

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
  /* The depth-composite stand-off, so check/sweep_ubias.mjs can measure it on
   * the real page instead of it being argued about.  Returns the value in use;
   * with an argument, sets it.  PKT and MTA both built this hook privately. */
  ubias: (v) => { if (v !== undefined) DU.uBias.value = +v;
                  return DU.uBias.value; },
  /* The exposure BOTH renderers run at (occlusion.js re-syncs the front one
   * from the back one every frame).  A knob, so a module with a close_grade()
   * measures its grade on the real page instead of arguing about it; FMM built
   * this privately as `__fmm.exposure` and it is sweepable by name. */
  exposure: (v) => { if (v !== undefined) renderer.toneMappingExposure = +v;
                     return renderer.toneMappingExposure; },
  /* The other two knobs whose value has to be MEASURED rather than argued
   * about, and which MTA, OTA and PKT each rebuilt privately before this:
   * the light gain (scene.json -> light_gain) and the materials.json side
   * channel.  Sweep them with check/sweep_ubias.mjs and score each grab with
   * compare.py.  A/B, never an opinion. */
  gain: (g) => { if (g !== undefined) setGain(+g); return GAIN; },
  matfix: (v) => { if (v !== undefined) { matFixOn = !!v; applyMatFix(); }
                   return matFixOn; },
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
 * ========================================================================= */

/* ===================================================================== M1 */
/* LIVE PROPS.  Three glbs: the punched-tape reel, the telegraph key and the
 * eight idiot lamps.  Everything static -- the console shell, the nameplate,
 * the drawer labels, the engraved lamp captions -- is in plate.png.
 *
 * The module as MODELLED is 337,532 triangles; 214,316 of those were platen
 * type, which is DOM now, so what ships live is counted below rather than
 * quoted. */
const P = S.props;
const [gReel, gKey, gLamps] = await Promise.all([
  load(A + P.reel.glb), load(A + P.key.glb), load(A + P.lamps.glb),
]);
const lampMat = {};                            // dome node name -> its material
gReel.scene.traverse(o => { if (o.isMesh) dress(o); });
gKey.scene.traverse(o => { if (o.isMesh) dress(o); });
gLamps.scene.traverse(o => { if (o.isMesh) lampMat[o.name] = dress(o); });

const reel = pivotAt(P.reel.hub);
const key = pivotAt(P.key.hinge);
const REEL_AXIS = new THREE.Vector3().fromArray(P.reel.axis).normalize();
const KEY_AXIS = new THREE.Vector3().fromArray(P.key.axis).normalize();
reel.inner.add(gReel.scene);
key.inner.add(gKey.scene);
scene.add(gLamps.scene);
applyMatFix();

let TRIS = 0, MESHES = 0;
for (const g of [gReel, gKey, gLamps])
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    MESHES++;
    const ix = o.geometry.getIndex();
    TRIS += (ix ? ix.count : o.geometry.getAttribute('position').count) / 3;
  });

/* The lamps: the glb ships every dome with its OFF material; ON is the same
 * dome carrying the emissive record materials.json holds for the "_on"
 * material.  One material per mesh (dress() clones), so a state swap acts
 * alone. */
function setLamps(stateName) {
  const pat = P.lamps.patterns[stateName];
  P.lamps.domes.forEach((d, i) => {
    const m = lampMat[d.node];
    if (!m) return;
    const rec = MJ[pat[i] ? d.on : d.off];
    if (!rec) return;
    m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                   THREE.LinearSRGBColorSpace);
    m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                      THREE.LinearSRGBColorSpace);
    m.emissiveIntensity = pat[i] ? rec.emit : 0;
    m.roughness = matFixOn ? rec.rough : m.roughness;
    m.metalness = matFixOn ? rec.metallic : m.metalness;
    /* keep the materials.json side channel in step with the state swap, so
     * __occ.matfix() cannot put the OFF lamp's roughness on a lit one. */
    for (const q of patched) if (q.m === m) q.rec = rec;
  });
}

/* ===================================================================== M2 */
/* THE SESSION MODEL -- a live RESP2 transcript.
 *
 * Seeded from the transcript the exporter rendered, then extended at runtime.
 * In the product these bytes come off the wire and are UNTRUSTED, so every
 * string reaches the page through textContent and nothing else.  The platen's
 * last line is the command being typed.  It is split the way redis-cli splits
 * a line -- whitespace, with "double" and 'single' quotes holding a word
 * together -- and posted as `args`, so `SET greeting "hello world"` stores two
 * words.  Every request goes through run(), so the platen, the lamps, the key
 * and the HUD always tell the same story. */
const TP = PLANES[0];
const NL = TP.type.n_lines;
const SEED = (S.platen_text || []).flat();
const TAPE_SEED = 'return 6*7';
const WRITE_VERBS = new Set([
  'SET', 'DEL', 'EXPIRE', 'PERSIST', 'INCR', 'DECR',
  'RPUSH', 'LPUSH', 'LPOP', 'RPOP', 'HSET', 'HDEL',
  'SAVE', 'FLUSHALL', 'FLUSHDB', 'REPLICAOF', 'SLAVEOF', 'SELECT',
]);
const log = SEED.slice(0, NL - 1);
let revs = 0, bank = 'idle', lastOp = 'AUTH';
let cmdBuf = '', passBuf = '', dbsize = null;
let cursorOn = true;
let platenOverride = null;                     // check-harness only
let busy = 0, keyHeld = false, sendGen = 0;
let cmdIn = null;
const history = [];
let histAt = 0;

function platenRect() {
  const c = TP.corners_px;
  if (!c) return { x: 388, y: 308, w: 511, h: 156 };
  const xs = [c.tl.x, c.tr.x, c.bl.x, c.br.x];
  const ys = [c.tl.y, c.tr.y, c.bl.y, c.br.y];
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

function ghostField(tag, attrs) {
  const el = document.createElement(tag);
  el.className = 'kvs-ghost';
  el.autocomplete = 'off';
  el.spellcheck = false;
  el.setAttribute('autocapitalize', 'off');
  el.setAttribute('autocorrect', 'off');
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}

/* redis-cli's split: whitespace between words, "..." with \n \t \" \\
 * escapes, '...' literal.  Throws on an unclosed quote. */
function tokenize(line) {
  const out = [];
  let cur = '', inTok = false, q = null;
  const esc = { n: '\n', t: '\t', r: '\r' };
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (q === '"') {
      if (c === '\\' && i + 1 < line.length) { const n = line[++i]; cur += esc[n] || n; }
      else if (c === '"') q = null;
      else cur += c;
    } else if (q === "'") {
      if (c === "'") q = null; else cur += c;
    } else if (c === '"' || c === "'") {
      q = c; inTok = true;
    } else if (/\s/.test(c)) {
      if (inTok) { out.push(cur); cur = ''; inTok = false; }
    } else {
      cur += c; inTok = true;
    }
  }
  if (q) throw new Error('unbalanced quotes');
  if (inTok) out.push(cur);
  return out;
}

/* how a command is echoed: words with spaces or quotes are re-quoted, and a
 * password never reaches the paper */
function shownArgs(argv) {
  const verb = String(argv[0] || '').toUpperCase();
  return argv.map((a, i) => {
    if (verb === 'AUTH' && i > 0) return '**********';
    return /^[^\s"'\\]+$/.test(a) ? a : JSON.stringify(a);
  }).join(' ');
}

function classify(verb, reply, failed) {
  if (failed || /^\(error\)/.test(String(reply == null ? '' : reply))) return 'fault';
  if (verb === 'EVAL') return 'eval';
  if (WRITE_VERBS.has(verb)) return 'write';
  return 'read';
}

/* a reply as redis-cli prints it, one array element per line */
function fmtValue(v, pad) {
  pad = pad || '';
  if (v === null || v === undefined) return [pad + '(nil)'];
  if (typeof v === 'number') return [pad + '(integer) ' + v];
  if (Array.isArray(v)) {
    if (!v.length) return [pad + '(empty array)'];
    const out = [];
    v.forEach((x, i) => {
      const lead = (i + 1) + ') ';
      const sub = fmtValue(x, '');
      out.push(pad + lead + sub[0]);
      const ind = pad + ' '.repeat(lead.length);
      for (const s of sub.slice(1)) out.push(ind + s);
    });
    return out;
  }
  const s = String(v);
  if (/^\(error\)/.test(s)) return [pad + s];
  return [pad + (/^[\w.:@/+-]+$/.test(s) ? s : JSON.stringify(s))];
}

function pushLines(lines) {
  for (const l of lines) log.push(l);
  while (log.length > NL - 1) log.shift();
}

async function kvsInteract(action, params) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15000);
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'KVS', action: action || 'cmd', params }),
      signal: ac.signal,
    });
    let data = {};
    try { data = await r.json(); } catch { data = {}; }
    const res = data.result || data;
    if (!r.ok) {
      return { ok: false,
        error: String((res && (res.error || res.summary)) || data.error
          || ('HTTP ' + r.status)) };
    }
    return res;
  } catch (e) {
    const msg = (e && e.name === 'AbortError')
      ? 'timeout' : String((e && e.message) || e || 'offline');
    return { ok: false, error: msg };
  } finally {
    clearTimeout(timer);
  }
}

/* ONE request to the bank.  The key goes down for the round trip.  A loud
 * request (the default) is typed onto the platen, lights the lamps and lands
 * on the ledger's printout; a quiet one (`quiet: true`) is bookkeeping the
 * ledger does around it, such as TYPE before a read, and only returns. */
async function run(argv, opts) {
  opts = opts || {};
  const gen = sendGen;
  const verb = String(argv[0] || 'PING').toUpperCase();
  const params = { args: argv };
  if (passBuf) params.password = passBuf;
  if (!opts.quiet) { busy++; keyDown = true; redraw(); }
  const res = await kvsInteract('cmd', params);
  if (!opts.quiet) {
    busy = Math.max(0, busy - 1);
    if (!busy && !keyHeld) keyDown = false;
  }
  if (gen !== sendGen) return res;               // pose() happened meanwhile
  const failed = !res || res.ok === false;
  if (!opts.quiet) {
    const shown = shownArgs(argv);
    const body = failed ? '(error) ' + String((res && res.error) || 'offline')
      : String(res.reply != null ? res.reply : '');
    pushLines(['> ' + shown, body]);
    lastOp = verb;
    bank = classify(verb, res && res.reply, failed);
    setLamps(bank);
    if (verb === 'EVAL') reelV += 260;
    if (!opts.noPrint)
      setPrintout(['> ' + shown].concat(failed || !('value' in res) ? [body]
                                                                     : fmtValue(res.value)));
    setStatus(body, failed || /^\(error\)/.test(body) ? 'err' : 'ok');
  }
  redraw();
  if (!opts.quiet && !failed && verb !== 'DBSIZE') refreshSize();
  return res;
}

/* the key count on the HUD and the ledger, read quietly after every request */
async function refreshSize() {
  const r = await run(['DBSIZE'], { quiet: true });
  if (r && r.ok !== false && typeof r.value === 'number') dbsize = r.value;
  paintSize();
}

async function sendNow() {
  const line = cmdBuf.trim();
  let argv;
  try { argv = line ? tokenize(line) : ['PING']; } catch (e) {
    pushLines(['> ' + line, '(error) ' + e.message]);
    bank = 'fault'; setLamps(bank); redraw();
    return;
  }
  if (!argv.length) argv = ['PING'];
  if (line && history[history.length - 1] !== line) history.push(line);
  histAt = history.length;
  cmdBuf = '';
  if (cmdIn) cmdIn.value = '';
  await run(argv);
}

/* ordered {label, value} segments assembled with DOM NODES.  Never a markup
 * string: this readout is where store replies land. */
function seg(host, rows) {
  host.textContent = '';
  rows.forEach((r, i) => {
    if (i) host.appendChild(document.createElement('br'));
    const lab = document.createElement('i');
    lab.textContent = r[0];
    const val = document.createElement('b');
    val.textContent = r[1];
    host.appendChild(lab); host.appendChild(val);
  });
}

function redraw() {
  const caret = cursorOn ? '_' : ' ';
  readouts[0].paint(platenOverride || log.concat(['> ' + cmdBuf + caret]));
  seg($('roL'), [
    ['MEMORY BANK  ', bank.toUpperCase()],
    ['LAST OP      ', lastOp],
    ['KEYS         ', dbsize == null ? '--' : String(dbsize)],
    ['SIGN-IN      ', passBuf ? 'OWN' : 'CONSOLE'],
  ]);
}
function paintAll() { redraw(); }

/* ---- THE LEDGER'S OWN PAPER.  Its status line, printout and key list.
 * Every line is painted with textContent only. */
function setStatus(text, kind) {
  const el = $('ledgerReply');
  el.textContent = text || '';
  el.className = kind || '';
  el.title = text || '';
}
let printout = null;
const lineCls = l => /^> /.test(l) ? 'sent' : (/^\s*(\d+\) )?\(error\)/.test(l) ? 'bad' : '');
function setPrintout(lines) {
  printout = lines ? lines.map(String) : null;
  const pre = $('ledgerLines');
  pre.textContent = '';
  if (!printout || !printout.length) {
    const e = document.createElement('span');
    e.className = 'empty';
    e.textContent = 'Scan for keys, pick one to read it, or type on the platen.';
    pre.appendChild(e);
    return;
  }
  for (const line of printout) {
    const e = document.createElement('div');
    const c = lineCls(line);
    if (c) e.className = c;
    e.textContent = line;
    pre.appendChild(e);
  }
  pre.scrollTop = 0;
}
function paintSize() {
  $('ledgerSize').textContent = dbsize == null ? '' : dbsize + (dbsize === 1 ? ' key' : ' keys');
  $('ledgerWho').textContent = passBuf ? 'your password' : "the console's own";
  redraw();
}
let keyList = [], selKey = null;
function paintKeys(note) {
  const box = $('ledgerKeys');
  box.textContent = '';
  if (!keyList.length) {
    const e = document.createElement('div');
    e.className = 'empty';
    e.textContent = note || 'Scan lists the keys that match.';
    box.appendChild(e);
    return;
  }
  for (const k of keyList) {
    const e = document.createElement('div');
    e.setAttribute('role', 'option');
    e.setAttribute('aria-selected', String(k === selKey));
    if (k === selKey) e.className = 'on';
    e.textContent = k;
    e.title = k;
    e.addEventListener('click', () => readKey(k));
    box.appendChild(e);
  }
}

/* ---- WHAT THE LEDGER DOES.  Ordinary store work, one command each. */
async function scanKeys() {
  const pat = $('ledgerMatch').value.trim() || '*';
  setStatus('scanning…', 'busy');
  const r = await run(['SCAN', '0', 'MATCH', pat, 'COUNT', '1000'], { noPrint: true });
  if (!r || r.ok === false || !Array.isArray(r.value)) { paintKeys('(no answer)'); return; }
  keyList = (Array.isArray(r.value[1]) ? r.value[1] : []).map(String).sort();
  paintKeys('No keys match ' + pat);
  setStatus(keyList.length + (keyList.length === 1 ? ' key matches ' : ' keys match ') + pat, 'ok');
}
const READ_BY_TYPE = {
  string: k => ['GET', k],
  list: k => ['LRANGE', k, '0', '-1'],
  hash: k => ['HGETALL', k],
};
async function readKey(k) {
  k = String(k == null ? $('ledgerKey').value : k);
  if (!k) { setStatus('Type a key, or pick one from the list.', 'err'); return; }
  selKey = k;
  $('ledgerKey').value = k;
  paintKeys();
  setStatus('reading ' + k + '…', 'busy');
  const t = await run(['TYPE', k], { quiet: true });
  const type = t && t.ok !== false ? String(t.value || 'none') : 'none';
  const ttl = await run(['TTL', k], { quiet: true });
  const secs = ttl && typeof ttl.value === 'number' ? ttl.value : null;
  $('ledgerType').textContent = type + (secs != null && secs >= 0 ? ' · ' + secs + ' s left' : '');
  $('ledgerTtl').value = '';
  if (type === 'none') {
    $('ledgerVal').value = '';
    setPrintout([k, '(no such key)']);
    setStatus(k + ' is not in the bank', 'err');
    return;
  }
  const how = READ_BY_TYPE[type];
  if (!how) { setPrintout([k + ' is a ' + type]); setStatus(type); return; }
  const r = await run(how(k));
  $('ledgerVal').value = type === 'string' && r && typeof r.value === 'string' ? r.value : '';
}
async function setKey() {
  const k = $('ledgerKey').value, v = $('ledgerVal').value, ttl = $('ledgerTtl').value.trim();
  if (!k) { setStatus('Type a key to store under.', 'err'); return; }
  const argv = ['SET', k, v];
  if (ttl) argv.push('EX', ttl);
  const r = await run(argv);
  if (r && r.ok !== false && !keyList.includes(k)) { keyList.push(k); keyList.sort(); }
  selKey = k;
  paintKeys();
}
async function delKey() {
  const k = $('ledgerKey').value;
  if (!k) { setStatus('Type a key to delete.', 'err'); return; }
  const r = await run(['DEL', k]);
  if (r && r.value === 1) {
    keyList = keyList.filter(x => x !== k);
    selKey = null;
    $('ledgerVal').value = '';
    $('ledgerType').textContent = '';
    paintKeys();
  }
}
async function runScript() {
  const words = id => $(id).value.trim().split(/\s+/).filter(Boolean);
  const keys = words('ledgerSKeys'), args = words('ledgerSArgs');
  await run(['EVAL', $('ledgerScript').value, String(keys.length)].concat(keys, args));
}

/* ===================================================================== M3 */
/* ANIMATION.  Runs once per frame BEFORE the split renders.  The readout
 * plane is bolted to the console face and does not ride a control, so nothing
 * calls r.place(). */
let spin = 0, reelV = 0, spinning = false, dragging = false, lastA = 0;
let keyDown = false, keyAng = P.key.angles.up;
/* THE REFIT PORT.  Mounted below, after the hotspot helper exists; declared
 * here because onFrame() and poseForCapture() both reach it and both are
 * defined before the mount.  live3d/refit.js, live3d/design/FIX_UPLOAD.md. */
let refit = null;
/* THE TELLTALE MAST.  Mounted below, beside the port and on the same rail.
 * live3d/mast.js, live3d/design/STATUS_AT_A_GLANCE.md section 6. */
let mast = null;

/* THE REEL IS PARKED AT LOAD, AND THAT IS A FIX, NOT A REGRESSION.
 * app.js started with `spinning = true` and a 520 ms cursor blink, and every
 * check in the brief calls __occ.pose() first -- which stops both.  So the
 * page a human opened was never the page anything was measured against, which
 * is exactly the class of defect check_occlusion.py's section 0 exists to
 * find (it caught OTA's propagation pulse and MQB's 6 fps scope trace the same
 * way).  The reel starts parked in the exporter's own rest pose and the
 * toolbar's `reel: parked` button, or a drag, or running a script, turns it. */
function bumpRevs(dDeg) { revs += Math.abs(dDeg) / 360; }

function onFrame(dt, now) {
  if (!dragging) {
    /* run: ease back to the idle rate, so a drag-throw or an EVAL kick decays
     * into the steady spin instead of snapping.  parked: exponential run-down,
     * which is what a real flywheel reel does when you let go. */
    if (spinning) reelV += (40 - reelV) * Math.min(1, dt * 1.6);
    else reelV *= Math.pow(0.25, dt);
    if (Math.abs(reelV) < 1e-4) reelV = 0;
    const d = reelV * dt;
    if (d) { spin = (spin + d + 3600) % 360; bumpRevs(d); }
  }
  reel.pivot.setRotationFromAxisAngle(REEL_AXIS, spin * D2R);

  const want = keyDown ? P.key.angles.down : P.key.angles.up;
  keyAng += (want - keyAng) * Math.min(1, dt * 22);
  key.pivot.setRotationFromAxisAngle(
    KEY_AXIS, (keyAng - P.key.angles.up) * D2R);
  /* The port animates off THIS loop and owns no timer of its own.  README
   * section 16.8: a module failed a byte-identical capture for a 520 ms blink
   * that pose() flagged off but never clearInterval'd.  There is nothing to
   * clear here because there is nothing to start. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  tickHeld(dt);
}

/* ===================================================================== M4 */
/* INTERACTION.  Hotspots live in #hots, z above the front canvas.          */
const hots = $('hots');
function stageXY(ev) {
  const r = $('stage').getBoundingClientRect(), k = r.width / W;
  return [(ev.clientX - r.left) / k, (ev.clientY - r.top) / k];
}
function hotspot(rect, label, wire) {
  const h = document.createElement('div');
  h.className = 'hot';
  h.style.left = rect.x + 'px'; h.style.top = rect.y + 'px';
  h.style.width = rect.w + 'px'; h.style.height = rect.h + 'px';
  h.title = label;
  hots.appendChild(h);
  wire(h);
  return h;
}
/* a hotspot that is also a keyboard button */
function buttonHot(h, act) {
  h.tabIndex = 0;
  h.setAttribute('role', 'button');
  h.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    ev.preventDefault();
    act();
  });
}

/* ---- HELD PAPER.  The bank ledger is DOM in a second CSS3D layer, laid on
 * the console face basis.  Its `k` runs 0..1: 0 is tucked behind the drawer
 * labels along the top of the bank, 1 is held up toward the camera over the
 * left bulkhead, clear of the platen, the key and the reel.  onFrame() eases
 * k toward `want`; no timers. */
const V = a => new THREE.Vector3().fromArray(a);
const FACE_U = V(TP.u), FACE_V = V(TP.v), FACE_N = V(TP.n);
const held = new CSS3DLayer($('held'), W, H);
const LEDGER = { el: $('kvsLedger'), w: 560, h: 740, k: 0, want: 0 };
LEDGER.rec = held.add(LEDGER.el);
/* THE DRAWER LABELS are baked into plate.png (four brass-framed cards under
 * the drums); scene.json does not declare them, so the strip is measured off
 * the plate. */
const DRAWERS = { x: 330, y: 180, w: 634, h: 34 };
const REF_D = camera.position.distanceTo(V(TP.origin));
/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the platen's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = REF_D * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  return { o, m: at.w * perPx / elW };
}
const LEDGER_REST = heldPose({ x: DRAWERS.x + DRAWERS.w / 2, y: DRAWERS.y + DRAWERS.h / 2,
  w: 150 }, LEDGER.w, 1.04);
const LEDGER_UP = heldPose({ x: 196, y: 350, w: 344 }, LEDGER.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function tickHeld(dt) {
  if (LEDGER.k !== LEDGER.want) {
    const step = dt * 4;
    LEDGER.k = LEDGER.want > LEDGER.k ? Math.min(LEDGER.want, LEDGER.k + step)
                                      : Math.max(LEDGER.want, LEDGER.k - step);
    if (LEDGER.k === 0) LEDGER.el.hidden = true;
  }
  if (!LEDGER.el.hidden) {
    const e = ease(LEDGER.k), m = LEDGER_REST.m + (LEDGER_UP.m - LEDGER_REST.m) * e;
    LEDGER.el.style.opacity = String(Math.min(1, e * 2.5));
    LEDGER.rec.matrix = new THREE.Matrix4().makeBasis(
      FACE_U.clone().multiplyScalar(m), FACE_V.clone().multiplyScalar(m), FACE_N)
      .setPosition(LEDGER_REST.o.clone().lerp(LEDGER_UP.o, e));
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

/* ---- the ledger: lift it / put it back, which face is up, and where focus
 * goes back to. */
let ledgerOpener = null, drawersHot = null;
function showFace(which) {
  const keys = which !== 'tape';
  $('faceKeys').hidden = !keys;
  $('faceTape').hidden = keys;
  $('tabKeys').setAttribute('aria-selected', String(keys));
  $('tabTape').setAttribute('aria-selected', String(!keys));
}
function openLedger(face, then) {
  const el = LEDGER.el;
  const wasDown = el.hidden || LEDGER.want === 0;
  if (wasDown) {
    const a = document.activeElement;
    ledgerOpener = (a && a !== document.body && a !== document.documentElement
                    && !el.contains(a)) ? a : null;
  }
  if (face) showFace(face);
  el.hidden = false;
  LEDGER.want = 1;
  if (wasDown || then) focusStill(then || $('ledgerCard'));
}
function closeLedger() {
  const el = LEDGER.el;
  const wasUp = LEDGER.want === 1;
  const a = document.activeElement;
  const focusWasHere = !a || a === document.body || a === document.documentElement
    || el.contains(a);
  LEDGER.want = 0;
  if (wasUp && focusWasHere) {
    const back = (ledgerOpener && ledgerOpener.isConnected && !el.contains(ledgerOpener))
      ? ledgerOpener : drawersHot;
    ledgerOpener = null;
    focusStill(back);
  }
}

/* the drawer labels: lift the ledger on its KEYS face and list the bank */
drawersHot = hotspot(DRAWERS, 'BANK DRAWERS — open the ledger and list the keys', h => {
  const go = () => {
    const first = LEDGER.want === 0 && !keyList.length;
    openLedger('keys');
    if (first) scanKeys();
  };
  h.addEventListener('click', go);
  buttonHot(h, go);
});

/* the reel: grab it and throw it.  Angular drag about the PROJECTED hub, then
 * momentum with a decay -- the same feel the shipped baked rotate control has,
 * except the geometry is real so the lighting travels with the spokes.
 * A click (no throw) lifts the ledger on its SCRIPT TAPE face. */
const PX = P.reel.pivot_px;
hotspot(P.reel.hotspot,
  P.reel.label + ' — click for the script tape; drag to spin',
  h => {
  h.style.cursor = 'grab';
  let dragStart = null;
  h.addEventListener('pointerdown', e => {
    dragStart = stageXY(e);
    dragging = false; setSpin(false); reelV = 0;
    h.style.cursor = 'grabbing';
    const [x, y] = dragStart;
    lastA = Math.atan2(y - PX.y, x - PX.x) / D2R;
    h.setPointerCapture(e.pointerId);
  });
  h.addEventListener('pointermove', e => {
    if (!dragStart) return;
    const [x, y] = stageXY(e);
    if (!dragging) {
      const dx = x - dragStart[0], dy = y - dragStart[1];
      if (dx * dx + dy * dy < 36) return;
      dragging = true;
    }
    const a = Math.atan2(y - PX.y, x - PX.x) / D2R;
    let d = a - lastA; if (d > 180) d -= 360; if (d < -180) d += 360;
    spin = (spin - d + 3600) % 360; lastA = a; reelV = -d * 26;
    bumpRevs(-d); redraw();
  });
  const up = () => {
    const wasDrag = dragging;
    const wasDown = dragStart != null;
    dragging = false; dragStart = null; h.style.cursor = 'grab';
    if (wasDown && !wasDrag) openLedger('tape', $('ledgerScript'));
  };
  h.addEventListener('pointerup', up);
  h.addEventListener('pointercancel', () => { dragging = false; dragStart = null; });
  buttonHot(h, () => openLedger('tape', $('ledgerScript')));
});

/* platen: #css3d is pointer-events none, so the typeable command line is a
 * hidden input in #hots covering the text_plane; what is typed paints on the
 * platen's last line.  Enter sends; Up / Down walk back through what was
 * sent this session. */
{
  const pr = platenRect();
  hotspot(pr,
    'TELETYPE PLATEN — type a command; Enter sends, Up / Down recall', h => {
    cmdIn = ghostField('input', { type: 'text', 'aria-label': 'Command' });
    h.appendChild(cmdIn);
    h.addEventListener('pointerdown', () => focusStill(cmdIn));
    cmdIn.addEventListener('input', () => { cmdBuf = cmdIn.value; redraw(); });
    cmdIn.addEventListener('focus', () => { cursorOn = true; redraw(); });
    cmdIn.addEventListener('blur', () => { cursorOn = false; redraw(); });
    cmdIn.addEventListener('keydown', e => {
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        if (!history.length) return;
        e.preventDefault();
        histAt = Math.max(0, Math.min(history.length,
          histAt + (e.key === 'ArrowUp' ? -1 : 1)));
        cmdBuf = cmdIn.value = history[histAt] || '';
        redraw();
        return;
      }
      if (e.key !== 'Enter' || e.repeat) return;
      e.preventDefault();
      sendNow();
    });
  });
}

/* the key: press it.  One press is one command on a fresh connection, the
 * line on the platen.  The key stays hinged down for the round trip. */
hotspot(P.key.hotspot, P.key.label + ' — press to send the platen line', h => {
  h.addEventListener('pointerdown', e => {
    keyHeld = true; keyDown = true;
    h.setPointerCapture(e.pointerId);
    sendNow();
  });
  const up = () => {
    keyHeld = false;
    if (!busy) { keyDown = false; redraw(); }
  };
  h.addEventListener('pointerup', up);
  h.addEventListener('pointercancel', up);
  buttonHot(h, () => sendNow());
});

/* the lamp strip shows what the last command was: READ, WRITE, EVAL or a
 * FAULT.  A click pings the bank. */
hotspot(P.lamps.hotspot, P.lamps.label + ' — click to ping the bank', h => {
  h.addEventListener('click', () => run(['PING']));
  buttonHot(h, () => run(['PING']));
});

/* the ledger's own controls */
{
  const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
  on('ledgerClose', 'click', () => closeLedger());
  on('tabKeys', 'click', () => showFace('keys'));
  on('tabTape', 'click', () => showFace('tape'));
  on('ledgerScan', 'click', () => scanKeys());
  on('ledgerRead', 'click', () => readKey());
  on('ledgerSet', 'click', () => setKey());
  on('ledgerDel', 'click', () => delKey());
  on('ledgerRun', 'click', () => runScript());
  on('ledgerPass', 'input', () => { passBuf = $('ledgerPass').value; paintSize(); });
  on('ledgerMatch', 'keydown', ev => {
    if (ev.key === 'Enter' && !ev.repeat) { ev.preventDefault(); scanKeys(); }
  });
  on('ledgerKey', 'keydown', ev => {
    if (ev.key === 'Enter' && !ev.repeat) { ev.preventDefault(); readKey(); }
  });
  /* arrow keys walk the key list; Enter reads the highlighted key */
  on('ledgerKeys', 'keydown', ev => {
    if (!keyList.length) return;
    const i = keyList.indexOf(selKey);
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      const j = Math.max(0, Math.min(keyList.length - 1,
        i + (ev.key === 'ArrowDown' ? 1 : -1)));
      selKey = keyList[j]; paintKeys();
      const row = $('ledgerKeys').children[j];
      if (row) row.scrollIntoView({ block: 'nearest' });
      resetClipScroll();
    } else if (ev.key === 'Enter' && selKey) {
      ev.preventDefault(); readKey(selKey);
    }
  });
  /* Ctrl/Cmd+Enter: SET on the KEYS face, RUN on the SCRIPT TAPE face */
  on('ledgerCard', 'keydown', ev => {
    if (ev.key !== 'Enter' || ev.repeat || !(ev.ctrlKey || ev.metaKey)) return;
    ev.preventDefault();
    if ($('faceTape').hidden) setKey(); else runScript();
  });
  /* Escape puts the ledger back.  Stopped here so nothing else in this page
   * (the refit docket's own Escape) also reacts. */
  const closeTop = () => {
    if (LEDGER.want) { closeLedger(); return true; }
    return false;
  };
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !LEDGER.want) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTop();
  });
  /* exposed so the shell can ask "did the module use this Escape?" first */
  window.__closeOverlay = closeTop;
}

/* the two extra toolbar buttons this module owns */
function setSpin(v) {
  spinning = !!v;
  if (spinning) reelV = Math.max(reelV, 40);
  const b = $('bSpin');
  b.classList.toggle('on', spinning);
  b.textContent = spinning ? 'reel: run' : 'reel: parked';
}
$('bSpin').addEventListener('click', () => setSpin(!spinning));
$('bMat').addEventListener('click', function () {
  matFixOn = !matFixOn;
  applyMatFix(); setLamps(bank);
  this.classList.toggle('on', matFixOn);
  this.textContent = matFixOn ? 'materials.json' : 'raw glTF';
});

/* ---- THE REFIT PORT -------------------------------------------------------
 * Nine lines, and none of them is KVS-specific: the anchor, the size, the
 * part names and the hotspot all come out of `scene.json -> refit`, which
 * `pipeline/refit_port.py` wrote.  It bolts to the SHIP STRUCTURE below the
 * console -- the front deck -- never to the faceplate, so no control moves and
 * no readout plane moves.  It declares NO readout plane: all of its text is
 * the screen-space docket, the same class of thing as this page's .hud
 * panel.  Passing `dress` is what chains attachDepthTest and then
 * attachForeground onto the port's materials; skip it and split.auditScene()
 * correctly reports double-blending. */
refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is KVS-specific either: the anchor,
 * the size, the part names, the vane pivot, the sweep travel and the hotspot
 * all come out of `scene.json -> mast`, which `pipeline/status_mast.py` wrote.
 *
 * It mounts on the refit port's own SERVICE RAIL, at 3.2 W from the port's
 * origin -- the port publishes `free_from_m` = 1.5 W as the floor and the
 * reason this sits further out is measured, in NOTES section 15: at 1.5 W the
 * port's docket covers the first 45 % of the tube, which is the half the
 * LANDING segments sort into, and reading the mast while the port is open is
 * the whole point of the close-up half.
 *
 * It declares NO readout plane.  Its words are the screen-space caption in
 * live3d/mast.css, the same class of thing as this page's .hud panel and
 * the port's docket, so check_occlusion.py's question 5, the dial-face rule
 * and check_text.py are not engaged by it.  `readouts.length` is still 1.
 *
 * Passing `dress` is what chains attachDepthTest and then attachForeground
 * onto the mast's materials; skip it and split.auditScene() correctly reports
 * double-blending. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

/* ===================================================================== M5 */
/* THE CAPTURE POSE.  It must equal the state export_kvs.py rendered
 * gt_full_read.png in, or compare.py measures the mismatch and not the
 * renderer.  It is also the state the page RESTS in -- section 0 of
 * check_occlusion.py compares the two and they must agree.
 *
 * There is no timer to clear.  app.js carried a 520 ms setInterval for the
 * blinking cursor and it cost the module a FAIL for 36 px at up to 87 levels,
 * because the two harness screenshots are ~350 ms apart.  The cursor is a
 * state, not an animation, in this page. */
function poseForCapture() {
  /* HIDE THE PORT.  Every number in live3d/RESULTS.md and section 1 of this
   * module's NOTES was captured from pose() against Blender renders that
   * contain no port; hiding it reproduces all of them unchanged and
   * re-renders nothing.  FIX_UPLOAD section 0, decision 3.  The port's own
   * behaviour is measured with it SHOWN -- __refit.show(true) -- which is a
   * separate capture, not this one. */
  if (refit) refit.pose();
  /* AND HIDE THE MAST, for exactly the same reason.  section 1's table and
   * every number in live3d/RESULTS.md were captured against Blender renders
   * that contain neither fitting. */
  if (mast) mast.pose();
  setSpin(false);
  cursorOn = false;
  spin = 0; reelV = 0; dragging = false;
  keyDown = false; keyHeld = false; keyAng = P.key.angles.up;
  busy = 0; sendGen++;
  bank = 'read'; lastOp = 'AUTH'; revs = 0;
  cmdBuf = ''; passBuf = ''; dbsize = null;
  history.length = 0; histAt = 0;
  if (cmdIn) { cmdIn.value = ''; cmdIn.blur(); }
  /* the ledger goes back behind the drawers, blank */
  LEDGER.want = LEDGER.k = 0;
  LEDGER.el.hidden = true;
  showFace('keys');
  keyList = []; selKey = null;
  for (const id of ['ledgerKey', 'ledgerVal', 'ledgerTtl', 'ledgerSKeys',
                    'ledgerSArgs', 'ledgerPass']) $(id).value = '';
  $('ledgerMatch').value = '*';
  $('ledgerScript').value = TAPE_SEED;
  $('ledgerType').textContent = '';
  paintKeys();
  setPrintout(null);
  setStatus('');
  paintSize();
  log.length = 0;
  for (const l of SEED.slice(0, NL - 1)) log.push(l);
  platenOverride = null;
  setLamps(bank);
  reel.pivot.setRotationFromAxisAngle(REEL_AXIS, 0);
  key.pivot.setRotationFromAxisAngle(KEY_AXIS, 0);
  redraw();
}

/* the banner, which is this page's own chrome and not a declared readout */
{
  $('banner').textContent = 'Core Memory Banks';
}
$('note').textContent =
  CODE + ' · ' + TRIS + ' live tris + ' + (refit ? refit.tris : 0) + ' refit + '
  + mast.tris + ' mast · ' + readouts.length
  + ' plane · gain ' + S.light_gain + ' · uBias '
  + (DU.uBias.value * 1000).toFixed(3) + ' mm';

/* Module-private measurement hooks, ALONGSIDE window.__occ and never instead
 * of it.  check/shoot.mjs (the original KVS evidence driver) calls these by
 * name, so they are kept working across the port. */
window.__kvs = {
  typeLayout: () => readouts[0].layout,
  spin: v => { setSpin(false); reelV = 0; spin = v; redraw(); },
  key: v => { keyDown = v; redraw(); },
  send: () => sendNow(),
  run: argv => run(argv),
  lamps: v => { bank = v; setLamps(v); redraw(); },
  text: v => document.body.classList.toggle('notext', !v),
  matfix: v => { matFixOn = !!v; applyMatFix(); setLamps(bank); },
  cursor: v => { cursorOn = !!v; redraw(); },
  platen: v => { platenOverride = v; redraw(); },
  cmd: v => {
    if (v !== undefined) {
      cmdBuf = String(v); if (cmdIn) cmdIn.value = cmdBuf; redraw();
    }
    return cmdBuf;
  },
  tape: v => {
    if (v !== undefined) $('ledgerScript').value = String(v);
    return $('ledgerScript').value;
  },
  password: v => {
    if (v !== undefined) {
      passBuf = String(v); $('ledgerPass').value = passBuf; paintSize();
    }
    return passBuf;
  },
  ledger: (v, face) => {
    if (v !== undefined) { if (v) openLedger(face || 'keys'); else closeLedger(); }
    return { want: LEDGER.want, k: LEDGER.k, face: $('faceTape').hidden ? 'keys' : 'tape',
             keys: keyList.slice(), sel: selKey, printout };
  },
  state: () => ({ bank, lastOp, dbsize, busy, history: history.slice(),
                  signIn: passBuf ? 'own' : 'console', log: log.slice() }),
  tris: () => ({ tris: TRIS, meshes: MESHES }),
  parts: (o) => { reel.pivot.visible = !!o.reel; key.pivot.visible = !!o.key;
                  gLamps.scene.visible = !!o.lamps; },
  planePx: () => TP.corners_px,
  facing: () => facingAudit(camera),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
  /* the BACK canvas alone, at a forced pixel ratio.  DO NOT let this be the
   * only path measured: it forces pixelRatio 1 and that is exactly how the
   * Retina bug (README 16.5) hid for a week. */
  shot: (pr) => {
    const old = renderer.getPixelRatio();
    if (pr) setBothPR(pr);
    split.beginBack();
    renderer.render(scene, camera);
    const d = renderer.domElement.toDataURL('image/png');
    if (pr) setBothPR(old);
    return d;
  },
  /* The element-space advance the browser actually laid out, against the
   * metres Blender's own type advanced.  `target_m` used to read the
   * undeclared identifier ADV_M in app.js -- this hook threw a ReferenceError
   * the moment anything called it.  It is TP.type.adv_m. */
  metrics: () => {
    const probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre';
    probe.textContent = 'M'.repeat(40);
    readouts[0].lines.appendChild(probe);
    const adv = probe.offsetWidth / 40;         // LAYOUT px: the CSS 3D
    probe.remove();                             // transform does not affect it
    return { advance_elem_px: adv, advance_m: adv * MPP,
             target_m: TP.type.adv_m,
             font_px: parseFloat(readouts[0].lines.style.fontSize),
             line_h_px: parseFloat(readouts[0].lines.style.lineHeight),
             family: getComputedStyle(readouts[0].lines).fontFamily };
  },
  glyphBox: () => {
    const r = $('stage').getBoundingClientRect(), k = r.width / W;
    const b = readouts[0].els[0].getBoundingClientRect();
    return { x: (b.left - r.left) / k, y: (b.top - r.top) / k,
             w: b.width / k, h: b.height / k };
  },
};

/* KVS declares `platen_text`, not `readout_text`, so the template's
 * load-time content check has nothing to compare against; check_text.py says
 * the same thing and reports rather than fails.  The line-to-element mapping
 * for a rolling transcript is the frontend's, not the exporter's. */
poseForCapture();
/* pose() hides the port; the page a human opens must SHOW it, or the page they
 * open is not the page this file describes.  check_occlusion.py's section 0
 * will report the difference between the as-loaded and posed frames, and that
 * section is REPORTED, NOT FAILED ON, for exactly this case.  KVS NOTES 7. */
if (refit) refit.show(true);
mast.show(true);
layout();
facingAudit(camera);
requestAnimationFrame(frame);
refreshSize();                     // the HUD's key count, once the bank answers
window.__loaded = true;
