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
import { CSS3DLayer, layoutType } from '../../css3d.js';
import { OcclusionSplit, attachForeground, makePlateFront,
         OCC_FLAG } from '../../occlusion.js';
import { applyColour } from '../../grade.js';
/* The telltale mast stays a status fitting. Grading is not mounted here. */
import { mountRefit } from '../../refit.js';
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'LOG';                     // Black Box / Flight Recorder
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
 * =========================================================================
 *
 * LOG — Black Box / Flight Recorder.  Audit verdict OCCLUDED, "the worst in
 * the fleet", and the only module whose readout is crossed by something that
 * MOVES.  Three things are load-bearing here and nowhere else:
 *
 *  1. THE SEARCH LENS SWEEPS THE TAPE.  It stands 64–66 mm proud of the
 *     printed lines and covers up to 61 of 224 audit samples.  Nothing is
 *     special-cased for it: the split pass evaluates `occInFrontOfText()` per
 *     FRAGMENT against the plane uniforms uploaded THIS frame, so an occluder
 *     that moves is the same code as one that does not.  The lens's brass ring
 *     and arm hide the type; its GLASS is alpha 0.10 and lets it through,
 *     which is what a magnifier should do and is not a special case either.
 *  2. THE RIBBON IS A MOVING READOUT PLANE.  350 mm of paper through a 180 mm
 *     window: the rect is the whole ribbon, the DOM element carries all
 *     fourteen lines, and the six that are behind the panel are redrawn over
 *     by the front pass's plate quad.  `placeTape()` moves the plane and the
 *     element with one call, exactly as OTA's cartridge does.
 *  3. THE TEAR-OFF TAIL IS A NON-PLANAR CARRIER.  Seven flat facets, seven
 *     planes, seven DOM elements — the only way a CSS3D element can lie on a
 *     curve.  MAX_PLANES is 12 for this.
 *
 * NO TIMERS.  Not one setInterval and not one setTimeout: every animation is a
 * state machine driven from onFrame(), so `frozen = true` stops all of it in
 * one place and two consecutive captures are byte-identical (BRIEF trap 24 —
 * KVS failed its own occlusion check for a 520 ms cursor blink that a flag
 * could not stop).
 */
const P = S.props;
const V3 = a => new THREE.Vector3().fromArray(a);
const FACE_U = V3(S.face.u), FACE_V = V3(S.face.v), FACE_N = V3(S.face.n);
const SPIN = V3(S.face.spin_axis);          // +angle => CLOCKWISE on screen

/* ------------------------------------------------------------- M1  PROPS */
const [gTape, gSp0, gSp1, gLens, gSrc, gLamps, gWipe, gGlass, gWLamp] =
  await Promise.all([P.tape.glb, P.tape.spools[0].glb, P.tape.spools[1].glb,
                     P.lens.glb, P.source.glb, P.source.lamps_glb,
                     P.wipe.glb, P.wipe.glass_glb, P.wipe.lamp_glb]
                    .map(f => load(A + f)));

let TRIS = 0;
function mount(g) {
  const out = [];
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    dress(o);
    out.push(o);
    const ix = o.geometry.index;
    TRIS += (ix ? ix.count : o.geometry.attributes.position.count) / 3;
  });
  return out;
}

/* The ribbon TRANSLATES, so a plain group is the whole rig; the two rolls
 * TURN, so they get pivots at their own hubs. */
const tapeGrp = new THREE.Group();
scene.add(tapeGrp);
mount(gTape); tapeGrp.add(gTape.scene);
const spools = [
  { rec: pivotAt(P.tape.spools[0].hub), g: gSp0 },
  { rec: pivotAt(P.tape.spools[1].hub), g: gSp1 },
];
spools.forEach((s, i) => { mount(s.g); s.rec.inner.add(s.g.scene);
                           s.axis = V3(P.tape.spools[i].axis); });

const lensPiv = pivotAt(P.lens.hub);
const lensMeshes = mount(gLens); lensPiv.inner.add(gLens.scene);
const LENS_AXIS = V3(P.lens.axis);

const srcPiv = pivotAt(P.source.hub);
mount(gSrc); srcPiv.inner.add(gSrc.scene);
const SRC_AXIS = V3(P.source.axis);
mount(gLamps); scene.add(gLamps.scene);

const wipePiv = pivotAt(P.wipe.hub);
mount(gWipe); wipePiv.inner.add(gWipe.scene);
const WIPE_AXIS = V3(P.wipe.axis);
mount(gGlass); scene.add(gGlass.scene);
const wipeLamp = mount(gWLamp); scene.add(gWLamp.scene);
const srcDomes = byName(gLamps, P.source.domes);
/* by NAME, never by traverse order: a name that does not resolve is otherwise
 * completely silent -- the prop simply never moves (PKT NOTES 9.1). */
function byName(g, names) {
  const out = names.map(n => g.scene.getObjectByName(n));
  const bad = names.filter((n, i) => !out[i]);
  if (bad.length) console.warn('unresolved glb nodes: ' + bad.join(', '));
  return out.filter(Boolean);
}
const paneMesh = gGlass.scene.getObjectByName(P.wipe.pane);
const shardMeshes = byName(gGlass, P.wipe.shards);

/* ==================================================================== *
 * TRANSPARENT LIVE GEOMETRY IS **BACK-ONLY**, AND HERE IS THE MEASUREMENT.
 *
 * LOG is the first module in the fleet with a TRANSPARENT live prop: the
 * magnifier's glass (alpha 0.10) and the break-glass pane and shards (0.30).
 * WHEN THIS WAS MEASURED both renderers were created with
 * `premultipliedAlpha: false` (occlusion.js's constructor and the template
 * above this line), while three's NormalBlending for a non-premultiplied
 * material is SRC_ALPHA / ONE_MINUS_SRC_ALPHA -- so a transparent fragment
 * drawn over an EMPTY region of a canvas left PREMULTIPLIED rgb in a buffer
 * the browser then composited as STRAIGHT.
 * Measured on this page, split ON, buffer pixel (600,340), the glass over the
 * ribbon:
 *
 *     front canvas   (38,40,38, a 49)      <- 0.19 * glass, premultiplied
 *     back canvas    (212,206,197, a 255)  <- the ribbon
 *     the page shows 178          the split-OFF page shows 210
 *     38 + (1-49/255)*212 = 209   <- reading the buffer as PREMULTIPLIED
 *                                    reproduces the correct answer to 1 level
 *
 * i.e. 32 levels too dark, over the whole disc.  THAT ONE-WORD FIX HAS NOW
 * LANDED -- fix round 4 put `premultipliedAlpha: true` on occlusion.js's front
 * renderer and the integration pass put it on this page's back renderer, so
 * the two agree and the browser reads both buffers as premultiplied.
 *
 * The BACK-ONLY declaration below is KEPT anyway, because it was never only a
 * workaround: **a TRANSPARENT fragment that crosses the partition boundary is
 * composited against two different backgrounds**, and even with a premultiplied
 * buffer the front half has no way to know what the back half already drew
 * under it.  So these three props stay BACK-ONLY: depth-composited exactly as
 * before, never drawn by the front pass, never culled from the back one.  They
 * are in `split.hideInFront`, which is the supported way to say that, and
 * `auditScene()` excuses them for exactly that reason.
 *
 * WHAT IT COSTS THE PRODUCT: nothing.  DOM text under a 10%-transmissive
 * magnifier reads through it either way, and it is the lens's brass RING, ARM
 * and GRIP -- all opaque, all still in the split -- that actually hide the
 * tape lines.  `evidence/03_lens_over_the_tape.png` is the picture.
 * ==================================================================== */
