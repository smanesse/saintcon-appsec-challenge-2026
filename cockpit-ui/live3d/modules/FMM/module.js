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
import { OcclusionSplit, attachForeground, makePlateFront } from '../../occlusion.js';
import { applyColour } from '../../grade.js';
/* THE TWO AFTERMARKET FITTINGS, both shared by all nine module pages.
 * `live3d/design/FIX_UPLOAD.md` is the port's design, `STATUS_AT_A_GLANCE.md`
 * the mast's.  Neither adds a readout plane and neither touches this module's
 * own geometry, its controls or its capture pose: every dimension, node name,
 * pivot and hotspot they use comes out of this module's own
 * `scene.json -> refit` / `-> mast`, which live3d/pipeline/refit_port.py and
 * live3d/pipeline/status_mast.py wrote. */
import { mountRefit } from '../../refit.js';
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'FMM';
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
   * VISIBLE and taking min(baked - live) over the pixels where live is nearer.
   * Emit it as `scene.json -> ubias_m`.  CONVERSION_BRIEF step 3.  Too small
   * only risks z-fighting on a genuinely coplanar prop, which is visible and
   * noisy; too big deletes geometry and is silent.  When in doubt go small. */
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
/* THE MODULE'S OWN COLOUR MANAGEMENT -- and FMM is the module that made this
 * file exist.  build.py's close_grade() puts a view transform on the CLOSE
 * camera only: the shell's seven lights dimmed to 45% (already in
 * scene.json -> lights), exposure -0.20 stops, and the look "AgX - Punchy".
 * plate.png is rendered THROUGH that and the live half was not, so every live
 * pixel came out +9..+26 levels brighter than the panel it is bolted to,
 * compare.py read 5.645 against 4.241, and the light_gain sweep had NO MINIMUM
 * AT ALL because the gain was being asked to cancel a grade.
 *
 * THIS PAGE USED TO CARRY ITS OWN COPY of that, below the line, wrapping
 * three's AgX chunk under the name `fmmAgXBase` and pinning both renderers'
 * toneMappingExposure by hand.  grade.js now owns both halves -- exposure onto
 * BOTH renderers (they are two halves of one partition and must agree) and the
 * MEASURED transfer for the look, `AgX - Punchy` -> pow 1.410 / sat 1.000,
 * FMM's own measurement, in LOOK_TRANSFER.  The local wrapper is DELETED,
 * because grade.js detects `fmmAgXBase` and refuses to apply the look on top
 * of it rather than squaring the transfer.  It must run BEFORE the first
 * material compiles, which is why it is here and not where the old block was.
 */
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

/* FMM -- CARGO BAY / MANIFEST VAULT.  The file-transfer console, and the only
 * one on the dash whose panel is split into two decks because the protocol is:
 *
 *   UPPER DECK = CONTROL CHANNEL   the CARGO LIFT lever (RETR / STOR and how
 *                                  hard the hoist pulls), the HOLD gauge, and
 *                                  the PASV / PORT channel selector
 *   LOWER DECK = DATA CHANNEL      the crate on its own rail -- a separate
 *                                  connection, negotiated per transfer
 *
 * THREE READOUTS, AND WHY THEY ARE WHERE THEY ARE (brief section 6, the
 * dial-face rule, which was measured on THIS module):
 *
 *   manifest  the manifest card.  build.py draws four ruled INK BARS there and
 *             no type at all; those bars are FMM's baked stand-in for content
 *             text, so they are excluded from plate.png and the four lines are
 *             DOM, exactly where the bars were.
 *   hold      the gauge's own BLANK BRASS NAMEPLATE.  0/18 in the audit and
 *             0/121 over 27 poses in the exporter's own probe.
 *   data      the blank left end of the DATA CHANNEL tray, which carries no
 *             readout at all today.
 *
 * AND NOT ON THE DIAL FACE.  The exporter probes that plane too and prints the
 * refusal as a number: 15/121 covered, LIVE needle + tail + hub among them.
 * There is no DOM copy of the needle's own angle anywhere on this page; the
 * nameplate carries the hold's ABSOLUTE figures, which a needle cannot show.
 *
 * There is no setInterval and no setTimeout in this file.  Every animation is
 * a state machine driven out of onFrame(), so pose() stops all of it by
 * clearing one flag -- the way to be sure a flag can stop everything is to own
 * no timers (KVS failed check 3 for a 520 ms cursor blink).
 */

const P = S.props;

/* ------------------------------------------------------------------ THE GRADE
 * FMM IS THE ONLY MODULE IN THE FLEET WITH A close_grade(), and the whole of
 * it now lives in the SHARED `live3d/grade.js`, called from section 5 above.
 * What used to be here -- `renderer.toneMappingExposure = 2^exposure`, the
 * same line on `split.renderer`, and a hand-rolled `fmmAgXBase` wrapper round
 * three's AgX chunk carrying `LOOK_POW = 1.410` -- is deleted, not duplicated:
 * grade.js's `patchLook()` detects a `fmmAgXBase` wrapper and REFUSES to apply
 * the look on top of it, so keeping both would silently have disabled the
 * shared path instead of doubling the transfer.  The measurement itself is
 * unchanged and is FMM's: "AgX - Punchy" -> per-channel pow 1.410 in sRGB
 * display space, sat 1.000, fitted over 26,670 opaque pixels, reproducing
 * Blender's own Punchy render to rms 2.70 levels against 26.09 unmodelled.
 * It is the `LOOK_TRANSFER` row in grade.js, credited to this module.
 * NOTES.md 8.1.
 */

/* the measured depth-composite stand-off.  scene.json carries it (the exporter
 * measures min(baked - live) off a second depth pass), so nothing is set here. */

/* ===================================================================== M1 */
/* LIVE PROPS.  Five glbs, 15 meshes, 2,152 triangles -- everything that moves
 * or changes material state.  The other 3,512 triangles are in plate.png. */
const [gLift, gHold, gChan, gLamp, gRail] = await Promise.all([
  load(A + P.lift.glb), load(A + P.hold.glb), load(A + P.channel.glb),
  load(A + P.channel.lamps_glb), load(A + P.rail.glb)]);

const meshes = {};
let TRIS = 0, NMESH = 0;
function take(g, into) {
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    dress(o);
    meshes[o.name] = o;
    NMESH++;
    const ix = o.geometry.index;
    TRIS += (ix ? ix.count : o.geometry.attributes.position.count) / 3;
  });
  into.add(g.scene);
}

const lift = pivotAt(P.lift.hub);
const hold = pivotAt(P.hold.hub);
const chan = pivotAt(P.channel.hub);
const rail = new THREE.Group();  scene.add(rail);
const lampG = new THREE.Group(); scene.add(lampG);
take(gLift, lift.inner);
take(gHold, hold.inner);
take(gChan, chan.inner);
take(gLamp, lampG);
take(gRail, rail);
applyMatFix();

const AX = {
  lift: new THREE.Vector3().fromArray(P.lift.axis).normalize(),
  hold: new THREE.Vector3().fromArray(P.hold.axis).normalize(),
  chan: new THREE.Vector3().fromArray(P.channel.axis).normalize(),
  rail: new THREE.Vector3().fromArray(P.rail.axis).normalize(),
};

/* A LAMP THAT IS NEVER LIT IN ANY glb HAS NO MATERIAL IN THREE.  build.py
 * exports dome 0 cyan and dome 1 off, so `fmm_lamp_amber` reaches the page only
 * through materials.json -- which carries every material in the scene, not just
 * the ones a glb happened to reference.  So the state swap is "put this
 * material RECORD onto the mesh's own cloned material", not "swap in another
 * material object".  The `patched` record is updated too, or the materials.json
 * A/B toggle would put the previous state's roughness back. */
