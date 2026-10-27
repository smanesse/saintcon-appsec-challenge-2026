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
/* The iris fitting restarts this service only. It is not a grade. */
import { mountRefit } from '../../refit.js';
/* THE TELLTALE MAST.  live3d/mast.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> mast`, which
 * pipeline/status_mast.py wrote.  live3d/design/STATUS_AT_A_GLANCE.md section
 * 6 is the design; live3d/status.js is the one derivation both halves use. */
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'IPM';
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


/* IPM — "Optical Sensor Array / Photo Lab".  A pulled-down periscope head
 * bracketed to the starboard column, over the ship's darkroom.  It is the
 * /convert client: pick an output scope on the dial, fire the capture plunger,
 * watch the plate develop in the tray under the safelight, and the finished
 * plate drains down the brass chute stencilled TO FMM HOLD.
 *
 * LIVE (three glbs, 22 meshes — the page counts the triangles at runtime out
 * of the loaded index accessors and prints them in the toolbar):
 *   dial.glb     the SCOPE selector knob: brass hub, bar and the red index,
 *                turning about the panel's own normal.  The module ships this
 *                as one baked sprite spun in CSS; here it is real geometry, so
 *                the bar's own highlight turns with it.
 *   capture.glb  the capture plunger (rod, knob, band), which slides 20 mm
 *                down its barrel, and the EXPOSE lamp, which is a MATERIAL
 *                swap on real geometry because the control declares the pair
 *                (`mats: {off: ipm_red_off, on: ipm_red_on}`) — BRIEF step 2
 *                rule 3.
 *   tray.glb     the developing plate: 15 merged tile meshes over 8 frames.
 *                `kind: frames`, and here that really does mean N discrete
 *                meshes rather than PKT's "one set on a continuous parameter":
 *                a tile MIGRATES between three silver densities as it
 *                develops, so frame k and frame k+1 are different quad soups
 *                and there is nothing continuous to drive.  All 15 ship in one
 *                glb and visibility is toggled per frame.  Frame 0 is empty —
 *                an unexposed plate.
 *
 * BAKED: all 85 static objects plus the shell — the panel strips, both
 * aperture frames, the periscope head, the resolver tubes, the tray pan and
 * fluid and the ivory plate the tiles develop on, the safelight, the chute.
 *
 * DOM (three readout planes): `source`, `output` and `develop`.  IPM had NO
 * declared readout home at all — the audit's verdict is MARGINAL with "no
 * readout home decided" — so choosing them was the design work, and NOTES.md
 * section 3 is the argument.  Two of the three are genuinely occluded at rest:
 * the safelight (baked) crops `develop`, and the capture plunger's own knob
 * (LIVE) crops the bottom of `output` and clears it when the plunger is
 * pressed.
 *
 * NO VALUE GOES ON THE SCOPE DIAL'S FACE (BRIEF section 6, and the audit
 * measured it: bezel 40/121, pointer bar 13/121, hub 6/121, index 4/121).
 * Nothing on the array prints the selected scope — the dial's own index is
 * that readout.  The work order's FIT IN row is the same state as form fields.
 */

const P = S.props;
const V = a => new THREE.Vector3().fromArray(a);

/* ------------------------------------------------------------ M1: PROPS */
const KEYS = ['dial', 'capture', 'tray'];
const G = {};
{
  const loaded = await Promise.all(KEYS.map(k => load(A + P[k].glb)));
  KEYS.forEach((k, i) => { G[k] = loaded[i]; });
}
let liveTris = 0, liveMeshes = 0;
for (const k of KEYS)
  G[k].scene.traverse(o => {
    if (!o.isMesh) return;
    dress(o);
    liveMeshes++;
    const ix = o.geometry.index;
    liveTris += (ix ? ix.count : o.geometry.attributes.position.count) / 3;
  });
applyMatFix();

/* Which `patched` record belongs to which material, so a state swap updates the
 * record as well as the material.  Without it applyMatFix() would put the
 * ORIGINAL roughness/metalness back over a swapped lamp the next time the
 * materials.json A/B is toggled — silently, and only after a toggle.
 * (PKT's fix; kept verbatim because the failure is identical here.) */
const patchOf = new Map();
for (const rec of patched) patchOf.set(rec.m, rec);

/* Apply a Blender material BY NAME out of materials.json.  This is how a
 * `states` control changes material state: the module declares the pair
 * (`mats.off` / `mats.on`) and the exporter writes their NAMES, so the frontend
 * never invents a colour.  It MUTATES the material dress() already cloned per
 * mesh and already put through attachDepthTest + attachForeground, so the split
 * is untouched — cloning a fresh material here would produce an UNATTACHED one
 * that draws in both passes and double-blends (BRIEF trap 15). */
function setMat(mesh, name) {
  const rec = MJ[name];
  const m = mesh && mesh.material;
  if (!rec || !m) return;
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
  const p = patchOf.get(m);
  if (p) p.rec = rec;
  m.roughness = rec.rough;
  m.metalness = rec.metallic;
}

/* every glb is exported in WORLD coordinates, so re-parenting a named object
 * into a group that starts at the identity keeps it exactly where it was. */
function pick(g, names) {
  return names.map(n => g.scene.getObjectByName(n)).filter(Boolean);
}

/* the SCOPE knob turns about the panel's own normal through the hub the
 * module declares (`ctrl.dial.anchor`). */
const dial = pivotAt(P.dial.hub);
dial.inner.add(G.dial.scene);

/* the plunger slides; the EXPOSE lamp does not, so it stays in the glb's own
 * scene and only its material changes. */
scene.add(G.capture.scene);
const plunger = new THREE.Group();
scene.add(plunger);
for (const o of pick(G.capture, P.capture.plunger)) plunger.add(o);
const lamp = G.capture.scene.getObjectByName(P.capture.lamp);

/* the tray: one glb, 15 meshes, one NAME LIST per frame.  A name that fails to
 * resolve is otherwise completely silent — the frame simply renders empty — so
 * window.__ipm.rig() reports how many of each frame's names were found. */
scene.add(G.tray.scene);
const trayFrames = P.tray.frame_nodes.map(ns => pick(G.tray, ns));
const trayAll = pick(G.tray, P.tray.nodes);

/* Retrieved plate, stood off above the live develop tiles. Hidden at rest and
 * during pose() so checkers stay on the exported theatre. */
let photoMesh = null, photoMat = null, photoTex = null;

/* IPM has NO rake: slots.pillar() aims the slot's local +Z at the pilot and the
 * working face IS the slot plane (the survey says `face helper : NONE`), so
 * there is no cone to sweep and the dial's axis is the root's own +Z.  It is
 * emitted NEGATED, MQB's convention, so a POSITIVE angle is CLOCKWISE on
 * screen — the direction build.py's own detents run (tick i sits at
 * (sin th, cos th), i.e. the up vector turned by −th about +Z).  The sign is
 * checked in the exporter against gt_dial_p062.png. */
const SPIN = V(S.panel.spin_axis).normalize();
const UPAX = V(P.capture.axis).normalize();