function backOnly(mesh) {
  const m = mesh.material;                 // dress() already cloned it
  m.side = THREE.DoubleSide;               // a lens, and a pane of glass
  m[OCC_FLAG] = false;                     // undo attachForeground's flag
  m.onBeforeCompile = null;
  attachDepthTest(m);                      // depth composite: YES.  occCull: no
  split.hideInFront.push(mesh);
}
const glassMeshes = lensMeshes.filter(m => /glass/.test(m.name))
  .concat([paneMesh]).concat(shardMeshes).filter(Boolean);
glassMeshes.forEach(backOnly);

applyMatFix();

/* Lamp state.  `source` and `wipe` both declare the material PAIR the BRIEF's
 * rule 3 asks for (`mats: {off, on}`), so the states are MODELLED from the
 * module's own materials rather than invented: every scalar comes out of
 * materials.json, which is the same side channel dress() reads. */
function setLampMat(mesh, name) {
  const rec = MJ[name];
  if (!rec) { console.warn('no material ' + name); return; }
  const m = mesh.material;
  m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                 THREE.LinearSRGBColorSpace);
  m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                    THREE.LinearSRGBColorSpace);
  m.emissiveIntensity = rec.emit || 0;
  m.roughness = rec.rough; m.metalness = rec.metallic;
  /* keep the materials.json side channel in step with the state swap, so
   * __occ.matfix() does not put the OFF lamp's roughness on a lit one. */
  for (const p of patched) if (p.m === m) p.rec = rec;
}

/* ------------------------------------------------- M2  THE SESSION MODEL
 * LOG speaks the coordinator: POST /ingest (compose strip), GET /search?q=
 * (magnifier, typeable, commit only), GET /logs/{name} (source dial *.log
 * OR typeable raw download name — freeform, incl. ..%2F…), DELETE /logs/{name}
 * (wipe lever), GET /dashboard (P2 tail, plaintext). Transport is
 * fetch('/api/interact') until track 01's api.js lands — this copy does not
 * import api.js.
 *
 * THE REST BUFFER IS scene.json -> readout_text, NOT A COPY OF IT.  Live
 * replies are a session overlay; pose() clears the overlay so checkers see
 * the exporter's rest strings.  Canned nav/mta/kvs theatre is retired: a
 * wipe does not resurrect it.
 */
const N_TAPE = S.text_planes[0].type.n_lines;      // 10
const N_TAIL = S.text_planes.length - 1;           // 7
const REST_LINES = S.readout_text.flat();          // 10 + 7, newest first

/* PER PLANE, because the tape and the tail do not have the same column count:
 * the tape's first column has to clear the sprocket perforations (NOTES 8.4)
 * so it is 17 wide, and the tail -- no perforations, no pen trace -- is 19.
 * The width is the carrier's geometry and it comes out of the exporter. */
const NCOLS = readouts.map(r => r.tp.type.n_cols);
const clip = (str, i) => {
  const s = str == null ? '' : String(str);
  return (s.length > NCOLS[i]) ? s.slice(0, NCOLS[i]) : s;
};
/* ISO timestamps do not fit 17/19 cols. Drop the leading token so
 * `[INFO] …` starts at column 0. clip() is layout, not XSS control. */
function dropIso(str) {
  const s = str == null ? '' : String(str);
  const i = s.indexOf(' ');
  if (i < 0) return s;
  return /^\d{4}-\d{2}-\d{2}T/.test(s.slice(0, i)) ? s.slice(i + 1) : s;
}

const LEVELS = ['INFO', 'WARN', 'ERROR'];
const SES = {
  src: P.source.states[S.capture_pose.source],   // "all"
  tapeT: S.capture_pose.tape_t,                  // 3/7
  lensDeg: S.capture_pose.lens_deg,              // -45 at capture
  wipe: S.capture_pose.wipe,                     // "sealed"
  level: 'INFO',
  /* Freeform ingest/search source.
   * Dial theatre stays in SES.src; typing here does not spin the dial. */
  sourceText: 'misc',
  /* Raw GET /logs/{name} — freeform, never forced to *.log.
   * Separate from sourceText so dial sync cannot wipe an encoded name. */
  downloadName: 'nav.log',
  q: '',
  lastInteract: null,                            // {action, params, ok, …}
  live: null,                                    // {tape:[], tail:[]} overlay
  /* What the log sheet holds: the long form of what the tape shows, oldest
   * line first.  null until something has been printed on it. */
  sheet: null,                                   // {title, name, lines[], note}
};

const qInput = $('logQ'), msgInput = $('logMsg'), levelBtn = $('logLevel');
const srcInput = $('logSrc'), dlInput = $('logDl');

/* FOCUS WITHOUT MOVING THE SCENE (f-mv6tbijc).  #viewport is overflow:hidden,
 * which is still a scroll container: focusing a field that pokes outside the
 * stage scrolls it sideways and the whole close-up jumps.  The fields are now
 * sized so they cannot poke out (index.html, `#hots #logQ`), and this is the
 * belt to that braces: focus without scrolling, then put the clipping
 * ancestors back at 0 in case anything scrolled them anyway. */
function resetClipScroll() {
  const vp = document.getElementById('viewport');
  if (vp) { vp.scrollLeft = 0; vp.scrollTop = 0; }
  const de = document.documentElement;
  de.scrollLeft = 0; de.scrollTop = 0;
  document.body.scrollLeft = 0; document.body.scrollTop = 0;
}
function focusStill(el) {
  if (!el) return;
  try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
  resetClipScroll();
}
{
  const vp = document.getElementById('viewport');
  if (vp) vp.addEventListener('scroll', resetClipScroll);
  addEventListener('scroll', resetClipScroll);
}

function dialLogName() {
  return (SES.src && SES.src !== 'all') ? SES.src + '.log' : null;
}
/* Wire name for dial download / wipe. Freeform sourceText wins for *.log
 * names; other typed names use SES.downloadName + #logDl. */
