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
/* THE REFIT PORT.  live3d/refit.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> refit`, which
 * pipeline/refit_port.py wrote.  live3d/design/FIX_UPLOAD.md is the design. */
import { mountRefit } from '../../refit.js';
/* THE TELLTALE MAST.  live3d/mast.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> mast`, which
 * pipeline/status_mast.py wrote.  live3d/design/STATUS_AT_A_GLANCE.md section
 * 6 is the design. */
import { mountMast } from '../../mast.js';
/* Track 01 shared client — consumed here, not forked. */
import { interact as apiInteract } from '../../api.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'OTA';                     // Fleet Replicator Grid / drone bay
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
  /* `ubias` added at integration time: `ubias_m` is a per-module MEASUREMENT
   * and this page had no hook, so it could not be swept.  CONVERSION_BRIEF
   * 5.2a, trap 24. */
  ubias: (v) => { if (v !== undefined) DU.uBias.value = +v;
                  return DU.uBias.value; },
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
 * OTA -- FLEET REPLICATOR GRID / DRONE BAY.  A drone rack clamped to the left
 * pillar.  The update-distribution console: a tape-reel cartridge is published
 * into the replicator throat, the update runs down a spine of chevrons, and
 * three cradled probes (fmm / ipm / log) roll their flip-dot version boards
 * forward as they report in.
 *
 * WHAT IS LIVE (34 meshes, four glbs) and WHY -- CONVERSION_BRIEF step 2:
 *   cartridge  `frames` in the shipped manifest.  Frames are a baked
 *              approximation of movement: the cartridge is ONE real mesh set
 *              and it now rides the throat continuously.               rule 1
 *   propagate  `frames`, 14 chevrons.  It declares the material TRIPLE
 *              (chev_off / chev_on / chev_hot), so the pulse is an emissive
 *              swap on real geometry rather than 9 sprites.        rules 1, 3
 *   fleet      `states`.  The three status beacons declare the material PAIR
 *              (amber_on / grn_on).  The version BOARDS are content text and
 *              are DOM; the beacons are the geometry.                  rule 3
 *   poll       `rotate`.  A needle.                                    rule 1
 * Everything else -- 114 static objects, 79,960 tris -- stays in plate.png.
 *
 * WHAT IS DOM: ota_cart_ver (the version being published), ota_chk_val (the
 * payload's SHA-256) and ota_ver_old/new_0..2 (each fleet member's running
 * version).  Stamped lettering -- PUBLISH, SHA-256, POLL, SEC, the cradle
 * codes FMM/IPM/LOG, FLEET REPLICATOR / GRID OTA-90 -- stays geometry.
 *
 * THE DIAL-FACE RULE (BRIEF section 6) applies to the POLL INTERVAL gauge and
 * the answer is "no plane".  The needle sweeps -125..+125 across the whole
 * face.  THERE IS NO DOM COPY OF THE POLL INTERVAL ANYWHERE ON THIS PAGE, not
 * on the dial, not in the toolbar: the needle is that readout.
 */

/* ---------------------------------------------------------------- M1  PROPS */
const P = S.props;
const V3 = a => new THREE.Vector3().fromArray(a);

const [gCart, gSpine, gLamps, gPoll] = await Promise.all([
  load(A + P.cartridge.glb), load(A + P.propagate.glb),
  load(A + P.fleet.glb), load(A + P.poll.glb),
]);

const matOf = {};                    // glb node name -> its cloned material
for (const g of [gCart, gSpine, gLamps, gPoll])
  g.scene.traverse(o => { if (o.isMesh) matOf[o.name] = dress(o); });

/* THE FrontSide TRAP, and OTA has it.  build.py's tri_down() emits each
 * chevron as ONE triangle with vertices wound (top-left, top-right, bottom),
 * whose face normal is local -Z -- i.e. INTO the panel, away from the camera.
 * EEVEE does not backface-cull so Blender renders all 14; three does, so
 * dress()'s THREE.FrontSide deletes the entire propagation spine, silently,
 * with no error and no auditScene() complaint.  facingAudit() below names
 * them.  The exporter flags it as props.propagate.double_sided. */
if (P.propagate.double_sided)
  for (const nm of P.propagate.nodes)
    if (matOf[nm]) matOf[nm].side = THREE.DoubleSide;

applyMatFix();

/* the cartridge rides a pivot that translates along the face's own +v axis */
const CART_AXIS = V3(P.cartridge.axis).normalize();
const cartPivot = new THREE.Object3D();
scene.add(cartPivot);
cartPivot.add(gCart.scene);
scene.add(gSpine.scene);
scene.add(gLamps.scene);

/* the needle turns about the panel's own normal, NEGATED by the exporter so a
 * positive angle is clockwise on screen -- the direction the gauge's own
 * -118..+118 ticks run.  No module declares `axis` on a rotate control. */
const pollPiv = pivotAt(P.poll.hub);
pollPiv.inner.add(gPoll.scene);
const POLL_AXIS = V3(P.poll.axis).normalize();

/* count what actually shipped, out of the loaded index accessors, rather than
 * quoting the Blender-side number back at itself */