/* the developing plate's own rect, which is where the print rests */
let TRAY_REST = null;
function mountTrayPhoto() {
  const n = V(PLANES[0].n).normalize();
  const u = V(PLANES[0].u).normalize();
  const v = V(PLANES[0].v).normalize();
  const box = new THREE.Box3();
  const vis = trayAll.map(o => o.visible);
  for (const o of trayAll) {
    o.visible = true;
    o.updateWorldMatrix(true, true);
    box.expandByObject(o);
  }
  vis.forEach((vv, i) => { trayAll[i].visible = vv; });
  if (box.isEmpty()) return;
  const c = box.getCenter(new THREE.Vector3());
  c.addScaledVector(n, 0.0008);
  const corners = [
    new THREE.Vector3(box.min.x, box.min.y, box.min.z),
    new THREE.Vector3(box.min.x, box.min.y, box.max.z),
    new THREE.Vector3(box.min.x, box.max.y, box.min.z),
    new THREE.Vector3(box.min.x, box.max.y, box.max.z),
    new THREE.Vector3(box.max.x, box.min.y, box.min.z),
    new THREE.Vector3(box.max.x, box.min.y, box.max.z),
    new THREE.Vector3(box.max.x, box.max.y, box.min.z),
    new THREE.Vector3(box.max.x, box.max.y, box.max.z),
  ];
  let umin = Infinity, umax = -Infinity, vmin = Infinity, vmax = -Infinity;
  for (const p of corners) {
    const d = p.clone().sub(c);
    const du = d.dot(u), dv = d.dot(v);
    if (du < umin) umin = du; if (du > umax) umax = du;
    if (dv < vmin) vmin = dv; if (dv > vmax) vmax = dv;
  }
  const w = Math.max(0.04, umax - umin);
  const h = Math.max(0.03, vmax - vmin);
  TRAY_REST = { c: c.clone(), w, h };
  photoMat = new THREE.MeshStandardMaterial({
    color: 0xffffff, metalness: 0, roughness: 1,
  });
  photoMesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), photoMat);
  photoMesh.position.copy(c);
  photoMesh.quaternion.setFromRotationMatrix(
    new THREE.Matrix4().makeBasis(u, v, n));
  photoMesh.visible = false;
  attachDepthTest(photoMat);
  attachForeground(photoMat);
  scene.add(photoMesh);
}
mountTrayPhoto();

/* per-plane ink, from the exporter's own measurement of Blender's render */
const RO = {};
readouts.forEach((r, i) => {
  const tp = PLANES[i];
  RO[tp.name] = r;
  if (tp.ink) r.el.style.color = 'rgb(' + tp.ink.join(',') + ')';
});
const COLS = {};
for (const tp of PLANES) COLS[tp.name] = (tp.type && tp.type.n_cols) || 24;

$('note').textContent =
  Math.round(liveTris) + ' tris · ' + liveMeshes + ' meshes · ' +
  S.lights.length + ' lights · ' + PLANES.length + ' planes';

/* ------------------------------------------- M2: THE SESSION MODEL
 * IPM is an HTTP image converter and this station is its client.  Every
 * control on the array and every field on the work order is one part of the
 * request IPM actually receives:
 *
 *   SOURCE    the endpoint and its body.  A built-in sample or an uploaded
 *             file goes to POST /convert as the multipart `image`; a URL goes
 *             to POST /convert-url and IPM downloads it itself; a zip goes to
 *             POST /convert-batch as the multipart `archive`.
 *   SCOPE     the dial.  256 / 512 / 1K set `width` and `height`; SVG loads
 *             the built-in SVG sample; ZIP switches to the batch endpoint.
 *   OUTPUT    `format` and `name`, the file IPM STORs into FMM.  A blank name
 *             lets IPM mint img_<hex>.png.
 *   CAPTURE   sends it.  IPM converts, STORs into FMM, and the bridge reads
 *             the result back through GET /image/{name}.  That picture is the
 *             one that develops in the tray.
 *
 * The work order (#ipm-bench) renders the same `st` as form fields, so the
 * dial, the plunger, the readouts and the panel cannot disagree.  Every value
 * that came from the service is written with textContent. */
const SCOPES = S.scopes;                       // from build.py, not hardcoded
/* The bridge's built-in sources (bridge/interactors.py _IPM_PLATES).  The
 * four plates are tiny test PNGs; the SVG is the metadata-path sample. */
const SAMPLES = [
  { key: 'ngc7293', name: 'NGC7293.PNG' },
  { key: 'helix-02', name: 'HELIX-02.PNG' },
  { key: 'm87-core', name: 'M87-CORE.PNG' },
  { key: 'crab-n1', name: 'CRAB-N1.PNG' },
  { key: 'svg', name: 'DRAWING.SVG' },
];
const SVG_SAMPLE = SAMPLES.length - 1;
const SIZES = { '256': 256, '512': 512, '1K': 1024 };
const SCOPE_SVG = SCOPES.indexOf('SVG');
const SCOPE_ZIP = SCOPES.indexOf('ZIP');
const DEV_FRAMES = P.tray.frames;
const MAX_UPLOAD = 8 * 1024 * 1024;
const HISTORY_MAX = 8;

const st = {
  scope: S.pose.dial,          // dial detent index
  capture: S.pose.capture,     // 'armed' | 'capture'
  dev: 0,                      // 0 .. DEV_FRAMES-1
  phase: 'ready',              // ready | expose | develop | fixed
  run: false,                  // is the develop CLOCK running?
  t: 0,
  restText: false,             // pose(): paint scene.json's readout_text
  /* the request */
  mode: 'sample',              // sample | upload | url | zip
  plate: 0,                    // index into SAMPLES
  upload: null,                // { name, b64, bytes } for POST /convert
  archive: null,               // { name, b64, bytes } for POST /convert-batch
  url: '',
  width: '', height: '',
  format: '',
  outName: '',
  /* the reply */
  pending: false,
  job: 0,
  jobEnv: null,
  sent: null,                  // the spec of the request in flight / last sent
  reply: null,                 // { spec, env } of the last convert
  replyVer: 0,
  storedName: null,
  bytes: null,
  retrievable: false,
  stored: null,
  svg: null,
  err: null,
  count: null,
  storedN: null,
  hasPhoto: false,
  /* GET /image/{name} */
  fetchJob: 0,
  fetching: null,
  fetched: null,               // { name, env }
  fetchVer: 0,
  history: [],                 // names stored this session, newest first
  print: null,                 // { name, r, label }: the last picture back
  printVer: 0,
  status: { text: '', kind: '' },  // the work order's one-line status
  health: null,                // null | 'up' | 'down' | 'unreachable'
};

/* Shared coordinator. Same origin `/api/interact` only — never :8080, never
 * a second client file. Never throws: offline / 4xx land on `develop`. */
async function interact(action, params) {
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'IPM', action, params: params || {} }),
    });
    let j = {};
    try { j = await r.json(); }
    catch (_) { j = { ok: false, error: 'non-JSON' }; }
    const result = (j.result && typeof j.result === 'object') ? j.result : j;
    const error = result.error || j.error || (r.ok ? null : ('HTTP ' + r.status));
    const ok = !!(r.ok && j.ok !== false && result.ok !== false);
    return { ok, reachable: true, result, error };
  } catch (e) {
    return { ok: false, reachable: false, result: {},
             error: String((e && e.message) || e) };
  }
}

function checkHealth() {
  interact('health').then(env => {
    st.health = !env.reachable ? 'unreachable' : (env.ok ? 'up' : 'down');
    paintAll();
  });
}

/* ---- dial <-> panel.  The dial is a coarse view of the same state. */
function applyScope(k) {
  st.scope = k;
  const s = SCOPES[k];
  if (k === SCOPE_ZIP) st.mode = 'zip';
  else if (k === SCOPE_SVG) { st.mode = 'sample'; st.plate = SVG_SAMPLE; }
  else if (SIZES[s]) {
    st.width = st.height = String(SIZES[s]);
    if (st.mode === 'zip') st.mode = 'sample';
    if (st.mode === 'sample' && st.plate === SVG_SAMPLE) st.plate = 0;
  }
}
function scopeFromPanel() {
  if (st.mode === 'zip') return SCOPE_ZIP;
  if (st.mode === 'sample' && st.plate === SVG_SAMPLE) return SCOPE_SVG;
  for (let i = 0; i < SCOPES.length; i++) {
    const n = SIZES[SCOPES[i]];
    if (n && st.width === String(n) && st.height === String(n)) return i;
  }
  /* a custom size has no detent: leave the dial on a size stop */
  return (st.scope === SCOPE_SVG || st.scope === SCOPE_ZIP)
    ? SCOPES.indexOf('512') : st.scope;
}

/* A new source or scope is a new job: the tray goes back to an unexposed
 * plate.  The panel keeps showing the last response until the next one. */
function clearJob() {
  st.restText = false;
  st.phase = 'ready';
  st.dev = 0;
  st.run = false;
  st.pending = false;
  st.job += 1;
  st.err = null;
  st.stored = null;
  st.storedName = null;
  st.bytes = null;
  st.retrievable = false;
  st.svg = null;
  st.count = null;
  st.storedN = null;
  hideTrayPhoto();
}
function onSourceChanged() {
  st.scope = scopeFromPanel();
  clearJob();
  paintAll();
  applyControls();
}

