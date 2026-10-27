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
/* THE REFIT PORT.  live3d/refit.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> refit`, which
 * pipeline/refit_port.py wrote.  live3d/design/FIX_UPLOAD.md is the design. */
import { mountRefit } from '../../refit.js';
/* THE TELLTALE MAST.  live3d/mast.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> mast`, which
 * pipeline/status_mast.py wrote.  live3d/design/STATUS_AT_A_GLANCE.md section
 * 6 is the design; live3d/status.js is the ONE derivation both halves use. */
import { mountMast } from '../../mast.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'DNSM';
const A = '../../assets/' + CODE + '/';

/* WHICH SCENE FILE.  `scene.json` unless the URL says otherwise, and the only
 * other name the exporter writes is `scene_rot.json` -- the SAME export with
 * the catalogue drum turned -30 deg (a facet EDGE dead centre in the window)
 * and the courier card pushed home, so the two MOVING carriers are scored in
 * motion and not only at rest.  plate.png and depth.bin are baked-only and
 * identical between them, so this is nothing but a different set of plane
 * frames and a different `pose`.
 *
 * THIS IS AN EDIT ABOVE THE `MODULE WORK STARTS HERE` LINE and it is reported
 * as such in NOTES.md section 8: check_occlusion.py already has `SCENE=` to
 * point its OFFLINE ORACLE at another scene, and there is no matching way to
 * point the PAGE at one, so any module that has to be captured in a second
 * pose must reach above the line.  Two lines, whitelisted, no path traversal. */
const SCENE = (function () {
  const q = new URLSearchParams(location.search).get('scene') || '';
  return /^[A-Za-z0-9_-]+\.json$/.test(q) ? q : 'scene.json';
})();

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
const [S, MJ] = await Promise.all([getJSON(A + SCENE),
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
const _fv = new THREE.Vector3();    // scratch for the facing test in place()

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
  const r = { tp, plane, el, lines, els: [], rec, wanted: true, back: false };
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
    /* BACK-FACING FACETS.  DNSM is the fleet's only rotating multi-facet
     * carrier, so it is the only module whose readouts can turn away from the
     * camera.  This page used to hide the DOM element itself here, with an
     * `.away{display:none}` class, because css3d.js's
     * `backface-visibility:hidden` was INERT at this matrix scale (makeBasis
     * scales the two in-plane columns by MPP = 2e-4, so the accumulated 2x2
     * determinant is ~3.1e-8 and Chrome declines to cull below ~1e-3).
     *
     * THAT WORKAROUND IS GONE.  css3d.js now decides the facing itself, every
     * frame, from the same normal, and hides the element with its own class --
     * verified against this module's `__dnsm.backFacing()` over the whole drum
     * rotation (-180..+180 in 2.5 deg steps, 145 poses x 8 elements = 1160
     * element-poses at dsf 1 AND dsf 2, 447 culls) with ZERO disagreements.
     * Two culls doing the same job is one more place for them to disagree.
     *
     * `r.back` is still computed, because it is not only a DOM concern: the
     * OCCLUSION PLANE must be disabled on a facet that has turned away, or the
     * GLSL keeps routing fragments in front of it to the front pass and
     * punches a hole in the near side of the drum.  `__dnsm.backFacing()` and
     * `__dnsm.domCulled()` are kept as the cross-check between the two.
     * NOTES.md section 8 has the repro and the numbers. */
    r.back = _fv.copy(o).sub(camera.position).dot(n) >= 0;
    r.plane.enabled = r.wanted && !r.back;
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

/* DNSM — NAV BEACON / STAR CHARTS.  The navigator's DNS console: a yoke-mounted
 * scope head hanging off the cockpit roof, its face canted 60 deg so it looks
 * the pilot in the eye.  Four controls, all of them LIVE:
 *
 *   sweep     the phosphor beacon, 10 decaying sectors + a bright leading edge,
 *             turning about the FACE NORMAL (not the slot's +Z -- the face is
 *             raked 60 deg, the steepest in the fleet, and rotating about the
 *             slot normal would sweep a cone).
 *   qtype     the query type: contacts on the plot, one record-type lamp lit,
 *             and the readout across the top.  Eight states; the module
 *             declares four lamp materials, so the material ladder is modelled.
 *   chart     the six-facet star-catalogue drum behind the window.  Shipped as
 *             `kind: frames`, but build.py's own frame loop is
 *             `piv.rotation_euler = (TILT - 2 pi i / 6, 0, 0)` -- ONE object
 *             set on ONE continuous parameter, exactly PKT's three frame sets.
 *             So it is a continuous angle here, not six stills.
 *   courier   the chart card sliding into its slot, and the import lamp.
 *
 * THE TWO HARD PARTS, both of them the audit's:
 *
 * 1. A NON-PLANAR CARRIER LONGER THAN ITS APERTURE.  A CSS3D element is flat,
 *    so the drum is SIX flat facets, each its own DOM element and its own
 *    readout plane, each TANGENT to its own facet 1.0 mm above the paper.
 *    Five of the six are invisible at rest -- three turned round the back
 *    (the shader's `den > -1e-6` test drops them, and css3d.js's
 *    backface-visibility:hidden drops the DOM), two behind `dnsm_face_under`
 *    and `dnsm_face_over`, which are BAKED PLATE.  That is the whole reason
 *    MAX_PLANES is 12 and the whole reason this module is OCCLUDED.
 *
 * 2. TWO MOVING PLANES.  The six facet planes ride the drum pivot and the
 *    courier plane rides the card.  Both the DOM element and the occlusion
 *    plane are moved by the same call, `r.place(o, u, v, n)`, from the REST
 *    frame the exporter declared -- never by mutating the exported numbers.
 *    OTA NOTES 8.2 is the pattern; this is the first module to drive the
 *    DIRECTION half of it as well as the translation half.
 */

const P = S.props;
const V3 = a => new THREE.Vector3().fromArray(a);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* ---------------------------------------------------------------- TODO 1 */
/* LIVE PROPS.  Four glbs, 5,488 triangles all told; the other 407,640 of this
 * module's 521,636 are content type and ship as ZERO. */
const [gSweep, gQtype, gChart, gCourier] = await Promise.all([
  load(A + P.sweep.glb), load(A + P.qtype.glb),
  load(A + P.chart.glb), load(A + P.courier.glb)]);

/* the raw glTF materials, BEFORE dress() clones them, so a lamp can be swapped
 * between the four states the module declares */
const rawMat = {};
function harvest(g) {
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    for (const m of (Array.isArray(o.material) ? o.material : [o.material]))
      if (m && !rawMat[m.name]) rawMat[m.name] = m;
  });
}
harvest(gQtype); harvest(gCourier); harvest(gSweep); harvest(gChart);