function namedLog() {
  const t = (SES.sourceText || '').trim();
  if (t && t !== 'all' && t !== 'misc') {
    if (/\.log$/i.test(t)) return t;
    return t + '.log';
  }
  return dialLogName();
}
function ingestSource() {
  const t = (SES.sourceText || '').trim();
  if (t && t !== 'all') return t.replace(/\.log$/i, '');
  return SES.src === 'all' ? 'misc' : SES.src;
}
function syncSourceTextFromDial() {
  SES.sourceText = SES.src === 'all' ? 'misc' : SES.src;
  if (srcInput) srcInput.value = SES.sourceText;
}
function emptyLive() {
  return { tape: Array(N_TAPE).fill(''), tail: Array(N_TAIL).fill('') };
}
/* The magnifier is a SEARCH: its angle picks the tape row it is sitting on,
 * and that row's line is what `GET /search?q=` would have returned.  The
 * value is not duplicated anywhere in the DOM (BRIEF section 6: the control IS
 * the readout) -- it goes to the toolbar note, which is page chrome. */
function lensRow() {
  const f = (SES.lensDeg - P.lens.range[0]) /
            (P.lens.range[1] - P.lens.range[0]);
  return Math.max(0, Math.min(N_TAPE - 1, Math.round((1 - f) * (N_TAPE - 1))));
}

function paintAll() {
  const tape = SES.live ? (SES.live.tape || []) : REST_LINES.slice(0, N_TAPE);
  const tail = SES.live
    ? (SES.live.tail || [])
    : REST_LINES.slice(N_TAPE, N_TAPE + N_TAIL);
  const prep = (s, i) => clip(SES.live ? dropIso(s) : (s || ''), i);
  readouts[0].paint(tape.slice(0, N_TAPE).map(s => prep(s, 0)));
  /* the tail IS the sheet: while it is torn off, the tail reads blank */
  const torn = sheetUp();
  for (let i = 0; i < N_TAIL; i++)
    readouts[1 + i].paint([torn ? '' : prep(tail[i] !== undefined ? tail[i] : '', 1 + i)]);
}

function applyState() {
  const si = P.source.states.indexOf(SES.src);
  srcPiv.pivot.quaternion.setFromAxisAngle(SRC_AXIS,
    P.source.angles[si] * D2R);
  srcDomes.forEach((d, i) => setLampMat(d,
    P.source.mats[i === si ? 'on' : 'off']));
  const sealed = SES.wipe === 'sealed';
  if (paneMesh) paneMesh.visible = sealed;
  shardMeshes.forEach(s => { s.visible = !sealed; });
  wipePiv.pivot.quaternion.setFromAxisAngle(WIPE_AXIS,
    (SES.wipe === 'wiped' ? -P.wipe.throw_deg : 0) * D2R);
  wipeLamp.forEach(m => setLampMat(m, P.wipe.mats[sealed ? 'off' : 'on']));
  paintAll();
}

function verbLine() {
  const last = SES.lastInteract;
  if (!last) {
    const name = namedLog();
    return name ? ('GET /logs/' + name) : 'src all';
  }
  const a = last.action;
  const p = last.params || {};
  if (a === 'ingest') return 'POST /ingest';
  if (a === 'search') return 'GET /search?q=' + (p.q || '');
  if (a === 'download') return 'GET /logs/' + (p.name || '');
  if (a === 'wipe') return 'DELETE /logs/' + (p.name || '');
  if (a === 'dashboard') return 'GET /dashboard';
  return a;
}

function note() {
  const last = SES.lastInteract;
  const err = last && last.ok === false
    ? ('  ·  ' + (last.error || 'offline'))
    : '';
  $('note').textContent =
    verbLine()
    + '  ·  tape ' + Math.round(SES.tapeT * 100) + '%'
    + '  ·  lens ' + SES.lensDeg.toFixed(0) + '°'
    + '  ·  ' + SES.level
    + '  ·  WIPE ' + SES.wipe.toUpperCase()
    + err
    + '  ·  ' + TRIS + ' live tris'
    + (refit ? ' + ' + refit.tris + ' refit' : '')
    + (mast ? ' + ' + mast.tris + ' mast' : '')
    + ', ' + readouts.length + ' planes';
}

/* --------------------------------------------------------- M3  ANIMATION
 * THE MOVING READOUT PLANE.  The tape rect rides the ribbon, so every frame
 * BOTH the DOM element and the occlusion plane are re-seated from one call --
 * the plane uniforms are re-uploaded from the TextPlane objects every frame
 * anyway (occlusion.js), so a plane on a control costs nothing extra.
 * `origin_tape0` is the rect at the tape's ZERO reference, which is the state
 * every glb was exported in; `corners_px` in scene.json is the rect at
 * pose(), which is the only place the cross-check is defined (BRIEF step 4).
 */
const TAPE_REST0 = V3(S.text_planes[0].origin_tape0);
const TAPE_AXIS = V3(P.tape.travel_axis);
const TAPE_U = V3(S.text_planes[0].u);
const TAPE_V = V3(S.text_planes[0].v);
const TAPE_N = V3(S.text_planes[0].n);
const _o = new THREE.Vector3();

function placeTape(t) {
  const off = P.tape.travel_m * t;
  tapeGrp.position.copy(TAPE_AXIS).multiplyScalar(off);
  tapeGrp.updateMatrixWorld(true);
  for (let i = 0; i < 2; i++) {
    spools[i].rec.pivot.quaternion.setFromAxisAngle(
      spools[i].axis, off * P.tape.spools[i].rad_per_m);
  }
  _o.copy(TAPE_REST0).addScaledVector(TAPE_AXIS, off);
  readouts[0].place(_o, TAPE_U, TAPE_V, TAPE_N);
}
function placeLens(deg) {
  lensPiv.pivot.quaternion.setFromAxisAngle(LENS_AXIS, deg * D2R);
}

/* ---- HELD PAPER.  The log sheet and the lens well are DOM in a second CSS3D
 * layer, laid on the recorder's face basis.  The sheet's `k` runs 0..1: 0 is
 * the tear-off tail hanging out of the slot, 1 is the sheet held up toward the
 * camera beside the tape.  onFrame() eases k toward `want`; no timers.  The
 * well sits on the lens glass and follows it wherever the lens swings. */
const held = new CSS3DLayer($('held'), W, H);
const SHEET = { el: $('sheet'), w: 540, h: 520, k: 0, want: 0,
                at: { x: 975, y: 330, w: 410 } };
SHEET.rec = held.add(SHEET.el);
const WELL = { el: qInput, w: 200 };
WELL.rec = held.add(qInput);