/* ---- the request */
function convertSpec() {
  const p = {};
  if (st.mode === 'zip') {
    if (st.archive) { p.archive_b64 = st.archive.b64; p.filename = st.archive.name; }
    else p.source = 'deck';
    return { action: 'convert-batch', params: p };
  }
  if (st.width) p.width = st.width;
  if (st.height) p.height = st.height;
  if (st.format) p.format = st.format;
  if (st.outName) p.name = st.outName;
  if (st.mode === 'url') {
    p.url = st.url;
    return { action: 'convert-url', params: p };
  }
  if (st.mode === 'upload' && st.upload) {
    p.image_b64 = st.upload.b64;
    p.filename = st.upload.name;
  } else {
    p.source = SAMPLES[st.plate].key;
  }
  return { action: 'convert', params: p };
}
function sendBlocker() {
  if (st.mode === 'upload' && !st.upload) return 'CHOOSE A FILE';
  if (st.mode === 'url' && !st.url.trim()) return 'TYPE A URL';
  return null;
}
/** What IPM will see, in the order the bridge builds the query string. */
function requestLines(spec) {
  const p = spec.params;
  const q = ['width', 'height', 'format', 'name', 'url']
    .filter(k => p[k] != null && p[k] !== '')
    .map(k => k + '=' + encodeURIComponent(p[k]));
  const line = 'POST /' + spec.action + (q.length ? '?' + q.join('&') : '');
  let body;
  if (spec.action === 'convert-url')
    body = 'no body: IPM downloads the URL itself';
  else if (spec.action === 'convert-batch')
    body = 'archive = ' + (st.archive
      ? st.archive.name + ' (' + fmtBytes(st.archive.bytes) + ')'
      : 'plates.zip (the four sample plates)');
  else if (st.mode === 'upload' && st.upload)
    body = 'image = ' + st.upload.name + ' (' + fmtBytes(st.upload.bytes) + ')';
  else
    body = 'image = ' + SAMPLES[st.plate].name + ' (built-in sample)';
  return [line, body];
}

function fireConvert() {
  const id = ++st.job;
  st.pending = true;
  st.jobEnv = null;
  const spec = convertSpec();
  st.sent = spec;
  interact(spec.action, spec.params).then(env => {
    if (id !== st.job) return;
    st.jobEnv = env;
    st.pending = false;
    if (st.phase === 'expose' && st.t >= EXPOSE_S)
      applyConvertResult(env);
  });
}

/* The capture plunger and the panel's SEND button are the same control. */
function pressCapture() {
  if (st.phase === 'expose' || st.pending) return;
  st.restText = false;
  const bad = sendBlocker();
  if (bad) {
    clearJob();
    st.err = bad;
    setStatus(bad === 'CHOOSE A FILE' ? 'Choose a file to upload first.' : 'Type the URL for IPM to fetch first.', 'err');
    paintAll();
    applyControls();
    focusPanel('source');
    return;
  }
  st.capture = 'capture';
  st.phase = 'expose';
  st.run = true;
  st.t = 0;
  st.dev = 0;
  st.err = null;
  st.svg = null;
  st.count = null;
  st.storedN = null;
  st.stored = null;
  st.storedName = null;
  st.bytes = null;
  st.retrievable = false;
  hideTrayPhoto();
  applyMaterials();
  fireConvert();
  setStatus(requestLines(st.sent)[0] + '  …', 'busy');
  paintAll();
}

function rasterMagic(hex) {
  if (!hex) return false;
  const h = String(hex).toLowerCase();
  return h.startsWith('89504e47') || h.startsWith('ffd8ff') || h.startsWith('47494638');
}
function hasPicture(r) {
  return !!(r && r.retrievable && r.image_b64 && rasterMagic(r.magic)
    && (!r.content_type || String(r.content_type).indexOf('image/') === 0));
}

function hideTrayPhoto() {
  st.hasPhoto = false;
  if (photoMesh) photoMesh.visible = false;
  if (photoMat) { photoMat.map = null; photoMat.needsUpdate = true; }
}

function setTrayPhoto(b64, mime) {
  if (!b64 || !photoMat) { hideTrayPhoto(); return; }
  const img = new Image();
  img.onload = () => {
    if (photoTex) { photoTex.dispose(); photoTex = null; }
    photoTex = new THREE.Texture(img);
    photoTex.colorSpace = THREE.SRGBColorSpace;
    photoTex.needsUpdate = true;
    photoMat.map = photoTex;
    photoMat.needsUpdate = true;
    st.hasPhoto = true;
    applyControls();
  };
  img.onerror = () => { hideTrayPhoto(); };
  const ct = (mime && String(mime).indexOf('image/') === 0) ? mime : 'image/png';
  img.src = 'data:' + ct + ';base64,' + b64;
}

function remember(name) {
  if (!name) return;
  const n = String(name);
  st.history = [n].concat(st.history.filter(x => x !== n)).slice(0, HISTORY_MAX);
}

function startDevelop() {
  st.phase = 'develop';
  st.dev = 0;
  st.t = 0;
  st.run = true;
}

function applyConvertResult(env) {
  st.pending = false;
  const r = (env && env.result) || {};
  st.reply = { spec: st.sent, env: env || { ok: false, reachable: false, result: {}, error: 'NO RESULT' } };
  st.replyVer++;
  if (env) st.health = !env.reachable ? 'unreachable' : st.health;
  if (!env || !env.ok) {
    st.phase = 'ready';
    st.run = false;
    st.stored = null;
    st.storedName = null;
    st.bytes = null;
    st.retrievable = false;
    st.svg = null;
    st.count = null;
    st.storedN = null;
    hideTrayPhoto();
    st.err = (env && (env.error || r.error)) || 'OFFLINE';
    const what = st.sent ? 'POST /' + st.sent.action + ': ' : '';
    setStatus(!env || !env.reachable ? 'No answer from the bridge: ' + st.err
      : what + st.err + (r.body ? '  ' + String(r.body).slice(0, 160) : ''), 'err');
    paintAll();
    applyControls();
    openOrder();
    return;
  }
  st.err = r.storeError ? String(r.storeError)
    : (r.convertError ? String(r.convertError)
      : (r.stored === false ? 'NOT STORED' : null));
  if (!st.err && r.stored && !r.retrievable)
    st.err = 'HTTP ' + (r.retrieve_status || 404);
  st.stored = r.stored;
  st.storedName = r.name || null;
  st.bytes = (typeof r.bytes === 'number') ? r.bytes : null;
  st.retrievable = !!r.retrievable;
  st.svg = r.svg || null;
  st.count = (typeof r.count === 'number') ? r.count : null;
  st.storedN = (typeof r.stored_n === 'number') ? r.stored_n : null;
  if (Array.isArray(r.results)) {
    for (let i = r.results.length - 1; i >= 0; i--)
      if (r.results[i] && r.results[i].stored) remember(r.results[i].name);
  } else if (r.stored) {
    remember(r.name);
  }
  if (hasPicture(r)) setTrayPhoto(r.image_b64, r.content_type);
  else hideTrayPhoto();
  st.print = { name: r.name || null, r, label: 'POST /' + (st.sent ? st.sent.action : 'convert') };
  st.printVer++;
  setStatus(r.summary || (st.err ? st.err : 'OK'), st.err ? 'err' : 'ok');
  if (st.err) openOrder();
  startDevelop();
  paintAll();
  applyControls();
}

/* GET /image/{name}: pull a stored file back out of the FMM hold and develop
 * it in the tray, without converting anything. */
function fetchStored(name) {
  name = String(name || '').trim();
  if (!name) return;
  st.restText = false;
  const id = ++st.fetchJob;
  st.fetching = name;
  paintAll();
  interact('image', { name }).then(env => {
    if (id !== st.fetchJob) return;
    st.fetching = null;
    st.fetched = { name, env };
    st.fetchVer++;
    const r = env.result || {};
    setStatus(env.ok ? 'GET /image/' + name + '  ' + retrLine(r)
      : 'GET /image/' + name + ': ' + (env.error || 'not found'), env.ok ? 'ok' : 'err');
    if (env.ok) {
      remember(name);
      st.print = { name, r, label: 'GET /image/' + name };
      st.printVer++;
      if (!st.pending && st.phase !== 'expose') {
        st.job += 1;
        st.err = null;
        st.stored = true;
        st.storedName = name;
        st.bytes = (typeof r.byte_length === 'number') ? r.byte_length : null;
        st.retrievable = true;
        st.svg = null;
        st.count = null;
        st.storedN = null;
        if (hasPicture(r)) setTrayPhoto(r.image_b64, r.content_type);
        else hideTrayPhoto();
        startDevelop();
      }
    }
    paintAll();
    applyControls();
  });
}