const node = {};
function index(g) { g.scene.traverse(o => { if (o.isMesh) node[o.name] = o; }); }
index(gSweep); index(gQtype); index(gChart); index(gCourier);

/* --- the beacon: one pivot at the scope hub, turning about the face normal */
const SWEEP_HUB = V3(P.sweep.hub);
const SWEEP_AXIS = V3(P.sweep.axis).normalize();
const sweepPivot = pivotAt(P.sweep.hub);
sweepPivot.inner.add(gSweep.scene);
gSweep.scene.traverse(o => {
  if (!o.isMesh) return;
  const m = dress(o);
  /* dnsm_sweep_sec_* is a single-sided annular wedge built by shell.mesh_from
   * with faces (b, b+2, b+3, b+1).  Its winding puts the front face at the
   * camera here, and facingAudit() confirms it -- but the whole phosphor fan
   * is exactly the shape trap 21 is about (MQB's ribbon, OTA's 14 one-triangle
   * chevrons), so it is checked on every load rather than assumed. */
  m.side = THREE.FrontSide;
});

/* --- the plot: 35 contacts across 8 query types, and 8 record-type lamps */
scene.add(gQtype.scene);
const LAMP_KEYS = ['off', 'on', 'amber', 'red'];
const domeMesh = P.qtype.domes.map(n => node[n]);
const blipMesh = {};
for (const q of P.qtype.states) blipMesh[q] = P.qtype.blips[q].map(n => node[n]);
const missing = [...P.qtype.domes, ...Object.values(P.qtype.blips).flat()]
  .filter(n => !node[n]);
if (missing.length) fail('qtype.glb is missing nodes: ' + missing.join(', '));

const domeSet = new Set(domeMesh);
gQtype.scene.traverse(o => { if (o.isMesh && !domeSet.has(o)) dress(o); });
/* Four dressed materials per dome.  dress() clones the mesh's CURRENT material
 * and attaches the depth composite and the split to the clone, so building the
 * four states means assigning each raw material in turn and dressing it.  All
 * four end up in `patched`, so __occ.matfix() still reaches every one of them,
 * and auditScene() only ever sees whichever is currently assigned. */
function lampStates(mesh, mats, keys) {
  const out = {};
  for (const k of keys) {
    const src = rawMat[mats[k]];
    if (!src) fail('material ' + mats[k] + ' is not in any glb');
    mesh.material = src;
    out[k] = dress(mesh);
  }
  mesh.material = out.off;
  return out;
}
const domeMats = domeMesh.map(m => lampStates(m, P.qtype.mats, LAMP_KEYS));

/* --- the catalogue drum: ONE object set on ONE continuous angle */
const DRUM_HUB = V3(P.chart.hub);
const DRUM_AXIS = V3(P.chart.axis).normalize();
const drumPivot = pivotAt(P.chart.hub);
drumPivot.inner.add(gChart.scene);
gChart.scene.traverse(o => { if (o.isMesh) dress(o); });

/* --- the courier card, and its import lamp */
const CARD_AXIS = V3(P.courier.up_axis).normalize();
const cardGroup = new THREE.Group();
scene.add(cardGroup);
cardGroup.add(gCourier.scene);
const courierDome = node[P.courier.dome];
if (!courierDome) fail('courier.glb has no ' + P.courier.dome);
const cardMesh = P.courier.card.map(n => node[n]).filter(Boolean);
gCourier.scene.traverse(o => { if (o.isMesh && o !== courierDome) dress(o); });
const courierMats = lampStates(courierDome, P.courier.mats, ['off', 'on']);
const COURIER_LAMP = { off: 'off', amber: 'on', on: 'on' };

applyMatFix();

/* live triangle count, out of the LOADED index accessors -- an independent
 * cross-check of the exporter's figure rather than a repeat of it */
let TRIS = 0;
for (const g of [gSweep, gQtype, gChart, gCourier])
  g.scene.traverse(o => {
    if (!o.isMesh || !o.geometry) return;
    const gm = o.geometry;
    TRIS += ((gm.index ? gm.index.count : gm.attributes.position.count) / 3) | 0;
  });

/* ---------------------------------------------------------------- TODO 2 */
/* THE SESSION MODEL.  DNSM speaks DNS: a name, a query type, an answer the
 * catalogue drum pages through, and a chart card that slides out of the
 * courier slot to look names up and send records in (POST /admin/import).  Every value shown comes out of scene.json --
 * `props.qtype.readouts`, `props.chart.pages`, `props.courier.head` -- so the
 * page and the exporter cannot drift (BRIEF step 2: do not re-derive a
 * module's own state in JS).  textContent only, never innerHTML: in the real
 * product these bytes are an answer section off the wire. */
const SES = {
  qtype: S.pose.qtype,
  chartDeg: S.pose.chart_deg,
  courier: S.pose.courier,
  sweepDeg: S.pose.sweep_deg,
  /* THE PAGE MUST REST IN THE STATE THE GROUND TRUTH WAS RENDERED IN.
   * This shipped as `true`, so the beacon swept continuously from load and the
   * page matched plate.png only during the instant it passed sweep_deg 0.
   * Every check pose()s first, so all of them passed and none of them could
   * see it -- which is precisely the hole check_occlusion.py question 0 was
   * added to close: it captures the page BEFORE pose(), and it reported 70,576
   * differing px at pr 2 on both scene.json and scene_rot.json.  Double-click
   * the scope to start the sweep; it is interaction, not rest state. */
  spin: false,
  /* the beacon also turns while a lookup is out */
  pinging: false,
  /* true only in the captured rest pose: the QNAME strip then shows the
   * ground truth's own line instead of the name being typed */
  posed: false,
  qname: 'www.example.com',
  lastRcode: null,
  lastSummary: null,
  queryEdit: false,
  chartLive: null,
  /* facet angle the drum eases to after a reply; null once dragged */
  chartTarget: null,
};
/* the page a human opens is ready to look up an address; only the captured
 * pose rests on the plate's own lamp state */
SES.qtype = 'A';