/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the tail's own distance from the camera. */
const TAIL0 = S.text_planes[1], TAIL6 = S.text_planes[N_TAIL];
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = camera.position.distanceTo(V3(TAIL0.origin)) * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  const m = at.w * perPx / elW;
  return { o, mx: m, my: m };
}
/* At rest the sheet is the tail: the span from the top of its first facet to
 * the foot of its last, flattened onto the face. */
const SHEET_REST = (() => {
  const top = V3(TAIL0.origin).addScaledVector(V3(TAIL0.v), TAIL0.half_h);
  const foot = V3(TAIL6.origin).addScaledVector(V3(TAIL6.v), -TAIL6.half_h);
  return { o: top.clone().lerp(foot, 0.5),
           mx: 2 * TAIL0.half_w / SHEET.w, my: top.distanceTo(foot) / SHEET.h };
})();
const SHEET_UP = heldPose(SHEET.at, SHEET.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function basis(o, mx, my) {
  return new THREE.Matrix4().makeBasis(FACE_U.clone().multiplyScalar(mx),
    FACE_V.clone().multiplyScalar(my), FACE_N).setPosition(o);
}
const glassMesh = lensMeshes.find(m => /glass/.test(m.name));
const glassBox = new THREE.Box3();
function placeWell() {
  lensPiv.pivot.updateMatrixWorld(true);
  glassBox.setFromObject(glassMesh || lensPiv.pivot);
  const c = glassBox.getCenter(new THREE.Vector3()).addScaledVector(FACE_N, 0.002);
  const m = 0.75 * glassBox.getSize(new THREE.Vector3()).y / WELL.w;
  WELL.rec.matrix = basis(c, m, m);
}
function tickHeld(dt) {
  if (SHEET.k !== SHEET.want) {
    const step = dt * 4;
    SHEET.k = SHEET.want > SHEET.k ? Math.min(SHEET.want, SHEET.k + step)
                                   : Math.max(SHEET.want, SHEET.k - step);
    if (SHEET.k === 0) SHEET.el.hidden = true;
    paintAll();
  }
  if (!SHEET.el.hidden) {
    const e = ease(SHEET.k);
    SHEET.rec.matrix = basis(SHEET_REST.o.clone().lerp(SHEET_UP.o, e),
      SHEET_REST.mx + (SHEET_UP.mx - SHEET_REST.mx) * e,
      SHEET_REST.my + (SHEET_UP.my - SHEET_REST.my) * e);
  }
  if (!qInput.hidden) placeWell();
  held.render(camera);
}
function sheetUp() { return SHEET.k > 0.02 || SHEET.want > 0; }

let tapeNow = SES.tapeT, lensNow = SES.lensDeg;
let frozen = false;
/* THE REFIT PORT and THE TELLTALE MAST.  Mounted at the bottom of this file,
 * after the hotspot helper exists; declared here because onFrame() and
 * poseForCapture() both reach them and both are defined before the mount. */
let refit = null;
let mast = null;

function onFrame(dt, now) {
  /* BOTH FITTINGS TICK FIRST, ABOVE ANYTHING THAT COULD GATE THEM.
   * CONVERSION_BRIEF trap 26 / FIX_UPLOAD 12.15 item 7: neither fitting owns a
   * timer, so every animation they have -- the iris, the ratchet, the tally
   * flag, the jewel, the mast's vane and its sweep band -- runs off these two
   * calls.  `frozen` is LOG's own capture latch: it pins the tape and the lens
   * onto their targets so a screenshot is still, and it is set by pose() and
   * cleared by any drag.  The fittings are not LOG's state and must not be
   * behind it; pose() STILLS them by HIDING them instead, which is
   * FIX_UPLOAD section 0 decision 3 and the reason every number in sections
   * 1-5 of this module's NOTES reproduces byte-identically. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  if (frozen) { tapeNow = SES.tapeT; lensNow = SES.lensDeg; }
  else {
    tapeNow += (SES.tapeT - tapeNow) * Math.min(1, dt * 10);
    lensNow += (SES.lensDeg - lensNow) * Math.min(1, dt * 12);
  }
  placeTape(tapeNow);
  placeLens(lensNow);
  tickHeld(dt);
}

/* ------------------------------------------------------- M4  INTERACTION */
const hots = $('hots');
function stageXY(e) {
  const r = $('stage').getBoundingClientRect();
  const k = r.width / W;
  return [(e.clientX - r.left) / k, (e.clientY - r.top) / k];
}
function hotspot(rect, label, on) {
  const h = document.createElement('div');
  h.className = 'hot';
  h.style.left = rect.x + 'px'; h.style.top = rect.y + 'px';
  h.style.width = rect.w + 'px'; h.style.height = rect.h + 'px';
  h.title = label;
  hots.appendChild(h);
  on(h);
  return h;
}
function drag(h, move) {
  const up = () => { removeEventListener('pointermove', mv);
                     removeEventListener('pointerup', up); };
  const mv = e => { frozen = false; move(...stageXY(e)); note(); };
  h.addEventListener('pointerdown', e => {
    e.preventDefault(); frozen = false; move(...stageXY(e)); note();
    addEventListener('pointermove', mv);
    addEventListener('pointerup', up, { once: true });
  });
}

function setFieldsHidden(hide) {
  qInput.hidden = hide;
  if (hide) {
    qInput.blur();
    SHEET.want = SHEET.k = 0;
    SHEET.el.hidden = true;
  }
}

/* Track 01 will replace this fetch with interact() from api.js. */
async function interact(action, params, opts) {
  const quiet = opts && opts.quiet;
  const body = { code: 'LOG', action, params: params || {} };
  if (!quiet) {
    SES.lastInteract = { action, params: body.params, ok: null, pending: true };
    note();
  }
  let data;
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    try { data = await r.json(); }
    catch (_) {
      const miss = { ok: false, reachable: false, error: 'coordinator offline' };
      if (!quiet) {
        SES.lastInteract = { action, params: body.params, ok: false,
                             error: miss.error, reachable: false };
        note();
      }
      return miss;
    }
  } catch (e) {
    const miss = { ok: false, reachable: false, error: String(e && e.message || e) };
    if (!quiet) {
      SES.lastInteract = { action, params: body.params, ok: false,
                           error: miss.error, reachable: false };
      note();
    }
    return miss;
  }
  const res = data.result || {};
  const err = res.error || data.error;
  const out = {
    ok: !!res.ok, reachable: true, result: res, error: err,
  };
  if (!quiet) {
    SES.lastInteract = {
      action, params: body.params, ok: out.ok, result: res,
      error: err, reachable: true,
    };
    note();
  }
  return out;
}

/* ---- what the player is told.  The dev #note is page chrome; this line on
 * the sheet is the station's own answer. */
function setStatus(text, kind) {
  const el = $('sheetReply');
  el.textContent = text || '';
  el.className = kind || '';
  el.title = text || '';
}
function report(res, okText) {
  if (res.ok) setStatus(res.result.summary || okText || '', 'ok');
  else setStatus((res.result && res.result.summary) || res.error
                 || 'no answer from the station', 'err');
}

/* ---- the sheet's long form.  Lines are painted with textContent only. */
function setSheet(title, name, lines, note) {
  SES.sheet = { title, name, lines: inertLines(lines), note: note || '' };
  renderSheet();
}
function renderSheet() {
  const sh = SES.sheet;
  const pre = $('sheetLines');
  $('sheetTitle').textContent = sh ? sh.title : 'Log sheet';
  $('sheetSize').textContent = sh ? (sh.note || sh.lines.length + ' line'
    + (sh.lines.length === 1 ? '' : 's')) : '';
  $('sheetSave').disabled = !sh || !sh.lines.length;
  pre.textContent = '';
  if (!sh || !sh.lines.length) {
    const e = document.createElement('span');
    e.className = 'empty';
    e.textContent = sh ? '(nothing printed)' : 'Open a file, or search with the lens.';
    pre.appendChild(e);
    return;
  }
  for (const line of sh.lines) {
    const e = document.createElement('div');
    const lv = /\[(WARN|ERROR)\]/.exec(line);
    if (lv) e.className = 'lv-' + lv[1];
    e.textContent = line;
    pre.appendChild(e);
  }
  pre.scrollTop = pre.scrollHeight;            // newest at the foot
}
/* The last download's URL is revoked by the next save, not by a timer: the
 * browser may still be reading it when click() returns. */
let saveUrl = null;
function saveSheet() {
  const sh = SES.sheet;
  if (!sh || !sh.lines.length) return;
  if (saveUrl) URL.revokeObjectURL(saveUrl);
  saveUrl = URL.createObjectURL(new Blob([sh.lines.join('\n') + '\n'],
                                         { type: 'text/plain' }));
  const a = document.createElement('a');
  a.href = saveUrl;
  a.download = (sh.name.split('/').pop() || 'log.txt').replace(/[^\w.-]+/g, '_');
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function inertLines(arr) {
  return (arr || []).map(m => String(m == null ? '' : m));
}

async function pullDashboard(fillTape, quiet) {
  const res = await interact('dashboard', {}, { quiet: !!quiet || !fillTape });
  if (fillTape && !quiet) report(res);
  if (!res.ok) return false;
  /* Interactor already strips HTML to plaintext; still paint via textContent. */
  const lines = inertLines(res.result.lines);
  if (!SES.live) SES.live = emptyLive();
  if (fillTape) {
    SES.live.tape = lines.slice(0, N_TAPE);
    SES.live.tail = lines.slice(N_TAPE, N_TAPE + N_TAIL);
    setSheet('Recent lines', 'recent.log', lines.slice().reverse());
  } else {
    SES.live.tail = lines.slice(0, N_TAIL);
  }
  paintAll();
  return true;
}

async function pullDownload(name, quiet) {
  const res = await interact('download', { name }, { quiet: !!quiet });
  if (!quiet) report(res);
  if (!res.ok) return false;
  /* Returned body as inert textContent on the tape, newest first, and in full
   * on the sheet, as the file reads. */
  const file = inertLines(res.result.lines);
  setSheet(res.result.name || name, res.result.name || name, file);
  const lines = file.slice().reverse();
  if (!SES.live) SES.live = emptyLive();
  SES.live.tape = lines;
  paintAll();
  await pullDashboard(false, true);
  return true;
}

/* Raw typed name → GET /logs/{name}; pass-through (no .log suffix). */
async function commitDownload() {
  const name = ((dlInput && dlInput.value) || SES.downloadName || '').trim();
  if (!name) return;
  SES.downloadName = name;
  if (dlInput) dlInput.value = name;
  await pullDownload(name);
}

async function commitSearch() {
  const q = ((qInput && qInput.value) || SES.q || '').trim();
  SES.q = q;
  if (!q) return;
  const params = { q };
  /* Prefer typed sourceText; else dial. */
  const src = ingestSource();
  if (src && src !== 'misc') params.source = src;
  else if (SES.src !== 'all') params.source = SES.src;
  const res = await interact('search', params);
  report(res);
  qInput.setAttribute('aria-invalid', String(!res.ok));
  qInput.title = res.ok ? 'Search the log: type a word, Enter to run it'
    : (res.error || 'no answer from the station');
  if (!res.ok) {
    /* Offline / crash: leave tape alone — never invent a success line. */
    return;
  }
  const found = res.result.matches || [];
  const n = res.result.count != null ? res.result.count : found.length;
  setSheet('Search: ' + q, 'search.log', found,
           n + ' match' + (n === 1 ? '' : 'es'));
  const matches = found.slice().reverse();
  if (!SES.live) SES.live = emptyLive();
  /* Inert: paint via textContent only (r.paint → textContent). */
  SES.live.tape = matches.map(m => String(m == null ? '' : m));
  paintAll();
}

async function commitIngest() {
  const message = ((msgInput && msgInput.value) || '').trim();
  if (!message) return;
  const source = ingestSource();
  const level = SES.level || 'INFO';
  const res = await interact('ingest', { source, level, message });
  report(res);
  if (!res.ok) return;
  const r = res.result || {};
  const stamp = '[' + (r.level || level) + '] ' + (r.message || message);
  if (!SES.live) SES.live = emptyLive();
  SES.live.tape = [stamp].concat(SES.live.tape || []);
  paintAll();
  /* reprint what the stamp landed in, so the new line shows at the foot */
  const into = (r.source || source) + '.log';
  SES.downloadName = into;
  dlInput.value = into;
  await pullDownload(into, true);
  msgInput.value = '';
}

hotspot(P.tape.hotspot, P.tape.label + ' — drag to run the paper', h =>
  drag(h, (x, y) => {
    const r = P.tape.hotspot;
    SES.tapeT = Math.max(0, Math.min(1, (y - r.y) / r.h));
  }));

hotspot(P.lens.hotspot, P.lens.label + ' — drag across the tape; commit search', h => {
  let sx = 0, sy = 0, dragged = false;
  h.addEventListener('pointerdown', e => {
    if (e.target.closest && e.target.closest('input,button')) return;
    e.preventDefault();
    frozen = false;
    sx = e.clientX; sy = e.clientY; dragged = false;
    const moveAngle = ev => {
      const [x, y] = stageXY(ev);
      if (Math.hypot(ev.clientX - sx, ev.clientY - sy) > 6) dragged = true;
      const px = P.lens.pivot_px.x, py = P.lens.pivot_px.y;
      const a = -Math.atan2(x - px, y - py) / D2R;
      SES.lensDeg = Math.max(P.lens.range[0], Math.min(P.lens.range[1], a));
      note();
    };
    const up = () => {
      removeEventListener('pointermove', moveAngle);
      removeEventListener('pointerup', up);
      if (!dragged) {
        qInput.hidden = false;
        if ((SES.q || qInput.value || '').trim()) commitSearch();
        else focusStill(qInput);
      }
    };
    moveAngle(e);
    addEventListener('pointermove', moveAngle);
    addEventListener('pointerup', up, { once: true });
  });
});

hotspot(P.source.hotspot, P.source.label + ' — pick a log file', h =>
  h.addEventListener('click', () => {
    const k = P.source.states;
    SES.src = k[(k.indexOf(SES.src) + 1) % k.length];
    syncSourceTextFromDial();
    frozen = false; applyState(); note();
    const name = namedLog();
    if (name) { SES.downloadName = name; dlInput.value = name; }
    if (name) pullDownload(name);
    else pullDashboard(true);
  }));

/* Wipe confirm: sealed → armed (glass only, no DELETE) → wiped (one DELETE).
 * Armed is the confirm step; only the wipe landing fires the wire. */
hotspot(P.wipe.hotspot, P.wipe.label + ' — break glass (armed), throw again to DELETE',
  h => h.addEventListener('click', () => {
    const k = P.wipe.states;
    const next = k[(k.indexOf(SES.wipe) + 1) % k.length];
    SES.wipe = next;
    frozen = false; applyState(); note();
    if (SES.wipe === 'armed') {
      $('note').textContent =
        'WIPE ARMED — throw again to CONFIRM DELETE /logs/'
        + (namedLog() || '(pick source)')
        + '  ·  ' + TRIS + ' live tris';
      return;
    }
    if (SES.wipe !== 'wiped') return;
    const name = namedLog();
    if (!name) {
      SES.live = emptyLive();
      paintAll();
      return;
    }
    interact('wipe', { name }).then(res => {
      report(res);
      if (!res.ok) return;
      /* Sealed later must NOT resurrect canned theatre — empty overlay only. */
      SES.live = emptyLive();
      setSheet(name, name, [], 'wiped');
      paintAll();
    });
  }));

/* ---- the sheet: tear it off the tail / feed it back into the slot, and where
 * focus goes back to. */
let sheetOpener = null;
let tailHot = null;
function openSheet() {
  const el = SHEET.el;
  const wasDown = el.hidden || SHEET.want === 0;
  if (wasDown) {
    const a = document.activeElement;
    sheetOpener = (a && a !== document.body && a !== document.documentElement
                   && !el.contains(a)) ? a : null;
  }
  frozen = false;
  el.hidden = false;
  SHEET.want = 1;
  paintAll();
  if (!SES.sheet) pullDashboard(true);
  /* Keyboard users land on the sheet; Tab leaves it freely and Escape or the
   * X always put it down. */
  if (wasDown) focusStill($('sheetCard'));
}
function closeSheet() {
  const el = SHEET.el;
  const wasUp = SHEET.want === 1;
  const a = document.activeElement;
  const focusWasHere = !a || a === document.body || a === document.documentElement
    || el.contains(a);
  SHEET.want = 0;
  if (wasUp && focusWasHere) {
    const back = (sheetOpener && sheetOpener.isConnected && !el.contains(sheetOpener))
      ? sheetOpener : tailHot;
    sheetOpener = null;
    focusStill(back);
  }
}

/* The tear-off tail.  Its rect is the tail's own declared planes, clipped to
 * clear the lens hotspot above it. */
{
  const c0 = TAIL0.corners_px, c6 = TAIL6.corners_px;
  const top = Math.max(c0.tl.y, P.lens.hotspot.y + P.lens.hotspot.h) + 2;
  const x0 = Math.min(c0.tl.x, c6.bl.x), x1 = Math.max(c0.tr.x, c6.br.x);
  tailHot = hotspot({ x: x0, y: top, w: x1 - x0, h: c6.bl.y - top },
    'LOG SHEET — tear off the tail to read and add lines', h => {
      h.tabIndex = 0;
      h.setAttribute('role', 'button');
      h.addEventListener('click', () => openSheet());
      h.addEventListener('keydown', ev => {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        ev.preventDefault();
        openSheet();
      });
    });
}

{
  const on = (el, ev, fn) => el.addEventListener(ev, fn);
  on($('sheetClose'), 'click', () => closeSheet());
  on($('sheetOpen'), 'click', () => commitDownload());
  on($('sheetSave'), 'click', () => saveSheet());
  on($('logStamp'), 'click', () => commitIngest());
  on(levelBtn, 'click', () => {
    SES.level = LEVELS[(LEVELS.indexOf(SES.level) + 1) % LEVELS.length];
    levelBtn.textContent = SES.level;
    levelBtn.dataset.level = SES.level;
    note();
  });
  on(srcInput, 'input', () => { SES.sourceText = srcInput.value; });
  on(dlInput, 'input', () => { SES.downloadName = dlInput.value; });
  on(qInput, 'input', () => { SES.q = qInput.value; });
  on(qInput, 'pointerdown', () => { frozen = false; });
  /* Enter submits from a single-line field only, never on key-repeat. */
  const enter = (el, fn) => on(el, 'keydown', ev => {
    if (ev.key !== 'Enter' || ev.repeat) return;
    ev.preventDefault();
    fn();
  });
  enter(qInput, () => commitSearch());
  enter(dlInput, () => commitDownload());
  enter(srcInput, () => focusStill(msgInput));
  enter(msgInput, () => commitIngest());
  /* Escape feeds the sheet back in.  Stopped here so nothing else in this page
   * (the refit docket's own Escape) also reacts.  The cockpit's Escape lives on
   * its own window and never sees keys typed inside this iframe. */
  const closeTop = () => {
    if (SHEET.want) { closeSheet(); return true; }
    return false;
  };
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !SHEET.want) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTop();
  });
  /* exposed so the shell can ask "did the module use this Escape?" first */
  window.__closeOverlay = closeTop;
  syncSourceTextFromDial();
  renderSheet();
}