function fmtKB(kb) {
  return (kb >= 100 ? kb.toFixed(0) : kb.toFixed(1)) + ' KB';
}
function fmtBytes(n) {
  if (typeof n !== 'number') return '?';
  return n < 1024 ? n + ' B' : fmtKB(n / 1024);
}

/* ---- the three readouts on the array */
function sourceLine() {
  if (st.mode === 'upload') return st.upload ? st.upload.name : 'NO FILE CHOSEN';
  if (st.mode === 'url') return st.url || 'NO URL';
  if (st.mode === 'zip') return st.archive ? st.archive.name : 'PLATES.ZIP  4 PLATES';
  return SAMPLES[st.plate].name + '  SAMPLE';
}
function outputLine() {
  if (st.bytes != null && (st.phase === 'develop' || st.phase === 'fixed'))
    return 'OUT ' + fmtKB(st.bytes / 1024);
  return 'OUT ------';
}
function developLine() {
  if (st.err && (st.phase === 'ready' || st.phase === 'expose'))
    return st.err;
  if (st.phase === 'ready') return 'PLATE ARMED';
  if (st.phase === 'expose' || st.pending) return 'EXPOSING PLATE';
  if (st.phase === 'develop')
    /* a PERCENTAGE, not "k of 8".  The tray has DEV_FRAMES=8 tile sets and
     * frame 0 is an unexposed plate, so "6/8" and "6/7" are both wrong by one
     * in one direction or the other and the exporter and the page would have
     * to agree on which. */
    return 'DEVELOPING PLATE '
      + Math.round(100 * st.dev / (DEV_FRAMES - 1)) + '%';
  if (st.svg && st.svg.text)
    return String(st.svg.text);
  if (st.svg)
    return 'SVG ' + (st.svg.width || '?') + 'x' + (st.svg.height || '?')
      + (st.stored ? ' STORED' : (st.err ? (' ' + st.err) : ''));
  if (st.count != null)
    return 'BATCH ' + (st.storedN || 0) + '/' + st.count
      + (st.stored ? ' STORED' : '');
  if (st.stored === false) return st.err || 'NOT STORED';
  if (st.stored && !st.retrievable) return st.err || 'NOT RETRIEVED';
  if (st.storedName) return 'FIXED  ' + st.storedName;
  return 'FIXED  STORED TO FMM';
}
/** Every readout is clipped to its own plane's column count.  That is LAYOUT,
 *  not safety: the safety is textContent.  The column count is the exporter's,
 *  measured off the carrier's geometry, so the page carries no second copy. */
function clip(name, s) {
  return String(s).slice(0, COLS[name]);
}
function paintAll() {
  if (st.restText) {
    /* pose(): the exact strings export_ipm.py rendered gt_platen0.png and
     * gt_full_read.png from, so the page and the ground truth cannot drift. */
    const want = S.readout_text || [];
    PLANES.forEach((tp, i) => RO[tp.name].paint((want[i] || []).map(String)));
  } else {
    /* the order is in the hand while it is up: its rail is blank */
    RO.source.paint([orderUp() ? '' : clip('source', sourceLine())]);
    RO.output.paint([clip('output', outputLine())]);
    RO.develop.paint([clip('develop', developLine())]);
  }
  renderPanel();
  syncOrderTab();
}

function syncOrderTab() {
  const b = $('bOrder');
  if (!b) return;
  const up = ORDER.want > 0;
  b.hidden = frozen;
  b.classList.toggle('on', up);
  b.setAttribute('aria-expanded', up ? 'true' : 'false');
}

function resetSession(posed) {
  st.scope = S.pose.dial;
  st.capture = S.pose.capture;
  st.mode = 'sample';
  st.plate = 0;
  st.upload = null;
  st.archive = null;
  st.url = '';
  st.format = '';
  st.outName = '';
  applyScope(st.scope);
  clearJob();
  st.jobEnv = null;
  st.sent = null;
  st.reply = null;
  st.replyVer++;
  st.fetchJob++;
  st.fetching = null;
  st.fetched = null;
  st.fetchVer++;
  st.history = [];
  st.print = null;
  st.printVer++;
  st.status = { text: '', kind: '' };
  if (ui.status) setStatus('', '');
  if (posed) {
    /* the capture pose: mid-develop, six frames into eight */
    st.restText = true;
    st.phase = 'develop';
    st.dev = S.pose.tray;
  }
  if (document.activeElement && document.activeElement.blur)
    document.activeElement.blur();
  if (ui.file) ui.file.value = '';
  if (ui.zip) ui.zip.value = '';
}

/* ---------------------------------------------- M3: STATE -> GEOMETRY */
function detentDeg(i) {
  const r = P.dial.range;
  return r[0] + (r[1] - r[0]) * i / (P.dial.detents.length - 1);
}
/* the eased values the frame loop drives towards the state above */
const an = { deg: detentDeg(S.pose.dial), drop: 0 };

function applyControls() {
  dial.pivot.quaternion.setFromAxisAngle(SPIN, an.deg * D2R);
  /* build.py's set: slider.location = (0, travel, 0), travel = -0.020, so the
   * plunger rides the face's own +v by travel x drop. */
  plunger.position.copy(UPAX).multiplyScalar(P.capture.travel_m * an.drop);
  /* the plate shows the picture once fixed, unless the print is out of it */
  const showPhoto = !frozen && photoMesh && st.hasPhoto && st.phase === 'fixed' && !printUp();
  if (photoMesh) photoMesh.visible = !!showPhoto;
  /* a print out of the tray leaves it empty: frame 0 is the unexposed plate */
  const out = !frozen && printUp() && st.phase === 'fixed';
  for (let f = 0; f < trayFrames.length; f++)
    for (const o of trayFrames[f]) o.visible = showPhoto ? false : (f === (out ? 0 : st.dev));
}
function applyMaterials() {
  setMat(lamp, P.capture.lamp_mats[st.capture === 'capture' ? 'on' : 'off']);
}

/* ------------------------------------------------------ M4: ANIMATION */
let frozen = false;               // set by pose(): the capture must be still
let dragging = null;
const EXPOSE_S = 0.30;            // shutter open
const DEV_S = 2.4;                // the whole develop, 0 -> DEV_FRAMES-1

function step(cur, want, dt, rate) {
  return cur + (want - cur) * Math.min(1, dt * rate);
}

/* THE TELLTALE MAST.  Mounted below in M5, after this page's own `hotspot()`
 * helper exists; declared here because onFrame() and poseForCapture() reach
 * it and both are defined before the mount.  pose() hides the mast and the
 * screen chrome so a capture stays on the exported theatre. */
let mast = null;
let refit = null;

function hideCaptureChrome() {
  dropHeld();
  for (const id of ['module-title', 'bTutorial', 'bOrder']) {
    const n = document.getElementById(id);
    if (n) n.hidden = true;
  }
}