const N_QUERY = S.text_planes[0].type.n_cols;
const PLANE_OF = {};
S.text_planes.forEach((tp, i) => { PLANE_OF[tp.name] = i; });
const N_COURIER = (S.text_planes[PLANE_OF.courier].type
  && S.text_planes[PLANE_OF.courier].type.n_cols) || 11;
const N_CHART_COLS = (S.text_planes[PLANE_OF.chart0]
  && S.text_planes[PLANE_OF.chart0].type
  && S.text_planes[PLANE_OF.chart0].type.n_cols) || 26;
const N_CHART_LINES = (S.text_planes[PLANE_OF.chart0]
  && S.text_planes[PLANE_OF.chart0].type
  && S.text_planes[PLANE_OF.chart0].type.n_lines) || 3;
const NX_STATE = 'NX';

function clipTo(s, n) {
  return String(s == null ? '' : s).slice(0, n);
}

function readoutLines(name, i) {
  if (name === 'query') {
    if (SES.queryEdit) return [clipTo(SES.qname, N_QUERY)];
    if (SES.lastSummary != null) return [clipTo(SES.lastSummary, N_QUERY)];
    if (SES.posed) return [String(P.qtype.readouts[S.pose.qtype]).padStart(N_QUERY)];
    return [clipTo(SES.qname.toUpperCase(), N_QUERY)];
  }
  if (name === 'courier') {
    if (SES.courier === 'empty') return [''];
    if (SES.courier === 'import') return [clipTo('READING', N_COURIER)];
    return [String(P.courier.head)];
  }
  const m = /^chart([0-9]+)$/.exec(name);
  if (m) {
    if (SES.chartLive) return SES.chartLive[+m[1]].slice();
    return P.chart.pages[+m[1]].slice();
  }
  /* any plane this module did not declare -- check/control_rig.py appends one
   * and gives it an empty line in readout_text.  Read it out of the scene
   * rather than guessing, so a control rig runs the real page unmodified. */
  return ((S.readout_text || [])[i] || []).slice();
}
function paintAll() {
  readouts.forEach((r, i) => r.paint(readoutLines(r.tp.name, i)));
}

/* ink is MEASURED off Blender's own render of this module's own type, per
 * readout (BRIEF section 7 rule 7): the catalogue and the card are warm grey
 * ink on cream paper, the query strip is emissive phosphor clipping to warm
 * white under AgX.  That is what Blender renders, so that is what the DOM
 * shows -- it is not "fixed" to a neutral. */
for (const r of readouts) {
  const c = S.ink && S.ink[r.tp.name];
  if (c) r.el.style.color = 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
}

function paintLamps() {
  const q = SES.qtype;
  const lit = (P.qtype.lit[q] || P.qtype.lit.A).slice();
  const on = P.qtype.lamp_mat[q] || 'on';
  if (SES.lastRcode === 'NXDOMAIN') lit[lit.length - 1] = 1;
  domeMesh.forEach((m, i) => {
    let key = 'off';
    if (lit[i]) key = (i === lit.length - 1) ? 'red' : on;
    m.material = domeMats[i][key];
  });
  for (const s of P.qtype.states)
    for (const m of (blipMesh[s] || [])) m.visible = (s === q);
}
function setQtype(q) {
  if (q === NX_STATE) return;
  SES.qtype = q;
  paintLamps();
  paintAll();
  paintCardType();
}
function setCourier(st) {
  SES.courier = st;
  const slide = P.courier.slide_m[st];
  for (const m of cardMesh) m.visible = (slide !== null);
  cardGroup.position.copy(CARD_AXIS)
    .multiplyScalar(slide === null ? P.courier.slide_m.chart : slide);
  courierDome.material = courierMats[COURIER_LAMP[P.courier.lamp_mat[st]]];
  { const r = readouts[PLANE_OF.courier];        // intent; place() ANDs facing
    r.wanted = (slide !== null); r.plane.enabled = r.wanted && !r.back; }
  /* NOTHING sets `visibility` inline on a .readout.  `body.notext .readout
   * {visibility:hidden}` is a CLASS rule and an inline style beats it, so an
   * inline `visibility:visible` makes that readout identical in the shown and
   * hidden grabs -- and check_text.py's DOM ink is exactly that difference.
   * It cost this module one `(NO DOM INK IN THESE ROWS) <- FAIL` on the
   * courier card, with the type on screen and in the right place.  An empty
   * card paints empty strings and disables its plane instead. */
  paintAll();
}

/* ---------------------------------------------------------------- TODO 3 */
/* ANIMATION, and THE TWO MOVING PLANES.
 *
 * The plane uniforms are re-uploaded from the TextPlane objects every frame,
 * so a plane parented to a control costs nothing extra -- but BOTH halves have
 * to move, the occlusion plane AND the DOM element, which is what the
 * template's r.place(o,u,v,n) does in one call.
 *
 * REST FRAMES ARE COPIED, NEVER MUTATED.  scene.json declares each plane at
 * the pose that scene file was authored in (`S.pose`), so the transform
 * applied here is the DELTA from that pose -- which is why scene.json (drum 0,
 * card in the mouth) and scene_rot.json (drum -30, card home) both come out
 * with `__occ.planes()` at ~1e-4 px after pose() rather than one of them
 * reading a few hundred. */
const CHART_REST = [];
for (let k = 0; k < P.chart.facets; k++) {
  const tp = S.text_planes[PLANE_OF['chart' + k]];
  CHART_REST.push({ o: V3(tp.origin).sub(DRUM_HUB), u: V3(tp.u),
                    v: V3(tp.v), n: V3(tp.n) });
}
const COURIER_REST = (() => {
  const tp = S.text_planes[PLANE_OF.courier];
  return { o: V3(tp.origin), u: V3(tp.u), v: V3(tp.v), n: V3(tp.n) };
})();
const _q = new THREE.Quaternion();
const _o = new THREE.Vector3(), _u = new THREE.Vector3();
const _v = new THREE.Vector3(), _n = new THREE.Vector3();

