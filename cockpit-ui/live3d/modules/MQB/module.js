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
/* Rebuild is one service, not a grade.  live3d/service-rebuild.js. */
import { mountRefit } from '../../refit.js';
/* THE TELLTALE MAST.  live3d/mast.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> mast`, which
 * pipeline/status_mast.py wrote.  live3d/design/STATUS_AT_A_GLANCE.md section
 * 6 is the design. */
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'MQB';                     // Drone Telemetry Bus / switchboard
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
/* every mesh dress() has handed back, so facingAudit() below can ask which of
 * them FrontSide is silently discarding.  CONVERSION_BRIEF trap 21. */
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
/* Which dressed meshes face AWAY from the camera in their entirety?  Those are
 * the ones FrontSide has just deleted -- CONVERSION_BRIEF trap 21, which cost
 * OTA 14 single-triangle chevrons with auditScene() still reporting [].  This
 * page already knows about it for `mqb_trace_*` (see ingest()); the audit is
 * here because the refit port's iris leaves and the telltale mast's vane are
 * exactly the shape the trap names, and `auditScene()` does not look for it.
 * Area-weighted over world-space triangle normals, so a mesh that is merely
 * oblique does not register.  Deliberately NOT part of window.__occ.audit(),
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
 * MQB -- an overhead patch bay raked 18 deg down at the pilot, obliquity to
 * its own close camera 0.00 deg (survey_modules.py).  Four live controls, and
 * SEVEN readout planes: five topic labels over the jack columns, the register
 * plate under the scope, and the will card.
 *
 * WHAT IS *NOT* A READOUT, and why (CONVERSION_BRIEF section 6, the fleet
 * dial-face rule):
 *   - the KEEP ALIVE gauge face.  Bezel crops 40/121 of it before the needle
 *     even moves, and the needle sweeps the middle.  The needle IS that
 *     reading; there is no DOM copy of it anywhere on this page.
 *   - the scope face.  The phosphor trace sits 2.0 mm proud and covers up to
 *     18/121 of it, continuously.
 *   - the SUBSCRIBERS strip.  The party-line cords dip over it (audit:
 *     2-3/36 samples, 27-34 mm proud).  It carries a stamped label today and
 *     it stays stamped.
 */

/* ===================================================================== M1 */
/* LIVE PROPS.  13,188 triangles in 46 meshes across four glbs -- exactly the
 * module's control-owned total from survey_modules.py, because unlike KVS none
 * of MQB's controls is a text carrier: the type was already on the panel, not
 * on a control. */
const P = S.props;
const MAT = {};                         // mesh name -> its cloned material
const OBJ = {};                         // mesh name -> the mesh
function ingest(g, opts) {
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    const m = dress(o);
    /* mqb_trace_* is a one-sided RIBBON swept along the bus waveform, and its
     * winding puts the front face AWAY from the camera.  Blender renders it
     * because EEVEE does not backface-cull; dress() sets FrontSide, so without
     * this the whole phosphor trace is invisible and nothing errors. */
    if (opts && opts.double) m.side = THREE.DoubleSide;
    MAT[o.name] = m; OBJ[o.name] = o;
  });
}

const [gScope, gPatch, gRetained, gKA] = await Promise.all([
  load(A + P.scope.glb), load(A + P.patch.glb),
  load(A + P.retained.glb), load(A + P.keepalive.glb),
]);
ingest(gScope, { double: true });
ingest(gPatch);
ingest(gRetained);
ingest(gKA);
scene.add(gScope.scene); scene.add(gPatch.scene); scene.add(gRetained.scene);

/* the needle turns about the FACE normal, not the slot's +Z: MQB rakes its
 * working face 18 deg off the slot plane and rotating about +Z sweeps a cone.
 * The exporter emits the axis already negated, so a POSITIVE angle is
 * clockwise on screen -- the direction the gauge's own -118..+118 ticks run.
 * Verified against Blender: assets/MQB/gt_ka_p000.png vs gt_ka_p060.png. */
const ka = pivotAt(P.keepalive.hub);
ka.inner.add(gKA.scene);
const KA_AXIS = new THREE.Vector3().fromArray(P.keepalive.axis).normalize();
applyMatFix();

const TRI = (() => {                    // counted out of the loaded geometry
  let t = 0;
  for (const n in OBJ) {
    const g = OBJ[n].geometry;
    t += (g.index ? g.index.count : g.attributes.position.count) / 3;
  }
  return Math.round(t);
})();

/* ===================================================================== M2 */
/* READOUT LAYOUT.
 *
 * Every piece of MQB type is Blender align_x='CENTER' / align_y='CENTER', and
 * MQB uses FOUR different FONT.size values (0.0090 topics, 0.0148 the party
 * jack, 0.0098 the register plate, 0.0068 the will card).  Two consequences
 * for the template's type block, both recorded in NOTES.md:
 *
 *  a) left_m + white-space:pre lays type out LEFT-aligned from a fixed column.
 *     Centred type whose CONTENT CHANGES cannot use a fixed left column, so
 *     the line box is made full-width and text-align:center does the centring
 *     -- which is exactly what Blender's align_x='CENTER' does (it centres the
 *     ADVANCE width, as does CSS, so the two agree for a monospaced face).
 *
 *  b) base_adj is a single number in ELEMENT pixels, and the offset it stands
 *     for scales with FONT SIZE.  One constant cannot serve four sizes.  So
 *     the exporter emits base_m -- Blender's own baseline offset below the
 *     text object's origin, MEASURED per size -- and the baseline is placed
 *     from the browser's real font metrics instead of fudged.  base_adj stays
 *     0 and there is no empirical constant in this module's overlay.
 */
const FONT_STACK = getComputedStyle(document.querySelector('.readout') ||
  document.createElement('div')).fontFamily ||
  '"Courier New", ui-monospace, Menlo, monospace';