let TRIS = 0, MESHES = 0;
for (const g of [gCart, gSpine, gLamps, gPoll])
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    MESHES++;
    const a = o.geometry.index || o.geometry.attributes.position;
    TRIS += (a.count / 3) | 0;
  });

/* an emissive/material state swap, from the pairs the module declares.  The
 * glb ships each mesh with whatever material it had at export time; the
 * materials.json side channel carries every Principled scalar by NAME, so a
 * swap is "write the other record's values into this mesh's own material". */
function setMat(node, mname) {
  const m = matOf[node], rec = MJ[mname];
  if (!m || !rec) return;
  m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                 THREE.LinearSRGBColorSpace);
  if (rec.emit > 0) {
    m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                      THREE.LinearSRGBColorSpace);
    m.emissiveIntensity = rec.emit;
  } else {
    m.emissiveIntensity = 0;
  }
  if (matFixOn) { m.roughness = rec.rough; m.metalness = rec.metallic; }
}

/* ------------------------------------------------------- M2  SESSION MODEL
 * OTA's protocol: POST /publish carries a cartridge (a version + the payload's
 * SHA-256); agents poll GET /updates/{module}/latest at the interval the dial
 * sets; each probe POSTs /devices/{id}/report and its board rolls forward.
 * The values below are generated at RUNTIME and exist in no image.  Every one
 * of them reaches the readout through textContent -- there is no innerHTML in
 * this file. */
const FLEET = P.fleet.modules;                 // ["FMM","IPM","LOG"]
const ORDER = P.fleet.order;                   // stale roll1 roll2 synced
const DONE = P.fleet.done;                     // state -> how many rolled
const LIT = P.propagate.lit;                   // chevrons lit, per frame

const SES = {
  version: P.fleet.versions.new,               // "1.5.0" -- in the cartridge
  prev: P.fleet.versions.old,                  // "1.4.2" -- what the rack ran
  checksum: (S.readout_text[1] || ['9F2C41B8'])[0],
  cartT: S.capture_pose.cart_t,                // 0 seated .. 1 fully raised
  latch: S.capture_pose.latch,
  prop: S.capture_pose.propagate,              // 0..8
  fleet: ORDER.indexOf(S.capture_pose.fleet),
  poll: S.capture_pose.poll_deg,               // degrees, -125..+125
  ops: 0,
  module: 'log',                               // the module on the card
  empty: false,                                // the grid has nothing for it yet
  /* the grid's own answer once it has given one; null = the canned rest */
  live: null,                                  // {updates: {fmm: '1.0.0'}, devices: [...]}
  lastResult: null,
};

const HEX = '0123456789ABCDEF';
function sha8() {                              // a fresh payload digest prefix
  const b = new Uint8Array(4);
  crypto.getRandomValues(b);
  let s = '';
  for (const v of b) s += HEX[v >> 4] + HEX[v & 15];
  return s;
}
function bump(v) {                             // 1.5.0 -> 1.6.0
  const p = v.split('.').map(Number);
  p[1] += 1; p[2] = 0;
  return p.join('.');
}

/* readout 0 = cartridge version, 1 = checksum, 2..4 = the three boards */
const INK = S.ink;
const rgb = a => 'rgb(' + a[0] + ',' + a[1] + ',' + a[2] + ')';
readouts[0].el.style.color = rgb(INK.cart);
readouts[1].el.style.color = rgb(INK.chk);

function shaPrefix(h) {
  const s = String(h || '').replace(/[^0-9a-fA-F]/g, '');
  return (s.slice(0, 8) || '????????').toUpperCase();
}

/* A board is the version the grid holds for that cradle's module; it reads
 * green once a registered device of that module reports running it. */
function boardText(i) {
  return SES.live.updates[FLEET[i].toLowerCase()] || '-.-.-';
}
function boardLive(i) {
  if (!SES.live) return false;
  const want = FLEET[i].toLowerCase();
  const ver = SES.live.updates[want];
  if (!ver) return false;
  return SES.live.devices.some(d => d &&
    String(d.module || '').toLowerCase() === want && d.version === ver &&
    !/fail|error/i.test(String(d.status || '')));
}
function paintBoards() {
  if (SES.live) {
    FLEET.forEach((code, i) => {
      readouts[2 + i].paint([boardText(i)]);
      readouts[2 + i].el.style.color = rgb(boardLive(i) ? INK.ver_new : INK.ver_old);
    });
    return;
  }
  const done = DONE[ORDER[SES.fleet]];
  for (let i = 0; i < 3; i++) {
    const rolled = i < done;
    readouts[2 + i].paint([rolled ? SES.version : SES.prev]);
    readouts[2 + i].el.style.color = rgb(rolled ? INK.ver_new : INK.ver_old);
  }
}

function paintAll() {
  readouts[0].paint([SES.empty ? '-.-.-' : SES.version]);
  readouts[1].paint([SES.empty ? '--------' : SES.checksum]);
  paintBoards();
  $('otaVersion').placeholder = 'blank publishes ' + nextVersion();
  note();
}

/* the toolbar status line.  #note is CLIPPED and the buttons are nowrap in the
 * template's CSS -- do not remove those two declarations, a long note is what
 * pushed MQB's buttons into the captured stage rect and failed check 3. */