function setMatByName(mesh, name) {
  const rec = MJ[name];
  if (!rec) { console.warn('no materials.json record for ' + name); return; }
  const m = mesh.material;
  m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                 THREE.LinearSRGBColorSpace);
  if (rec.emit > 0) {
    m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                      THREE.LinearSRGBColorSpace);
    m.emissiveIntensity = rec.emit;
  } else {
    m.emissive.setRGB(0, 0, 0, THREE.LinearSRGBColorSpace);
    m.emissiveIntensity = 0;
  }
  for (const p of patched) if (p.m === m) p.rec = rec;
  m.roughness = matFixOn ? rec.rough : m.roughness;
  m.metalness = matFixOn ? rec.metallic : m.metalness;
  m.needsUpdate = true;
}
const domes = P.channel.domes.map(n => meshes[n]);

/* ===================================================================== M2 */
/* THE SESSION MODEL.  FMM speaks FTP: a CONTROL channel carrying orders and a
 * DATA channel, negotiated per transfer, carrying the payload.  Every value
 * below is generated here and reaches a readout through the template's
 * r.paint() -> textContent.  No innerHTML anywhere in this file. */
const CATALOGUE = [                     // frozen for pose() / checkers only
  ['44-12', 'CARGO.TAR.GZ', 2211840],
  ['44-13', 'BALLAST.IMG', 1048576],
  ['51-02', 'STARCHART.DB', 3670016],
  ['51-07', 'RATIONS.MAN', 524288],
  ['62-19', 'HULL.PATCH.Z', 786432],
];
const CP = S.capture_pose;
const FILE_NAME = /^([a-zA-Z0-9_]+)+\.[a-zA-Z0-9]+$/;
const FULL_CAP = 4 * 1024 * 1024;      // the bridge's RETR full=1 cap

const SES = {
  authenticated: false,
  token: '',
  cwd: '',
  enterCwd: '',              // path arg for one-shot SESS+CWD
  listing: [],
  sel: 0,
  type: 'I',
  user: '',
  retrName: '',
  view: null,                // { name, bytes, size, partial } of the last RETR
  upload: null,              // { name, bytes } when Upload carries a disk file
  slip: '',                  // 'view' | 'up' while the cargo slip is unrolled
  showLog: false,
  xferTo: 1,
  xferThen: null,
  log: [],
  posed: false,
  lastReply: '',
  transcript: '',
  preview: '',
  done: 0,
  size: 0,
  xferPlay: false,
  idx: 0,
  dir: 'STOR',
  liftDeg: CP.lift_deg,
  holdPct: CP.hold_pct,
  channel: CP.channel,
  host: '',
  port: 0,
  t: CP.rail_t,
  running: false,
};

function isFile(name) {
  return typeof name === 'string' && FILE_NAME.test(name);
}
function isDir(name) {
  return !!name && !isFile(name);
}
function currentEntry() {
  return SES.listing[SES.sel] || '';
}
function shortCwd(raw) {
  let s = String(raw || '');
  const q = s.match(/"([^"]*)"/);
  if (q) s = q[1];
  else if (/^\d{3}\s/.test(s)) s = s.slice(4);
  return s.replace(/^\.\//, '');
}

async function interact(action, params) {
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'FMM', action, params: params || {} }),
    });
    let j = {};
    try { j = await r.json(); }
    catch (e) { return { ok: false, error: 'bad json' }; }
    const result = (j && j.result != null) ? j.result : j;
    if (result && typeof result === 'object') return result;
    return { ok: false, error: 'empty result' };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
}

function replyOf(result) {
  if (!result) return '';
  if (result.reply) return String(result.reply);
  const tr = result.transcript;
  if (Array.isArray(tr) && tr.length)
    return String(tr[tr.length - 1] || '');
  return String(result.error || result.summary || '');
}

/* Interact replies are inert text only — never assigned to innerHTML. */
function transcriptText(result) {
  if (!result) return '';
  const parts = [];
  const seen = Object.create(null);
  function push(line) {
    const s = String(line == null ? '' : line);
    if (!s || seen[s]) return;
    seen[s] = 1;
    parts.push(s);
  }
  if (Array.isArray(result.transcript))
    result.transcript.forEach(push);
  push(result.reply);
  if (Array.isArray(result.entries) && result.entries.length)
    push('ENTRIES: ' + result.entries.map(String).join(' | '));
  if (result.preview != null && result.preview !== '')
    push('PREVIEW: ' + String(result.preview));
  push(result.summary);
  push(result.error);
  if (result.session_token)
    push('token=' + String(result.session_token));
  if (result.endpoint && result.endpoint.host)
    push('endpoint ' + result.endpoint.host + ':' + result.endpoint.port
      + (result.endpoint.mode ? ' (' + result.endpoint.mode + ')' : ''));
  return parts.join('\n');
}

function applyEndpoint(result) {
  const ep = result && result.endpoint;
  if (!ep) return;
  if (ep.host) SES.host = ep.host;
  if (ep.port) SES.port = ep.port;
}

function noteReply(result) {
  SES.lastReply = replyOf(result);
  SES.transcript = transcriptText(result);
  SES.preview = result && result.preview != null ? String(result.preview) : '';
}

function rnd(lo, hi) {                    // a real random, not Math.random
  const b = new Uint32Array(1);
  crypto.getRandomValues(b);
  return lo + (b[0] % (hi - lo + 1));
}
function negotiate() {                    // local throw theatre when logged out
  SES.port = rnd(49152, 65535);
  SES.host = SES.channel === 'pasv' ? '10.14.2.9' : '10.14.2.31';
}

/* ---- formatting.  Layout only; the safety is textContent. */
function group(n) {                       // 2211840 -> "2 211 840"
  const s = String(n), out = [];
  for (let i = s.length; i > 0; i -= 3) out.unshift(s.slice(Math.max(0, i - 3), i));
  return out.join(' ');
}
function mib(bytes) {                     // 1509949 -> "1.44M"
  return (bytes / 1048576).toFixed(2) + 'M';
}
function fit(s, n) {                      // pad/clip to the plane's own columns
  s = String(s);
  return s.length > n ? s.slice(0, n) : s + ' '.repeat(n - s.length);
}
function lr(a, b, n) {                    // "DATA CH       PASV"
  a = String(a); b = String(b);
  const gap = Math.max(1, n - a.length - b.length);
  return fit(a + ' '.repeat(gap) + b, n);
}

const NC = {};                             // the exporter's own column counts
readouts.forEach(r => { NC[r.tp.name] = r.tp.type.n_cols; });

function lines(name) {
  if (name === 'hold') {
    const capB = 2097152;
    return [fit(mib(capB * SES.holdPct) + ' / ' + mib(capB), NC.hold)];
  }
  if (name === 'data') {
    const ch = String(SES.channel || 'pasv').toUpperCase();
    const ty = SES.type || 'I';
    const ep = SES.host ? (SES.host + ':' + SES.port) : '';
    const err = SES.lastReply && /^(530|550|553|425|504|501)\b/.test(SES.lastReply);
    const msg = /^425\b/.test(SES.lastReply || '') && SES.channel === 'port'
      ? '425 PORT: USE PASV' : SES.lastReply;
    return [lr('DATA CH', ch + '  ' + ty, NC.data),
            fit(ep, NC.data),
            fit(err ? msg : ((SES.done || 0) + ' / ' + (SES.size || 0)), NC.data)];
  }
  const cols = NC.manifest;
  if (sheetUp()) return ['', '', '', ''];  // the sheet is in the hand
  if (!SES.authenticated) {
    return [fit('SIGNED OUT', cols),
            fit('', cols),
            fit('CLICK TO PICK UP', cols),
            fit('THE SHEET', cols)];
  }
  const cwd = shortCwd(SES.cwd) || 'ftproot';
  const win = 3;
  const n = SES.listing.length;
  let start = 0;
  if (n > win) {
    start = SES.sel;
    if (start > n - win) start = Math.max(0, n - win);
  }
  const rows = [fit(cwd, cols)];
  for (let i = 0; i < win; i++) {
    const idx = start + i;
    if (idx >= n) { rows.push(fit('', cols)); continue; }
    const mark = idx === SES.sel ? '>' : ' ';
    let nm = String(SES.listing[idx]);
    if (isDir(nm) && nm !== '.' && nm !== '..') nm += '/';
    rows.push(fit(mark + ' ' + nm, cols));
  }
  return rows;
}
function paintAll() {
  if (SES.posed) {
    const canned = S.readout_text || [];
    readouts.forEach((r, i) => r.paint(canned[i] || []));
    return;
  }
  readouts.forEach(r => r.paint(lines(r.tp.name)));
}