const _mctx = document.createElement('canvas').getContext('2d');
function faceMetrics(px) {
  _mctx.font = '700 ' + px + 'px ' + FONT_STACK;
  const m = _mctx.measureText('M');
  return { asc: m.fontBoundingBoxAscent, desc: m.fontBoundingBoxDescent,
           cap: m.actualBoundingBoxAscent };
}
const layoutErr = [];
for (const r of readouts) {
  const t = r.tp.type;
  if (!t) continue;
  r.lines.style.left = '0px';
  r.lines.style.width = '100%';
  r.lines.style.textAlign = 'center';
  const F = parseFloat(r.lines.style.fontSize);
  const L = parseFloat(r.lines.style.lineHeight);
  const fm = faceMetrics(F);
  /* where the browser puts the baseline inside a line box of height L */
  const baseInBox = (L - (fm.asc + fm.desc)) / 2 + fm.asc;
  /* where Blender put it: the text origin sits top_m above the rect centre,
   * and the baseline sits base_m (negative) below the origin. */
  const yBase = (r.tp.half_h - (t.top_m + t.base_m)) / MPP;
  r.lines.style.top = (yBase - baseInBox + (t.base_adj || 0)).toFixed(3) + 'px';
  /* cross-check: the face's own cap height against Blender's, in element px */
  layoutErr.push({ name: r.tp.name, font_px: +F.toFixed(3),
                   cap_dom_px: +fm.cap.toFixed(3),
                   cap_blender_px: +(t.cap_m / MPP).toFixed(3) });
}

/* ===================================================================== M3 */
/* THE SESSION MODEL -- an MQTT broker's console.
 *
 * Capture pose is still deterministic (WILLS[0], exported topics).  Live
 * bytes come off POST /api/interact.  The console holds ONE session on the
 * bus, under its own client id, signed in with the console's password unless
 * the operator types their own on the card.  Every value reaches the panel
 * and the card through textContent. */
let seed = 20260902;
const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;

const WILLS = [
  ['IF THIS', 'LINE', 'DROPS', 'PLAY', 'THIS'],
  ['DRONE 07', 'LOST', 'LINK AT', 'SECTOR', 'NINE'],
  ['HULL', 'BREACH', 'AT BAY', 'THREE', 'VENT'],
  ['NO PING', 'IN 60S', 'CUT THE', 'FUEL', 'FEED'],
  ['LAST', 'FIX WAS', 'GRID', 'FOUR', 'ALPHA'],
];
/* The jack labels a human opens the page on.  The capture pose paints the
 * exported ones (P.patch.topics), which the Blender plate was rendered with. */
const LIVE_TOPICS = ['drone/07/pos', 'hull/temp', 'nav/fix', 'will/lost', 'bay/door'];
const CID = 'cockpit-' + Array.from(crypto.getRandomValues(new Uint8Array(3)),
  b => b.toString(16).padStart(2, '0')).join('');

const SES = {
  topics: P.patch.topics.slice(),        // the five jack labels, as built
  clients: 7,
  retain: 3,
  will: WILLS[0].slice(),
  patch: P.patch.order[P.patch.order.length - 1],
  retained: P.retained.order[2],
  keepalive: 60.0,                       // degrees on the gauge
  scope: 0,
  plugged: [false, false, false, false, false],
  focus: 0,
  connected: false,
  live: false,                           // needle follows the keep-alive
  keepAliveS: 30,
};
/* THE PAGE RESTS IN ITS POSED STATE.  `running` used to start TRUE, so the ten
 * phosphor ribbons cycled at 6 fps, the keep-alive needle swept its 12 s ramp
 * and a session `step()` fired every 2.2 s from the first frame after load --
 * and every check in the brief calls `__occ.pose()` first, so the whole suite
 * PASSED while the page a human opens was never in the state anything was
 * measured against.  check_occlusion.py's section 0 measured the gap at
 * 15,850 px (pr 1) / 61,474 px (pr 2), worst 188 levels, strings identical.
 *
 * It starts PAUSED now, and the theatre is started by the `bus: paused`
 * toolbar button or by `__mqb.run(true)`.  Every hotspot pauses it, and a
 * live session never runs it. */
let running = false;
let nextEvent = 0;
/* bumped by pose(): an answer that lands after it is dropped */
let poseGen = 0;

function fmtRegister() {
  const c = String(Math.max(0, Math.min(99, SES.clients))).padStart(2, '0');
  const r = String(Math.max(0, Math.min(9, SES.retain)));
  return 'CLIENTS ' + c + '  RETAIN ' + r;
}
function paintAll() {
  for (let i = 0; i < 5; i++) readouts[i].paint([SES.topics[i]]);
  readouts[5].paint([fmtRegister()]);
  /* the will card is the operator card's rest; while the card is up the
   * plane is bare */
  readouts[6].paint(CARD && !CARD.el.hidden ? [] : SES.will);
}

/* Theatre only, and never over a live session. */
function step() {
  if (SES.connected) return;
  const k = Math.floor(rnd() * 3);
  if (k === 0) {
    const o = P.retained.order;
    setRetained(o[(o.indexOf(SES.retained) + 1) % o.length]);
  } else if (k === 1) {
    const o = P.patch.order;
    setPatch(o[(o.indexOf(SES.patch) + 1) % o.length]);
  } else {
    setScope(SES.scope + 1);
  }
  note();
}

