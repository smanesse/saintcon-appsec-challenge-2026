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
/* THE TELLTALE MAST.  live3d/mast.js is shared by all nine modules and reads
 * everything it needs out of `scene.json -> mast`, which
 * pipeline/status_mast.py wrote.  live3d/design/STATUS_AT_A_GLANCE.md section
 * 6 is the design and section 8 is PKT's own variant of it. */
import { mountMast } from '../../mast.js';
/* A.L.I.E.N. ship roster — just the bearings/names for the four hulls, so the
 * harpoon can aim at the ship chosen in the fleet-scoring form. (The old
 * interactive packet campaign was removed; alien-campaign.js is kept only for
 * this ship metadata.) */
import { SHIPS as ALIEN_SHIPS } from '../../alien-campaign.js';
/* A.L.I.E.N. FLEET SCORING is the weapons console's one job: edit the exploit
 * stub on disk, then test it locally or submit it for scoring. The harpoon is
 * its fire control — selecting a ship aims it, and a result plays the reel /
 * impact animation. Same-origin /api/* via api.js. */
import { mountAlienSubmit } from '../../alien-submit.js';

/* ===================================================================== 0 */
/* WHICH MODULE.  Change this one string and the asset paths follow.        */
const CODE = 'PKT';                     // the Signal Harpoon
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
  /* PER MODULE, AND MEASURED -- `scene.json -> ubias_m`, like every other
   * module.  This page used to carry the template's old 0.002 default here and
   * override it to 0.0008 below the MODULE WORK line, which is the one place
   * nobody looking at scene.json would find it.  See the DEPTH BIAS comment
   * in M0 for what 2 mm cost PKT. */
  uBias: { value: (typeof S.ubias_m === 'number') ? S.ubias_m : 0.0005 },
  uEnable: { value: 1 },
};
if (typeof S.ubias_m !== 'number')
  console.warn('scene.json has no `ubias_m`: the depth composite is running ' +
    'on a 0.5 mm guess.');
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


/* PKT — "The Signal Harpoon", the packet transmitter.  The one OFFENSIVE
 * console on the dash: it sends packets OUT at automated systems in the void
 * (derelicts, unmanned relays, listening posts) and reels back whatever they
 * answer.  There is no inbound channel and there are no other players here;
 * the defensive loop — automated tests against the pilot's own eight modules —
 * is a different panel entirely.
 *
 * LIVE (seven glbs, 214 meshes — the page counts the triangles at runtime out
 * of the loaded index accessors and prints them in the toolbar):
 *   target.glb   the knurled azimuth hand-wheel and its index pointer, turning
 *                about the raked console face's own normal.
 *   payload.glb  the 8-chamber munition drum.  SHIPPED AS `kind: frames`, eight
 *                baked stills 45 deg apart, and frames are a baked
 *                approximation of movement (BRIEF step 2 rule 1) — so it is now
 *                one drum on a continuous angle, and the eight `pkt_payload_txt`
 *                FONT objects it carried collapse into ONE DOM readout.
 *   charge.glb   the capacitor lever (5 baked frames -> a continuous slide up
 *                the face), the four vacuum tubes (five declared emissive
 *                materials, `tube_lv`) and the five redline pips (declared
 *                off/on pairs).
 *   arm.glb      the red break-glass cage and the master-arm toggle, both
 *                hinging about the root's +X, plus two lamps with declared
 *                off/on pairs.
 *   fire.glb     the plunger, sliding along the face normal, and the muzzle
 *                flash at the bore.
 *   catch.glb    the return-line platen (4 baked frames -> a continuous paper
 *                advance) and the two spools that reel it in.
 *   verdict.glb  the three IMPACT lamps and the tinted header bar, which is
 *                the one live object that is IN FRONT OF a declared readout in
 *                the module's own authoring — see M2 and NOTES.md section 4.
 *
 * BAKED: all 280 static objects plus the shell.  The plate carries correct
 * pixels behind every live object: the wheel well, the drum well, the breech
 * window, the lever slot, the arm plate, the fire well, the machine interior
 * behind the platen and the header bar's chrome surround.
 *
 * DOM (four readout planes): the contact designation on the scope's band, the
 * seated munition class in the breech window, the return-line printout in the
 * aperture, and the impact verdict on the header bar.  ALL FOUR carry bytes
 * that in the real product come back off the wire from a target service, so
 * every one of them is written with textContent and there is NO innerHTML in
 * this file, in the exporter, or anywhere PKT owns.
 */

const P = S.props;
const V = a => new THREE.Vector3().fromArray(a);