/* ---- the three MEASURED inks, one per readout (scene.json -> ink). */
readouts.forEach(r => {
  const c = S.ink && S.ink[r.tp.name];
  if (c) r.el.style.color = 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
});

function dataParams(extra) {
  const p = {
    token: SES.token,
    type: SES.type,
    channel: SES.channel === 'port' ? 'port' : 'pasv',
  };
  if (SES.enterCwd) p.cwd = SES.enterCwd;
  if (extra) Object.assign(p, extra);
  return p;
}

/* ---- bytes <-> base64, for full RETR and binary STOR. */
function b64ToBytes(b64) {
  const s = atob(b64 || '');
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}
function bytesToB64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000)
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
function asText(bytes) {               // null when the bytes are not text
  if (bytes.indexOf(0) >= 0) return null;
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch (e) { return null; }
}
function hexDump(bytes, max) {
  const n = Math.min(bytes.length, max), rows = [];
  for (let o = 0; o < n; o += 16) {
    const row = bytes.subarray(o, Math.min(o + 16, n));
    const hex = Array.from(row, b => b.toString(16).padStart(2, '0')).join(' ');
    const asc = Array.from(row, b => (b >= 32 && b < 127) ? String.fromCharCode(b) : '.').join('');
    rows.push(o.toString(16).padStart(6, '0') + '  ' + hex.padEnd(48) + ' ' + asc);
  }
  return rows.join('\n');
}
const IMG_TYPES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
                    gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp' };
function ext(name) {
  const m = /\.([A-Za-z0-9]+)$/.exec(name || '');
  return m ? m[1].toLowerCase() : '';
}
function sizeText(n) {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KiB';
  return (n / 1048576).toFixed(2) + ' MiB';
}
function joinPath(base, name) {
  return base.split('/').filter(Boolean).concat([name]).join('/');
}
function parentPath(path) {
  return path.split('/').filter(Boolean).slice(0, -1).join('/');
}

/* ---- HELD PAPER.  The manifest sheet and the cargo slip are DOM cards in a
 * second CSS3D layer, laid on the panel's own basis (every FMM plane shares one
 * u / v / n).  `k` runs 0..1: 0 is the paper at rest (the sheet flat on the
 * clipboard, the slip rolled up in the crate), 1 is held up toward the camera.
 * onFrame() eases k toward `want`; no timers. */
const held = new CSS3DLayer($('held'), W, H);
const MAN = PLANES.find(p => p.name === 'manifest') || PLANES[0];
const PU = new THREE.Vector3().fromArray(MAN.u);
const PV = new THREE.Vector3().fromArray(MAN.v);
const PN = new THREE.Vector3().fromArray(MAN.n);
const SHEET = { el: $('punch'), w: 520, h: 470, k: 0, want: 0,
                at: { x: 440, y: 290, w: 430 } };
const SLIP = { el: $('slip'), w: 460, h: 440, k: 0, want: 0,
               at: { x: 925, y: 318, w: 350 } };
SHEET.rec = held.add(SHEET.el);
SLIP.rec = held.add(SLIP.el);

/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the clipboard's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = camera.position.distanceTo(new THREE.Vector3().fromArray(MAN.origin)) * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  const m = at.w * perPx / elW;
  return { o, mx: m, my: m };
}
const SHEET_REST = {
  o: new THREE.Vector3().fromArray(MAN.origin),
  mx: 2 * MAN.half_w / SHEET.w, my: 2 * MAN.half_h / SHEET.h,
};
const SHEET_UP = heldPose(SHEET.at, SHEET.w, 0.86);
const SLIP_UP = heldPose(SLIP.at, SLIP.w, 0.86);
const crateBox = new THREE.Box3();
function slipRest() {                     // rolled up on top of the crate
  rail.updateMatrixWorld(true);
  crateBox.setFromObject(meshes.fmm_skid_body || rail);
  const c = crateBox.getCenter(new THREE.Vector3());
  const sz = crateBox.getSize(new THREE.Vector3());
  const my = 0.004 / SLIP.h;
  return { o: c.addScaledVector(PV, sz.y * 0.35 + SLIP.h * my / 2).addScaledVector(PN, 0.01),
           mx: 0.05 / SLIP.w, my };
}
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function placeHeld(H_, rest, up) {
  const e = ease(H_.k);
  const o = rest.o.clone().lerp(up.o, e);
  const mx = rest.mx + (up.mx - rest.mx) * e;
  const my = rest.my + (up.my - rest.my) * e;
  H_.rec.matrix = new THREE.Matrix4().makeBasis(
    PU.clone().multiplyScalar(mx), PV.clone().multiplyScalar(my), PN).setPosition(o);
}
function tickHeld(dt) {
  let moved = false;
  for (const H_ of [SHEET, SLIP]) {
    if (H_.k === H_.want) continue;
    const step = dt * 4;
    H_.k = H_.want > H_.k ? Math.min(H_.want, H_.k + step) : Math.max(H_.want, H_.k - step);
    moved = true;
    if (H_.k === 0 && H_.want === 0) H_.el.hidden = true;
  }
  if (!SHEET.el.hidden) placeHeld(SHEET, SHEET_REST, SHEET_UP);
  if (!SLIP.el.hidden) placeHeld(SLIP, slipRest(), SLIP_UP);
  if (moved) paintAll();
  held.render(camera);
}
function sheetUp() { return SHEET.k > 0.02 || SHEET.want > 0; }

/* ---- the sheet: pick up / put down, and where focus goes back to. */
let punchOpener = null;
let manifestHot = null;
function openPunch() {
  const el = $('punch');
  const wasHidden = el.hidden || SHEET.want === 0;
  if (wasHidden) {
    const a = document.activeElement;
    punchOpener = (a && a !== document.body && a !== document.documentElement
                   && !el.contains(a)) ? a : null;
  }
  el.hidden = false;
  SHEET.want = 1;
  SES.posed = false;
  renderDesk();
  /* Keyboard users land on the sheet (Escape then works at once); it is not a
   * trap: Tab leaves it freely and Escape / the X always put it down. */
  if (wasHidden) {
    const card = $('punchCard');
    try { card.focus({ preventScroll: true }); } catch (e) { card.focus(); }
  }
}
function hidePunch() {
  const el = $('punch');
  const wasOpen = SHEET.want === 1;
  const a = document.activeElement;
  const focusWasHere = !a || a === document.body || a === document.documentElement
    || el.contains(a);
  SHEET.want = 0;
  if (wasOpen && focusWasHere) {
    const back = (punchOpener && punchOpener.isConnected && !el.contains(punchOpener))
      ? punchOpener : manifestHot;
    punchOpener = null;
    if (back && back.focus) {
      try { back.focus({ preventScroll: true }); } catch (e) { back.focus(); }
    }
  }
}
/* ---- the slip: unroll out of the crate / roll back in. */
function openSlip(mode) {
  SES.slip = mode;
  if (mode === 'view') renderView();
  else $('deskViewSize').textContent = '';
  $('slipView').hidden = mode !== 'view';
  $('slipUp').hidden = mode !== 'up';
  $('slipTitle').textContent = mode === 'up' ? 'Outbound slip'
    : (SES.view ? SES.view.name : 'Cargo slip');
  SLIP.el.hidden = false;
  SLIP.want = 1;
  SES.posed = false;
  renderDesk();
}
function closeSlip() {
  const a = document.activeElement;
  if (SLIP.el.contains(a)) {
    const back = SHEET.want ? $('deskList') : manifestHot;
    if (back) back.focus({ preventScroll: true });
  }
  SLIP.want = 0;
}
function setStatus(text, kind, fix) {
  const el = $('punchReply');
  el.textContent = text || '';
  el.className = kind || '';
  el.title = text || '';
  $('punchFix').hidden = !fix;
}