function placeDrum() {
  /* the glb is exported at drum angle 0, so the GEOMETRY takes the absolute
   * angle; the PLANES were declared at S.pose.chart_deg, so they take the
   * delta from it. */
  drumPivot.pivot.quaternion.setFromAxisAngle(DRUM_AXIS, SES.chartDeg * D2R);
  drumPivot.pivot.updateMatrixWorld(true);
  _q.setFromAxisAngle(DRUM_AXIS, (SES.chartDeg - S.pose.chart_deg) * D2R);
  for (let k = 0; k < CHART_REST.length; k++) {
    const R = CHART_REST[k];
    _o.copy(R.o).applyQuaternion(_q).add(DRUM_HUB);
    _u.copy(R.u).applyQuaternion(_q);
    _v.copy(R.v).applyQuaternion(_q);
    _n.copy(R.n).applyQuaternion(_q);
    readouts[PLANE_OF['chart' + k]].place(_o, _u, _v, _n);
  }
}
function placeCard() {
  const slide = P.courier.slide_m[SES.courier];
  const d = (slide === null ? P.courier.slide_m.chart : slide)
    - P.courier.slide_m[S.pose.courier];
  _o.copy(COURIER_REST.o).addScaledVector(CARD_AXIS, d);
  readouts[PLANE_OF.courier].place(_o, COURIER_REST.u, COURIER_REST.v,
                                   COURIER_REST.n);
}
function placeSweep() {
  sweepPivot.pivot.quaternion.setFromAxisAngle(
    SWEEP_AXIS, (SES.sweepDeg - S.pose.sweep_deg) * D2R);
}

/* THE REFIT PORT and THE TELLTALE MAST.  Mounted below, after this page's own
 * `hotspot()` helper exists; declared here because onFrame() and
 * poseForCapture() both reach them and both are defined before the mount. */
let refit = null;
let mast = null;

function onFrame(dt, now) {
  /* FIRST, and above everything else this function does.  CONVERSION_BRIEF
   * trap 26 / FIX_UPLOAD 12.15 item 7: neither fitting owns a timer, so the
   * iris, the throat pulse, the jewel breath, the ratchet, the tally flag,
   * the mast's sweep band, its vane easing and its cap breath all animate off
   * these two calls.  DNSM has no `running`/`frozen` early return today --
   * `SES.spin` is a branch, not a gate -- but putting them anywhere below a
   * future one would freeze both fittings on exactly the page a human opens.
   * `pose()` is what stills them for a capture, and it does it by HIDING them. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);
  tickHeld(dt);
  if (SES.spin || SES.pinging) {
    SES.sweepDeg += P.sweep.spin_deg_s * dt;
    while (SES.sweepDeg > 180) SES.sweepDeg -= 360;
    while (SES.sweepDeg < -180) SES.sweepDeg += 360;
  }
  if (SES.chartTarget != null) {
    let d = SES.chartTarget - SES.chartDeg;
    while (d > 180) d -= 360;
    while (d < -180) d += 360;
    const step = 240 * dt;
    if (Math.abs(d) <= step) { SES.chartDeg = SES.chartTarget; SES.chartTarget = null; }
    else SES.chartDeg += Math.sign(d) * step;
  }
  placeSweep();
  placeDrum();
  placeCard();
}

/* ---------------------------------------------------------------- TODO 4 */
/* INTERACTION.  Hotspots go in #hots, above the front canvas. */
function stagePt(ev) {
  const b = $('stage').getBoundingClientRect();
  const k = b.width / W;
  return { x: (ev.clientX - b.left) / k, y: (ev.clientY - b.top) / k };
}
function hotspot(rect, label, opts) {
  const d = document.createElement('div');
  d.className = 'hot';
  d.style.left = rect.x + 'px'; d.style.top = rect.y + 'px';
  d.style.width = rect.w + 'px'; d.style.height = rect.h + 'px';
  d.title = label;
  $('hots').appendChild(d);
  if (opts.click) d.addEventListener('click', opts.click);
  if (opts.drag) {
    let last = null;
    d.addEventListener('pointerdown', e => {
      last = stagePt(e); d.setPointerCapture(e.pointerId);
      opts.drag(last, null, true); e.preventDefault();
    });
    d.addEventListener('pointermove', e => {
      if (!last) return;
      const p = stagePt(e);
      opts.drag(p, { dx: p.x - last.x, dy: p.y - last.y }, false);
      last = p;
    });
    const up = e => { last = null; try { d.releasePointerCapture(e.pointerId); }
                      catch (_) { } };
    d.addEventListener('pointerup', up);
    d.addEventListener('pointercancel', up);
  }
  return d;
}

/* Track 01 owns live3d/api.js.  This close-up POSTs /api/interact itself and
 * does not open a second client shape. */
async function interact(action, params) {
  try {
    const r = await fetch('/api/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: CODE, action, params: params || {} }),
    });
    let d = null;
    try { d = await r.json(); } catch (_) { d = null; }
    if (d && d.result) return d.result;
    if (d) return d;
    return { ok: false, error: 'HTTP ' + r.status };
  } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
}

/* ---- WHAT THE BEACON SAID.  Every reply lands in three places: the QNAME
 * strip (one line), the star chart drum (the answer section, paged three lines
 * to a facet) and the chart card's printout (the whole reply). */
const LOOK_TYPES = P.qtype.states.filter(q => q !== 'AXFR' && q !== NX_STATE);
const ZONE = 'example.com';
const RECENT_MAX = 24;
const recent = [];           // { name, type, rcode, answers, summary }
let recentSel = -1;
let zoneRecords = null;      // record count from the last import / reload

function pagesFromLines(lines) {
  const pages = [];
  let i = 0;
  for (let f = 0; f < P.chart.facets; f++) {
    const pg = [];
    for (let r = 0; r < N_CHART_LINES; r++, i++)
      pg.push(clipTo(lines[i] || '', N_CHART_COLS));
    pages.push(pg);
  }
  return pages;
}

/* one drum line per record, in the chart's own upper-case house style:
 * owner (first label, or @ at the apex), type, value */
function rrLine(a) {
  const owner = String((a && a.name) || '').replace(/\.$/, '').toLowerCase();
  const host = (owner === ZONE ? '@' : owner.split('.')[0].toUpperCase()) || '@';
  const t = String((a && a.type) || '');
  const v = String((a && a.value) || '').toUpperCase();
  return clipTo(host.slice(0, 5).padEnd(6) + t.slice(0, 5).padEnd(6) + v, N_CHART_COLS);
}

/* the drum carries the plot log, newest first: a heading per lookup, then
 * its records, until the six facets are full */