function onFrame(dt, now) {
  /* ABOVE THE `frozen` GATE, not below it.  The fittings own no timer of
   * their own, so the iris and the mast animate off this call.  Below the
   * gate they would freeze the instant `pose()` ran.  `pose()` stills them
   * for a capture by hiding them. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  tickHeld(dt);
  if (frozen) return;
  if (!dragging) an.deg = step(an.deg, detentDeg(st.scope), dt, 9);
  an.drop = step(an.drop, st.capture === 'capture' ? 1 : 0, dt, 16);

  if (!st.run) { applyControls(); return; }
  if (st.phase === 'expose') {
    st.t += dt;
    if (st.t >= EXPOSE_S && st.capture === 'capture') {
      st.capture = 'armed';                 // the plunger springs back
      applyMaterials();
    }
    if (st.t >= EXPOSE_S && !st.pending) {
      applyConvertResult(st.jobEnv);
    }
  } else if (st.phase === 'develop') {
    st.t += dt;
    const k = Math.min(DEV_FRAMES - 1,
                       Math.floor((st.t / DEV_S) * (DEV_FRAMES - 1)));
    if (k !== st.dev) { st.dev = k; paintAll(); }
    if (st.t >= DEV_S) {
      st.dev = DEV_FRAMES - 1;
      st.phase = 'fixed';
      st.run = false;
      st.t = 0;
      if (st.stored) openPrint();        // the finished print lifts out of the tray
      paintAll();
    }
  }
  applyControls();
}

/* ---------------------------------------------------- M5: INTERACTION */
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
  d.title = title;                        // textContent-safe: no markup
  d.addEventListener('pointerdown', ev => { frozen = false; onDown(ev, d); });
  $('hots').appendChild(d);
  return d;
}
function drag(el, ev, move) {
  el.setPointerCapture(ev.pointerId);
  const up = () => {
    dragging = null;
    if (typeof move.settle === 'function') move.settle();
    el.removeEventListener('pointermove', move);
    el.removeEventListener('pointerup', up);
    el.removeEventListener('pointercancel', up);
  };
  el.addEventListener('pointermove', move);
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', up);
}

/* the SCOPE dial: angular drag about its PROJECTED hub, snapping to the
 * nearest engraved detent on release.  Screen y runs down, so a clockwise drag
 * is a positive screen angle and a positive angle about `spin_axis`. */
hotspot(P.dial.hotspot, P.dial.label + ' — output size, SVG sample, or ZIP batch', (ev, el) => {
  const hub = P.dial.pivot_px;
  const ang = pt => Math.atan2(pt.x - hub.x, hub.y - pt.y) / D2R;
  const lo = P.dial.range[0], hi = P.dial.range[1];
  dragging = true;
  const move = e2 => {
    an.deg = Math.max(lo, Math.min(hi, ang(stagePt(e2))));
    const f = (an.deg - lo) / (hi - lo);
    const k = Math.round(f * (P.dial.detents.length - 1));
    if (k !== st.scope) {
      applyScope(k);
      /* re-scoping starts a new job: the resolver has to run again */
      clearJob();
      paintAll();
    }
    applyControls();
  };
  move.settle = () => { an.deg = detentDeg(st.scope); applyControls(); };
  move(ev);
  drag(el, ev, move);
});

/* the CAPTURE plunger: press it and the request goes out. */
hotspot(P.capture.hotspot, P.capture.label + ' — send the request to IPM', () => {
  pressCapture();
});

/* the DEVELOPING TRAY: build.py declares `axis: "y"` on this control and its
 * own demo scrubs the frame on a VERTICAL drag, so this does the same rather
 * than inferring the axis from the hotspot's shape. */
hotspot(P.tray.hotspot, P.tray.label + ' — click: lift the print; drag: scrub the develop', (ev, el) => {
  dragging = true;
  const r = P.tray.hotspot;
  const y0 = stagePt(ev).y;
  let scrubbing = false;
  const move = e2 => {
    const p = stagePt(e2);
    if (!scrubbing && Math.abs(p.y - y0) < 4) return;
    scrubbing = true;
    const f = Math.max(0, Math.min(1, (p.y - r.y) / r.h));
    const k = Math.round(f * (DEV_FRAMES - 1));
    if (k !== st.dev) {
      st.restText = false;
      st.dev = k;
      st.phase = (k >= DEV_FRAMES - 1) ? 'fixed' : 'develop';
      st.run = false;                 // a hand on the tray stops the clock
      st.t = (k / (DEV_FRAMES - 1)) * DEV_S;
      paintAll();
      applyControls();
    }
  };
  move.settle = () => { if (!scrubbing && (st.print || st.history.length)) openPrint(); };
  drag(el, ev, move);
});

/* the periscope head: cycle the built-in samples.  It has no control in the
 * module's manifest, so this is a hotspot over the drum rather than a declared
 * one. */
hotspot(S.head.hotspot, S.head.label + ' — load the next sample', () => {
  st.plate = st.mode === 'sample' ? (st.plate + 1) % SAMPLES.length : 0;
  st.mode = 'sample';
  onSourceChanged();
});

function planeRect(tp) {
  const c = tp.corners_px;
  const xs = [c.tl.x, c.tr.x, c.bl.x, c.br.x];
  const ys = [c.tl.y, c.tr.y, c.bl.y, c.br.y];
  const x = Math.min(...xs), y = Math.min(...ys);
  return { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y };
}

/* The SOURCE and OUTPUT rails are labels for panel fields: a click jumps to
 * the field that sets them. */
{
  const tpS = PLANES.find(p => p.name === 'source');
  const tpO = PLANES.find(p => p.name === 'output');
  if (tpS && tpS.corners_px) {
    const h = hotspot(planeRect(tpS), 'SOURCE — pick up the work order', ev => {
      ev.preventDefault();
      focusPanel('source');
    });
    h.classList.add('well');
  }
  if (tpO && tpO.corners_px) {
    const h = hotspot(planeRect(tpO), 'OUTPUT — pick up the work order', ev => {
      ev.preventDefault();
      focusPanel('output');
    });
    h.classList.add('well');
  }
}

/* ---- HELD PAPER ------------------------------------------------------------
 * The station's UI lives on the array, not beside it (FMM's manifest sheet and
 * cargo slip are the pattern).  Two DOM cards in a second CSS3D layer, laid on
 * the panel's own basis (every IPM plane shares one u / v / n):
 *
 *   WORK ORDER (#ipm-bench)  the request.  At rest it is exactly the SOURCE
 *                            rail; picked up, it eases toward the camera left
 *                            of the column.  While it is up the rail paints
 *                            blank: the order is in the hand.
 *   PRINT (#ipmPrint)        the reply.  At rest it is exactly the developing
 *                            plate; when a develop finishes it lifts out of the
 *                            tray, right of the column, and the tray is empty
 *                            while it is up.  It also carries the FMM HOLD
 *                            ledger for reading stored files back.
 *
 * `k` runs 0..1, rest to held; onFrame() eases it toward `want` through
 * tickHeld().  No timers.  Lifted paper is in front of all geometry, so it
 * needs no occlusion split and declares no readout plane.  Plain DOM and
 * textContent only. */
const ui = {};
function mk(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
function textInput(placeholder) {
  const i = mk('input');
  i.type = 'text';
  i.spellcheck = false;
  i.autocomplete = 'off';
  if (placeholder) i.placeholder = placeholder;
  return i;
}
function fieldRow(label, ...controls) {
  const row = mk('label', 'prow');
  row.appendChild(mk('span', 'pk', label));
  const cell = mk('div', 'cell');
  for (const c of controls) cell.appendChild(c);
  row.appendChild(cell);
  return row;
}
function setVal(inp, v) {
  if (document.activeElement !== inp && inp.value !== v) inp.value = v;
}
function readFile(input, kind) {
  const f = input.files && input.files[0];
  if (!f) return;
  if (f.size > MAX_UPLOAD) {
    input.value = '';
    clearJob();
    st.err = 'FILE OVER 8 MB';
    setStatus('That file is over 8 MB.', 'err');
    paintAll();
    return;
  }
  const rd = new FileReader();
  rd.onload = () => {
    const s = String(rd.result || '');
    const rec = { name: f.name, b64: s.slice(s.indexOf(',') + 1), bytes: f.size };
    if (kind === 'zip') st.archive = rec;
    else st.upload = rec;
    onSourceChanged();
  };
  rd.onerror = () => { clearJob(); st.err = 'COULD NOT READ FILE'; paintAll(); };
  rd.readAsDataURL(f);
}

const held = new CSS3DLayer($('held'), W, H);
const SRC = PLANES.find(p => p.name === 'source') || PLANES[0];
const PU = V(SRC.u).normalize();
const PV = V(SRC.v).normalize();
const PN = V(SRC.n).normalize();
const ORDER = { el: $('ipm-bench'), w: 500, h: 500, k: 0, want: 0,
                at: { x: 290, y: 340, w: 430 } };
const PRINT = { el: $('ipmPrint'), w: 420, h: 560, k: 0, want: 0,
                at: { x: 990, y: 360, w: 360 } };
ORDER.rec = held.add(ORDER.el);
PRINT.rec = held.add(PRINT.el);

/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the SOURCE rail's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = camera.position.distanceTo(V(SRC.origin)) * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  const m = at.w * perPx / elW;
  return { o, mx: m, my: m };
}
const ORDER_REST = { o: V(SRC.origin), mx: 2 * SRC.half_w / ORDER.w, my: 2 * SRC.half_h / ORDER.h };
const PRINT_REST = TRAY_REST
  ? { o: TRAY_REST.c.clone(), mx: TRAY_REST.w / PRINT.w, my: TRAY_REST.h / PRINT.h }
  : { o: V(SRC.origin), mx: 0.02 / PRINT.w, my: 0.02 / PRINT.h };