/* A 425 means the data channel never opened.  In PORT mode that is almost
 * always the station failing to connect BACK to the desk, which the player
 * cannot fix from here -- so say so, and offer the one-click way out. */
function dataChannelFailed(r) {
  return !r.ok && /^425\b/.test(SES.lastReply || '');
}
function explain425() {
  if (SES.channel === 'port')
    return 'PORT failed (425): the station could not connect back to the desk to open '
      + 'the data channel. Switch CHANNEL to PASV and try again.';
  return 'PASV failed (425): the desk could not open the data channel to the station. '
    + 'Try again, or switch CHANNEL on the bay.';
}

/* ---- the control log: every exchange, newest last, capped. */
const LOG_MAX = 60;
function logExchange(label, result) {
  const body = transcriptText(result);
  SES.log.push('> ' + label + '\n' + (body || '(no reply)'));
  if (SES.log.length > LOG_MAX) SES.log.splice(0, SES.log.length - LOG_MAX);
  const el = $('deskLog');
  el.textContent = SES.log.join('\n\n');
  el.scrollTop = el.scrollHeight;
}
function toggleLog() {
  SES.showLog = !SES.showLog;
  renderDesk();
  if (SES.showLog) { const el = $('deskLog'); el.scrollTop = el.scrollHeight; }
}

/* One request at a time.  `label` is what the status line calls it. */
let inFlight = false;
async function op(label, fn) {
  if (inFlight) return null;
  inFlight = true;
  SES.posed = false;
  setStatus(label + ' ...', 'busy');
  renderDesk();
  try { return await fn(); }
  finally { inFlight = false; renderDesk(); paintAll(); }
}
async function call(label, action, params) {
  const r = await interact(action, params);
  noteReply(r);
  logExchange(label, r);
  if (/^530\b/.test(SES.lastReply) && SES.token && action !== 'login') {
    signOut('Session no longer valid: ' + SES.lastReply);
    return r;
  }
  if (dataChannelFailed(r)) {
    setStatus(explain425(), 'err', SES.channel === 'port');
    if (!SHEET.want) openPunch();          // a lift pull must not fail silently
    return r;
  }
  setStatus(r.summary || SES.lastReply || r.error || '', r.ok ? 'ok' : 'err');
  return r;
}

/* The crate's run along the rail.  t = 1 is the dock under the slip; an inbound
 * file (RETR) arrives there, an outbound one (STOR) leaves from it. */
function startXfer(size, dir, from, to, then) {
  SES.dir = dir;
  SES.size = size;
  SES.done = size;
  SES.t = from;
  SES.xferTo = to;
  SES.xferThen = then || null;
  SES.xferPlay = true;
  SES.running = true;
}
function onXferDone() {
  const f = SES.xferThen;
  SES.xferThen = null;
  if (f) f();
}

/* ---- session */
async function doLogin() {
  const user = $('punchUser').value.trim();
  const pass = $('punchPass').value;
  if (!user) { setStatus('Enter a user name.', 'err'); return; }
  await op('LOGIN ' + user, async () => {
    const r = await call('LOGIN ' + user, 'login', { user, pass });
    if (!(r.ok && (r.session_token || r.authenticated))) { SES.authenticated = false; return; }
    beginSession(user, r.session_token || '', r.cwd);
    await listNow();
  });
  $('deskList').focus({ preventScroll: true });
}
async function doSess() {
  const token = $('punchTok').value.trim();
  if (!token) { setStatus('Enter a session token.', 'err'); return; }
  await op('SESS ' + token, async () => {
    const r = await call('SESS ' + token, 'sess', { token });
    if (!r.ok) { SES.authenticated = false; return; }
    const m = /resumed as ([\w.@-]+)/i.exec(r.reply || '');
    beginSession(m ? m[1] : '', token, r.cwd);
    await listNow();
  });
}
function beginSession(user, token, cwd) {
  SES.authenticated = true;
  SES.user = user;
  SES.token = token;
  SES.cwd = cwd || '';
  SES.enterCwd = '';
  SES.listing = [];
  SES.sel = 0;
  $('punchTok').value = token;
}
function signOut(why) {
  SES.authenticated = false;
  SES.token = '';
  SES.user = '';
  SES.enterCwd = '';
  SES.cwd = '';
  SES.listing = [];
  SES.sel = 0;
  closeSlip();
  setStatus(why || 'Signed out. The token is forgotten on this desk.', why ? 'err' : '');
  renderDesk();
  paintAll();
}

/* ---- folders */
function applyListing(result) {
  if (!result) return;
  if (Array.isArray(result.entries)) {
    const dirs = [], files = [];
    result.entries.map(String).forEach(n => {
      if (n === '.' || n === '..') return;  // the sheet has its own Up
      (isFile(n) ? files : dirs).push(n);
    });
    const by = (a, b) => a.localeCompare(b);
    const keep = currentEntry();
    SES.listing = dirs.sort(by).concat(files.sort(by));
    const i = SES.listing.indexOf(keep);
    SES.sel = i >= 0 ? i : 0;
  }
  if (result.cwd) SES.cwd = result.cwd;
  applyEndpoint(result);
}
async function listNow() {
  const r = await call('LIST ' + (SES.enterCwd || '/'), 'list', dataParams());
  if (r.ok) applyListing(r);
  else applyEndpoint(r);
  return r;
}
function refreshList() {
  if (!SES.authenticated) return null;
  return op('LIST', listNow);
}
async function cwdNow(path) {
  if (!path) {
    const prev = SES.enterCwd;
    SES.enterCwd = '';
    const r = await listNow();
    if (!r.ok) SES.enterCwd = prev;
    return r;
  }
  const r = await call('CWD ' + path, 'cwd', {
    token: SES.token, dir: path, type: SES.type,
    channel: SES.channel === 'port' ? 'port' : 'pasv',
  });
  if (r.ok) { SES.enterCwd = path; SES.sel = 0; SES.listing = []; applyListing(r); }
  return r;
}
function navigate(path) {
  if (!SES.authenticated) return null;
  return op('CWD', () => cwdNow(path));
}
function goUp() {
  if (!SES.enterCwd) return null;
  return navigate(parentPath(SES.enterCwd));
}
/* A listing has names only.  Names shaped like file names are fetched; anything
 * else is tried as a folder first and fetched if the server says it is not. */
function openEntry(name) {
  if (!name || !SES.authenticated) return null;
  if (isFile(name)) return retrieve(name);
  return op('CWD', async () => {
    const r = await cwdNow(joinPath(SES.enterCwd, name));
    if (!r.ok && /^550\b/.test(r.reply || '')) await retrNow(name);
  });
}