let lastErr = '';
function note(msg) {
  if (msg !== undefined) lastErr = msg || '';
  if (lastErr) {
    $('note').textContent = lastErr;
    return;
  }
  const done = DONE[ORDER[SES.fleet]];
  const fleetTag = SES.live ? 'live' : ORDER[SES.fleet];
  $('note').textContent =
    TRIS + ' tris · ' + MESHES + ' live meshes · ' +
    S.lights.length + ' area lights · ' + readouts.length +
    ' readout planes · publish ' + SES.version + ' ' + SES.checksum +
    ' · spine ' + LIT[SES.prop] + '/' + P.propagate.chev_n +
    ' · fleet ' + fleetTag + ' ' +
    FLEET.map((c, i) => c + ((SES.live ? boardLive(i) : i < done)
                             ? '✓' : '·')).join(' ');
}

/* the geometry state that follows from SES */
function applyState() {
  setMat(P.cartridge.latch,
         SES.latch ? P.cartridge.latch_mats.on : P.cartridge.latch_mats.off);
  const lit = LIT[SES.prop];
  P.propagate.nodes.forEach((nm, i) => {
    setMat(nm, i === lit - 1 ? P.propagate.mats.hot
                             : (i < lit ? P.propagate.mats.on
                                        : P.propagate.mats.off));
  });
  if (SES.live) {
    P.fleet.beacons.forEach((nm, i) =>
      setMat(nm, boardLive(i) ? P.fleet.mats.green : P.fleet.mats.amber));
  } else {
    const done = DONE[ORDER[SES.fleet]];
    P.fleet.beacons.forEach((nm, i) =>
      setMat(nm, i < done ? P.fleet.mats.green : P.fleet.mats.amber));
  }
}

/* ------------------------------------------------------------ M3  ANIMATION
 * Runs once per frame BEFORE the split renders.  Everything here is driven by
 * SES and by two eased followers, so there is no timer to leak: pose() sets
 * the state and clears `running`, and two consecutive captures are identical.
 */
let cartNow = SES.cartT, pollNow = SES.poll;
/* THE PAGE RESTS IN ITS POSED STATE, AND `running` USED TO START TRUE.
 *
 * `onFrame` advances `SES.prop` every 0.28 s while
 * `SES.latch && SES.prop < P.propagate.frames - 1`.  At rest `SES.latch` is
 * true and `SES.prop` is `capture_pose.propagate` = 6 of 9 frames, so on a
 * page nobody had touched the propagation pulse walked 6 -> 7 -> 8 in the
 * first ~0.56 s and then stopped.  Every check in the brief calls
 * `__occ.pose()` first, which resets `SES.prop` to 6 and clears `running`, so
 * the whole suite PASSED and the page a human opens was two chevrons further
 * down the spine than anything that had been measured.
 *
 * check_occlusion.py's section 0 caught it and named it as owed follow-up:
 * 174 px at pr 1 / 647 px at pr 2, worst 128 levels, strings identical -- a
 * 9x86 strip at x 697..707, y 530..615, which is the last two chevrons of the
 * spine lighting up.  It is the same shape as IPM's develop-clock bug and
 * DNSM's `SES.spin: true`.
 *
 * The pulse is a CONSEQUENCE OF PUBLISHING, not an idle animation: `publish()`
 * sets `SES.prop = 0` and starts it, and the propagate hotspot drags it by
 * hand.  So `running` starts FALSE and the rest state stands.  The two eased
 * followers are unaffected -- with `running` false they snap, which is what
 * they already do after `pose()`. */
let running = false;
let pulseAcc = 0;

/* THE REFIT PORT and THE TELLTALE MAST.  Mounted below, after the hotspot
 * helper exists; declared here because onFrame() and poseForCapture() both
 * reach them and both are defined before the mount.  live3d/refit.js,
 * live3d/mast.js. */
let refit = null;
let mast = null;

/* The cart_ver readout is a MOVING PLANE (BRIEF step 4).  The plane uniforms
 * are re-uploaded from the TextPlane objects every frame, so a plane that
 * rides a control costs nothing extra -- but BOTH the DOM element and the
 * occlusion plane have to move, which is exactly what r.place() does. */
const CART_REST = {
  o: V3(S.text_planes[0].origin),
  u: V3(S.text_planes[0].u), v: V3(S.text_planes[0].v),
  n: V3(S.text_planes[0].n),
};
const _o = new THREE.Vector3();

function placeCartridge(t) {
  const d = P.cartridge.lift * t;
  cartPivot.position.copy(CART_AXIS).multiplyScalar(d);
  cartPivot.updateMatrixWorld(true);
  _o.copy(CART_REST.o).addScaledVector(CART_AXIS, d);
  readouts[0].place(_o, CART_REST.u, CART_REST.v, CART_REST.n);
}
function placeNeedle(deg) {
  pollPiv.pivot.quaternion.setFromAxisAngle(POLL_AXIS, deg * D2R);
}