/* -------------------------------------------------------- THE DEPTH BIAS
 * BRIEF trap 24 -- "uBias is 2 mm ... a module whose prop sits less than 2 mm
 * proud of a baked surface will lose that prop into the plate ... the failure
 * mode looks like 'the prop is a bit small', not like an error."  PKT is the
 * module where it bites, and it is not subtle: `pkt_hdr_bar`, the tinted
 * verdict header, stands 1.15 mm proud of `pkt_hdr_frame`, which is BAKED, so
 * `vLinDepth > baked - uBias` discards the ENTIRE 208 x 20 px emissive strip
 * into the plate.  No error, no console warning, auditScene() clean, and the
 * page simply shows the dark frame where the lit bar should be.
 *
 * Measured on this page (NOTES.md 5.3), compare.py against Blender, at the
 * time this module was converted:
 *     uBias 0.0020 (the template's default)  rms 15.905   <- bar discarded
 *     uBias 0.0010                           rms 10.180
 *     uBias 0.0008 (then shipped)            rms 10.177
 *     uBias 0.0005                           rms 10.172
 *     uBias 0.0                              rms 10.163
 *
 * THE VALUE IS NOW IN `scene.json -> ubias_m` AND IS 0.000840, not 0.0008.
 * `DU.uBias.value = 0.0008` used to be set on this line, below the MODULE WORK
 * line -- the one place a reader of scene.json would never find it, and the
 * reason the fleet's ubias table listed PKT as "sets it in module.js rather
 * than in scene.json".  0.0008 was 0.7 x a HAND-measured 1.15 mm stand-off;
 * `live3d/pipeline/live_depth.py` rasterises the shipped glbs against the
 * shipped depth.bin and finds a 4,390-px PLATEAU at 1.200 mm -- 6.0% of the
 * live-nearer set, which is the header bar itself -- so 0.7 x 1.200 mm =
 * 0.000840.  Two independent methods 4% apart, and the re-swept cliff is
 * between 0.0010 (rms 9.895) and 0.0015 (rms 15.730), so the shipped value
 * still clears it by 40%.
 */
const KEYS = ['target', 'payload', 'charge', 'arm', 'fire', 'catch', 'verdict'];

/* ------------------------------------------------------------ M1: PROPS */
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

/* Which `patched` record belongs to which material, so a state swap can update
 * the record as well as the material.  Without this, applyMatFix() would put
 * the ORIGINAL roughness/metalness back over a swapped lamp the next time the
 * materials.json A/B is toggled — silently, and only after a toggle. */
const patchOf = new Map();
for (const rec of patched) patchOf.set(rec.m, rec);

/* Apply a Blender material, BY NAME, out of materials.json.  This is how a
 * `states` control changes material state at runtime: the module declares the
 * pairs (`off[i]`/`on[i]`, `tube_lv[]`, `hdr_mats{}`) and the exporter writes
 * their NAMES, so the frontend never invents a colour.  Note it MUTATES the
 * material dress() already cloned per-mesh and already put through
 * attachDepthTest + attachForeground, so the split is untouched — cloning a
 * fresh material here would produce an UNATTACHED one that draws in both
 * passes and double-blends (BRIEF trap 15). */
function setMat(mesh, name) {
  const rec = MJ[name];
  const m = mesh.material;
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
  if (p) { p.rec = rec; }
  m.roughness = rec.rough;
  m.metalness = rec.metallic;
}

/* every glb is exported in WORLD coordinates, so re-parenting a named object
 * into a group that starts at the identity keeps it exactly where it was. */
function pick(g, names) {
  return names.map(n => g.scene.getObjectByName(n)).filter(Boolean);
}
function slider(objs) {                  // a group that TRANSLATES
  const grp = new THREE.Group();
  scene.add(grp);
  for (const o of objs) grp.add(o);
  return grp;
}
function hinge(hubArr, objs) {           // a group that ROTATES about a hub
  const r = pivotAt(hubArr);
  for (const o of objs) r.inner.add(o);
  return r;
}

const wheel = pivotAt(P.target.hub);
wheel.inner.add(G.target.scene);
const drum = pivotAt(P.payload.hub);
drum.inner.add(G.payload.scene);
scene.add(G.charge.scene);
const lever = slider(pick(G.charge, P.charge.lever));
const tubes = pick(G.charge, P.charge.tubes);
const pips = pick(G.charge, P.charge.pips);
scene.add(G.arm.scene);
const cage = hinge(P.arm.cage_hinge, pick(G.arm, P.arm.cage));
const toggle = hinge(P.arm.toggle_hinge, pick(G.arm, P.arm.toggle));
const armLamps = pick(G.arm, P.arm.lamps);
scene.add(G.fire.scene);
const plunger = slider(pick(G.fire, P.fire.plunger));
const flash = pick(G.fire, P.fire.flash);
scene.add(G.catch.scene);
const platen = slider(pick(G.catch, P.catch.platen));
const spools = P.catch.spools.map((names, i) =>
  hinge(P.catch.spool_hubs[i], pick(G.catch, names)));