function chartFromRecent() {
  const lines = [];
  for (const e of recent) {
    const head = e.name.replace(/\.$/, '').toUpperCase() + ' ' + e.type;
    lines.push(clipTo('> ' + head, N_CHART_COLS));
    if (e.answers.length) for (const a of e.answers) lines.push(rrLine(a));
    else lines.push(clipTo('  ' + (e.rcode || 'NO REPLY'), N_CHART_COLS));
    if (lines.length >= P.chart.facets * N_CHART_LINES) break;
  }
  return pagesFromLines(lines);
}

function querySummary(result) {
  if (!result) return 'NO REPLY';
  if (!result.ok) return clipTo('FAULT ' + (result.error || ''), N_QUERY);
  if (result.rcode === 'NXDOMAIN') return 'NXDOMAIN  NO SUCH NAME';
  const answers = result.answers || [];
  const qt = String(result.query || '').split(' ').pop() || SES.qtype;
  const hit = answers.find(a => a.type === qt) || answers[0];
  if (hit) return clipTo(('QT ' + qt).padEnd(10) + String(hit.value || '').toUpperCase(), N_QUERY);
  return clipTo((result.rcode || 'NOERROR') + ' NO RECORDS', N_QUERY);
}

/* the printout, dig-style: one line per record with its ttl */
function printLookup(e) {
  const out = [{ t: '; ' + e.name + '  ' + e.type, c: 'sent' }];
  if (e.error) { out.push({ t: e.error, c: 'bad' }); return out; }
  const n = e.answers.length;
  out.push({ t: ';; ' + (e.rcode || '?') + ', ' + n + (n === 1 ? ' record' : ' records'),
             c: e.rcode === 'NOERROR' ? '' : 'bad' });
  for (const a of e.answers)
    out.push({ t: String(a.name || '') + '.  ' + (a.ttl != null ? a.ttl : '') + '  '
                  + a.type + '  ' + a.value, c: '' });
  return out;
}

/* ---- THE CHART CARD's own surfaces */
function setReply(msg, cls) {
  const el = $('cardReply');
  el.textContent = msg || '';
  el.className = cls || '';
}
function setPrintout(rows) {
  const pre = $('cardLines');
  pre.textContent = '';
  if (!rows || !rows.length) {
    const s = document.createElement('span');
    s.className = 'empty';
    s.textContent = 'Replies print here.';
    pre.appendChild(s);
    return;
  }
  rows.forEach((r, i) => {
    const s = document.createElement('span');
    if (r.c) s.className = r.c;
    s.textContent = r.t + (i < rows.length - 1 ? '\n' : '');
    pre.appendChild(s);
  });
  pre.scrollTop = 0;
}
function paintZone() {
  $('cardZone').textContent = ZONE + (zoneRecords == null ? ''
    : ' · ' + zoneRecords + (zoneRecords === 1 ? ' record' : ' records'));
}
function paintRecent() {
  const box = $('cardRecent');
  box.textContent = '';
  $('cardCount').textContent = recent.length ? String(recent.length) : '';
  if (!recent.length) {
    const d = document.createElement('div');
    d.className = 'empty';
    d.textContent = 'No lookups yet.';
    box.appendChild(d);
    return;
  }
  recent.forEach((e, i) => {
    const d = document.createElement('div');
    d.setAttribute('role', 'option');
    d.setAttribute('aria-selected', String(i === recentSel));
    if (i === recentSel) d.className = 'on';
    d.textContent = e.type.padEnd(6) + e.name + '  ' + (e.answers.length ? e.answers.length + ' rr'
      : (e.rcode || 'fault').toLowerCase());
    d.addEventListener('click', () => replot(i));
    box.appendChild(d);
  });
}
function paintCardType() {
  $('cardType').value = LOOK_TYPES.includes(SES.qtype) ? SES.qtype : 'A';
  $('cardRcode').textContent = SES.lastRcode || '';
}

/* ---- REQUESTS */
let busy = { query: false, import: false, reload: false };

/* one lookup.  The beacon sweeps while it is out; the drum rolls back to its
 * first facet when the reply lands. */
async function fireQuery() {
  if (busy.query) return;
  const name = String(SES.qname || '').trim();
  if (!name) { setReply('Type a name to look up.', 'err'); return; }
  busy.query = true;
  SES.queryEdit = false;
  SES.pinging = true;
  const qtype = LOOK_TYPES.includes(SES.qtype) ? SES.qtype : 'A';
  SES.lastSummary = clipTo('QT ' + qtype + '  ' + name.toUpperCase(), N_QUERY);
  paintAll();
  $('cardLook').disabled = true;
  setReply('Looking up ' + name + ' ' + qtype + '...', 'busy');
  try {
    const result = await interact('query', { name, type: qtype });
    const e = {
      name, type: qtype,
      rcode: (result && result.rcode) || null,
      answers: (result && result.ok && result.answers) || [],
      error: result && !result.ok ? (result.error || 'no reply') : null,
    };
    recent.unshift(e);
    if (recent.length > RECENT_MAX) recent.length = RECENT_MAX;
    recentSel = 0;
    SES.lastRcode = e.rcode;
    SES.lastSummary = querySummary(result);
    SES.chartLive = chartFromRecent();
    SES.chartTarget = 0;
    paintLamps();
    paintAll();
    paintRecent();
    paintCardType();
    setPrintout(printLookup(e));
    if (e.error) setReply(e.error, 'err');
    else setReply(e.rcode === 'NOERROR' ? (e.answers.length + (e.answers.length === 1 ? ' record' : ' records'))
                  : e.rcode === 'NXDOMAIN' ? 'No such name in the chart.' : String(e.rcode),
                  e.rcode === 'NOERROR' ? 'ok' : 'err');
  } finally {
    SES.pinging = false;
    $('cardLook').disabled = false;
    busy.query = false;
  }
}

function replot(i) {
  const e = recent[i];
  if (!e) return;
  recentSel = i;
  setQname(e.name);
  setQtype(e.type);
  fireQuery();
}

function recordsFrom(msg) {
  const m = /(\d+) records/.exec(msg || '');
  return m ? +m[1] : null;
}

/* the courier: the card is pushed home while the beacon reads it, and comes
 * back to the mouth when it answers */