/* ---- transfers */
async function retrNow(name) {
  const r = await call('RETR ' + name, 'retr', dataParams({ filename: name, full: 1 }));
  applyEndpoint(r);
  if (!r.ok) return r;
  const bytes = r.content_b64 != null ? b64ToBytes(r.content_b64)
    : new TextEncoder().encode(r.preview || '');
  const i = SES.listing.indexOf(name);
  if (i >= 0) SES.sel = i;
  SES.view = { name, bytes, size: r.size || bytes.length,
               partial: !!r.truncated || r.content_b64 == null };
  SES.retrName = name;
  renderView();
  /* roll any open slip back in, run the crate in to the dock, then unroll */
  SLIP.want = 0;
  startXfer(r.size || bytes.length, 'RETR', 0, 1, () => openSlip('view'));
  return r;
}
function retrieve(name) {
  name = name || currentEntry();
  if (!SES.authenticated) { openPunch(); setStatus('Sign in first.', 'err'); return null; }
  if (!name) { setStatus('Pick a file on the manifest first.', 'err'); return null; }
  return op('RETR ' + name, () => retrNow(name));
}
function uploadName() {
  return $('punchStor').value.trim();
}
function newSlip() {
  if (!SES.authenticated) { openPunch(); setStatus('Sign in first.', 'err'); return; }
  SES.t = 1;                         // the crate glides to the dock
  SES.running = true;
  openSlip('up');
  $('punchStor').focus({ preventScroll: true });
}
function upload() {
  if (!SES.authenticated) { openPunch(); setStatus('Sign in first.', 'err'); return null; }
  const filename = uploadName();
  if (!isFile(filename)) {
    if (SES.slip !== 'up' || SLIP.want === 0) openSlip('up');
    setStatus('Name not accepted: letters, digits or underscores, a dot, an extension.', 'err');
    return null;
  }
  const bytes = SES.upload ? SES.upload.bytes : new TextEncoder().encode($('punchBody').value);
  return op('STOR ' + filename, async () => {
    const r = await call('STOR ' + filename + ' (' + bytes.length + ' B)', 'stor',
      dataParams({ filename, body_b64: bytesToB64(bytes) }));
    applyEndpoint(r);
    if (!r.ok) return;
    /* fold the slip into the crate, and the crate runs out to the station */
    closeSlip();
    startXfer(bytes.length, 'STOR', 1, 0);
    await listNow();
    const i = SES.listing.indexOf(filename);
    if (i >= 0) SES.sel = i;
    setStatus(r.summary || r.reply, 'ok');
  });
}