function onFrame(dt, now) {
  /* ABOVE THE `running` BRANCH, not inside it.  CONVERSION_BRIEF trap 26:
   * neither fitting owns a timer, so the iris, the throat pulse, the jewel
   * breath, the ratchet, the tally, the mast's sweep, its vane easing and its
   * cap breath all animate off these two calls.  OTA's `running` starts FALSE
   * -- the page rests in capture_pose and the propagation pulse is started by
   * publish(), not by loading the page -- so a tick() inside the branch would
   * be a tick() that never runs on exactly the page a human opens. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  if (running) {
    cartNow += (SES.cartT - cartNow) * Math.min(1, dt * 9);
    pollNow += (SES.poll - pollNow) * Math.min(1, dt * 7);
    if (SES.latch && SES.prop < P.propagate.frames - 1) {
      pulseAcc += dt;
      while (pulseAcc > 0.28) {         // the update running down the rack
        pulseAcc -= 0.28;
        SES.prop = Math.min(P.propagate.frames - 1, SES.prop + 1);
        applyState(); note();
      }
    }
  } else {
    cartNow = SES.cartT; pollNow = SES.poll;
  }
  placeCartridge(cartNow);
  placeNeedle(pollNow);
  tickHeld(dt);
}

/* ---------------------------------------------------------- M4  INTERACTION */
const hots = $('hots');
function stageXY(e) {
  const r = $('stage').getBoundingClientRect();
  const k = r.width / W;
  return [(e.clientX - r.left) / k, (e.clientY - r.top) / k];
}
function hotspot(rect, label, wire) {
  const h = document.createElement('div');
  h.className = 'hot';
  h.style.cssText =
    `left:${rect.x}px;top:${rect.y}px;width:${rect.w}px;height:${rect.h}px`;
  h.title = label;                    // textContent-safe; never innerHTML
  hots.appendChild(h);
  wire(h);
  return h;
}
function drag(h, set) {
  h.addEventListener('pointerdown', e => {
    running = true; h.setPointerCapture(e.pointerId); set(e);
  });
  h.addEventListener('pointermove', e => {
    if (h.hasPointerCapture(e.pointerId)) set(e);
  });
}

/* Track 01 client: flatten api.js envelope so callers keep reading
 * manifest / computed / devices on the top-level result. Offline → {ok:false}.
 * Never innerHTML; never a hung spinner. */
async function interact(code, action, params) {
  let env;
  try {
    env = await apiInteract(code, action, params || {});
  } catch (e) {
    return { ok: false, reachable: false, error: (e && e.message) || 'offline' };
  }
  const res = (env && env.result && typeof env.result === 'object')
    ? env.result : {};
  const out = Object.assign({}, res, {
    ok: !!(env && env.ok),
    reachable: !!(env && env.reachable),
  });
  if (!out.ok && !out.error)
    out.error = (env && env.error) || 'interact failed';
  return out;
}

/* ---- what the player is told.  The dev #note is page chrome; this line on
 * the card is the grid's own answer. */
function setStatus(text, kind) {
  const el = $('cardReply');
  el.textContent = text || '';
  el.className = kind || '';
  el.title = text || '';
}
function report(res, okText) {
  if (res.ok) setStatus(res.summary || okText || '', 'ok');
  else setStatus(res.error || res.summary || 'no answer from the grid', 'err');
}

/* ---- the printout on the card: a manifest the grid holds, or the fleet.
 * `cls(line)` tags a line; every line is painted with textContent only. */
let printout = null;                // {title, note, lines[], cls}
function setPrintout(title, note, lines, cls) {
  printout = { title, note: note || '',
               lines: (lines || []).map(m => String(m == null ? '' : m)), cls };
  renderPrintout();
}
function renderPrintout() {
  const pr = printout;
  const pre = $('cardLines');
  $('cardTitle').textContent = pr ? pr.title : 'Cartridge';
  $('cardNote').textContent = pr ? pr.note : '';
  pre.textContent = '';
  if (!pr || !pr.lines.length) {
    const e = document.createElement('span');
    e.className = 'empty';
    e.textContent = pr ? '(nothing printed)'
      : 'Publish the cartridge, or click the cradles to read the fleet.';
    pre.appendChild(e);
    return;
  }
  for (const line of pr.lines) {
    const e = document.createElement('div');
    const c = pr.cls && pr.cls(line);
    if (c) e.className = c;
    e.textContent = line || '\u00a0';
    pre.appendChild(e);
  }
  pre.scrollTop = 0;
}
const pad = (k, n) => (k + ' '.repeat(n)).slice(0, Math.max(n, k.length + 1));
function manifestLines(man, extra) {
  const out = [];
  for (const k of ['module', 'version', 'sha256'])
    if (man[k] != null && man[k] !== '') out.push(pad(k, 10) + man[k]);
  for (const [k, v] of extra || [])
    if (v != null && v !== '') out.push(pad(k, 10) + v);
  return out;
}

/* the version a blank card publishes: the one after the latest */
function nextVersion() {
  if (SES.empty) return '1.0.0';
  const m = /^(\d+)\.(\d+)/.exec(String(SES.version || ''));
  return m ? m[1] + '.' + (+m[2] + 1) + '.0' : '1.0.0';
}
function readCard() {
  return {
    module: $('otaModule').value || 'log',
    version: $('otaVersion').value.trim() || nextVersion(),
  };
}

let posing = false;
let publishing = false;
let pubGen = 0;
let poseGen = 0;                       // a read that outlives pose() is dropped

function applyLocalPublish() {
  /* Capture helper / pose-in-flight: no network. Latch + pulse only. */
  running = true;
  pulseAcc = 0;
  SES.latch = true;
  SES.prev = SES.version;
  SES.version = bump(SES.version);
  SES.checksum = sha8();
  SES.fleet = 0;
  SES.live = null;
  SES.prop = 0;
  SES.ops++;
  applyState(); paintAll();
}

/* PUBLISH -- seat the cartridge, or POST on the card.  Latch, spine pulse and
 * the new label run only after a 201; then the boards re-read the grid. */
async function publish() {
  if (posing) { applyLocalPublish(); return; }
  if (publishing) return;
  publishing = true;
  const gen = ++pubGen;
  const params = readCard();
  $('cardPublish').disabled = true;
  setStatus('publishing ' + params.module + ' ' + params.version + '…', 'busy');
  note('publishing…');
  const res = await interact('OTA', 'publish', params);
  publishing = false;
  $('cardPublish').disabled = false;
  if (posing || gen !== pubGen) return;
  SES.lastResult = Object.assign({ action: 'publish' }, res);
  report(res, 'published');
  if (!res.ok) {
    note(res.error || 'publish failed');
    setPrintout('Not published', params.module + ' ' + params.version,
                [res.error || 'publish failed']);
    applyState();
    return;
  }
  note('');
  const man = res.manifest || {};
  running = true;
  pulseAcc = 0;
  SES.latch = true;
  SES.prev = SES.version;
  SES.version = man.version || params.version;
  SES.checksum = shaPrefix(man.sha256);
  SES.module = man.module || params.module;
  SES.empty = false;
  SES.fleet = 0;
  SES.prop = 0;
  SES.ops++;
  $('otaModule').value = SES.module;
  $('otaVersion').value = '';
  setPrintout('Published', SES.module + ' ' + SES.version,
              manifestLines(man, [['size', res.size != null ? res.size + ' bytes' : ''],
                                  ['published', res.published_at]]));
  applyState(); paintAll();
  pullFleet(true);
}

/* The grid's latest package for the card's module onto the cartridge label
 * and the checksum window.  Offline the label keeps what it had. */
async function pullLatest(mod, quiet) {
  mod = mod || SES.module;
  if (!quiet) setStatus('reading ' + mod + ' latest…', 'busy');
  const g = poseGen;
  const res = await interact('OTA', 'latest', { module: mod });
  if (posing || g !== poseGen || mod !== SES.module) return null;
  SES.lastResult = Object.assign({ action: 'latest' }, res);
  if (!quiet) report(res, mod + ' latest');
  if (!res.ok) {
    if (res.http_status === 404) {
      SES.empty = true;
      paintAll();
      if (!quiet) setPrintout('Latest', mod, ['nothing published for ' + mod + ' yet']);
    }
    return null;
  }
  SES.empty = false;
  if (res.version) SES.version = res.version;
  SES.checksum = shaPrefix(res.sha256);
  paintAll();
  if (!quiet) setPrintout('Latest', mod + ' ' + (res.version || ''),
                          manifestLines(res.manifest || res));
  return res;
}

/* What the grid holds for each module onto the three boards, and who has
 * reported in onto the beacons.  Offline the boards keep the canned rest. */
async function pullFleet(quiet) {
  if (!quiet) setStatus('reading the fleet…', 'busy');
  const g = poseGen;
  const res = await interact('OTA', 'status', {});
  if (posing || g !== poseGen) return null;
  SES.lastResult = Object.assign({ action: 'status' }, res);
  if (!quiet) report(res, 'fleet');
  if (!Array.isArray(res.updates)) return null;
  const updates = {};
  for (const u of res.updates)
    if (u && u.module) updates[String(u.module).toLowerCase()] = u.latest;
  SES.live = { updates, devices: Array.isArray(res.devices) ? res.devices : [] };
  applyState(); paintAll();
  if (!quiet) printFleet(res);
  return res;
}
function printFleet(res) {
  const lines = ['published'];
  for (const c of FLEET) {
    const m = c.toLowerCase();
    lines.push('  ' + pad(m, 6) + (SES.live.updates[m] || '(nothing yet)'));
  }
  lines.push('');
  if (!Array.isArray(res.devices)) {
    lines.push('devices   ' + (res.error || 'not readable'));
  } else {
    lines.push('devices (' + (res.device_count != null ? res.device_count
                                                       : res.devices.length) + ')');
    if (!res.devices.length) lines.push('  none registered');
    for (const d of res.devices)
      lines.push('  ' + [d.id || '?', d.module || '?', d.version || '-',
                         d.status || '-'].join('  '));
  }
  setPrintout('Fleet', (res.device_count != null ? res.device_count : 0) + ' devices',
              lines, l => (l === 'published' || /^devices/.test(l)) ? 'key' : '');
}

/* ---- HELD PAPER.  The cartridge card is DOM in a second CSS3D layer, laid on
 * the rack's face basis.  Its `k` runs 0..1: 0 is the label on the cartridge
 * (wherever the cartridge is in the throat), 1 is the card held up toward the
 * camera over the open bulkhead on the left.  onFrame() eases k toward `want`;
 * no timers. */
const held = new CSS3DLayer($('held'), W, H);
const CARD = { el: $('otaCard'), w: 540, h: 660, k: 0, want: 0,
               at: { x: 240, y: 372, w: 380 } };
CARD.rec = held.add(CARD.el);
const LABEL = S.text_planes[0];        // the cartridge label, readout 0
function cardRest() {
  const o = CART_REST.o.clone().addScaledVector(CART_AXIS, P.cartridge.lift * cartNow);
  return { o, mx: 2 * LABEL.half_w / CARD.w, my: 2 * LABEL.half_h / CARD.h };
}
/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the label's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = camera.position.distanceTo(CART_REST.o) * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  const m = at.w * perPx / elW;
  return { o, mx: m, my: m };
}
const CARD_UP = heldPose(CARD.at, CARD.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
/* At rest the card lies in the rack's face; lifted it turns most of the way
 * toward the camera, so the rack's 27 degree yaw does not skew the text. */
const FACE_TURN = 0.75;
const Q_FACE = new THREE.Quaternion().setFromRotationMatrix(
  new THREE.Matrix4().makeBasis(CART_REST.u, CART_REST.v, CART_REST.n));
const Q_UP = Q_FACE.clone().slerp(camera.quaternion, FACE_TURN);
const _q = new THREE.Quaternion(), _sc = new THREE.Vector3();
function tickHeld(dt) {
  if (CARD.k !== CARD.want) {
    const step = dt * 4;
    CARD.k = CARD.want > CARD.k ? Math.min(CARD.want, CARD.k + step)
                                : Math.max(CARD.want, CARD.k - step);
    if (CARD.k === 0) CARD.el.hidden = true;
  }
  if (!CARD.el.hidden) {
    const e = ease(CARD.k), r = cardRest();
    _q.copy(Q_FACE).slerp(Q_UP, e);
    _sc.set(r.mx + (CARD_UP.mx - r.mx) * e, r.my + (CARD_UP.my - r.my) * e, 1);
    CARD.rec.matrix = new THREE.Matrix4().compose(r.o.lerp(CARD_UP.o, e), _q, _sc);
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

/* ---- the card: lift it off the cartridge / lay it back, and where focus
 * goes back to. */
let cardOpener = null;
let cartHot = null;
function openCard(then) {
  const el = CARD.el;
  const wasDown = el.hidden || CARD.want === 0;
  if (wasDown) {
    const a = document.activeElement;
    cardOpener = (a && a !== document.body && a !== document.documentElement
                  && !el.contains(a)) ? a : null;
  }
  el.hidden = false;
  CARD.want = 1;
  /* Keyboard users land on the card; Tab leaves it freely and Escape or the
   * X always put it down. */
  if (wasDown) focusStill(then || $('otaCardBody'));
}
function closeCard() {
  const el = CARD.el;
  const wasUp = CARD.want === 1;
  const a = document.activeElement;
  const focusWasHere = !a || a === document.body || a === document.documentElement
    || el.contains(a);
  CARD.want = 0;
  if (wasUp && focusWasHere) {
    const back = (cardOpener && cardOpener.isConnected && !el.contains(cardOpener))
      ? cardOpener : cartHot;
    cardOpener = null;
    focusStill(back);
  }
}
function cardUp() { return CARD.want > 0; }

/* PUBLISH -- a click lifts the card; dragging the cartridge down until it
 * seats publishes what is on the card, and the card comes up to answer. */
cartHot = hotspot(P.cartridge.hotspot, P.cartridge.label +
        ' — click for the card; pull it up, then push it down to publish', h => {
  h.style.cursor = 'ns-resize';
  h.tabIndex = 0;
  h.setAttribute('role', 'button');
  let downY = 0, dragged = false;
  h.addEventListener('pointerdown', e => {
    running = true;
    h.setPointerCapture(e.pointerId);
    downY = stageXY(e)[1];
    dragged = false;
  });
  h.addEventListener('pointermove', e => {
    if (!h.hasPointerCapture(e.pointerId)) return;
    const [, y] = stageXY(e);
    if (!dragged && Math.abs(y - downY) < 6) return;
    dragged = true;
    const r = P.cartridge.hotspot;
    const f = Math.max(0, Math.min(1, (r.y + r.h - y) / r.h));
    SES.cartT = f;                       // the cartridge follows the pointer
    const seated = f < 0.02;
    if (seated && !SES.latch && !publishing) { openCard(); publish(); }
    if (!seated && SES.latch && f > 0.10) { SES.latch = false; applyState(); }
    note();
  });
  h.addEventListener('pointerup', () => { if (!dragged) openCard(); });
  h.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    ev.preventDefault();
    openCard();
  });
});

/* PROPAGATE -- drag the pulse down the spine by hand */
hotspot(P.propagate.hotspot, P.propagate.label +
        ' — drag to run the update down the rack', h => {
  h.style.cursor = 'ns-resize';
  drag(h, e => {
    const [, y] = stageXY(e);
    const r = P.propagate.hotspot;
    const f = Math.max(0, Math.min(1, (y - r.y) / r.h));
    SES.prop = Math.round(f * (P.propagate.frames - 1));
    applyState(); note();
  });
});

/* the CRADLES read the fleet onto the boards and print it on the card */
hotspot(P.fleet.hotspot, P.fleet.label + ' — read the fleet', h => {
  h.addEventListener('click', () => {
    if (posing) return;
    openCard();
    pullFleet(false);
  });
});

/* POLL INTERVAL -- angular drag about the projected hub.  NO DOM READOUT: the
 * needle is the value (BRIEF section 6).  Letting go polls the grid for the
 * card's module, the way a device would. */
hotspot(P.poll.hotspot, P.poll.label +
        ' — drag the needle, let go to check for the latest package', h => {
  h.style.cursor = 'grab';
  const PX = P.poll.pivot_px;
  drag(h, e => {
    const [x, y] = stageXY(e);
    let a = Math.atan2(x - PX.x, PX.y - y) / D2R;
    SES.poll = Math.max(P.poll.range[0], Math.min(P.poll.range[1], a));
    note();
  });
  h.addEventListener('pointerup', () => { if (!posing) pullLatest(SES.module, !cardUp()); });
});

{
  const on = (el, ev, fn) => el.addEventListener(ev, fn);
  on($('cardClose'), 'click', () => closeCard());
  on($('cardPublish'), 'click', () => publish());
  on($('cardLatest'), 'click', () => pullLatest(SES.module, false));
  on($('cardFleet'), 'click', () => pullFleet(false));
  on($('otaModule'), 'change', () => {
    SES.module = $('otaModule').value;
    pullLatest(SES.module, false);
  });
  /* Enter in the version field publishes, never on key-repeat */
  on($('otaVersion'), 'keydown', ev => {
    if (ev.key !== 'Enter' || ev.repeat) return;
    ev.preventDefault();
    publish();
  });
  /* Escape lays the card back on the cartridge.  Stopped here so nothing else
   * in this page (the refit docket's own Escape) also reacts.  The cockpit's
   * Escape lives on its own window and never sees keys typed in this iframe. */
  const closeTop = () => {
    if (CARD.want) { closeCard(); return true; }
    return false;
  };
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !CARD.want) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTop();
  });
  /* exposed so the shell can ask "did the module use this Escape?" first */
  window.__closeOverlay = closeTop;
}