scene.add(G.verdict.scene);
const vrdLamps = pick(G.verdict, P.verdict.lamps);
const hdrBar = G.verdict.scene.getObjectByName(P.verdict.hdr);

/* Every rotation in this module is about the RAKED CONSOLE FACE's own normal
 * (44 deg off the slot plane), except the arm cage and toggle, which hinge
 * about the root's +X and commute with the rake.  `spin_axis` is the face
 * normal NEGATED, so a POSITIVE angle is a CLOCKWISE turn on screen — the
 * direction the engraved bearing arc runs and the direction the module's own
 * demo turns the wheel.  Rotating about the SLOT's +Z instead would sweep a
 * cone; that is the measurement bug the occlusion audit had to fix, and no
 * module declares `axis` on a `rotate` control. */
const SPIN = V(S.panel.spin_axis).normalize();
const SPOOLAX = V(P.catch.spool_axis).normalize();
const UPAX = V(P.charge.up_axis).normalize();
const NRMAX = V(P.fire.normal_axis).normalize();
const HINGEAX = V(P.arm.hinge_axis).normalize();

/* ------------------- per-plane ink and column counts, from the exporter ---
 * Four readouts, four measured ink colours (BRIEF section 7 rule 7: the median
 * over alpha > 0.5 of Blender's own render of THAT readout's own type with
 * THAT readout's own material, no colour transform).  They are genuinely
 * different — emissive phosphor green, amber on the lit breech, dark ink on
 * paper — so one "warm grey" would have been wrong three times.
 * Alignment and every type metric come from layoutType(); nothing here
 * re-implements the type path. */
const RO = {};
readouts.forEach((r, i) => {
  const tp = PLANES[i];
  RO[tp.name] = r;
  if (tp.ink) r.el.style.color = 'rgb(' + tp.ink.join(',') + ')';
});
const COLS = {};
const NLINES = {};
for (const tp of PLANES) {
  COLS[tp.name] = (tp.type && tp.type.n_cols) || 24;
  NLINES[tp.name] = (tp.type && tp.type.n_lines) || 1;
}

$('note').textContent =
  Math.round(liveTris) + ' tris · ' + liveMeshes + ' meshes · ' +
  S.lights.length + ' lights · ' + PLANES.length + ' planes';

/* ------------------------------------------- M2: THE SESSION MODEL
 * PKT's protocol is one shot at a time: sweep the bearing until a contact
 * locks, index a munition class into the breech, spool the capacitor bank,
 * throw the master arm, fire, and read whatever the target sends back down the
 * return line.
 *
 * THE TARGETS ARE THE LOCAL A.L.I.E.N. TEACHING SHIPS (ports 8091–8094), not
 * other players. Nothing fires back.
 *
 * THE RETURNED BYTES ARE UNTRUSTED.  They are rendered as TEXT — textContent,
 * through the template's r.paint() — and never as markup.  `paper()` below
 * wraps and folds them to the platen's own 28 columns and maps control bytes
 * to '.', which is a LAYOUT concern ONLY: the safety is textContent, not the
 * filter, and the filter must never be mistaken for one. */
/* Bearing locks match alien-campaign SHIPS (four hulls). pose() still paints
 * the scene.json capture strings. Live play replaces them with the roster ship. */
const CONTACTS = ALIEN_SHIPS.map((s) => ({
  b: s.bearing,
  id: s.short,
  code: s.code,
  ok: [],
}));
const LOCK_WINDOW = 9;                        // deg
const VERDICT_TEXT = { idle: '', hit: 'IMPACT', refused: 'SHIELDED',
                       deflected: 'NO EFFECT' };
let packetLabel = '';

const st = {
  bear: S.pose.bearing, lock: null, pay: S.pose.payload, chg: S.pose.charge,
  arm: S.pose.arm, fire: S.pose.fire, verdict: S.pose.verdict,
  paper: [], pending: [], pendingVerdict: 'idle',
  scroll: 0, phase: 'idle', t: 0,
};
let alienSubmit = null;

/* Ship number (1..4) of the currently locked contact, or 0 if none. */
function lockNum() {
  const code = st.lock && st.lock.code;    // 'AL01'..'AL04'
  const m = code && /(\d+)$/.exec(code);
  return m ? parseInt(m[1], 10) : 0;
}

/* Aim the harpoon at ship `num` (1-based) and mirror it into the readout. */
function aimShip(num) {
  const s = ALIEN_SHIPS[num - 1];
  if (!s) return;
  setBearing(s.bearing);
  an.bear = st.bear;
  packetLabel = s.short || '';
  applyControls();
  paintAll();
}