const ORDER_UP = heldPose(ORDER.at, ORDER.w, 0.86);
const PRINT_UP = heldPose(PRINT.at, PRINT.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function placeHeld(P_, rest, up) {
  const e = ease(P_.k);
  const o = rest.o.clone().lerp(up.o, e);
  const mx = rest.mx + (up.mx - rest.mx) * e;
  const my = rest.my + (up.my - rest.my) * e;
  P_.rec.matrix = new THREE.Matrix4().makeBasis(
    PU.clone().multiplyScalar(mx), PV.clone().multiplyScalar(my), PN).setPosition(o);
}
function tickHeld(dt) {
  let moved = false;
  for (const P_ of [ORDER, PRINT]) {
    if (P_.k === P_.want) continue;
    P_.k = P_.want > P_.k ? Math.min(P_.want, P_.k + dt * 4) : Math.max(P_.want, P_.k - dt * 4);
    moved = true;
    if (P_.k === 0 && P_.want === 0) P_.el.hidden = true;
  }
  if (!ORDER.el.hidden) placeHeld(ORDER, ORDER_REST, ORDER_UP);
  if (!PRINT.el.hidden) placeHeld(PRINT, PRINT_REST, PRINT_UP);
  if (moved) { paintAll(); applyControls(); }
  held.render(camera);
}
function orderUp() { return ORDER.k > 0.02 || ORDER.want > 0; }
function printUp() { return PRINT.k > 0.02 || PRINT.want > 0; }
/* pose(): both cards back where they rest, instantly, and out of the DOM flow */
function dropHeld() {
  for (const P_ of [ORDER, PRINT]) { P_.k = P_.want = 0; P_.el.hidden = true; }
}

let opener = null;
function lift(P_) {
  if (frozen) return;
  if (P_.want === 0) {
    const a = document.activeElement;
    if (a && a !== document.body && !ORDER.el.contains(a) && !PRINT.el.contains(a)) opener = a;
  }
  P_.el.hidden = false;
  P_.want = 1;
  st.restText = false;
  paintAll();
}
function putDown(P_) {
  const a = document.activeElement;
  const focusWasHere = !a || a === document.body || P_.el.contains(a);
  P_.want = 0;
  if (focusWasHere && opener && opener.isConnected && opener.focus) {
    try { opener.focus({ preventScroll: true }); } catch (e) { opener.focus(); }
  }
  if (!orderUp() && !printUp()) opener = null;
}
function openOrder() { lift(ORDER); }
function openPrint() { lift(PRINT); }

function setStatus(text, kind) {
  st.status = { text: String(text || ''), kind: kind || '' };
  if (ui.status) {
    ui.status.textContent = st.status.text;
    ui.status.className = 'pstatus ' + st.status.kind;
    ui.status.title = st.status.text;
  }
}

function buildPanel() {
  /* ---- the work order */
  const card = ORDER.el;
  ui.bench = card;
  card.appendChild(mk('span', 'clamp'));
  const head = mk('div', 'phd');
  head.appendChild(mk('span', 'ttl', 'Work order'));
  ui.health = mk('span', 'lab-health', 'IPM ?');
  head.appendChild(ui.health);
  const close = mk('button', 'pclose', '×');
  close.type = 'button';
  close.title = 'Put the order down (Esc). The Work order tab brings it back.';
  close.setAttribute('aria-label', 'Put the order down');
  close.addEventListener('click', () => putDown(ORDER));
  head.appendChild(close);
  $('bOrder').addEventListener('click', () => {
    if (ORDER.want) putDown(ORDER);
    else openOrder();
  });
  card.appendChild(head);
  card.appendChild(mk('p', 'hint',
    'IPM converts a picture to PNG, stores it in the FMM hold, and hands it back by name.'));

  const sec = (host, n, title) => {
    const s = mk('section', 'lab-sec');
    const h = mk('h2', 'phd2');
    h.appendChild(mk('span', 'n', n));
    h.appendChild(document.createTextNode(title));
    s.appendChild(h);
    host.appendChild(s);
    return s;
  };

  /* 1 SOURCE */
  ui.secSource = sec(card, '1', 'SOURCE');
  const tabs = mk('div', 'seg');
  ui.tabs = {};
  for (const [m, lab] of [['sample', 'SAMPLE'], ['upload', 'UPLOAD'],
                          ['url', 'URL'], ['zip', 'ZIP']]) {
    const b = mk('button', null, lab);
    b.type = 'button';
    b.addEventListener('click', () => { st.mode = m; onSourceChanged(); });
    ui.tabs[m] = b;
    tabs.appendChild(b);
  }
  ui.secSource.appendChild(tabs);

  ui.body = {};
  ui.body.sample = mk('div', 'lab-body');
  ui.sampleSel = mk('select');
  SAMPLES.forEach((x, i) => {
    const o = mk('option', null, x.name);
    o.value = String(i);
    ui.sampleSel.appendChild(o);
  });
  ui.sampleSel.addEventListener('change', () => {
    st.plate = +ui.sampleSel.value;
    onSourceChanged();
  });
  ui.body.sample.appendChild(fieldRow('PLATE', ui.sampleSel));
  ui.body.sample.appendChild(mk('p', 'hint', 'Built-in test images. The periscope head cycles them.'));

  ui.body.upload = mk('div', 'lab-body');
  ui.file = mk('input');
  ui.file.type = 'file';
  ui.file.accept = 'image/*,.svg';
  ui.file.addEventListener('change', () => readFile(ui.file, 'upload'));
  ui.uploadName = textInput('file name sent to IPM');
  ui.uploadName.addEventListener('input', () => {
    if (st.upload) st.upload.name = ui.uploadName.value;
    paintAll();
  });
  ui.body.upload.appendChild(fieldRow('FILE', ui.file));
  ui.body.upload.appendChild(fieldRow('SEND AS', ui.uploadName));

  ui.body.url = mk('div', 'lab-body');
  ui.url = textInput('http://host/picture.png');
  ui.url.addEventListener('input', () => { st.url = ui.url.value; paintAll(); });
  ui.body.url.appendChild(fieldRow('URL', ui.url));
  ui.body.url.appendChild(mk('p', 'hint', 'IPM downloads this address itself, then converts it.'));

  ui.body.zip = mk('div', 'lab-body');
  ui.zip = mk('input');
  ui.zip.type = 'file';
  ui.zip.accept = '.zip,application/zip';
  ui.zip.addEventListener('change', () => readFile(ui.zip, 'zip'));
  ui.zipClear = mk('button', 'sm', 'Use samples');
  ui.zipClear.type = 'button';
  ui.zipClear.addEventListener('click', () => {
    st.archive = null;
    ui.zip.value = '';
    onSourceChanged();
  });
  ui.body.zip.appendChild(fieldRow('ARCHIVE', ui.zip, ui.zipClear));
  ui.body.zip.appendChild(mk('p', 'hint',
    'Every image inside is converted and stored. No file: the four samples go as plates.zip.'));
  for (const k of Object.keys(ui.body)) ui.secSource.appendChild(ui.body[k]);

  /* 2 OUTPUT */
  ui.secOutput = sec(card, '2', 'OUTPUT');
  const sizes = mk('div', 'seg');
  ui.sizeBtn = {};
  for (const s of Object.keys(SIZES)) {
    const b = mk('button', null, s);
    b.type = 'button';
    b.addEventListener('click', () => {
      st.width = st.height = String(SIZES[s]);
      if (st.mode === 'zip') st.mode = 'sample';
      onSourceChanged();
    });
    ui.sizeBtn[s] = b;
    sizes.appendChild(b);
  }
  ui.w = textInput('512');
  ui.h = textInput('512');
  ui.w.inputMode = ui.h.inputMode = 'numeric';
  ui.w.classList.add('num');
  ui.h.classList.add('num');
  const onWH = () => {
    st.width = ui.w.value.trim();
    st.height = ui.h.value.trim();
    st.scope = scopeFromPanel();
    paintAll();
  };
  ui.w.addEventListener('input', onWH);
  ui.h.addEventListener('input', onWH);
  ui.secOutput.appendChild(fieldRow('FIT IN', sizes, ui.w, mk('span', 'x', '×'), ui.h));
  ui.format = textInput('png');
  ui.format.classList.add('fmt');
  ui.format.setAttribute('list', 'ipm-formats');
  const dl = mk('datalist');
  dl.id = 'ipm-formats';
  for (const f of ['png', 'jpg', 'gif', 'webp', 'bmp', 'tiff']) {
    const o = mk('option');
    o.value = f;
    dl.appendChild(o);
  }
  ui.secOutput.appendChild(dl);
  ui.format.addEventListener('input', () => { st.format = ui.format.value.trim(); paintAll(); });
  ui.name = textInput('blank: IPM picks img_<hex>.png');
  ui.name.addEventListener('input', () => { st.outName = ui.name.value.trim(); paintAll(); });
  ui.secOutput.appendChild(fieldRow('STORE AS', ui.name, mk('span', 'x', 'FORMAT'), ui.format));
  ui.batchNote = mk('p', 'hint', 'A batch takes only the archive: IPM uses its own size and names.');
  ui.secOutput.appendChild(ui.batchNote);

  /* 3 REQUEST */
  ui.secRequest = sec(card, '3', 'REQUEST');
  ui.reqLine = mk('code', 'lab-req');
  ui.reqBody = mk('div', 'lab-reqbody');
  ui.secRequest.appendChild(ui.reqLine);
  ui.secRequest.appendChild(ui.reqBody);

  const btns = mk('div', 'pbtns');
  ui.send = mk('button', 'go', 'Capture · send');
  ui.send.type = 'button';
  ui.send.title = 'Same as the CAPTURE PLUNGER on the array';
  ui.send.addEventListener('click', () => pressCapture());
  ui.viewPrint = mk('button', 'sm', 'Print');
  ui.viewPrint.type = 'button';
  ui.viewPrint.title = 'Lift the last print out of the tray';
  ui.viewPrint.addEventListener('click', () => openPrint());
  btns.appendChild(ui.send);
  btns.appendChild(mk('span', 'sp'));
  btns.appendChild(ui.viewPrint);
  card.appendChild(btns);
  ui.status = mk('div', 'pstatus');
  ui.status.setAttribute('role', 'status');
  ui.status.setAttribute('aria-live', 'polite');
  card.appendChild(ui.status);

  /* ---- the print */
  const pr = PRINT.el;
  const phd = mk('div', 'phd');
  ui.printTitle = mk('span', 'ttl', 'Print');
  ui.printSize = mk('span', 'sz');
  const pclose = mk('button', 'pclose', '×');
  pclose.type = 'button';
  pclose.title = 'Put the print back in the tray (Esc)';
  pclose.setAttribute('aria-label', 'Put the print down');
  pclose.addEventListener('click', () => putDown(PRINT));
  phd.appendChild(ui.printTitle);
  phd.appendChild(ui.printSize);
  phd.appendChild(pclose);
  pr.appendChild(phd);
  ui.photo = mk('div', 'photo');
  pr.appendChild(ui.photo);
  ui.secResponse = sec(pr, '4', 'RESPONSE');
  ui.secResponse.classList.add('grow');
  ui.resp = mk('div', 'lab-resp');
  ui.secResponse.appendChild(ui.resp);
  ui.secHold = sec(pr, '5', 'FMM HOLD');
  ui.fetchName = textInput('stored file name');
  ui.fetchBtn = mk('button', 'sm', 'Fetch');
  ui.fetchBtn.type = 'button';
  ui.fetchBtn.title = 'GET /image/{name}: read a stored file back and develop it';
  ui.fetchBtn.addEventListener('click', () => fetchStored(ui.fetchName.value));
  ui.secHold.appendChild(fieldRow('NAME', ui.fetchName, ui.fetchBtn));
  ui.chips = mk('div', 'chips');
  ui.secHold.appendChild(ui.chips);

  /* Enter submits from a single-line FIELD only, never on key-repeat, and goes
   * to the action that field belongs to (FMM's cards do the same). */
  const enterKeys = ev => {
    const t = ev.target;
    if (ev.key !== 'Enter' || !t || t.tagName !== 'INPUT' || t.type === 'file' || ev.repeat) return;
    ev.preventDefault();
    if (t === ui.fetchName) fetchStored(ui.fetchName.value);
    else pressCapture();
  };
  card.addEventListener('keydown', enterKeys);
  pr.addEventListener('keydown', enterKeys);

  /* Escape puts the print down first, then the order, and only then leaves
   * the close-up: window.__closeOverlay() is the cockpit's contract for that
   * (live3d/app.js, ESCAPE, ONE POLICY). */
  const closeTop = () => {
    if (PRINT.want) { putDown(PRINT); return true; }
    if (ORDER.want) { putDown(ORDER); return true; }
    return false;
  };
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape' || !(PRINT.want || ORDER.want)) return;
    ev.preventDefault();
    ev.stopPropagation();
    closeTop();
  });
  window.__closeOverlay = closeTop;
}