async function adminCall(action, params, what) {
  if (busy[action]) return null;
  busy[action] = true;
  $('recSend').disabled = $('recReload').disabled = true;
  setCourier('import');
  setReply(what + '...', 'busy');
  try {
    const result = await interact(action, params);
    const msg = (result && (result.summary || result.error)) || 'no reply';
    const n = recordsFrom(result && result.summary);
    if (n != null) zoneRecords = n;
    paintZone();
    SES.lastSummary = clipTo(!(result && result.ok) ? 'FAULT ' + msg
      : n == null ? msg.toUpperCase()
      : (action === 'reload' ? 'RELOADED' : 'CHART IN').padEnd(10) + n + ' RR', N_QUERY);
    SES.queryEdit = false;
    paintAll();
    setPrintout([{ t: '; ' + what.toLowerCase(), c: 'sent' },
                 { t: msg, c: result && result.ok ? '' : 'bad' }]);
    setReply(result && result.ok ? 'Chart accepted.' : msg, result && result.ok ? 'ok' : 'err');
    return result;
  } finally {
    setCourier('chart');
    $('recSend').disabled = $('recReload').disabled = false;
    busy[action] = false;
  }
}

function hasRecords(text) {
  return String(text).split('\n').some(l => {
    const s = l.replace(/;.*/, '').trim();
    return s && s[0] !== '$';
  });
}
async function fireImport() {
  const body = $('recText').value;
  if (!hasRecords(body)) { setReply('Add a record line first.', 'err'); return; }
  const r = await adminCall('import', { body }, 'Sending the chart');
  if (r && r.ok) $('recNote').textContent = 'sent';
}
async function fireReload() {
  const r = await adminCall('reload', {}, 'Reloading the zone file');
  if (r && r.ok) $('recNote').textContent = 'zone file reloaded';
}

/* compose one zone line from the record row and add it to the chart text */
function addRecord() {
  const name = $('recName').value.trim() || '@';
  const type = $('recType').value;
  let val = $('recVal').value.trim();
  if (/\s/.test(name)) { setReply('A name has no spaces.', 'err'); return; }
  if (!val) { setReply('Type a value for the record.', 'err'); $('recVal').focus(); return; }
  if (type === 'TXT' && !/^".*"$/.test(val)) val = '"' + val.replace(/"/g, '\\"') + '"';
  const ta = $('recText');
  const cur = ta.value.replace(/\s*$/, '');
  ta.value = (cur ? cur + '\n' : '') + name.padEnd(8) + ' ' + type.padEnd(6) + ' ' + val + '\n';
  ta.scrollTop = ta.scrollHeight;
  $('recVal').value = '';
  $('recNote').textContent = 'line added, not sent';
  setReply('');
  $('recVal').focus();
}

function beginQueryEdit() {
  SES.queryEdit = true;
  SES.lastSummary = null;
  paintAll();
}
function setQname(v) {
  SES.qname = String(v == null ? '' : v).slice(0, 253);
  if ($('cardName').value !== SES.qname) $('cardName').value = SES.qname;
}

function queryHotRect() {
  const c = S.text_planes[PLANE_OF.query].corners_px;
  const xs = [c.tl.x, c.tr.x, c.bl.x, c.br.x];
  const ys = [c.tl.y, c.tr.y, c.bl.y, c.br.y];
  const x = Math.floor(Math.min.apply(null, xs));
  const y = Math.floor(Math.min.apply(null, ys));
  return { x, y,
    w: Math.ceil(Math.max.apply(null, xs) - x),
    h: Math.ceil(Math.max.apply(null, ys) - y) };
}

/* a hotspot that the keyboard can reach: Tab to it, Enter or Space acts */
function buttonHot(h, act) {
  h.tabIndex = 0;
  h.setAttribute('role', 'button');
  h.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    ev.preventDefault();
    act();
  });
}

/* ---- HELD PAPER.  The chart card is DOM in a second CSS3D layer, laid on
 * the console face basis.  Its `k` runs 0..1: 0 is tucked into the courier
 * slot, 1 is held up toward the camera over the right of the desk.  onFrame()
 * eases k toward `want`; no timers. */
const TPQ = S.text_planes[PLANE_OF.query];
const FACE_U = V3(TPQ.u), FACE_V = V3(TPQ.v), FACE_N = V3(TPQ.n);
const held = new CSS3DLayer($('held'), W, H);
const CARD = { el: $('dnsmCard'), w: 560, h: 700, k: 0, want: 0 };
CARD.rec = held.add(CARD.el);
const REF_D = camera.position.distanceTo(V3(TPQ.origin));
/* A pose that lands the element's centre on stage pixel (x, y), `w` px wide,
 * at `depth` x the QNAME strip's own distance from the camera. */