/* ---- THE REFIT PORT -------------------------------------------------------
 * Nine lines, and none of them is OTA-specific: the anchor, the size, the part
 * names, the leaf pivots and the hotspot all come out of
 * `scene.json -> refit`, which pipeline/refit_port.py wrote.  It bolts to the
 * SHIP STRUCTURE beside the instrument -- the pillar above the rack, on the
 * crown of the column at (658, 32) -- never to the rack's faceplate, so no
 * control moves and no readout plane moves.  It clears the cartridge's 140 mm
 * lift corridor (x 538.5..605.6) by 18.6 px.  It declares NO readout plane:
 * all of its text is the screen-space docket, so check_occlusion.py question
 * 5, the dial-face rule and check_text.py are NOT ENGAGED by it.
 * readouts.length is still 5.
 *
 * `hotspot` is passed exactly as this page defines it.  refit.js's shared
 * wireHotspot() adapter handles all five conventions in the fleet; OTA is a
 * WIRER, so it produces byte-identical DOM to a hand call.  Do not hand-roll
 * an adapter here (FIX_UPLOAD 12.15 item 1).
 *
 * Passing this page's own `dress` is what chains attachDepthTest and then
 * attachForeground onto the port's materials; skip it and split.auditScene()
 * correctly reports double-blending. */
refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is OTA-specific either: the anchor,
 * the size, the part names, the vane pivot, the sweep travel and the hotspot
 * all come out of `scene.json -> mast`, which pipeline/status_mast.py wrote.
 *
 * It is NOT on the refit port's service rail, and that is a measurement.  The
 * port's carrier is the CROWN OF A COLUMN 127 px wide and the rail runs along
 * screen-right, so the published free_from_m = 1.5 W lands the mast's A = 0
 * past the column's edge: 2.3 % solid carrier, off frame.  So it takes
 * status_mast.py's `--at` route on the DECK at the foot of the column --
 * STATUS_AT_A_GLANCE 6.1's original "small brass status sub-plate bolted to
 * the panel", which 11.2's rail was an upgrade to, not a replacement for.
 *
 * Its face is raked 57 degrees, not MQB's and MTA's 0 and not KVS's 45.  The
 * deck's own two in-plane axes project at 539.9 and 581.2 px/m -- near enough
 * the same rate that a fitting lying flat on it is one-dimensional on screen,
 * which is exactly the condition KVS raked for.  At 57 the face sits at 21.68
 * degrees with its axes at 718.8 and 752.2 px/m, unforeshortened in both --
 * and 21.68 is within 1.1 degrees of OTA's own declared working-face
 * obliquity of 22.76.  Run `--rakes`; do not inherit.
 *
 * It declares NO readout plane.  Its words are the screen-space caption in
 * live3d/mast.css, the same class of thing as the port's docket, so
 * check_occlusion.py question 5, the dial-face rule and check_text.py are not
 * engaged by it.  `readouts.length` is still 5.
 *
 * `place()` is re-run on `refit:docket` by mast.js itself; this page needs no
 * MutationObserver.  Passing this page's own `dress` is what chains
 * attachDepthTest and then attachForeground onto the mast's materials. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