function focusPanel(which) {
  openOrder();
  const s = which === 'output' ? ui.secOutput : ui.secSource;
  const target = which === 'output' ? ui.name
    : ({ sample: ui.sampleSel, upload: ui.file, url: ui.url, zip: ui.zip })[st.mode];
  s.classList.remove('flash');
  void s.offsetWidth;                       // restart the CSS animation
  s.classList.add('flash');
  if (target) target.focus({ preventScroll: true });
}

function kv(host, rows) {
  const dl = mk('dl', 'kv');
  for (const [k, v] of rows) {
    if (v == null || v === '') continue;
    dl.appendChild(mk('dt', null, k));
    dl.appendChild(mk('dd', null, String(v)));
  }
  host.appendChild(dl);
}
function rawJSON(host, r) {
  const copy = {};
  for (const k of Object.keys(r || {}))
    copy[k] = (k === 'image_b64' && r[k]) ? '<' + String(r[k]).length + ' base64 chars>' : r[k];
  const det = mk('details');
  det.appendChild(mk('summary', null, 'RAW REPLY'));
  det.appendChild(mk('pre', null, JSON.stringify(copy, null, 2)));
  host.appendChild(det);
}
function retrLine(r) {
  return r.retrievable
    ? '200  ' + (r.content_type || '?') + '  ' + fmtBytes(r.byte_length)
    : 'HTTP ' + (r.retrieve_status == null ? '?' : r.retrieve_status);
}
function savePrint() {
  const p = st.print;
  if (!p || !hasPicture(p.r)) return;
  const bin = atob(p.r.image_b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([buf], { type: p.r.content_type || 'image/png' }));
  const a = mk('a');
  a.href = url;
  a.download = p.name || 'print.png';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* The print shows the last picture that came back, from a convert or from the
 * hold.  Errors go on the work order's status line instead. */
function renderPrint() {
  const p = st.print;
  for (const host of [ui.photo, ui.resp]) while (host.firstChild) host.removeChild(host.firstChild);
  ui.printTitle.textContent = p ? p.name || 'Print' : 'No print yet';
  ui.printSize.textContent = p && p.r && typeof p.r.byte_length === 'number' ? fmtBytes(p.r.byte_length) : '';
  if (!p) {
    ui.photo.appendChild(mk('p', 'hint', 'Send a work order and the print develops here.'));
    return;
  }
  const r = p.r || {};
  if (hasPicture(r)) {
    const img = mk('img');
    img.alt = 'image returned by IPM';
    img.src = 'data:' + (r.content_type || 'image/png') + ';base64,' + r.image_b64;
    ui.photo.appendChild(img);
  } else {
    ui.photo.appendChild(mk('p', 'hint', 'Stored, but no picture came back.'));
  }
  const rows = [['request', p.label]];
  if (typeof r.count === 'number') rows.push(['batch', (r.stored_n || 0) + ' of ' + r.count + ' stored']);
  if (typeof r.bytes === 'number') rows.push(['stored', fmtBytes(r.bytes)]);
  if (r.svg) rows.push(['svg', (r.svg.width || '?') + ' × ' + (r.svg.height || '?')
    + (r.svg.text ? '  ' + r.svg.text : '')]);
  rows.push(['convert', r.convertError], ['store', r.storeError], ['read back', retrLine(r)]);
  kv(ui.resp, rows);
  if (Array.isArray(r.results) && r.results.length) {
    const list = mk('div', 'batch');
    for (const x of r.results) {
      const b = mk('button', 'sm');
      b.type = 'button';
      b.textContent = (x.stored ? '✓ ' : '✗ ') + String(x.name || '?')
        + (typeof x.bytes === 'number' ? '  ' + fmtBytes(x.bytes) : '');
      b.disabled = !x.stored || !x.name;
      b.title = 'GET /image/' + String(x.name || '');
      b.addEventListener('click', () => fetchStored(x.name));
      list.appendChild(b);
    }
    ui.resp.appendChild(list);
  }
  const btns = mk('div', 'pbtns');
  const save = mk('button', null, 'Save');
  save.type = 'button';
  save.title = 'Save the picture to this computer';
  save.disabled = !hasPicture(r);
  save.addEventListener('click', savePrint);
  btns.appendChild(save);
  btns.appendChild(mk('span', 'sp'));
  ui.resp.appendChild(btns);
  rawJSON(ui.resp, r);
}

let panelSig = '';
function renderPanel() {
  if (!ui.bench) return;
  for (const m of Object.keys(ui.tabs)) {
    ui.tabs[m].classList.toggle('on', st.mode === m);
    ui.body[m].hidden = st.mode !== m;
  }
  setVal(ui.sampleSel, String(st.plate));
  setVal(ui.uploadName, st.upload ? st.upload.name : '');
  ui.uploadName.disabled = !st.upload;
  setVal(ui.url, st.url);
  ui.zipClear.disabled = !st.archive;

  const batch = st.mode === 'zip';
  for (const s of Object.keys(ui.sizeBtn))
    ui.sizeBtn[s].classList.toggle('on', !batch && st.width === String(SIZES[s])
      && st.height === String(SIZES[s]));
  setVal(ui.w, st.width);
  setVal(ui.h, st.height);
  setVal(ui.format, st.format);
  setVal(ui.name, st.outName);
  for (const i of [ui.w, ui.h, ui.format, ui.name]) i.disabled = batch;
  ui.batchNote.hidden = !batch;

  const [line, body] = requestLines(convertSpec());
  ui.reqLine.textContent = line;
  ui.reqBody.textContent = body;
  const busy = st.pending || st.phase === 'expose';
  ui.send.disabled = busy;
  ui.send.textContent = busy ? 'Exposing…' : 'Capture · send';
  ui.viewPrint.disabled = !st.print && !st.history.length;

  const h = st.health;
  ui.health.className = 'lab-health' + (h === 'up' ? ' up' : (h ? ' down' : ''));
  ui.health.textContent = h === 'up' ? 'IPM ONLINE' : h === 'down' ? 'IPM DOWN'
    : h === 'unreachable' ? 'NO BRIDGE' : 'IPM ?';

  /* rebuild the print only when it changes, not every develop frame */
  const sig = [st.printVer, st.history.join('|')].join('#');
  if (sig !== panelSig) {
    panelSig = sig;
    renderPrint();
    while (ui.chips.firstChild) ui.chips.removeChild(ui.chips.firstChild);
    for (const n of st.history) {
      const b = mk('button', 'sm', n);
      b.type = 'button';
      b.title = 'GET /image/' + n;
      b.addEventListener('click', () => { ui.fetchName.value = n; fetchStored(n); });
      ui.chips.appendChild(b);
    }
  }
}
buildPanel();
refit = await mountRefit({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__refit = refit;

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same nine lines, and none of them is IPM-specific either: the anchor,
 * the size, the part names, the vane pivot, the sweep travel and the hotspot
 * all come out of `scene.json -> mast`, which pipeline/status_mast.py wrote.
 * See export_ipm.py's IPM_MAST block for where it went and why.
 *
 * It declares NO readout plane.  Its words are the screen-space caption and
 * detail panel in live3d/mast.css, the same class of thing as the port's
 * docket.  `readouts.length` is still 3.
 *
 * `place()` is re-run on `refit:docket` by mast.js itself; this page needs no
 * MutationObserver.  mast.js also places the caption BEFORE its first
 * status.json fetch, so this page needs no module-side `mast.place()` line
 * either (STATUS_AT_A_GLANCE 17.1). */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

/* --------------------------------------------- M6: THE CAPTURE POSE
 * DETERMINISTIC, and it is the state export_ipm.py rendered gt_full_read.png
 * and gt_platen0.png in: the SCOPE dial at the 512 detent (−62.5°), the
 * capture plunger at ARMED — its own declared rest, and what puts ipm_plg_knob
 * across the bottom of the `output` strip — and the tray six frames into an
 * eight-frame develop.
 *
 * THERE IS NO setInterval OR setTimeout ANYWHERE IN THIS FILE.  Every
 * animation is a state machine driven out of onFrame(), so `frozen = true`
 * stops all of it in one place and two consecutive captures are byte-identical.
 * KVS failed this check for a 520 ms cursor blink that a flag could not stop. */
function settle() {
  an.deg = detentDeg(st.scope);
  an.drop = (st.capture === 'capture') ? 1 : 0;
  applyMaterials();
  applyControls();
  paintAll();
}
function poseForCapture() {
  /* Hide the mast and the screen chrome. Captures were measured against
   * renders that contain neither, so hiding them keeps that comparison. */
  hideCaptureChrome();
  if (refit) refit.pose();
  if (mast) mast.pose();
  frozen = true;
  dragging = null;
  resetSession(true);
  settle();
}

/* A module-private hook, ALONGSIDE window.__occ and never instead of it:
 * check/shoot_occlusion.mjs drives only __occ.  This exists so the comparisons
 * that are not part of that contract — driving a control to a chosen state,
 * and asking which declared object names actually resolved — can be measured
 * on the real page rather than argued about. */
window.__ipm = {
  set: o => { frozen = true; Object.assign(st, o); settle(); },
  drive: (k, v) => { frozen = true; an[k] = v; applyControls(); },
  tris: () => ({ tris: liveTris, meshes: liveMeshes }),
  rig: () => ({
    dial: (() => { let n = 0; dial.inner.traverse(o => { if (o.isMesh) n++; });
                   return n; })(),
    plunger: plunger.children.length,
    lamp: !!lamp,
    trayFrames: trayFrames.map(f => f.length),
    tray: trayAll.length,
  }),
  facing: () => facingAudit(camera),
  layout: () => readouts.map(r => r.layout),
  state: () => JSON.parse(JSON.stringify(st)),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's own derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
};

resetSession(false);
settle();
checkHealth();
openOrder();                     /* the order lifts off its rail at load */
/* This page rests unposed: it never calls poseForCapture() at load, and it
 * opens on a clean, armed plate rather than the capture pose's mid-develop
 * strings, which describe no real job.  pose() paints those strings straight
 * out of scene.json -> readout_text.  The mast is shown. The work order, the
 * title, the tutorial control, and the
 * rebuild control stay on the page a person opens. check_occlusion.py's
 * section 0 reports the difference between the as-loaded and the posed
 * frames, and that section is reported, not failed, for exactly this case. */
mast.show(true);

layout();
/* One-sided geometry that FrontSide has deleted.  Console warning only; it is
 * not part of __occ.audit(), which means something else and must stay []. */
facingAudit(camera);
requestAnimationFrame(frame);
window.__loaded = true;