/* ===================================================================== M4 */
/* CONTROL STATE -> GEOMETRY                                                */
function setScope(i) {
  SES.scope = ((i % P.scope.nodes.length) + P.scope.nodes.length)
    % P.scope.nodes.length;
  P.scope.nodes.forEach((n, j) => { if (OBJ[n]) OBJ[n].visible = j === SES.scope; });
}
function setPatch(name) {
  SES.patch = name;
  for (const st of P.patch.order)
    for (const n of P.patch.states[st])
      if (OBJ[n]) OBJ[n].visible = st === name;
}
function setRetained(name) {
  SES.retained = name;
  const [lampKey, pipKey, tab] = P.retained.poses[name];
  applyLampMat(P.retained.dome, P.retained.mats[lampKey], lampKey === 'lamp_on');
  applyLampMat(P.retained.pip, P.retained.mats[pipKey], pipKey === 'pip_on');
  for (const n of P.retained.held) if (OBJ[n]) OBJ[n].visible = tab;
}
/* the glb ships one of the pair; the OTHER comes out of materials.json by
 * name, which is only possible because the module declared both. */
function applyLampMat(node, matName, on) {
  const m = MAT[node], rec = MJ[matName];
  if (!m || !rec) return;
  m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                 THREE.LinearSRGBColorSpace);
  m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                    THREE.LinearSRGBColorSpace);
  m.emissiveIntensity = on ? rec.emit : 0;
  m.roughness = matFixOn ? rec.rough : m.roughness;
  m.metalness = matFixOn ? rec.metallic : m.metalness;
}
function setKeepalive(deg) {
  SES.keepalive = Math.max(P.keepalive.range[0],
                           Math.min(P.keepalive.range[1], deg));
  ka.pivot.quaternion.setFromAxisAngle(KA_AXIS, SES.keepalive * D2R);
}
function syncPatchVisual() {
  const n = SES.plugged.reduce((a, p) => a + (p ? 1 : 0), 0);
  if (SES.plugged[4]) setPatch('party');
  else if (n >= 2) setPatch('two');
  else if (n === 1) setPatch('one');
  else setPatch('idle');
}

function planeRect(i) {
  const c = PLANES[i] && PLANES[i].corners_px;
  if (!c) return { x: 0, y: 0, w: 0, h: 0 };
  const xs = [c.tl.x, c.tr.x, c.bl.x, c.br.x];
  const ys = [c.tl.y, c.tr.y, c.bl.y, c.br.y];
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

function jackAt(x) {
  let best = 0, bestD = 1e9;
  for (let i = 0; i < 5; i++) {
    const r = planeRect(i);
    const d = Math.abs(x - (r.x + r.w / 2));
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

function topicHasWild(t) {
  return /[+#]/.test(t || '');
}

/* Track 01 client is not in this tree.  Same-origin /api/interact via serve.py. */
async function interact(action, params) {
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: CODE, action, params: params || {} }),
      keepalive: action === 'disconnect',
    });
    let data;
    try { data = await r.json(); }
    catch { return { ok: false, error: 'bad JSON from coordinator' }; }
    const res = (data && data.result) || data;
    if (!r.ok && res && res.ok === undefined)
      return { ok: false, error: String(res.error || ('HTTP ' + r.status)) };
    return res;
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e || 'offline') };
  }
}

/* one request at a time on the held socket */
let busQ = Promise.resolve();
function bus(action, params) {
  const run = () => interact(action, params);
  const p = busQ.then(run, run);
  busQ = p.then(() => {}, () => {});
  return p;
}

/* ---- THE CARD'S OWN PAPER.  Its status line, printout, line header and
 * jack list.  Every line is painted with textContent only. */
const TRAFFIC_CAP = 300;
const traffic = [];
let heard = 0;
function setStatus(text, kind) {
  const e = $('cardReply');
  e.textContent = text || '';
  e.className = kind || '';
  e.title = text || '';
}
const lineCls = l => /^> /.test(l) ? 'sent' : (/^\s*\(error\)/.test(l) ? 'bad' : '');
function print(lines) {
  for (const l of lines) traffic.push(String(l));
  if (traffic.length > TRAFFIC_CAP) traffic.splice(0, traffic.length - TRAFFIC_CAP);
  paintTraffic();
}
function paintTraffic() {
  const pre = $('cardLines');
  pre.textContent = '';
  if (!traffic.length) {
    const e = document.createElement('span');
    e.className = 'empty';
    e.textContent = 'Plug a jack to listen on its topic. What the bus carries prints here.';
    pre.appendChild(e);
  } else {
    for (const line of traffic) {
      const e = document.createElement('div');
      const c = lineCls(line);
      if (c) e.className = c;
      e.textContent = line;
      pre.appendChild(e);
    }
    pre.scrollTop = pre.scrollHeight;
  }
  $('cardCount').textContent = heard ? heard + (heard === 1 ? ' message' : ' messages') : '';
}
let selJack = 0;
function paintLine() {
  $('cardLine').textContent = SES.connected ? 'LINE UP' : 'LINE DOWN';
  $('cardCid').textContent = CID;
  const n = SES.plugged.filter(Boolean).length;
  $('cardPlugged').textContent = n ? n + ' plugged' : '';
  $('cardConn').disabled = SES.connected;
  $('cardHang').disabled = !SES.connected;
  const box = $('cardJacks');
  box.textContent = '';
  SES.topics.forEach((t, i) => {
    const e = document.createElement('div');
    e.setAttribute('role', 'option');
    e.setAttribute('aria-selected', String(i === selJack));
    if (SES.plugged[i]) e.className = 'on';
    for (const s of [String(i + 1), t || '(no topic)', SES.plugged[i] ? 'PLUGGED' : '--']) {
      const c = document.createElement('span');
      c.textContent = s;
      e.appendChild(c);
    }
    e.title = t;
    e.addEventListener('click', () => { selJack = i; toggleJack(i); });
    box.appendChild(e);
  });
}

/* the focused jack's topic follows onto the card's SEND face */
function focusJack(i) {
  SES.focus = i;
  selJack = i;
  $('cardTopic').value = SES.topics[i] || '';
  paintLine();
}