/* --------------------------------------------------- M5  THE CAPTURE POSE
 * DETERMINISTIC, and identical to export_log.py's POSE_* block -- the numbers
 * come out of scene.json -> capture_pose so the two cannot drift apart.  There
 * is nothing to clearInterval because this module owns no timer; `frozen`
 * pins the two eased followers onto their targets, so pose() twice in a row
 * gives byte-identical screenshots.
 *
 * THE LENS STAYS OVER THE TAPE.  BRIEF 5.3 is explicit that parking live
 * geometry off a readout to make check 4 pass is the wrong trade, and LOG is
 * the module it names.  -34 deg is where a recorder rests while somebody is
 * reading it.
 */
function poseForCapture() {
  /* HIDE BOTH FITTINGS.  Every number in live3d/RESULTS.md and sections 1-5 of
   * this module's NOTES was captured from pose() against Blender renders that
   * contain neither of them; hiding them reproduces all of it unchanged and
   * re-renders nothing.  FIX_UPLOAD section 0 decision 3.  The fittings' own
   * behaviour is measured with them SHOWN --
   * `window.__refit.show(true);window.__mast.show(true)` -- which is a separate
   * capture whose report is byte-identical to this one. */
  if (refit) refit.pose();
  if (mast) mast.pose();
  SES.src = P.source.states[S.capture_pose.source];
  SES.tapeT = S.capture_pose.tape_t;
  SES.lensDeg = S.capture_pose.lens_deg;
  SES.wipe = S.capture_pose.wipe;
  SES.level = 'INFO';
  SES.q = '';
  SES.downloadName = 'nav.log';
  SES.lastInteract = null;
  SES.live = null;
  SES.sheet = null;
  syncSourceTextFromDial();
  qInput.value = '';
  qInput.removeAttribute('aria-invalid');
  msgInput.value = '';
  dlInput.value = SES.downloadName;
  levelBtn.textContent = levelBtn.dataset.level = SES.level;
  setStatus('');
  renderSheet();
  setFieldsHidden(true);
  tapeNow = SES.tapeT; lensNow = SES.lensDeg;
  frozen = true;
  applyState();
  placeTape(tapeNow); placeLens(lensNow);
  note();
}