/* PAYLOAD drum: step the target to the next ship. */
function cycleShip() {
  if (!CONTACTS.length) return;
  let i = st.lock ? CONTACTS.indexOf(st.lock) : -1;
  i = (i + 1) % CONTACTS.length;
  aimShip(i + 1);
  if (alienSubmit) alienSubmit.selectShipByNumber(i + 1);
}

function nearest(b) {
  let best = null, d = 1e9;
  for (const c of CONTACTS) {
    const k = Math.abs(c.b - b);
    if (k < d) { d = k; best = c; }
  }
  return d <= LOCK_WINDOW ? best : null;
}

/** Fold arbitrary returned bytes onto the platen: hard-wrap at the aperture's
 *  own column count, map control bytes to '.', keep the order.  LAYOUT ONLY. */
function paper(text) {
  const cols = COLS.catch, out = [];
  for (const raw of String(text).split('\n')) {
    let line = '';
    for (const ch of raw) line += (ch < ' ' || ch === '\u007f') ? '.' : ch;
    if (!line.length) { out.push(''); continue; }
    while (line.length > cols) {
      out.push(line.slice(0, cols));
      line = line.slice(cols);
    }
    out.push(line);
  }
  return out;
}

/* The rest state is the console after ONE completed engagement, and its strings
 * come from scene.json — the same strings export_pkt.py rendered gt_platen0.png
 * from — so the page and the ground truth cannot drift.  MTA seeds its rest
 * queue out of scene.json for the same reason; everything after the first
 * interaction is generated here at runtime. */
function resetSession() {
  st.bear = S.pose.bearing;
  st.lock = nearest(st.bear);
  st.pay = S.pose.payload;
  st.chg = S.pose.charge;
  st.arm = S.pose.arm;
  st.fire = S.pose.fire;
  st.verdict = S.pose.verdict;
  st.paper = (S.readout_text[2] || []).slice();
  st.pending = st.paper.slice();
  st.pendingVerdict = st.verdict;
  st.scroll = 0;
  st.phase = 'idle';
  st.t = 0;
}

/** the visible window of the printout: N lines of paper behind the aperture */
function paperWindow() {
  const n = NLINES.catch;
  const top = Math.max(0, Math.min(st.scroll,
                                   Math.max(0, st.paper.length - n)));
  const out = [];
  for (let i = 0; i < n; i++) out.push(st.paper[top + i] || '');
  return out;
}

function paintAll() {
  RO.target.paint([st.lock ? st.lock.id : 'NO CONTACT']);
  RO.payload.paint([packetLabel]);
  RO.catch.paint(paperWindow());
  RO.verdict.paint([VERDICT_TEXT[st.verdict]]);
}

/* ---------------------------------------------- M3: STATE -> GEOMETRY */
/* the eased values the frame loop drives towards the state above */
const an = { bear: st.bear, pay: st.pay * P.payload.deg_per_step,
             chg: st.chg, cage: 0, tog: 0, drop: 0, adv: 0, spool: 0 };

function armAngles(nm) {
  return [P.arm.cage_deg[nm], P.arm.toggle_deg[nm]];
}
function applyControls() {
  wheel.pivot.quaternion.setFromAxisAngle(SPIN, an.bear * D2R);
  drum.pivot.quaternion.setFromAxisAngle(SPIN, an.pay * D2R);
  lever.position.copy(UPAX).multiplyScalar(
    P.charge.throw_m * an.chg / (P.charge.steps - 1));
  cage.pivot.quaternion.setFromAxisAngle(HINGEAX, an.cage * D2R);
  toggle.pivot.quaternion.setFromAxisAngle(HINGEAX, an.tog * D2R);
  plunger.position.copy(NRMAX).multiplyScalar(-P.fire.drop_m * an.drop);
  platen.position.copy(UPAX).multiplyScalar(P.catch.advance_m * an.adv);
  for (let i = 0; i < spools.length; i++)
    spools[i].pivot.quaternion.setFromAxisAngle(
      SPOOLAX, P.catch.spool_deg_per_step[i] * an.spool * D2R);
  for (const o of flash) o.visible = (st.fire === 'fired');
}

/* the material state of every `states` control, from the module's own declared
 * material pairs.  Called on every state change and once at load, so the page
 * never depends on which state the glb happened to be exported in. */