/* ---- WHAT THE CONSOLE DOES ON THE BUS ----------------------------------- */
function kaRestart() {
  kaFallT0 = performance.now();
  kaLastT = 0;
  kaShown = P.keepalive.range[0];
  setKeepalive(kaShown);
}
function markDown() {
  SES.connected = false;
  SES.live = false;
  SES.plugged = [false, false, false, false, false];
  syncPatchVisual();
  paintLine();
}
/* the bridge forgets a session whose socket died; the next call says so */
function lostLine(r) {
  if (r && r.ok === false && /no held session/.test(String(r.error || ''))) {
    markDown();
    print(['(error) the line is down']);
    return true;
  }
  return false;
}
function failText(r, what) {
  return String((r && (r.error || r.summary)) || (what + ' failed'));
}

async function connect() {
  const gen = poseGen;
  const kaIn = parseInt($('cardKa').value, 10);
  SES.keepAliveS = Number.isFinite(kaIn) ? Math.max(0, Math.min(3600, kaIn)) : 30;
  $('cardKa').value = String(SES.keepAliveS);
  setStatus('connecting…', 'busy');
  const r = await bus('connect', {
    client_id: CID,
    password: $('cardPass').value,
    keep_alive: SES.keepAliveS,
    will_topic: $('cardWillTopic').value.trim(),
    will_message: SES.will.filter(Boolean).join('\n'),
  });
  if (gen !== poseGen) return false;
  print(['> CONNECT ' + CID]);
  if (r && r.ok) {
    SES.connected = true;
    SES.live = true;
    SES.plugged = [false, false, false, false, false];
    syncPatchVisual();
    kaRestart();
    print(['CONNACK accepted']);
    setStatus('Line up as ' + CID, 'ok');
    pollStats();
  } else {
    print(['(error) ' + failText(r, 'CONNECT')]);
    setStatus(failText(r, 'CONNECT'), 'err');
  }
  paintLine();
  note();
  return SES.connected;
}
async function ensureConnected() {
  return SES.connected || connect();
}

async function hangup(graceful) {
  if (!SES.connected) return;
  const gen = poseGen;
  const will = $('cardWillTopic').value.trim();
  markDown();
  await bus('disconnect', { client_id: CID, graceful: !!graceful });
  if (gen !== poseGen) return;
  print([graceful ? '> DISCONNECT' : '> (cord yanked)']);
  setStatus(graceful ? 'Hung up' : (will ? 'Line dropped. The will plays on ' + will
                                         : 'Line dropped'), graceful ? 'ok' : 'err');
  pollStats();
  note();
}

let statsBusy = false;
async function pollStats() {
  if (statsBusy) return;
  statsBusy = true;
  const gen = poseGen;
  const r = await bus('stats', {});
  statsBusy = false;
  if (gen !== poseGen || !r || !r.ok) return;
  if (typeof r.clients_connected === 'number') SES.clients = r.clients_connected;
  if (typeof r.retained_count === 'number') SES.retain = r.retained_count;
  paintAll();
}

/* the needle pings quietly every keep-alive; a click on the gauge says so */
async function pingNow(quiet) {
  if (!SES.connected) return;
  const gen = poseGen;
  kaRestart();
  const r = await bus('ping', { client_id: CID });
  if (gen !== poseGen || lostLine(r)) return;
  if (r && r.ok) { if (!quiet) setStatus('The bus answered the ping', 'ok'); }
  else setStatus(failText(r, 'PINGREQ'), 'err');
}

/* what the bus delivered: onto the printout, one scope step each, and the
 * retained lamp shows whether the last one was a kept copy.  What arrives in
 * answer to a SUBSCRIBE is the kept copy, whatever its retain bit says. */
function receive(msgs, kept) {
  if (!msgs || !msgs.length) return;
  for (const m of msgs) {
    print(['< ' + m.topic + (kept || m.retain ? '  (kept copy)' : ''),
           '  ' + String(m.payload == null ? '' : m.payload)]);
    heard++;
    setScope(SES.scope + 1);
  }
  const last = msgs[msgs.length - 1];
  setRetained(kept || last.retain ? 'retained' : 'live');
  paintTraffic();
  note();
}

let draining = false;
async function drain() {
  draining = true;
  const gen = poseGen;
  const r = await bus('drain', { client_id: CID });
  draining = false;
  if (gen !== poseGen || lostLine(r)) return;
  if (r && r.ok) receive(r.messages);
}

async function publish(spec) {
  const topic = String(spec.topic || '').trim();
  if (!topic || topicHasWild(topic)) {
    setStatus('Publish needs a concrete topic, such as hull/temp.', 'err');
    return { ok: false };
  }
  if (!(await ensureConnected())) return { ok: false };
  const gen = poseGen;
  const qos = spec.qos ? 1 : 0;
  setStatus('publishing…', 'busy');
  const r = await bus('publish', {
    client_id: CID, topic, message: spec.message, qos, retain: !!spec.retain,
  });
  if (gen !== poseGen || lostLine(r)) return r;
  const tags = (qos ? ' qos 1' : '') + (spec.retain ? ' retained' : '');
  print(['> PUBLISH ' + topic + tags,
         spec.message === '' ? '  (empty)' : '  ' + spec.message]);
  if (r && r.ok) {
    setScope(SES.scope + 1);
    setStatus(spec.retain && spec.message === '' ? 'Cleared the kept copy on ' + topic
              : 'Published on ' + topic + (qos ? ', acknowledged' : ''), 'ok');
  } else {
    print(['(error) ' + failText(r, 'PUBLISH')]);
    setStatus(failText(r, 'PUBLISH'), 'err');
  }
  pollStats();
  return r;
}
function publishCard() {
  return publish({ topic: $('cardTopic').value, message: $('cardPayload').value,
                   qos: $('cardQos').value === '1', retain: $('cardRetain').checked });
}