/* ==================================================================== *
 * THE PAINT CLIP IS TURNED OFF, AND IT IS NOT COSMETIC.
 *
 * The shared template's CSS carries `.readout{overflow:hidden}`.  With EIGHT
 * readouts, seven of them near-coplanar strips 6 mm apart on a folded carrier,
 * Chrome SILENTLY DROPS ONE of those composited layers -- and which one moves
 * with the geometry and with the pixel ratio:
 *
 *   half_h 0.01147 (114.688 el px)   tail_4 missing at pr 1, present at pr 2
 *   half_h 0.0115  (115 el px)       tail_3 missing at pr 1 AND pr 2
 *   half_h 0.0100  (100 el px)       tail_3 missing at pr 2 only
 *
 * Measured on the page: the element lays out, getBoundingClientRect is
 * correct, its computed style is identical to its neighbours', a SOLID
 * BACKGROUND on it does not paint, re-appending it last in the DOM does not
 * help, and giving it a NEIGHBOUR'S transform does not help.  `overflow:clip`,
 * `clip-path:inset(0)`, `contain:paint`, `will-change:transform`,
 * `isolation:isolate` and `transform-style:flat` all reproduce it, so it is
 * the PAINT CLIP and not the flattening.  `overflow:visible` paints all eight,
 * at both ratios, every time.
 *
 * Dropping the clip is SAFE HERE because it is provably redundant:
 * export_log.py asserts, per plane, that the type fits inside the rect --
 * `|top_m| + cap/2 <= half_h`, `top_m - (n-1)*lead - cap/2 >= -half_h`,
 * `left_m >= -half_w` and `left_m + n_cols*adv <= half_w` -- so no glyph can
 * leave its own rect and there is nothing for the clip to do.  It also buys
 * back the descender headroom: at 100 el px the cap top sits 1.7 px inside the
 * clip box, which is a second thing waiting to bite.
 *
 * THE FIX IS `transform-style: flat` ON THE READOUT, and it is one word.
 * `css3d.js`'s `add()` sets `transformStyle = 'preserve-3d'` INLINE on every
 * element it adds.  That makes each readout its own 3D rendering context, so
 * its `.lines` child becomes a 3D-context member with its own layer -- and
 * with seven of those stacked 6 mm apart Chrome drops one of them.  CSS says
 * `overflow` other than `visible` should already force the used value to
 * `flat`; Chrome honours the inline `preserve-3d` instead.  Setting it flat
 * explicitly paints all seven at BOTH pixel ratios, with the template's own
 * `overflow:hidden` clip left exactly as it is.
 *
 * Nothing is lost: a readout is a flat quad with plain divs inside it.  There
 * is no 3D content under a `.readout` for `preserve-3d` to preserve.
 *
 * REPORTED, NOT FIXED IN SHARED CODE: NOTES.md 8.3.  `css3d.js` should not set
 * `preserve-3d` on the leaf it adds; it affects any module with several
 * readouts on one folded carrier -- DNSM's drum is next. */