/* ------------------------------------------------------- M5  THE CAPTURE POSE
 * DETERMINISTIC, and equal to scene.json -> capture_pose, which is the state
 * export_ota.py rendered gt_full_read.png and gt_platen0.png in.  Scoring a
 * mismatched state measures the mismatch, not the renderer.
 *
 * `running = false` is the whole timer story here: this module starts no
 * setInterval and no setTimeout at all, so there is nothing to clearInterval.
 * The two followers snap to their targets and the propagation pulse stops
 * advancing, so pose() twice in a row gives byte-identical screenshots.  (KVS
 * failed this for a 520 ms cursor blink: 36 px at up to 87 levels.) */
function poseForCapture() {
  /* HIDE BOTH FITTINGS.  Every number in live3d/RESULTS.md and in this
   * module's NOTES was captured from pose() against Blender renders that
   * contain neither, so hiding them reproduces all of them unchanged and
   * re-renders nothing.  FIX_UPLOAD section 0, decision 3; STATUS_AT_A_GLANCE
   * 6.5.  Each fitting's own behaviour is measured with it SHOWN --
   * __refit.show(true) / __mast.show(true) -- which is a separate capture. */
  posing = true;
  pubGen++;                              // drop any in-flight publish result
  poseGen++;                             // and any in-flight read
  CARD.want = CARD.k = 0;
  CARD.el.hidden = true;
  if (refit) refit.pose();
  if (mast) mast.pose();
  running = false;
  pulseAcc = 0;
  lastErr = '';
  const C = S.capture_pose;
  SES.version = P.fleet.versions.new;
  SES.prev = P.fleet.versions.old;
  SES.checksum = (S.readout_text[1] || ['9F2C41B8'])[0];
  SES.cartT = C.cart_t;
  SES.latch = C.latch;
  SES.prop = C.propagate;
  SES.fleet = ORDER.indexOf(C.fleet);
  SES.poll = C.poll_deg;
  SES.empty = false;
  SES.live = null;
  SES.lastResult = null;
  setStatus('');
  printout = null;
  renderPrintout();
  cartNow = SES.cartT; pollNow = SES.poll;
  placeCartridge(cartNow);
  placeNeedle(pollNow);
  applyState();
  paintAll();
  posing = false;
}