async function plugJack(i) {
  focusJack(i);
  const topic = (SES.topics[i] || '').trim();
  if (!topic) { setStatus('Type a topic on that jack first.', 'err'); return; }
  if (!(await ensureConnected())) return;
  const gen = poseGen;
  const r = await bus('subscribe', { client_id: CID, topic, qos: 0 });
  if (gen !== poseGen || lostLine(r)) return;
  print(['> SUBSCRIBE ' + topic]);
  if (r && r.ok) {
    SES.plugged[i] = true;
    syncPatchVisual();
    setStatus('Listening on ' + topic, 'ok');
    receive(r.messages, true);
  } else {
    print(['(error) ' + failText(r, 'SUBSCRIBE')]);
    setStatus(failText(r, 'SUBSCRIBE'), 'err');
  }
  paintLine();
  note();
}

async function unplugJack(i, topic) {
  topic = topic == null ? (SES.topics[i] || '') : topic;
  SES.plugged[i] = false;
  syncPatchVisual();
  paintLine();
  if (!SES.connected) return;
  const gen = poseGen;
  const r = await bus('unsubscribe', { client_id: CID, topic });
  if (gen !== poseGen || lostLine(r)) return;
  print(['> UNSUBSCRIBE ' + topic]);
  setStatus(r && r.ok ? 'Stopped listening on ' + topic : failText(r, 'UNSUBSCRIBE'),
            r && r.ok ? 'ok' : 'err');
  note();
}
function toggleJack(i) {
  running = false;
  if (SES.plugged[i]) unplugJack(i); else plugJack(i);
}

/* ===================================================================== M5 */
/* ANIMATION.  Runs once per frame BEFORE the split renders.  No readout plane
 * rides a control here -- all seven are bolted to the panel -- so nothing
 * calls r.place().  The bus is read from here too (drain and stats on a
 * clock), so there is no timer to clear in pose(). */
let kaShown = SES.keepalive;
let kaFallT0 = 0;
let kaLastT = 0;
let nextDrain = 0, nextStats = 0;
const DRAIN_MS = 1500, STATS_MS = 4000;
/* THE REFIT PORT.  Mounted below, after the hotspot helper exists; declared
 * here because onFrame() and poseForCapture() both reach it and both are
 * defined before the mount.  live3d/refit.js, live3d/design/FIX_UPLOAD.md. */
let refit = null;
/* THE TELLTALE MAST.  Mounted beside the port, on the same carrier and the
 * same rail cross-section.  live3d/mast.js, STATUS_AT_A_GLANCE section 6. */
let mast = null;
function onFrame(dt, now) {
  /* BEFORE the `running` gate, not after.  The port's iris, throat pulse,
   * jewel breath, ratchet and tally all animate off refit.tick() because the
   * port owns no timer of its own (FIX_UPLOAD 8.3 item 4).  Below the gate the
   * port would be frozen on exactly the page a human opens. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  tickHeld(dt);
  const span = P.keepalive.range[1] - P.keepalive.range[0];
  if (SES.live) {
    const win = Math.max(1, SES.keepAliveS);
    const t = (Math.max(0, now - kaFallT0) / 1000) % win;
    if (t < kaLastT && SES.keepAliveS > 0) pingNow(true);
    kaLastT = t;
    const want = P.keepalive.range[0] + span * (t / win);
    kaShown += (want - kaShown) * Math.min(1, dt * 9);
    setKeepalive(kaShown);
  }
  if (SES.connected) {
    if (!draining && SES.plugged.some(Boolean) && now > nextDrain) {
      nextDrain = now + DRAIN_MS;
      drain();
    }
    if (now > nextStats) { nextStats = now + STATS_MS; pollStats(); }
  }
  if (!running || SES.connected) return;
  setScope(Math.floor(now / 166.7));
  const t = (now / 1000) % 12.0;
  const want = P.keepalive.range[0] + span * (t / 12.0);
  kaShown += (want - kaShown) * Math.min(1, dt * 9);
  setKeepalive(kaShown);
  if (now > nextEvent) { nextEvent = now + 2200; step(); }
}

/* ===================================================================== M6 */
/* INTERACTION.  Hotspots live in #hots, above the front canvas.            */
function hotspot(rect, title, wire) {
  const h = document.createElement('div');
  h.className = 'hot';
  h.style.left = rect.x + 'px'; h.style.top = rect.y + 'px';
  h.style.width = rect.w + 'px'; h.style.height = rect.h + 'px';
  h.title = title;
  $('hots').appendChild(h);
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
const stageXY = ev => {
  const b = $('stage').getBoundingClientRect();
  const k = b.width / W;
  return [(ev.clientX - b.left) / k, (ev.clientY - b.top) / k];
};

/* ---- HELD PAPER.  The operator card is DOM in a second CSS3D layer, laid on
 * the will card's basis.  Its `k` runs 0..1: 0 is the will card in its
 * holder at the top right of the panel, 1 is drawn out of the holder by its
 * pull tab and held up to the right of the panel, turned a little toward the
 * middle of the panel the way a hand holds a card, clear of the topic lines,
 * the retained switch and the gauge.
 * onFrame() eases k toward `want`; no timers. */
const V = a => new THREE.Vector3().fromArray(a);
const TPW = PLANES[6];
const FACE_U = V(TPW.u), FACE_V = V(TPW.v), FACE_N = V(TPW.n);
const held = new CSS3DLayer($('held'), W, H);
const CARD = { el: $('mqbCard'), w: 560, h: 740, k: 0, want: 0 };
CARD.rec = held.add(CARD.el);
const WILL_RECT = planeRect(6);
const REF_D = camera.position.distanceTo(V(TPW.origin));
/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the will card's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = REF_D * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  return { o, m: at.w * perPx / elW };
}
const CARD_REST = heldPose({ x: WILL_RECT.x + WILL_RECT.w / 2, y: WILL_RECT.y + WILL_RECT.h / 2,
  w: WILL_RECT.w }, CARD.w, 0.995);
const CARD_UP = heldPose({ x: 1088, y: 372, w: 318 }, CARD.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
/* At rest the card lies in the panel face; held, it is yawed about its own
 * vertical so its inner edge sits deeper than its outer one, and rolled a
 * hair off true.  The panel faces the camera dead on, so without this the
 * card reads as a flat overlay rather than paper in the scene. */
const HELD_YAW = -16 * D2R, HELD_ROLL = 2.2 * D2R;
const Q_FACE = new THREE.Quaternion().setFromRotationMatrix(
  new THREE.Matrix4().makeBasis(FACE_U, FACE_V, FACE_N));
const Q_UP = Q_FACE.clone()
  .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), HELD_YAW))
  .multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), HELD_ROLL));