/* ---- the slip's view of a fetched file */
let imgUrl = null;
function renderView() {
  const v = SES.view;
  const pre = $('deskView'), img = $('deskImg');
  if (imgUrl) { URL.revokeObjectURL(imgUrl); imgUrl = null; }
  img.hidden = true;
  img.removeAttribute('src');
  pre.hidden = false;
  pre.className = '';
  $('deskSave').disabled = !v;
  $('deskEdit').disabled = !v || asText(v.bytes) == null;
  if (!v) { pre.textContent = ''; $('deskViewSize').textContent = ''; return; }
  $('deskViewSize').textContent = sizeText(v.size) + (v.partial ? ' (partial)' : '');
  const type = IMG_TYPES[ext(v.name)];
  if (type && v.bytes.length) {
    imgUrl = URL.createObjectURL(new Blob([v.bytes], { type }));
    img.src = imgUrl;
    img.alt = v.name;
    img.hidden = false;
    pre.hidden = true;
    return;
  }
  const text = asText(v.bytes);
  if (text != null) {
    pre.textContent = v.bytes.length ? (text.length > 200000
      ? text.slice(0, 200000) + '\n... (Save to see the rest)' : text) : '(empty file)';
    return;
  }
  pre.className = 'hex';
  pre.textContent = hexDump(v.bytes, 4096)
    + (v.bytes.length > 4096 ? '\n... binary, ' + sizeText(v.bytes.length) + ' (Save to keep it)' : '');
}
function saveView() {
  const v = SES.view;
  if (!v) return;
  const url = URL.createObjectURL(new Blob([v.bytes], { type: 'application/octet-stream' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = v.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
function editView() {
  const v = SES.view;
  const text = v && asText(v.bytes);
  if (text == null) return;
  clearDiskFile();
  $('punchStor').value = v.name;
  $('punchBody').value = text;
  openSlip('up');
  $('punchBody').focus({ preventScroll: true });
}

/* ---- upload source: the textarea, or a file from disk */
function clearDiskFile() {
  SES.upload = null;
  $('deskFile').value = '';
}
async function pickDiskFile(file) {
  if (!file) return;
  if (file.size > FULL_CAP) {
    setStatus('That file is ' + sizeText(file.size) + '; a crate carries up to '
      + sizeText(FULL_CAP) + '.', 'err');
    return;
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  SES.upload = { name: file.name, bytes };
  const m = /^(.*?)(?:\.([^.]*))?$/.exec(file.name);
  const base = m[1].replace(/[^A-Za-z0-9_]/g, '_') || 'upload';
  const tail = (m[2] || '').replace(/[^A-Za-z0-9]/g, '') || 'bin';
  $('punchStor').value = base + '.' + tail;
  renderDesk();
}

/* ---- transfer settings: the bay's CHANNEL and TYPE controls */
function setChannel(ch) {
  if (SES.channel === ch) return;
  SES.channel = ch;
  SES.posed = false;
  applyLamps();
  if (SES.authenticated) refreshList();
  else negotiate();
  paintAll();
}
function setType(code) {
  SES.type = code === 'A' ? 'A' : 'I';
  SES.posed = false;
  paintAll();
  if (SES.authenticated)
    op('TYPE ' + SES.type, () => call('TYPE ' + SES.type, 'type', { token: SES.token, code: SES.type }));
}
function doType() { setType(SES.type === 'I' ? 'A' : 'I'); }

/* ---- paint the paper from SES.  textContent only, no markup from the wire. */
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function renderDesk() {
  const authed = SES.authenticated;
  $('deskLogin').hidden = authed;
  $('deskMain').hidden = !authed;
  ['punchLogin', 'punchSess'].forEach(id => { $(id).disabled = inFlight; });

  const nm = uploadName();
  const bad = !!nm && !isFile(nm);
  $('punchStor').setAttribute('aria-invalid', String(bad));
  $('deskNameHint').classList.toggle('bad', bad);
  $('deskNameHint').textContent = bad
    ? 'not accepted: letters, digits or underscores, a dot, an extension'
    : 'letters, digits or underscores, a dot, an extension';
  $('punchDoStor').disabled = inFlight || !isFile(nm);
  $('punchBody').disabled = !!SES.upload;
  $('deskFileNote').textContent = SES.upload
    ? 'from disk: ' + SES.upload.name + ', ' + sizeText(SES.upload.bytes.length) : '';
  $('deskPick').textContent = SES.upload ? 'Use text' : 'From disk…';
  if (!authed) return;

  $('deskWho').textContent = (SES.user || 'session').toUpperCase();
  $('deskTokShow').textContent = SES.token ? 'token ' + SES.token : '';
  $('deskCopyTok').disabled = !SES.token;

  const crumbs = $('deskCrumbs');
  crumbs.textContent = '';
  const parts = SES.enterCwd.split('/').filter(Boolean);
  const crumb = (label, path) => {
    const b = mk('button', '', label);
    b.type = 'button';
    b.title = 'Go to /' + path;
    b.disabled = inFlight;
    b.addEventListener('click', () => navigate(path));
    crumbs.appendChild(b);
  };
  crumb('ftproot', '');
  parts.forEach((p, i) => {
    crumbs.appendChild(mk('span', 'sep', '/'));
    crumb(p, parts.slice(0, i + 1).join('/'));
  });
  if (parts.length) crumbs.lastChild.setAttribute('aria-current', 'page');
  $('deskUp').disabled = inFlight || !parts.length;
  $('punchList').disabled = inFlight;

  $('deskList').hidden = !!SES.showLog;
  $('deskLog').hidden = !SES.showLog;
  $('deskLogBtn').classList.toggle('on', !!SES.showLog);
  $('deskLogBtn').setAttribute('aria-pressed', String(!!SES.showLog));

  const list = $('deskList');
  const scroll = list.scrollTop;
  list.textContent = '';
  if (!SES.listing.length)
    list.appendChild(mk('div', 'empty', inFlight ? 'Listing ...' : 'This folder is empty.'));
  SES.listing.forEach((name, i) => {
    const row = mk('div', 'row' + (i === SES.sel ? ' sel' : ''));
    row.setAttribute('role', 'option');
    row.setAttribute('aria-selected', String(i === SES.sel));
    row.id = 'deskRow' + i;
    row.appendChild(mk('span', 'kind', isFile(name) ? 'FILE' : 'DIR'));
    row.appendChild(mk('span', 'nm', isFile(name) ? name : name + '/'));
    row.title = isFile(name) ? 'Double-click to open' : 'Double-click to enter';
    row.addEventListener('click', () => selectEntry(i));
    row.addEventListener('dblclick', () => openEntry(name));
    list.appendChild(row);
  });
  list.scrollTop = scroll;
  if (SES.listing.length) list.setAttribute('aria-activedescendant', 'deskRow' + SES.sel);
  else list.removeAttribute('aria-activedescendant');

  const cur = currentEntry();
  const open = $('punchDoRetr');
  open.disabled = inFlight || !cur;
  open.textContent = cur && !isFile(cur) ? 'Enter' : 'Open';
  $('deskNew').disabled = inFlight;
}
function selectEntry(i) {
  if (i < 0 || i >= SES.listing.length) return;
  SES.sel = i;
  SES.posed = false;
  if (isFile(SES.listing[i])) SES.retrName = SES.listing[i];
  renderDesk();
  paintAll();
  const row = $('deskRow' + i);
  if (row) row.scrollIntoView({ block: 'nearest' });
}

/* ---- the CARGO LIFT: up fetches the selected file, down loads the slip. */
function commitLift() {
  SES.posed = false;
  const r = rate();
  SES.dir = r >= 0 ? 'STOR' : 'RETR';
  if (!(Math.abs(r) > 0)) return;
  if (!SES.authenticated) {
    openPunch();
    setStatus('Sign in first: the lift moves cargo for a signed-in desk.', 'err');
    paintAll();
    return;
  }
  if (SES.dir === 'RETR') {
    const name = currentEntry();
    if (!isFile(name)) { setStatus('Lift up fetches the selected file. Select one first.', 'err'); return; }
    retrieve(name);
    return;
  }
  if (SES.slip !== 'up' || SLIP.want === 0) { newSlip(); return; }
  upload();
}

/* ===================================================================== M3 */
/* THE REFIT PORT and THE TELLTALE MAST.  Mounted at the bottom of this file,
 * after this module's own hotspot helper exists; declared HERE because
 * onFrame() and poseForCapture() both reach them and both are defined before
 * the mount runs. */
let refit = null;
let mast = null;

/* ANIMATION.  One eased follower per control, all driven from onFrame, all
 * gated on SES.running so pose() stops everything by clearing one flag. */
const NOW = { lift: SES.liftDeg, hold: SES.holdPct, chan: 0, rail: SES.t };
const HOLD_RANGE = P.hold.range;           // [-125, +125]

function holdDeg(pct) {
  return HOLD_RANGE[0] + (HOLD_RANGE[1] - HOLD_RANGE[0]) * pct;
}
function railX(t) {
  return P.rail.range[0] + (P.rail.range[1] - P.rail.range[0]) * t;
}
function applyRig() {
  lift.pivot.setRotationFromAxisAngle(AX.lift, NOW.lift * D2R);
  hold.pivot.setRotationFromAxisAngle(AX.hold, holdDeg(NOW.hold) * D2R);
  chan.pivot.setRotationFromAxisAngle(AX.chan, NOW.chan * D2R);
  rail.position.copy(AX.rail).multiplyScalar(railX(NOW.rail) - P.rail.rest_x);
}
function applyLamps() {
  const lit = P.channel.lit[SES.channel];
  domes.forEach((d, i) => setMatByName(
    d, i === lit ? P.channel.mats[SES.channel] : P.channel.mats.off));
}
function snap() {
  NOW.lift = SES.liftDeg; NOW.hold = SES.holdPct;
  NOW.chan = P.channel.angle_deg[SES.channel]; NOW.rail = SES.t;
  applyRig(); applyLamps(); paintAll();
}

/* the hoist's pull: the lever's distance from the mid detent, signed.  Above
 * the middle the hoist STORs (outbound), below it RETRs (inbound). */
function rate() {
  const mid = (P.lift.range[0] + P.lift.range[1]) / 2;
  return (SES.liftDeg - mid) / (P.lift.range[1] - mid) * 0.34;   // /s
}
function onFrame(dt, now) {
  /* BOTH FITTINGS TICK BEFORE THIS MODULE'S `SES.running` GATE, and that is
   * deliberate.  `SES.running` is FMM's own session flag -- pose() clears it
   * and it is the only timer this file has.  The port and the mast are not
   * this module's state: neither owns a timer of its own, so every animation
   * either of them has (the iris, the throat pulse, the jewel breath, the
   * ratchet, the tally, the mast's sweep, its vane easing, its cap breath)
   * runs off these two calls.  Below the gate they would freeze on a page
   * nobody had touched yet.  pose() HIDES them instead, which is FIX_UPLOAD
   * section 0 decision 3 and the reason every number in this module's NOTES
   * reproduces byte-identically.  CONVERSION_BRIEF trap 26. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  if (SES.xferPlay) {
    const spd = Math.max(Math.abs(rate()), 0.9) * dt;
    SES.t = SES.xferTo > SES.t ? Math.min(SES.xferTo, SES.t + spd)
                               : Math.max(SES.xferTo, SES.t - spd);
    if (SES.t === SES.xferTo) {
      SES.xferPlay = false;
      onXferDone();
    }
    paintAll();
  } else if (SES.running) {
    const r = rate();
    SES.dir = r >= 0 ? 'STOR' : 'RETR';
    if (r !== 0) {
      SES.t = Math.min(1, Math.max(0, SES.t + Math.abs(r) * dt));
      paintAll();
    }
  }
  const k = SES.running ? Math.min(1, dt * 9) : 1;
  NOW.lift += (SES.liftDeg - NOW.lift) * k;
  NOW.hold += (SES.holdPct - NOW.hold) * k;
  NOW.rail += (SES.t - NOW.rail) * k;
  const want = P.channel.angle_deg[SES.channel];
  NOW.chan += (want - NOW.chan) * k;
  applyRig();
  tickHeld(dt);
}

/* ===================================================================== M4 */
/* INTERACTION.  Four hotspots, the rects the exporter measured off the live
 * geometry's own bounding boxes and clipped disjoint. */
function hotspot(key, label, onDown, onMove) {
  const h = document.createElement('div');
  const rc = P[key].hotspot;
  h.className = 'hot';
  h.style.left = rc.x + 'px'; h.style.top = rc.y + 'px';
  h.style.width = rc.w + 'px'; h.style.height = rc.h + 'px';
  h.title = label;                          // textContent-safe; never innerHTML
  $('hots').appendChild(h);
  h.addEventListener('pointerdown', ev => {
    h.setPointerCapture(ev.pointerId);
    SES.running = true;
    SES.posed = false;
    onDown(ev, h);
    if (onMove) h.onpointermove = e => onMove(e, h);
  });
  const up = () => { h.onpointermove = null; };
  h.addEventListener('pointerup', up);
  h.addEventListener('pointercancel', up);
  return h;
}
function hotspotRect(rc, label, onDown, onMove, onUp) {
  const h = document.createElement('div');
  h.className = 'hot';
  h.style.left = rc.x + 'px'; h.style.top = rc.y + 'px';
  h.style.width = rc.w + 'px'; h.style.height = rc.h + 'px';
  h.title = label;
  $('hots').appendChild(h);
  h.addEventListener('pointerdown', ev => {
    h.setPointerCapture(ev.pointerId);
    SES.posed = false;
    if (onDown) onDown(ev, h);
    if (onMove) h.onpointermove = e => onMove(e, h);
  });
  const up = ev => {
    h.onpointermove = null;
    if (onUp) onUp(ev, h);
  };
  h.addEventListener('pointerup', up);
  h.addEventListener('pointercancel', up);
  return h;
}
const frac = (ev, h, horiz) => {
  const r = h.getBoundingClientRect();
  const f = horiz ? (ev.clientX - r.left) / r.width
                  : 1 - (ev.clientY - r.top) / r.height;
  return Math.max(0, Math.min(1, f));
};
const liftHot = hotspot('lift', 'CARGO LIFT — drag: up RETR, down STOR',
  (ev, h) => setLift(ev, h), (ev, h) => setLift(ev, h));
function setLift(ev, h) {
  const f = frac(ev, h, false);
  SES.liftDeg = P.lift.range[1] + (P.lift.range[0] - P.lift.range[1]) * f;
  SES.dir = rate() >= 0 ? 'STOR' : 'RETR';
  paintAll();
}
liftHot.addEventListener('pointerup', () => { commitLift(); });
hotspot('rail', 'DATA RAIL — drag the crate to scrub the transfer',
  (ev, h) => setRail(ev, h), (ev, h) => setRail(ev, h));
function setRail(ev, h) { SES.t = frac(ev, h, true); paintAll(); }

hotspot('hold', 'HOLD — drag around the dial',
  (ev, h) => setHold(ev), (ev, h) => setHold(ev));
function setHold(ev) {
  const st = $('stage').getBoundingClientRect();
  const k = st.width / W;
  const px = st.left + P.hold.pivot_px.x * k;
  const py = st.top + P.hold.pivot_px.y * k;
  let a = Math.atan2(ev.clientX - px, py - ev.clientY) / D2R;
  a = Math.max(HOLD_RANGE[0], Math.min(HOLD_RANGE[1], a));
  SES.holdPct = (a - HOLD_RANGE[0]) / (HOLD_RANGE[1] - HOLD_RANGE[0]);
  paintAll();
}
hotspot('channel', 'CHANNEL — click for PASV / PORT', () => {
  const st = P.channel.states;
  setChannel(st[(st.indexOf(SES.channel) + 1) % st.length]);
});

/* Manifest hotspot over the clipboard. Clip x < 488 so HOLD (which starts at
 * 488) keeps the gauge.  A click opens the cargo desk; once signed in, a
 * double-click opens the entry the manifest is pointing at. */
{
  const man = (PLANES.find && PLANES.find(p => p.name === 'manifest')) || PLANES[0];
  const c = man && man.corners_px;
  const x = c ? Math.round(Math.min(c.tl.x, c.bl.x)) : 384;
  const y = c ? Math.round(Math.min(c.tl.y, c.tr.y)) : 127;
  const right = c ? Math.max(c.tr.x, c.br.x) : 509;
  const bottom = c ? Math.max(c.bl.y, c.br.y) : 205;
  const w = Math.max(8, Math.min(right, 488) - x);
  const h = Math.max(8, bottom - y);
  let lastCardUp = 0;
  manifestHot = hotspotRect({ x, y, w, h }, 'MANIFEST — open the cargo desk',
    null, null,
    () => {
      const now = performance.now();
      const dbl = now - lastCardUp < 300;
      lastCardUp = dbl ? 0 : now;
      openPunch();
      if (dbl && SES.authenticated) openEntry(currentEntry());
      paintAll();
    });
}

/* Keyboard access to the card, and a real element for focus to return to. */
if (manifestHot) {
  manifestHot.tabIndex = 0;
  manifestHot.setAttribute('role', 'button');
  manifestHot.setAttribute('aria-label', 'Manifest: open the cargo desk to sign in and move files');
  manifestHot.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    ev.preventDefault();
    if (ev.repeat) return;
    SES.posed = false;
    openPunch();
    paintAll();
  });
}

/* TYPE I/A, hand-placed on the lower edge of the channel plate so the
 * PASV/PORT throw stays a click on the pointer/grip. No exporter rect. */
{
  const typeHot = hotspotRect(
    { x: 1030, y: 338, w: 42, h: 36 },
    'TYPE — click I / A',
    () => { doType(); });
  typeHot.className = 'hot typehot';
}

/* ---- THE REFIT PORT -------------------------------------------------------
 * Nine lines, and none of them is FMM-specific: the anchor, the size, the part
 * names, the leaf pivots and the hotspot all come out of `scene.json -> refit`,
 * which `pipeline/refit_port.py` wrote.  It bolts to the SHIP STRUCTURE below
 * the instrument -- the panel under the DATA CHANNEL deck -- never to the
 * faceplate, so no control moves and no readout plane moves.  It declares NO
 * readout plane: all of its text is the screen-space docket in
 * live3d/refit.css, so check_occlusion.py's question 5, the dial-face rule and
 * check_text.py are NOT ENGAGED by it rather than merely satisfied, and FMM
 * still reports THREE planes.
 *
 * `hotspot` IS THIS MODULE'S OWN, PASSED STRAIGHT IN.  FMM's helper is the odd
 * one in the fleet -- `(key, label, onDown, onMove)`, a KEY into `S.props`
 * rather than a rect -- and handing it to the fittings used to throw at
 * creation (`Cannot read properties of undefined (reading 'hotspot')`).  The
 * shared `wireHotspot()` adapter in refit.js separates FMM's shape by arity
 * before it can throw and builds the same `.hot` element in this page's own
 * `#hots` layer.  Nothing per-module is needed and nothing is hand-rolled
 * here.  FIX_UPLOAD 12.15 item 1.
 *
 * Passing `dress` is what chains attachDepthTest and then attachForeground
 * onto the port's materials; skip it and split.auditScene() correctly reports
 * double-blending.  It is ALSO what puts the port through this module's
 * grade: `applyColour()` in section 5 patches three's AgX chunk and both
 * renderers' exposure BEFORE any material compiles, and the port's materials
 * compile here, afterwards -- so the port is graded by exactly the transfer
 * the panel it is bolted to was baked through.  FMM is the only module in the
 * fleet where that sentence has any content; see NOTES section 11.
 *
 * `root_scale` IS NOT PASSED.  The `-- refit` entry point builds in an empty
 * scene in world coordinates, so it is 1.0 there whatever a module's main()
 * uses; refit_port.check_root_scale() now refuses anything else.  FMM's own
 * scale is 1 in any case. */
refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is FMM-specific either.
 *
 * IT IS ON THE PORT'S OWN SERVICE RAIL, at the published `free_from_m` = 1.5 W
 * floor, with the rail CONTINUOUS from the port's own built end -- which is
 * STATUS_AT_A_GLANCE 11.2 working unmodified for the first time in four
 * modules.  KVS had to walk out to 3.2 W and MQB to 12.2 W to clear their own
 * dockets and MTA could not use the rail at all; on FMM the port's anchor was
 * chosen (see `FMM_REFIT` in pipeline/export_fmm.py) so that the docket lands
 * to the port's LEFT, which leaves the whole rail clear.  Measured on this
 * page with the port open: the docket owns x 39.7..559.7, the mast's hotspot
 * starts at 673.7, 0 px2 either way.
 *
 * It declares NO readout plane.  Its words are the screen-space caption and
 * detail panel in live3d/mast.css, so check_occlusion.py's question 5, the
 * dial-face rule and check_text.py are not engaged by it.  `readouts.length`
 * is still 3.
 *
 * It renders through this module's grade for the same reason the port does --
 * `dress` chains onto materials that compile after `applyColour()` patched
 * three's AgX chunk.  Measured: with the look removed, the mast's own pixels
 * move +29 levels, the same as FMM's live lift and crate.  NOTES section 11. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

/* ===================================================================== M5 */
/* THE CAPTURE POSE.  Byte-for-byte the state export_fmm.py rendered
 * gt_full_read.png and gt_platen0.png in (scene.json -> capture_pose and
 * readout_text), so compare.py and check_text.py score the renderer and not a
 * mismatch.  It stops the module dead: SES.running = false is the only timer
 * this file has, because it is the only one it owns. */
function poseForCapture() {
  /* HIDE BOTH FITTINGS.  Every number in live3d/RESULTS.md and sections 1-8 of
   * this module's NOTES was captured from pose() against Blender renders that
   * contain neither of them; hiding them reproduces all of it unchanged and
   * re-renders nothing.  FIX_UPLOAD section 0, decision 3.  The fittings' own
   * behaviour is measured with them SHOWN --
   * `window.__refit.show(true);window.__mast.show(true)` -- which is a
   * separate capture, and that report is byte-identical to this one. */
  if (refit) refit.pose();
  if (mast) mast.pose();
  SHEET.want = SHEET.k = 0; SHEET.el.hidden = true;
  SLIP.want = SLIP.k = 0; SLIP.el.hidden = true;
  SES.running = false;
  SES.xferPlay = false;
  SES.posed = true;
  SES.idx = 0;
  SES.dir = 'STOR';
  SES.liftDeg = CP.lift_deg;
  SES.holdPct = CP.hold_pct;
  SES.channel = CP.channel;
  SES.t = CP.rail_t;
  SES.host = '10.14.2.9';
  SES.port = 52104;
  SES.type = 'I';
  snap();
}

/* module-private hooks, ALONGSIDE window.__occ and never instead of it: the
 * fleet harness drives only __occ.  These are how the numbers in NOTES.md were
 * measured on the real page rather than argued about. */
window.__fmm = {
  ses: () => JSON.parse(JSON.stringify(SES)),
  set: (k, v) => { SES[k] = v; snap(); return SES[k]; },
  lamps: () => domes.map(d => [d.name, '#' + d.material.color.getHexString(),
                               d.material.emissiveIntensity]),
  facing: () => facingAudit(camera),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's own derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
  tris: () => ({ tris: TRIS, meshes: NMESH, lights: S.lights.length,
                 planes: readouts.length }),
  layout: () => readouts.map(r => ({ name: r.tp.name, ...r.layout })),
  rig: () => Object.keys(meshes),
  exposure: (v) => { if (v !== undefined) renderer.toneMappingExposure = +v;
                     return renderer.toneMappingExposure; },
};

$('note').textContent =
  TRIS + ' tris + ' + (refit ? refit.tris : 0) + ' refit + ' + mast.tris + ' mast · ' + NMESH +
  ' live meshes · ' + S.lights.length +
  ' area lights · ' + readouts.length + ' readout planes';

/* pose() hides both fittings; the page a human opens must SHOW them, or the
 * page they open is not the page this file describes.  check_occlusion.py's
 * section 0 reports the difference between the as-loaded and posed frames and
 * that section is REPORTED, NOT FAILED ON, for exactly this case. */
if (refit) refit.show(true);
mast.show(true);
/* AND PLACE THE CAPTION NOW, not when the network answers.  `mast.show()` does
 * `refresh().then(place)`, so until the first `status.json` response lands the
 * caption element is laid out with its offsets unset and PAINTS AT THE STAGE'S
 * TOP-LEFT CORNER -- a dark `FMM TELLTALE / UNTESTED` panel at (0, 0).  On KVS
 * and MQB the response arrives in 130-175 ms and nobody sees it; on FMM and on
 * MTA it arrives at 3.1-3.5 s, because this page's own scene.json, 3.7 MB of
 * depth.bin, plate.png and five glbs are ahead of it in the connection queue,
 * and the panel sits in the corner for that whole time.  Reproduced by
 * delaying `status.json` and screenshotting: evidence/19.  `place()` is public
 * and idempotent, and `refresh()` calls it again with the real caption, so the
 * only cost is one extra solve at load.  **This is a shared-code defect
 * (`mast.js`'s `show()` should place before it fetches, not after) and it is
 * REPORTED, not changed** -- the same shape as MQB's MutationObserver. */
mast.place();

{
  const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
  on('punchClose', 'click', () => hidePunch());
  on('slipClose', 'click', () => closeSlip());
  on('punchLogin', 'click', () => doLogin());
  on('punchSess', 'click', () => doSess());
  on('deskSignOut', 'click', () => signOut());
  on('deskCopyTok', 'click', () => {
    const done = () => setStatus('Token ' + SES.token + ' copied.', 'ok');
    try { navigator.clipboard.writeText(SES.token).then(done, () => setStatus('Token: ' + SES.token, '')); }
    catch (e) { setStatus('Token: ' + SES.token, ''); }
  });
  on('deskUp', 'click', () => goUp());
  on('punchList', 'click', () => refreshList());
  on('deskLogBtn', 'click', () => toggleLog());
  on('punchDoRetr', 'click', () => openEntry(currentEntry()));
  on('deskNew', 'click', () => newSlip());
  on('punchFix', 'click', () => {
    setStatus('Switched CHANNEL to PASV.', 'ok');
    setChannel('pasv');
  });
  on('deskSave', 'click', () => saveView());
  on('deskEdit', 'click', () => editView());
  on('punchDoStor', 'click', () => upload());
  on('punchStor', 'input', () => renderDesk());
  on('deskPick', 'click', () => {
    if (SES.upload) { clearDiskFile(); renderDesk(); return; }
    $('deskFile').click();
  });
  on('deskFile', 'change', () => pickDiskFile($('deskFile').files && $('deskFile').files[0]));
  on('deskList', 'keydown', ev => {
    const n = SES.listing.length;
    let i = SES.sel;
    if (ev.key === 'ArrowDown') i = Math.min(n - 1, i + 1);
    else if (ev.key === 'ArrowUp') i = Math.max(0, i - 1);
    else if (ev.key === 'Home') i = 0;
    else if (ev.key === 'End') i = n - 1;
    else if (ev.key === 'Enter') { ev.preventDefault(); openEntry(currentEntry()); return; }
    else if (ev.key === 'Backspace') { ev.preventDefault(); goUp(); return; }
    else return;
    ev.preventDefault();
    selectEntry(i);
  });
  /* Enter submits from a single-line FIELD only; the slip's body takes
   * Ctrl/Cmd+Enter, so plain Enter is still a newline there. */
  const enterKeys = ev => {
    const tg = ev.target;
    if (ev.key !== 'Enter' || ev.repeat) return;
    if (tg === $('punchBody')) {
      if (ev.ctrlKey || ev.metaKey) { ev.preventDefault(); upload(); }
      return;
    }
    if (!tg || tg.tagName !== 'INPUT') return;
    ev.preventDefault();
    if (tg === $('punchTok')) doSess();
    else if (tg === $('punchStor')) upload();
    else doLogin();
  };
  on('punchCard', 'keydown', enterKeys);
  on('slipCard', 'keydown', enterKeys);
  /* Escape rolls the slip up first, then puts the sheet down.  Stopped here so
   * nothing else in this page (the refit docket's own Escape) also reacts.  The
   * cockpit's Escape lives on its own window and never sees keys typed inside
   * this iframe. */
  const closeTop = () => {
    if (SLIP.want) { closeSlip(); return true; }
    if (SHEET.want) { hidePunch(); return true; }
    return false;
  };
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !(SLIP.want || SHEET.want)) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTop();
  });
  /* exposed so the shell can ask "did the module use this Escape?" first */
  window.__closeOverlay = closeTop;
  renderView();
  renderDesk();
}

snap();
layout();
facingAudit(camera);
requestAnimationFrame(frame);
window.__loaded = true;