readouts.forEach(r => { r.el.style.transformStyle = 'flat'; });

/* ...AND THE SEVEN TAIL ELEMENTS ARE PADDED, WHICH IS THE HALF THAT FIXED
 * pixelRatio 2.  `transform-style: flat` alone paints all seven at pr 1 and
 * six at pr 2; a SHORT 3D-transformed layer is what Chrome drops, and the
 * tape readout -- 1035 x 1168 el px, ten lines -- has never been dropped in
 * any configuration at any ratio.  Growing ONE tail element to 300 el px
 * painted all seven at BOTH ratios; growing all seven does the same.
 *
 * The PLANE IS NOT TOUCHED.  `half_h` stays 0.0100 m, so the occlusion rect,
 * the ground-truth oracle, corners_px and the ink scoping are all exactly what
 * the exporter declared -- this only grows the transparent DOM box the glyphs
 * sit in, and shifts `.lines` by the same amount so not one glyph moves.  The
 * element's centre is its transform origin (`translate(-50%,-50%)`), so
 * growing it by 2P moves the centre down by P and `.lines.top += P` puts it
 * back.  Verified: the DOM ink lands where it did before, on Blender's own
 * pixels (check_text, NOTES 5.6). */
/* SWEPT, so that this is a PLATEAU and not a lucky point.  Net element height
 * = 2*half_h/MPP + 2*EL_PAD, measured at both pixel ratios (NOTES 8.3):
 *     210  410  510  710  1110 el px  ->  7/7 tail lines at pr 1 AND pr 2
 *     310                 el px  ->  6/7 at pr 1, 5/7 at pr 2
 *     110 (no padding)    el px  ->  6/7 at pr 1, 5/7 at pr 2
 * 300 puts the element at 710, four hundred pixels clear of the only height
 * that reproduces the drop. */
const EL_PAD = 300;                        // element px added top and bottom
for (const r of readouts.slice(1)) {
  r.el.style.height = (parseFloat(r.el.style.height) + 2 * EL_PAD) + 'px';
  r.lines.style.top = (parseFloat(r.lines.style.top) + EL_PAD) + 'px';
}