const _q = new THREE.Quaternion(), _sc = new THREE.Vector3();
function tickHeld(dt) {
  if (CARD.k !== CARD.want) {
    const step = dt * 4;
    CARD.k = CARD.want > CARD.k ? Math.min(CARD.want, CARD.k + step)
                                : Math.max(CARD.want, CARD.k - step);
    if (CARD.k === 0) { CARD.el.hidden = true; paintAll(); }
  }
  if (!CARD.el.hidden) {
    const e = ease(CARD.k), m = CARD_REST.m + (CARD_UP.m - CARD_REST.m) * e;
    CARD.el.style.opacity = String(Math.min(1, e * 2.5));
    _q.copy(Q_FACE).slerp(Q_UP, e);
    _sc.set(m, m, 1);
    CARD.rec.matrix = new THREE.Matrix4().compose(
      CARD_REST.o.clone().lerp(CARD_UP.o, e), _q, _sc);
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

/* ---- the card: lift it / put it back, which face is up, and where focus
 * goes back to. */
let cardOpener = null, willHot = null;
const FACES = ['line', 'send', 'will'];
function showFace(which) {
  if (!FACES.includes(which)) which = 'line';
  for (const f of FACES) {
    const id = f[0].toUpperCase() + f.slice(1);
    $('face' + id).hidden = f !== which;
    $('tab' + id).setAttribute('aria-selected', String(f === which));
  }
}
function faceUp() {
  return FACES.find(f => !$('face' + f[0].toUpperCase() + f.slice(1)).hidden);
}
function openCard(face, then) {
  const el = CARD.el;
  const wasDown = el.hidden || CARD.want === 0;
  if (wasDown) {
    const a = document.activeElement;
    cardOpener = (a && a !== document.body && a !== document.documentElement
                  && !el.contains(a)) ? a : null;
  }
  if (face) showFace(face);
  el.hidden = false;
  CARD.want = 1;
  paintAll();
  if (wasDown || then) focusStill(then || $('cardBody'));
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
      ? cardOpener : willHot;
    cardOpener = null;
    focusStill(back);
  }
}

hotspot(P.patch.hotspot, P.patch.label + ' — plug a jack to listen, unplug to stop, yank to drop the line', h => {
  let yankCol = null, yanked = false;
  const inBay = (x, y) => {
    const r = P.patch.hotspot;
    return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
  };
  h.addEventListener('pointerdown', e => {
    const [x] = stageXY(e);
    const i = jackAt(x);
    yankCol = SES.plugged[i] ? i : null;
    yanked = false;
    if (yankCol != null) h.setPointerCapture(e.pointerId);
  });
  h.addEventListener('pointermove', e => {
    if (yankCol == null) return;
    const [x, y] = stageXY(e);
    if (!inBay(x, y)) yanked = true;
  });
  h.addEventListener('pointerup', () => {
    if (yankCol != null && yanked) hangup(false);
    yankCol = null;
  });
  h.addEventListener('click', e => {
    if (yanked) { yanked = false; return; }
    const [x] = stageXY(e);
    toggleJack(jackAt(x));
  });
});
/* the retained switch steps kept copy -> live -> clear, publishing the card's
 * payload on the focused jack's topic, and lifts the card so the answer is
 * visible */
hotspot(P.retained.hotspot, P.retained.label + ' — publish on the focused topic: kept, live, or clear', h => {
  const go = () => {
    running = false;
    const o = P.retained.order;
    const next = o[(o.indexOf(SES.retained) + 1) % o.length];
    const payload = $('cardPayload').value;
    const topic = SES.topics[SES.focus] || '';
    const spec = next === 'clear' ? { topic, message: '', retain: true }
               : { topic, message: payload, retain: next === 'retained' };
    $('cardTopic').value = topic;
    $('cardRetain').checked = next !== 'live';
    openCard('send');
    publish(spec).then(r => { if (r && r.ok) setRetained(next); note(); });
  };
  h.addEventListener('click', go);
  buttonHot(h, go);
});
/* the scope: drag scrubs the trace; a click that is not a drag lifts the card
 * so the traffic is readable */
hotspot(P.scope.hotspot, P.scope.label + ' — click to read the traffic; drag to run the trace', h => {
  let down = null, dragged = false;
  const set = ev => {
    const r = h.getBoundingClientRect();
    const f = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
    setScope(Math.round(f * (P.scope.nodes.length - 1)));
    note();
  };
  h.addEventListener('pointerdown', e => {
    running = false; down = [e.clientX, e.clientY]; dragged = false;
    h.setPointerCapture(e.pointerId);
  });
  h.addEventListener('pointermove', e => {
    if (!down) return;
    if (!dragged && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 6) return;
    dragged = true;
    set(e);
  });
  h.addEventListener('pointerup', () => {
    if (down && !dragged) openCard(null, $('cardLines'));
    down = null;
  });
  h.addEventListener('pointercancel', () => { down = null; });
  buttonHot(h, () => openCard(null, $('cardLines')));
});
hotspot(P.keepalive.hotspot, P.keepalive.label + ' — click to ping the bus, drag to aim', h => {
  let dragged = false, sx = 0, sy = 0;
  const set = ev => {
    const [x, y] = stageXY(ev);
    const a = Math.atan2(x - P.keepalive.pivot_px.x,
                         P.keepalive.pivot_px.y - y) / D2R;
    kaShown = a; setKeepalive(a); note();
  };
  const ping = () => {
    if (SES.connected) pingNow();
    else setStatus('The line is down. Connect first.', 'err');
  };
  h.addEventListener('pointerdown', e => {
    running = false;
    dragged = false;
    sx = e.clientX; sy = e.clientY;
    h.setPointerCapture(e.pointerId);
    h.onpointermove = ev => {
      if (Math.hypot(ev.clientX - sx, ev.clientY - sy) > 6) {
        dragged = true;
        set(ev);
      }
    };
  });
  h.addEventListener('pointerup', () => {
    h.onpointermove = null;
    if (!dragged) ping();
  });
  buttonHot(h, ping);
});

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is MQB-specific either: the anchor,
 * the size, the part names, the vane pivot, the sweep travel and the hotspot
 * all come out of `scene.json -> mast`, which pipeline/status_mast.py wrote.
 *
 * It mounts on the refit port's own service rail at 12.2 W, not the published
 * 1.5 W floor, and not KVS's 3.2 W: on MQB `refit.js`'s docket solver lands
 * the docket at (312, 390) 520 x 318 -- to the RIGHT of the port, because the
 * left candidate clamps to x 12 and then covers the port's own envelope --
 * so everything from 1.5 W to about 11.6 W is under the docket whenever the
 * port is open, and reading the mast while the port is open is the whole
 * point of the close-up half.  NOTES section 15.
 *
 * Its face is raked 0 degrees, not KVS's 45: MQB's apron faces the close
 * camera dead on, so the rake IS the obliquity, and MQB's two in-plane axes
 * already project at 2450.8 px/m each at 90 degrees to one another -- the
 * condition KVS had to rake to reach.
 *
 * It declares NO readout plane.  Its words are the screen-space caption in
 * live3d/mast.css, the same class of thing as the port's docket, so
 * check_occlusion.py question 5, the dial-face rule and check_text.py are not
 * engaged by it.  `readouts.length` is still 7.
 *
 * Passing this page's own `dress` is what chains attachDepthTest and then
 * attachForeground onto the mast's materials; skip it and split.auditScene()
 * correctly reports double-blending. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

/* ---- typeable jack labels (textContent only) ---------------------------- */
const typeIn = $('typeIn');
let typeJack = -1;

function hideType() {
  typeJack = -1;
  typeIn.classList.remove('on');
}
function commitType() {
  if (typeJack < 0) return;
  const i = typeJack;
  const was = SES.topics[i];
  const now = typeIn.value.replace(/\r?\n/g, '').trim();
  hideType();
  if (now === was) return;
  SES.topics[i] = now;
  paintAll();
  focusJack(i);
  /* a plugged jack follows its new label */
  if (SES.plugged[i]) unplugJack(i, was).then(() => { if (now) plugJack(i); });
}
typeIn.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); commitType(); }
  else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); hideType(); }
});
typeIn.addEventListener('blur', () => commitType());