function heldPose(at, elW, depth) {
  const p = new THREE.Vector3((at.x / W) * 2 - 1, -(at.y / H) * 2 + 1, 0.5).unproject(camera);
  const dir = p.sub(camera.position).normalize();
  const D = REF_D * depth;
  const o = camera.position.clone().addScaledVector(dir, D);
  const perPx = 2 * D * Math.tan(camera.fov * D2R / 2) / H;
  return { o, m: at.w * perPx / elW };
}
const CH = P.courier.hotspot;
const CARD_REST = heldPose({ x: CH.x + CH.w / 2, y: CH.y + CH.h / 2, w: 120 }, CARD.w, 1.04);
const CARD_UP = heldPose({ x: 1106, y: 352, w: 336 }, CARD.w, 0.86);
const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function tickHeld(dt) {
  if (CARD.k !== CARD.want) {
    const step = dt * 4;
    CARD.k = CARD.want > CARD.k ? Math.min(CARD.want, CARD.k + step)
                                : Math.max(CARD.want, CARD.k - step);
    if (CARD.k === 0) CARD.el.hidden = true;
  }
  if (!CARD.el.hidden) {
    const e = ease(CARD.k), m = CARD_REST.m + (CARD_UP.m - CARD_REST.m) * e;
    CARD.el.style.opacity = String(Math.min(1, e * 2.5));
    CARD.rec.matrix = new THREE.Matrix4().makeBasis(
      FACE_U.clone().multiplyScalar(m), FACE_V.clone().multiplyScalar(m), FACE_N)
      .setPosition(CARD_REST.o.clone().lerp(CARD_UP.o, e));
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

/* ---- the card: slide it out / put it back, which face is up, and where
 * focus goes back to */
let cardOpener = null, courierHot = null;
function showFace(which) {
  const look = which !== 'records';
  $('faceLookup').hidden = !look;
  $('faceRecords').hidden = look;
  $('tabLookup').setAttribute('aria-selected', String(look));
  $('tabRecords').setAttribute('aria-selected', String(!look));
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
      ? cardOpener : courierHot;
    cardOpener = null;
    focusStill(back);
  }
}

/* ---- HOTSPOTS */

/* the beacon: grab it to slew by hand, double-click to let it run again.
 * Letting go after a drag, or a click that is not a drag, sends the lookup. */
const sweepHot = hotspot(P.sweep.hotspot, P.sweep.label + ' — send the lookup', {
  drag: (p) => {
    SES.spin = false;
    const a = -Math.atan2(p.x - P.sweep.pivot_px.x,
                          p.y - P.sweep.pivot_px.y) / D2R + 180;
    SES.sweepDeg = a > 180 ? a - 360 : a;
  },
});
sweepHot.addEventListener('pointerup', () => { fireQuery(); });
sweepHot.addEventListener('dblclick', () => { SES.spin = true; });
buttonHot(sweepHot, () => fireQuery());

/* the lamp row picks the record type -- NOT the scope face, which the beacon
 * sweeps end to end (BRIEF section 6: values do not go on a surface a control
 * persistently sweeps, and neither does the affordance for changing them).
 * Only the six lookup types answer a click; the last lamp (NX) is the miss
 * telltale. */
hotspot(P.qtype.hotspot, P.qtype.label + ' — pick the record type', {
  click: (ev) => {
    const p = stagePt(ev);
    const f = clamp((p.x - P.qtype.hotspot.x) / P.qtype.hotspot.w, 0, 0.999);
    const q = P.qtype.states[Math.floor(f * P.qtype.states.length)];
    if (!LOOK_TYPES.includes(q)) return;
    setQtype(q);
  },
});

/* drag the window to roll the catalogue drum */
hotspot(P.chart.hotspot, P.chart.label + ' — drag to read the replies', {
  drag: (p, d) => {
    if (!d) return;
    SES.chartTarget = null;
    SES.chartDeg -= d.dy * 0.55;
    while (SES.chartDeg > 180) SES.chartDeg -= 360;
    while (SES.chartDeg < -180) SES.chartDeg += 360;
  },
});

/* the courier slot: the chart card slides out of it */
courierHot = hotspot(P.courier.hotspot, P.courier.label + ' — take out the chart card', {
  click: () => openCard(null),
});
buttonHot(courierHot, () => openCard(null));

/* QNAME on the existing 22-col query plane. Enter sends. */
const qnameHot = hotspot(queryHotRect(), 'QNAME — type a name, Enter looks it up', {
  click: (ev) => { ev.currentTarget.focus(); beginQueryEdit(); },
});
qnameHot.tabIndex = 0;
qnameHot.addEventListener('paste', (ev) => {
  ev.preventDefault();
  const t = (ev.clipboardData && ev.clipboardData.getData('text')) || '';
  if (!t) return;
  beginQueryEdit();
  setQname(SES.qname + t.replace(/[\r\n\t]/g, ''));
  paintAll();
});
qnameHot.addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter') {
    ev.preventDefault();
    fireQuery();
    return;
  }
  if (ev.key === 'Escape') {
    ev.currentTarget.blur();
    SES.queryEdit = false;
    paintAll();
    return;
  }
  if (ev.key === 'Backspace') {
    ev.preventDefault();
    beginQueryEdit();
    setQname(SES.qname.slice(0, -1));
    paintAll();
    return;
  }
  if (ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
    ev.preventDefault();
    beginQueryEdit();
    setQname(SES.qname + ev.key);
    paintAll();
  }
});
qnameHot.addEventListener('blur', () => {
  if (SES.queryEdit) { SES.queryEdit = false; paintAll(); }
});