/* a module-private capture hook, ALONGSIDE window.__occ and never instead of
 * it -- the fleet harness drives only __occ.  This is how the materials.json
 * A/B and the moving-plane measurement are taken off the real page. */
window.__ota = {
  ses: () => JSON.parse(JSON.stringify(SES)),
  tris: TRIS, meshes: MESHES,
  matfix: v => { matFixOn = !!v; applyMatFix(); applyState(); },
  gain: (g) => { if (g !== undefined) setGain(+g); return GAIN; },
  cart: t => { running = false; SES.cartT = t; cartNow = t;
               placeCartridge(t); },
  poll: d => { running = false; SES.poll = d; pollNow = d; placeNeedle(d); },
  fleet: nm => { SES.fleet = ORDER.indexOf(nm); applyState(); paintAll(); },
  prop: k => { SES.prop = k; applyState(); note(); },
  publish,
  latest: pullLatest,
  fleetPull: pullFleet,
  card: v => { if (v !== undefined) { if (v) openCard(); else closeCard(); }
               return { want: CARD.want, k: CARD.k, printout }; },
  result: () => SES.lastResult,
  /* the FrontSide trap, made measurable: flip the spine's materials back to
     THREE.FrontSide and the 14 chevrons vanish -- with no error, no console
     message and an EMPTY split.auditScene(), because the materials are
     attached perfectly correctly.  facingAudit() is the thing that finds it. */
  side: v => { for (const nm of P.propagate.nodes) {
                 const m = matOf[nm]; if (!m) continue;
                 m.side = v ? THREE.DoubleSide : THREE.FrontSide;
                 m.needsUpdate = true; } },
  facing: () => facingAudit(camera),
  layout: () => readouts.map((r, i) => ({
    i, name: r.tp.name, ...(r.layout || {}) })),
  planeO: () => readouts.map(r => r.plane.o.toArray()),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's own derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
};

applyState();
poseForCapture();
/* pose() hides both fittings; the page a human opens must SHOW them, or the
 * page they open is not the page this file describes.  check_occlusion.py's
 * section 0 reports the difference between the as-loaded and the posed frames,
 * and that section is REPORTED, NOT FAILED ON, for exactly this case. */
if (refit) refit.show(true);
mast.show(true);
/* `running = true` USED TO BE HERE, one line after poseForCapture(), which is
 * what actually shipped the rest-state defect: the page settled into
 * capture_pose and then immediately started advancing out of it.  See the
 * `running` declaration in M3.  The pulse is started by publish(), not by
 * loading the page. */
layout();
/* One-sided geometry that FrontSide has deleted.  Console warning only; it is
 * not part of __occ.audit(), which means something else and must stay []. */
facingAudit(camera);
/* the cartridge and the boards show the grid once it answers */
pullLatest(SES.module, true);
pullFleet(true);
requestAnimationFrame(frame);
window.__loaded = true;