function focusTopic(i) {
  commitType();
  focusJack(i);
  typeJack = i;
  const r = planeRect(i);
  typeIn.value = SES.topics[i] || '';
  typeIn.style.left = r.x + 'px';
  typeIn.style.top = r.y + 'px';
  typeIn.style.width = r.w + 'px';
  typeIn.style.height = r.h + 'px';
  typeIn.style.fontSize = readouts[i].lines.style.fontSize;
  typeIn.classList.add('on');
  focusStill(typeIn);
  typeIn.select();
}
for (let i = 0; i < 5; i++) {
  hotspot(planeRect(i), 'TOPIC ' + (i + 1) + ' — type the topic this jack listens on', h => {
    const go = () => { running = false; focusTopic(i); };
    h.addEventListener('click', e => { e.stopPropagation(); go(); });
    buttonHot(h, go);
  });
}
/* the will card: lift the operator card */
willHot = hotspot(WILL_RECT, 'OPERATOR CARD — open the card: line, send and will', h => {
  const go = () => { running = false; openCard(); };
  h.addEventListener('click', go);
  buttonHot(h, go);
});
$('hots').appendChild(typeIn);

refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* the card's own controls */
const WILL_IN = [...$('cardWill').querySelectorAll('input')];
{
  const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
  on('cardClose', 'click', () => closeCard());
  for (const f of FACES) on('tab' + f[0].toUpperCase() + f.slice(1), 'click', () => showFace(f));
  on('cardConn', 'click', () => connect());
  on('cardHang', 'click', () => hangup(true));
  on('cardPub', 'click', () => publishCard());
  /* one field per line of the will card; Enter moves down a line */
  WILL_IN.forEach((inp, i) => {
    inp.addEventListener('input', () => {
      SES.will = WILL_IN.map(e => e.value.toUpperCase());
      paintAll();
    });
    inp.addEventListener('keydown', ev => {
      if (ev.key !== 'Enter' || ev.ctrlKey || ev.metaKey) return;
      ev.preventDefault();
      if (WILL_IN[i + 1]) focusStill(WILL_IN[i + 1]);
    });
  });
  on('cardPass', 'keydown', ev => {
    if (ev.key === 'Enter' && !ev.repeat && !SES.connected) { ev.preventDefault(); connect(); }
  });
  /* arrow keys walk the jacks; Enter or Space plugs or unplugs */
  on('cardJacks', 'keydown', ev => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      selJack = Math.max(0, Math.min(4, selJack + (ev.key === 'ArrowDown' ? 1 : -1)));
      paintLine();
    } else if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      toggleJack(selJack);
    }
  });
  /* Ctrl/Cmd+Enter publishes from the SEND face */
  on('cardBody', 'keydown', ev => {
    if (ev.key !== 'Enter' || ev.repeat || !(ev.ctrlKey || ev.metaKey)) return;
    if (faceUp() !== 'send') return;
    ev.preventDefault();
    publishCard();
  });
  /* Escape puts the card back.  Stopped here so nothing else in this page
   * (the refit docket's own Escape) also reacts. */
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