/* ---- the card's own controls */
{
  for (const sel of ['cardType', 'recType']) {
    for (const q of LOOK_TYPES) {
      const o = document.createElement('option');
      o.value = o.textContent = q;
      $(sel).appendChild(o);
    }
  }
  const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
  on('cardClose', 'click', () => closeCard());
  on('tabLookup', 'click', () => showFace('lookup'));
  on('tabRecords', 'click', () => showFace('records'));
  on('cardName', 'input', () => { setQname($('cardName').value); SES.queryEdit = false; paintAll(); });
  on('cardName', 'keydown', ev => {
    if (ev.key === 'Enter' && !ev.repeat) { ev.preventDefault(); fireQuery(); }
  });
  on('cardType', 'change', () => setQtype($('cardType').value));
  on('cardLook', 'click', () => fireQuery());
  on('recAdd', 'click', () => addRecord());
  on('recVal', 'keydown', ev => {
    if (ev.key === 'Enter' && !ev.repeat && !(ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); addRecord(); }
  });
  on('recText', 'input', () => { $('recNote').textContent = 'not sent'; });
  on('recSend', 'click', () => fireImport());
  on('recReload', 'click', () => fireReload());
  /* arrow keys walk the plot log; Enter plots the highlighted lookup again */
  on('cardRecent', 'keydown', ev => {
    if (!recent.length) return;
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      recentSel = Math.max(0, Math.min(recent.length - 1,
        recentSel + (ev.key === 'ArrowDown' ? 1 : -1)));
      paintRecent();
      const row = $('cardRecent').children[recentSel];
      if (row) row.scrollIntoView({ block: 'nearest' });
      resetClipScroll();
    } else if (ev.key === 'Enter' && recentSel >= 0) {
      ev.preventDefault(); replot(recentSel);
    }
  });
  /* Ctrl/Cmd+Enter sends the chart text on the RECORDS face */
  on('cardBody', 'keydown', ev => {
    if (ev.key !== 'Enter' || ev.repeat || !(ev.ctrlKey || ev.metaKey)) return;
    ev.preventDefault();
    if ($('faceRecords').hidden) fireQuery(); else fireImport();
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

const REC_SEED = '$ORIGIN ' + ZONE + '.\n';
function resetCard() {
  CARD.want = CARD.k = 0;
  CARD.el.hidden = true;
  showFace('lookup');
  recent.length = 0; recentSel = -1;
  zoneRecords = null;
  for (const id of ['recName', 'recVal']) $(id).value = '';
  $('recType').value = 'A';
  $('recText').value = REC_SEED;
  $('recNote').textContent = '';
  setQname(SES.qname);
  paintCardType();
  paintRecent();
  paintZone();
  setPrintout(null);
  setReply('');
}
resetCard();

/* ---------------------------------------------------------------- TODO 5 */
/* THE RESTING STATE THE HARNESS SCORES.  Deterministic by construction: this
 * page starts NO setInterval and NO setTimeout at all -- the beacon is driven
 * from the rAF loop the template already runs, and pose() clears the one flag
 * that makes it move.  Two consecutive captures are byte-identical.
 *
 * The pose comes out of scene.json, so this function and the exporter cannot
 * disagree about which frame gt_full_read.png was rendered in. */
function poseForCapture() {
  /* HIDE BOTH FITTINGS.  Every number in live3d/RESULTS.md and in this
   * module's NOTES was captured from pose() against Blender renders that
   * contain neither, so hiding them reproduces all of them unchanged and
   * re-renders nothing -- including the 407,640 triangles of content type
   * DNSM bakes into plate.png.  FIX_UPLOAD section 0 decision 3;
   * STATUS_AT_A_GLANCE 6.5 item 1.  Each fitting's own behaviour is measured
   * with it SHOWN -- __refit.show(true) / __mast.show(true) -- which is a
   * separate capture, and that capture is byte-identical to the pre-build
   * baseline at pixelRatio 1 and 2, section 0 included. */
  if (refit) refit.pose();
  if (mast) mast.pose();
  SES.spin = false;
  SES.pinging = false;
  SES.posed = true;
  SES.sweepDeg = S.pose.sweep_deg;
  SES.chartDeg = S.pose.chart_deg;
  SES.chartTarget = null;
  SES.lastRcode = null;
  SES.lastSummary = null;
  SES.queryEdit = false;
  SES.chartLive = null;
  busy.query = busy.import = busy.reload = false;
  /* the card goes back into the slot, blank */
  resetCard();
  tickHeld(0);
  setQtype(S.pose.qtype);
  setCourier(S.pose.courier);
  placeSweep(); placeDrum(); placeCard();
  paintAll();
  checkReadoutText();
}

/* the load-time state IS the posed state except for the beacon, which turns on
 * its own -- MQB's case, section 0 of check_occlusion.py, and legitimate */
setQtype(SES.qtype);
setCourier(SES.courier);
placeSweep(); placeDrum(); placeCard();

/* ---- THE REFIT PORT -------------------------------------------------------
 * Nine lines, and none of them is DNSM-specific: the anchor, the size, the
 * part names, the leaf pivots and the hotspot all come out of
 * `scene.json -> refit`, which pipeline/refit_port.py wrote.  It bolts to the
 * SHIP STRUCTURE beside the instrument -- the desk the panel hangs in front
 * of, at (170, 600) -- never to the panel's faceplate, so no control moves
 * and no readout plane moves.  It declares NO readout plane: all of its text
 * is the screen-space docket, so check_occlusion.py question 5, the dial-face
 * rule and check_text.py are NOT ENGAGED by it.  `readouts.length` is still
 * 8, six of them one rotating drum.
 *
 * `hotspot` is passed exactly as this page defines it.  DNSM's is the fleet's
 * FOURTH convention -- `(rect, label, {click, drag})`, an options OBJECT --
 * and it is the one that used to register ZERO CLICKS WITH NO ERROR AT ALL:
 * the fitting was simply dead and nothing said so.  refit.js's shared
 * wireHotspot() adapter detects the convention behaviourally and handles all
 * four.  Do not hand-roll an adapter here (FIX_UPLOAD 12.15 item 1).
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
 * The same nine lines, and none of them is DNSM-specific either.  See
 * export_dnsm.py's DNSM_MAST block for where it went and why: the sill arm of
 * the same desk plane the port is on, on the `--at` route because the port's
 * service rail would run straight into the faceplate.
 *
 * It declares NO readout plane.  Its words are the screen-space caption and
 * detail panel in live3d/mast.css, the same class of thing as the port's
 * docket.  `readouts.length` is still 8.
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

/* MODULE-PRIVATE hooks, ALONGSIDE __occ and never instead of it.  The fleet
 * harness drives __occ only; these are for reading DNSM's own numbers off the
 * real page instead of arguing about them. */
window.__dnsm = {
  facing: () => facingAudit(camera),
  tris: () => TRIS,
  state: () => JSON.parse(JSON.stringify(SES)),
  set: (k, v) => {
    if (k === 'qtype') setQtype(v);
    else if (k === 'courier') setCourier(v);
    else if (k === 'qname') { setQname(v); paintAll(); }
    else {
      SES[k] = v;
      if (k === 'lastRcode') paintLamps();
      paintAll();
    }
  },
  query: () => fireQuery(),
  importZone: () => fireImport(),
  reload: () => fireReload(),
  /* the chart card: card() reads it, card(true|false, face) lifts or drops it */
  card: (v, face) => {
    if (v !== undefined) { if (v) openCard(face || 'lookup'); else closeCard(); }
    return { k: CARD.k, want: CARD.want, face: $('faceRecords').hidden ? 'lookup' : 'records' };
  },
  recent: () => JSON.parse(JSON.stringify(recent)),
  planeO: () => readouts.map(r => r.plane.o.toArray()),
  planeN: () => readouts.map(r => r.plane.n.toArray()),
  enabledPlanes: () => readouts.map(r => r.plane.enabled),
  backFacing: () => readouts.map(r => r.back),
  /* the SHARED cull's own class (css3d.js), so backFacing() vs domCulled()
   * is still the cross-check between this module's normal test and the
   * layer's.  It was `.away` -- this module's own class -- until the shared
   * cull landed and the local one was deleted. */
  domCulled: () => readouts.map(r => r.el.classList.contains('css3d-back')),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's own derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
};

$('note').textContent =
  CODE + ' · ' + SCENE + ' · ' + TRIS + ' live tris · '
  + readouts.length + ' planes (6 drum facets) · gain '
  + S.light_gain + ' · uBias ' + (S.ubias_m * 1000).toFixed(3) + ' mm';
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
layout();
/* One-sided geometry that FrontSide has deleted.  Console warning only; it is
 * not part of __occ.audit(), which means something else and must stay []. */
facingAudit(camera);
/* This page rests UNPOSED, and mountRefit()/mountMast() already end in
 * show(true).  These two lines are the fleet's own statement of the invariant
 * that matters: the page a human opens must SHOW both fittings, or it is not
 * the page this file describes.  check_occlusion.py's section 0 reports the
 * difference between the as-loaded and the posed frames, and that section is
 * REPORTED, NOT FAILED ON, for exactly this case. */
if (refit) refit.show(true);
mast.show(true);
requestAnimationFrame(frame);
window.__loaded = true;