function applyMaterials() {
  const lv = Math.max(0, Math.min(P.charge.tube_mats.length - 1,
                                  Math.round(an.chg)));
  for (const o of tubes) setMat(o, P.charge.tube_mats[lv]);
  pips.forEach((o, i) => setMat(o, i <= st.chg
    ? P.charge.pip_on[i] : P.charge.pip_off[i]));
  const lit = P.arm.lit[st.arm] || [0, 0];
  armLamps.forEach((o, i) => setMat(o, lit[i]
    ? P.arm.lamp_on[i] : P.arm.lamp_off[i]));
  const vl = P.verdict.lit[st.verdict];
  vrdLamps.forEach((o, i) => setMat(o, i === vl
    ? P.verdict.lamp_on[i] : P.verdict.lamp_off[i]));
  if (hdrBar) setMat(hdrBar, P.verdict.hdr_mats[st.verdict]);
}

/* ------------------------------------------------------ M4: ANIMATION */
let frozen = false;             // set by pose(): the capture must be still
let dragging = null;
/* The two shared fittings, declared HERE so `onFrame()` below and
 * `poseForCapture()` further down can both reach them and both are defined
 * before the mount.  live3d/refit.js, live3d/mast.js. */
let refit = null;
let mast = null;
const REEL_S = 1.6;             // seconds the return line takes to reel in
const FIRE_S = 0.22;

function step(cur, want, dt, rate) {
  return cur + (want - cur) * Math.min(1, dt * rate);
}