addEventListener('pagehide', () => {
  if (SES.connected) interact('disconnect', { client_id: CID, graceful: true });
});

function note() {
  /* KEEP THIS SHORT.  The toolbar is a fixed-height flex row: a long note
   * shrinks the buttons until their labels wrap, the buttons grow past 38 px
   * and overflow UPWARDS into the captured stage rect.  See index.html. */
  $('note').textContent =
    TRI + ' tris · ' + readouts.length + ' planes · ' + SES.patch + '/' +
    SES.retained + ' · ka ' + SES.keepalive.toFixed(0) + '°' +
    (SES.connected ? ' · line up' : running ? '' : ' · paused');
}

/* ===================================================================== M7 */
/* THE CAPTURE POSE.  Must equal export_mqb.py's POSE_* constants exactly, or
 * compare.py measures the state mismatch instead of the renderer. */
function poseForCapture() {
  /* Hide the title and rebuild plate.  They are screen-space chrome, same as
   * the mast: the Blender plates have none of it. */
  document.documentElement.classList.add('capture');
  if (refit) refit.pose();
  /* AND HIDE THE MAST, for exactly the same reason. */
  if (mast) mast.pose();
  hideType();
  running = false;
  poseGen++;
  if (SES.connected) interact('disconnect', { client_id: CID, graceful: true });
  SES.connected = false;
  SES.live = false;
  draining = statsBusy = false;
  /* the card goes back onto the will card, blank */
  CARD.want = CARD.k = 0;
  CARD.el.hidden = true;
  showFace('line');
  for (const id of ['cardPass', 'cardTopic', 'cardPayload']) $(id).value = '';
  $('cardKa').value = '30';
  $('cardQos').value = '0';
  $('cardRetain').checked = false;
  $('cardWillTopic').value = 'will/lost';
  traffic.length = 0; heard = 0; selJack = 0;
  setStatus('');
  const CP = S.capture_pose;
  seed = 20260902;
  SES.topics = P.patch.topics.slice();
  SES.clients = 7; SES.retain = 3; SES.will = WILLS[0].slice();
  SES.plugged = [false, false, false, false, false];
  SES.focus = 0; SES.keepAliveS = 30;
  WILL_IN.forEach((e, i) => { e.value = SES.will[i] || ''; });
  setPatch(CP.patch);
  setRetained(CP.retained);
  setScope(CP.scope);
  kaShown = CP.keepalive_deg;
  setKeepalive(CP.keepalive_deg);
  paintAll();
  paintLine();
  paintTraffic();
  note();
}

/* Module-specific MEASUREMENT hook.  Used only by the evidence captures in
 * NOTES.md -- nothing in the shipped page reads it.  It exists because two of
 * the numbers the brief asks for are A/B comparisons (materials.json on vs
 * off; and, for MQB alone, the parented-light size correction) and there is no
 * other way to make the same page render both. */
window.__mqb = {
  layout: () => layoutErr,
  /* trap 21.  There was no hook on this page before the port landed and the
   * integration pass had to record "facingAudit() no hook on this page". */
  facing: () => facingAudit(camera),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
  tris: TRI,
  ses: () => JSON.parse(JSON.stringify(SES)),
  card: (v, face) => {
    if (v !== undefined) { if (v) openCard(face); else closeCard(); }
    return { want: CARD.want, k: CARD.k, face: faceUp(), cid: CID,
             traffic: traffic.slice(), heard };
  },
  run: v => setRunning(v),
  matfix: v => { matFixOn = !!v; applyMatFix(); setRetained(SES.retained); },
  gain: (g) => { if (g !== undefined) setGain(+g); return GAIN; },
  bias: v => { DU.uBias.value = v; },
  /* 'world'   = the emitting square as it really is, L.data.size * the light
   *             object's world scale (MQB parents its four close lights to a
   *             root scaled 0.70, so the square is 0.70x smaller than
   *             L.data.size says and the radiance 1/0.49 higher).
   * 'blender' = L.data.size raw, which is what transliterate.lights_json()
   *             emits and what every unparented-light module gets. */
  lightMode: mode => {
    S.lights.forEach((L, i) => {
      const size = (mode === 'blender' && L.size_blender !== undefined)
        ? L.size_blender : L.size;
      const Ar = Math.max(1e-6, size * size);
      lights[i].userData.base = L.energy / (Ar * Math.PI);
      lights[i].intensity = lights[i].userData.base * GAIN;
      lights[i].width = lights[i].height = size;
    });
  },
};

/* THE RUN TOGGLE.  The theatre is paused at load (see `running` above) so the
 * page rests in scene.json -> capture_pose; this is how a human starts it. */
function setRunning(v) {
  running = !!v;
  const b = $('bRun');
  b.classList.toggle('on', running);
  b.textContent = running ? 'bus: running' : 'bus: paused';
  if (running) nextEvent = performance.now() + 2200;
  note();
}
$('bRun').addEventListener('click', () => setRunning(!running));

poseForCapture();
document.documentElement.classList.remove('capture');
/* The page a human opens is deliberately not the captured pose: the jacks
 * carry concrete topics, no cord is in until one is plugged, the retained
 * lamp is dark until something arrives, and the register waits for the
 * broker's own count. */
SES.topics = LIVE_TOPICS.slice();
syncPatchVisual();
setRetained('clear');
focusJack(0);
paintAll();
/* The refit port and the mast both show.  pose() hides them and the title;
 * that difference is reported, not failed. */
if (refit) refit.show(true);
mast.show(true);
layout();
note();
facingAudit(camera);
requestAnimationFrame(frame);
pollStats();
window.__loaded = true;