/* Ink is MEASURED off Blender's own render of this module's own type, per
 * readout (BRIEF section 7 rule 7): warm grey on ivory paper, and the tail
 * facets read 4-10 levels lighter than the ribbon because they are tipped
 * toward the console's own key light. */
readouts.forEach((r, i) => {
  const ink = S.ink[r.tp.name];
  if (ink) r.el.style.color = 'rgb(' + ink.join(',') + ')';
});

applyState();
placeTape(SES.tapeT);
placeLens(SES.lensDeg);
note();

/* The iris fitting is the rebuild entry. It is not a grade. */
refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is LOG-specific either.
 *
 * IT IS NOT ON THE PORT'S SERVICE RAIL, and that is measured, not preferred.
 * STATUS_AT_A_GLANCE 11.2 mounts this fitting on the port's rail at 1.5 W and
 * says to solve the rail first.  Solved first, LOG's rail runs screen-RIGHT
 * straight at the TEAR-OFF TAIL, which hangs out of the slot standing 95 mm
 * proud of the fascia: from 150 px the mast's envelope overlaps the declared
 * readout rect `tail_6`, between 160 and 170 px the lift CLIFFS from 10.8 mm
 * to 34.0 mm, at 180 px it is 41.7 mm (27 x ubias_m, against KVS's 9.04) and
 * at 200 px the cantilever floor refuses outright.  The 140 px mast that does
 * solve there would be the fleet's smallest AND would sit entirely under the
 * port's own docket.  So this module takes `status_mast.py`'s second,
 * documented route -- `--at PX,PY`, a sub-plate bolted to the panel, which is
 * STATUS_AT_A_GLANCE 6.1's ORIGINAL design and 6.2 rule 4's permitted home --
 * on the RIGHT of the same fascia sill, mirroring the port across the
 * recorder.  The docket that comes out of a left-hand port owns x 12..532, so
 * the right sill is completely clear of it and the mast reads WITH the port
 * open, which is 6.5 item 4's whole point.  The numbers are in section 12 of
 * this module's NOTES.
 *
 * It declares NO readout plane.  Its words are the screen-space caption in
 * live3d/mast.css, so check_occlusion.py's question 5, the dial-face rule and
 * check_text.py are not engaged by it.  `readouts.length` is still 8. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;
note();

/* A module-private hook alongside window.__occ, never instead of it: this is
 * how the numbers in NOTES.md were measured ON THE REAL PAGE rather than
 * argued about, and how the lens is driven ACROSS the tape by the sweep
 * capture (NOTES 5.5). */
window.__log = {
  lens: d => { if (d !== undefined) { SES.lensDeg = +d; lensNow = +d;
                                      placeLens(lensNow); note(); }
               return SES.lensDeg; },
  tape: t => { if (t !== undefined) { SES.tapeT = +t; tapeNow = +t;
                                      placeTape(tapeNow); note(); }
               return SES.tapeT; },
  src: k => { if (k !== undefined) { SES.src = k; applyState(); note(); }
              return SES.src; },
  wipe: k => { if (k !== undefined) { SES.wipe = k; applyState(); note(); }
               return SES.wipe; },
  q: v => { if (v !== undefined) {
              SES.q = String(v);
              if (qInput) qInput.value = SES.q;
              note();
            }
            return SES.q; },
  sourceText: v => { if (v !== undefined) {
                       SES.sourceText = String(v);
                       if (srcInput) srcInput.value = SES.sourceText;
                       note();
                     }
                     return SES.sourceText; },
  downloadName: v => { if (v !== undefined) {
                         SES.downloadName = String(v);
                         if (dlInput) dlInput.value = SES.downloadName;
                         note();
                       }
                       return SES.downloadName; },
  download: () => commitDownload(),
  level: v => { if (v !== undefined) {
                  SES.level = String(v);
                  levelBtn.textContent = levelBtn.dataset.level = SES.level;
                  note();
                }
                return SES.level; },
  message: v => { if (v !== undefined) {
                    if (msgInput) msgInput.value = String(v);
                    note();
                  }
                  return msgInput ? msgInput.value : ''; },
  lastInteract: () => SES.lastInteract,
  sheet: v => { if (v !== undefined) { if (v) openSheet(); else closeSheet(); }
                return { want: SHEET.want, k: SHEET.k, content: SES.sheet }; },
  freeze: v => { if (v !== undefined) frozen = !!v; return frozen; },
  tris: () => TRIS,
  facing: () => facingAudit(camera),
  layout: () => readouts.map(r => ({ name: r.tp.name, ...(r.layout || {}) })),
  planeO: () => readouts.map(r => r.plane.o.toArray()),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's derive() and never a second path. */
  mast: () => mast && mast.state(),
  mastSet: rec => mast.set(rec),
  rig: () => ({ tape: gTape.scene.children.length,
                spools: [gSp0, gSp1].map(g => g.scene.children.length),
                lens: gLens.scene.children.length,
                pane: !!paneMesh, shards: shardMeshes.length,
                domes: srcDomes.length, wipeLamp: wipeLamp.length }),
};

paintAll();
/* DOES THE PAGE ACTUALLY REST IN THE STATE THE GROUND TRUTH WAS RENDERED IN?
 * A monospaced readout can paint the WRONG STRING of the RIGHT LENGTH and
 * every position-based check passes: IPM shipped `OUT 10.3 KB` / `...6/7`
 * against a ground truth of `OUT 41.2 KB` / `...6/8` and check_text.py scored
 * 0.819 px, verify_assets.py passed, and both occlusion runs passed.  Three
 * lines, at load, comparing what the session model generated against what the
 * exporter rendered.  check_text.py now makes the same comparison offline;
 * this one tells you in the browser, where you are actually looking.
 * IPM NOTES 8.4. */
function checkReadoutText() {
  const want = S.readout_text || [];
  readouts.forEach((r, i) => {
    const got = r.els.map(e => e.textContent);
    const w = (want[i] || []).map(String);
    if (!w.length) return;
    if (JSON.stringify(got) !== JSON.stringify(w))
      console.warn('readout ' + (r.tp.name || i) + ' at rest is '
        + JSON.stringify(got) + ' but scene.json -> readout_text says '
        + JSON.stringify(w) + ' -- the page and the ground truth have drifted');
  });
}
checkReadoutText();
/* pose() hides both fittings; the page a human opens must SHOW them, or the
 * page they open is not the page this file describes.  check_occlusion.py's
 * section 0 reports the difference between the as-loaded and the posed frames
 * and that section is REPORTED, NOT FAILED ON, for exactly this case. */
mast.show(true);
layout();
/* One-sided geometry that FrontSide has deleted.  Console warning only; it is
 * not part of __occ.audit(), which means something else and must stay []. */
facingAudit(camera);
requestAnimationFrame(frame);
window.__loaded = true;