function onFrame(dt, now) {
  /* ABOVE THE `frozen` GATE, and that is CONVERSION_BRIEF trap 26.  Neither
   * fitting owns a timer, so a `tick()` below a paused-at-load gate freezes
   * both of them on exactly the page a human opens -- and this module's gate
   * latches on EVERY pointerdown (`hotspot()` clears it), so the port's iris
   * would stop mid-retraction the moment the player touched anything else.
   * `pose()` is what stills them for a capture, and it does it by HIDING
   * them.  FIX_UPLOAD 12.15 item 7; both fittings warn if `tick()` has not
   * been called in 90 frames while they are visible. */
  if (refit) refit.tick(dt, now);
  if (mast) mast.tick(dt, now);

  if (frozen) return;
  if (!dragging) an.bear = step(an.bear, st.bear, dt, 9);
  an.pay = step(an.pay, st.pay * P.payload.deg_per_step, dt, 8);
  const chgWas = Math.round(an.chg);
  an.chg = step(an.chg, st.chg, dt, 7);
  if (Math.round(an.chg) !== chgWas) applyMaterials();   // the bank heats up
  const aa = armAngles(st.arm);
  an.cage = step(an.cage, aa[0], dt, 7);
  an.tog = step(an.tog, aa[1], dt, 12);
  an.drop = step(an.drop, st.fire === 'fired' ? 1 : 0, dt, 18);

  if (st.phase === 'fire') {
    st.t += dt;
    if (st.t >= FIRE_S) { st.phase = 'reel'; st.t = 0; st.fire = 'ready'; }
  } else if (st.phase === 'reel') {
    st.t += dt;
    const u = Math.min(1, st.t / REEL_S);
    an.adv = (P.catch.steps - 1) * u;
    an.spool = (P.catch.steps - 1) * u * 2.5;
    /* the teleprinter types the return out a line at a time, so the platen's
     * advance and the arriving bytes are the same motion */
    const shown = Math.floor(u * st.pending.length);
    if (shown !== st.paper.length) {
      st.paper = st.pending.slice(0, shown);
      st.scroll = Math.max(0, st.paper.length - NLINES.catch);
      paintAll();
    }
    if (u >= 1) {
      st.phase = 'idle';
      st.paper = st.pending.slice();
      st.scroll = Math.max(0, st.paper.length - NLINES.catch);
      st.verdict = st.pendingVerdict;
      st.arm = 'safe';
      applyMaterials();
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
  d.title = title;                       // textContent-safe: no markup
  d.addEventListener('pointerdown', ev => { frozen = false; onDown(ev, d); });
  $('hots').appendChild(d);
  return d;
}
function setBearing(b) {
  const lo = P.target.range[0], hi = P.target.range[1];
  st.bear = Math.max(lo, Math.min(hi, b));
  const was = st.lock;
  st.lock = nearest(st.bear);
  if (st.lock !== was && st.arm !== 'safe') { st.arm = 'safe'; applyMaterials(); }
  paintAll();
}

function applyLiveTarget() {
  const n = lockNum() || 1;
  const ship = ALIEN_SHIPS[n - 1];
  if (!ship) return;
  st.paper = [];
  st.pending = [];
  st.pendingVerdict = 'idle';
  st.verdict = 'idle';
  st.scroll = 0;
  st.phase = 'idle';
  st.arm = 'safe';
  st.fire = 'ready';
  packetLabel = ship.short || '';
  setBearing(ship.bearing);
  an.bear = st.bear;
  applyMaterials();
  applyControls();
  if (alienSubmit) alienSubmit.selectShipByNumber(n);
}

function beginReelWithText(text, verdict) {
  st.pending = paper(String(text || ''));
  st.pendingVerdict = verdict || 'deflected';
  st.fire = 'fired';
  st.verdict = 'idle';
  st.paper = [];
  st.scroll = 0;
  an.adv = 0; an.spool = 0;
  st.phase = 'fire';
  st.t = 0;
  applyMaterials();
  paintAll();
}

/* the azimuth wheel: angular drag about its PROJECTED hub, the same shape as
 * app.js section 9.  Screen y runs down, so a clockwise drag is a positive
 * screen angle and a positive bearing. */
hotspot(P.target.hotspot, P.target.label + ' — sweep the void', (ev, el) => {
  const hub = P.target.pivot_px;
  const ang = pt => Math.atan2(pt.y - hub.y, pt.x - hub.x) / D2R;
  let last = ang(stagePt(ev));
  dragging = true;
  el.setPointerCapture(ev.pointerId);
  const move = e2 => {
    const a = ang(stagePt(e2));
    let d = a - last;
    while (d > 180) d -= 360;
    while (d < -180) d += 360;
    setBearing(st.bear + d);
    an.bear = st.bear;
    last = a;
    applyControls();
  };
  const up = () => {
    dragging = null;
    const c = nearest(st.bear);
    if (c) setBearing(c.b);              // the wheel settles onto the contact
    if (alienSubmit && st.lock) alienSubmit.selectShipByNumber(lockNum());
    el.removeEventListener('pointermove', move);
    el.removeEventListener('pointerup', up);
    el.removeEventListener('pointercancel', up);
  };
  el.addEventListener('pointermove', move);
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', up);
});

hotspot(P.payload.hotspot, P.payload.label + ' — step the target', () => {
  cycleShip();
});
hotspot(P.charge.hotspot, P.charge.label + ' — spool the bank', () => {
  st.chg = (st.chg + 1) % P.charge.steps;
  applyMaterials();
});
hotspot(P.arm.hotspot, P.arm.label + ' — throw the master arm', () => {
  if (st.phase !== 'idle') return;
  if (!st.lock || st.chg < 3) {          // the interlock refuses
    st.arm = 'interlock';
    applyMaterials();
    return;
  }
  st.arm = (st.arm === 'armed') ? 'safe' : 'armed';
  applyMaterials();
});
hotspot(P.fire.hotspot, P.fire.label + ' — launch', () => {
  if (st.arm !== 'armed' || st.phase !== 'idle' || !st.lock) return;
  /* The trigger launches the fleet-scoring run for the locked ship; the reel /
   * impact plays when the result comes back (alienSubmit's onResult). */
  st.arm = 'safe';
  applyMaterials();
  const started = alienSubmit && alienSubmit.launch && alienSubmit.launch(lockNum());
  if (!started) beginReelWithText('SIGNAL HARPOON // no target in range', 'refused');
});
hotspot(P.catch.hotspot, P.catch.label + ' — scroll the printout', () => {
  const over = Math.max(0, st.paper.length - NLINES.catch);
  st.scroll = over ? (st.scroll + 1) % (over + 1) : 0;
  paintAll();
});
hotspot(P.verdict.hotspot, P.verdict.label + ' — acknowledge', () => {
  st.verdict = 'idle';
  applyMaterials();
  paintAll();
});

/* ---- A.L.I.E.N. fleet-scoring form (after st/an/paper exist) ----------
 * The harpoon is its fire control: picking a ship aims it, the trigger launches
 * the run, and a result plays the reel / impact verdict. */
if ($('alienSubmit')) {
  alienSubmit = mountAlienSubmit($('alienSubmit'), {
    onSelectShip: (num) => { if (!frozen) aimShip(num); },
    onResult: (verdict, text) => {
      if (!frozen && st.phase === 'idle') beginReelWithText(text, verdict);
    },
  });
  window.__alienSubmit = alienSubmit;
}

/* ---- A.L.I.E.N. docket: collapse to reach the harpoon controls -------- */
(function wireAlienDock() {
  const dock = $('alienDock');
  if (!dock) return;
  const collapseBtn = $('alienCollapse');
  function setCollapsed(on) {
    dock.classList.toggle('collapsed', on);
    if (collapseBtn) {
      collapseBtn.setAttribute('aria-expanded', on ? 'false' : 'true');
      collapseBtn.textContent = on ? '▸' : '▾';   // ▸ / ▾
      collapseBtn.setAttribute('aria-label', on ? 'Expand A.L.I.E.N. panel' : 'Collapse A.L.I.E.N. panel');
      collapseBtn.title = on ? 'Expand panel' : 'Collapse panel';
    }
  }
  if (collapseBtn) collapseBtn.addEventListener('click', () => setCollapsed(!dock.classList.contains('collapsed')));
})();

/* --------------------------------------------- M6: THE CAPTURE POSE
 * DETERMINISTIC, and it is the state export_pkt.py rendered gt_full_read.png
 * and gt_platen0.png in — the scene.json capture pose, capacitor bank idling, master arm safe, plunger ready, platen at
 * advance 0, verdict HIT with the return still on the paper.
 *
 * THERE IS NO setInterval OR setTimeout ANYWHERE IN THIS FILE.  Every animation
 * is a state machine driven out of onFrame(), so `frozen = true` stops all of
 * it in one place and two consecutive captures are byte-identical.  KVS failed
 * this check for a 520 ms cursor blink that setting a flag could not stop. */
function settle() {
  an.bear = st.bear;
  an.pay = st.pay * P.payload.deg_per_step;
  an.chg = st.chg;
  const aa = armAngles(st.arm);
  an.cage = aa[0];
  an.tog = aa[1];
  an.drop = (st.fire === 'fired') ? 1 : 0;
  applyMaterials();
  applyControls();
  paintAll();
}
function poseForCapture() {
  /* HIDE BOTH FITTINGS.  Every number in NOTES.md sections 1-9 and in
   * live3d/RESULTS.md was captured from pose() against Blender renders that
   * contain neither, so hiding them reproduces all of them unchanged and
   * re-renders nothing.  FIX_UPLOAD section 0 decision 3;
   * STATUS_AT_A_GLANCE 6.5.  Each fitting's own behaviour is measured with it
   * SHOWN -- __refit.show(true) / __mast.show(true) -- which is a separate
   * capture, and that capture's report is byte-identical to this one. */
  if (refit) refit.pose();
  if (mast) mast.pose();
  /* The A.L.I.E.N. docket is screen-space chrome too — hide for capture
     stability (one overlay now, so one hide). */
  const dockEl = $('alienDock');
  if (dockEl) dockEl.classList.add('as-hidden');
  if (alienSubmit) alienSubmit.stop();
  frozen = true;
  dragging = null;
  resetSession();
  an.adv = S.pose.catch;
  an.spool = S.pose.catch;
  settle();
  /* Force ground-truth readout strings from scene.json so renaming live
   * contacts to alien ship labels does not break check_text / gt plates. */
  if (S.readout_text) {
    if (S.readout_text[0]) RO.target.paint(S.readout_text[0].slice());
    if (S.readout_text[1]) RO.payload.paint(S.readout_text[1].slice());
    if (S.readout_text[2]) RO.catch.paint(S.readout_text[2].slice());
    if (S.readout_text[3]) RO.verdict.paint(S.readout_text[3].slice());
  }
}

/* A module-private capture hook, ALONGSIDE window.__occ and never instead of
 * it: check/shoot_occlusion.mjs drives only __occ.  This exists so the two
 * comparisons that are not part of that contract — the materials.json A/B, and
 * driving a control to a chosen pose — can be shot from the real page rather
 * than argued about. */
window.__pkt = {
  matfix: v => { matFixOn = !!v; applyMatFix(); },
  gain: (g) => { if (g !== undefined) setGain(+g); return GAIN; },
  /* THE DEPTH COMPOSITE'S STAND-OFF TOLERANCE, in metres (BRIEF trap 24).  PKT
   * is the module where it actually bites: pkt_hdr_bar stands 1.15 mm proud of
   * pkt_hdr_frame, which is BAKED, so at the template's default uBias = 2 mm
   * `vLinDepth > baked - uBias` discards the whole bar into the plate -- a
   * 208 x 20 px emissive strip, silently, with no error anywhere.  Swept and
   * measured in NOTES.md section 5.3. */
  ubias: (v) => { if (v !== undefined) DU.uBias.value = +v;
                  return DU.uBias.value; },
  set: o => { frozen = true; Object.assign(st, o);
              st.lock = nearest(st.bear); settle(); },
  drive: (k, v) => { frozen = true; an[k] = v; applyControls(); },
  tris: () => ({ tris: liveTris, meshes: liveMeshes }),
  /* how many of the exporter's declared object NAMES actually resolved in the
   * loaded glbs.  A name that does not resolve is silent -- the control simply
   * never moves or never changes material -- so it is worth being able to ask. */
  rig: () => ({
    lever: lever.children.length, tubes: tubes.length, pips: pips.length,
    cage: cage.inner.children.length, toggle: toggle.inner.children.length,
    armLamps: armLamps.length, plunger: plunger.children.length,
    flash: flash.length, platen: platen.children.length,
    spools: spools.map(x => x.inner.children.length),
    vrdLamps: vrdLamps.length, hdr: !!hdrBar,
    hdrColor: hdrBar ? hdrBar.material.color.getHexString() : null,
    hdrEmissive: hdrBar ? hdrBar.material.emissive.getHexString() : null,
    hdrEmitI: hdrBar ? hdrBar.material.emissiveIntensity : null,
    hdrMatName: hdrBar ? hdrBar.material.name : null,
    tubeEmitI: tubes[0] ? tubes[0].material.emissiveIntensity : null,
  }),
  layout: () => readouts.map((r, i) =>
    Object.assign({ name: PLANES[i].name }, r.layout)),
  facing: () => facingAudit(camera),
  state: () => ({ bear: st.bear, lock: st.lock && st.lock.id, pay: st.pay,
                  chg: st.chg, arm: st.arm, fire: st.fire,
                  verdict: st.verdict, lines: st.paper.length, matFixOn }),
  /* the mast's own hooks, so a state can be looked at without a status.json.
   * They take a RECORD, not a display state, so what is exercised is
   * status.js's own derive() and never a second path. */
  mast: () => mast.state(),
  mastSet: rec => mast.set(rec),
  refit: () => (refit ? refit.state() : null),
};

/* PKT has no refit port and no rebuild control. The telltale mast stays. */

/* ---- THE TELLTALE MAST -----------------------------------------------------
 * The same six lines, and none of them is PKT-specific either: the anchor, the
 * size, the rake, the part names and the hotspot all come out of
 * `scene.json -> mast`, which pipeline/status_mast.py wrote.
 *
 * PKT IS THE OFFENSIVE VARIANT (STATUS_AT_A_GLANCE section 8), and this is the
 * first module in the fleet to ship it: a notched brass TALLY STICK instead of
 * a graduated glass tube, filling UPWARD as GOOD NEWS -- distinct fleet vulns
 * confirmed landing this session, `confirmed / 54` -- with the cap bead as the
 * ARM lamp and NO VANE.  PKT has no `unit_tests/`, no `vuln_tests/` and is not
 * in `bridge/data/catalog.json`, so neither of the eight defensive masts' two
 * axes exists for it; the tally shows the FLEET's tally, not PKT's own health.
 * `status.js` branches on the RECORD's own `kind`, never on `code === 'PKT'`.
 *
 * It is NOT on the port's service rail, and that is measured: the dash lip
 * crowns near the middle of the frame, so the port's own fitted plane is in
 * front of the baked dash only over u = -140..+130 mm, and a 180 px mast from
 * the published free_from_m (1.5 W) would stand ~9 mm behind the plate at its
 * far end -- FMM's convex fascia with the curvature reversed, and the
 * cantilevered shelf MTA rejected.  So it takes the `--at` route on the same
 * dash shelf, immediately to the port's PORT side: mast envelope
 * 754.5..942.6 x 672.6..706.1, the port's hotspot from 959.8, a 13.2 px gutter
 * and 0 px2 either way.  The docket's bottom edge is pinned at y 659.5 and the
 * mast's hotspot starts at 668.6, so the mast is fully readable with the port
 * open, which STATUS_AT_A_GLANCE 6.5 item 4 says is the whole reason the
 * close-up half exists.
 *
 * Its face is raked 45 degrees.  The dash's own two in-plane axes project at
 * 827.9 and 664.2 px/m -- a ratio of 1.25, which is KVS's condition, not
 * MQB's or FMM's.  Run `--rakes`; do not inherit.  Fleet: KVS 45, MQB 0,
 * MTA 0, OTA 57, FMM 0, PKT 45.
 *
 * It declares NO readout plane.  Its words are the screen-space caption in
 * live3d/mast.css, the same class of thing as the port's docket, so
 * check_occlusion.py question 5, the dial-face rule and check_text.py are not
 * engaged by it.  `readouts.length` is still 4.
 *
 * `place()` is re-run on `refit:docket` by mast.js itself, and `show()` places
 * BEFORE its first fetch, so this page needs neither a MutationObserver nor
 * FMM's module-side `mast.place()` line. */
mast = await mountMast({
  THREE, scene, camera, split, S, code: CODE, assetBase: A,
  load, dress, hotspot, layerHost: $('stage'), stageEl: $('stage'),
});
window.__mast = mast;

poseForCapture();
frozen = false;
mast.show(true);
{
  const dockEl = $('alienDock');
  if (dockEl) dockEl.classList.remove('as-hidden');
}
applyLiveTarget();
layout();
/* One-sided geometry that FrontSide has deleted.  Console warning only; it is
 * not part of __occ.audit(), which means something else and must stay []. */
facingAudit(camera);
requestAnimationFrame(frame);
window.__loaded = true;
