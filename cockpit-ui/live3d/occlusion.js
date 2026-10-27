/* SAINTCON 2026 — SPLIT-PASS TEXT OCCLUSION.  SHARED MACHINERY.
 *
 * This file is the fleet's.  Every module close-up imports it unchanged; if
 * you find yourself editing it to convert a module, that is the signal that
 * something belongs in here rather than in your module.  See
 * live3d/CONVERSION_BRIEF.md for the recipe and live3d/design/TEXT_OCCLUSION.md
 * for the decision, the measurements and the three rejected alternatives.
 *
 * THE PROBLEM.  Content text is DOM (README section 12, "ARCHITECTURE
 * RATIFIED").  DOM laid on the scene with a CSS 3D transform ALWAYS composites
 * above the WebGL canvas, so any geometry that passes in FRONT of a readout
 * draws behind its own text.  Measured, fleet-wide, in
 * live3d/audit/OCCLUSION_AUDIT.md: LOG, DNSM and PKT are occluded today, FMM
 * and IPM have no clean home for their values, and SEVEN OF TEN findings are a
 * STATIC bezel, aperture, lip or rail cropping the surface the text lies on --
 * i.e. BAKED PIXELS, with no mesh to project and no silhouette to mask.  KVS,
 * the reference module, is very nearly clean: 269 of 78,003 pixels of its
 * platen rect (0.34%) have baked geometry in front of the plane, a 2.4-3.2 mm
 * sliver of the console rim on the rect's bottom three rows.
 *
 * THE ANSWER.  Do not mask the text.  SPLIT THE SCENE IN TWO AT THE TEXT PLANE
 * and put the DOM in the gap:
 *
 *      <img>  baked plate                                    z-index 1
 *      canvas #gl        everything BEHIND the text planes    z-index 2
 *      div    #css3d     the DOM readouts, unchanged          z-index 3
 *      canvas #glFront   everything IN FRONT of them          z-index 4
 *
 * The two passes are a PARTITION, not a duplicate: every fragment is drawn by
 * exactly one of them, so there is no double-blended antialias edge where they
 * meet.  The test is per-fragment and analytic -- no mask image, no silhouette
 * polygon, no per-frame encode -- and it is exact to the pixel because it is
 * the same arithmetic the depth composite already uses.
 *
 * The test, for a fragment at view-space position p and a text plane with
 * view-space origin o, unit normal n, unit axes u,v and half sizes hw,hh:
 *
 *      s = dot(o,n) / dot(p,n)         // scale that puts the ray on the plane
 *      the plane is BEHIND this fragment  <=>  s > 1
 *      the hit point s*p is inside the readout rect  <=>
 *          |dot(s*p - o, u)| <= hw  and  |dot(s*p - o, v)| <= hh
 *
 * "In front of the text" means both: behind-the-plane AND inside the rect.
 * Outside every readout rect a fragment is background-half by definition,
 * because there is no text there to be in front of.
 *
 * Costs, honestly: one extra draw of the live geometry per frame (KVS ships
 * 3,388 triangles, so this is noise; measured at +-0.15 ms/frame with the sign
 * unstable across runs), one extra GL context, and the readout must be a
 * bounded PLANE -- the same constraint the CSS3D overlay already has.  A
 * curved carrier is N facets either way, which is why MAX_PLANES is 12.
 *
 * A CORRECTION THIS FILE OWES LOG.  Earlier revisions of these comments said
 * LOG's ribbon "curves off its rollers".  IT DOES NOT: `log_ribbon` is a single
 * FLAT BOX, the spools are separate cylinders and the paper does not wrap them,
 * and LOG's tape plane never cuts its own carrier.  The genuinely non-planar
 * carrier in LOG is the TEAR-OFF TAIL, seven facets -- which is still a reason
 * for MAX_PLANES = 12 and for the `plane cut` allowance, just not the reason
 * that was written down.  LOG NOTES 8.8.
 *
 * NOTHING IN HERE TOUCHES THE TEXT.  The DOM nodes, the font metrics, the
 * textContent-only rule and the "sharp at any window size" property are the
 * shipped ones, byte for byte.  There is ONE text path in this project.
 */
import * as THREE from 'three';

/* 12, not 4.  The occlusion audit found two modules whose text carrier is NOT
 * a plane -- DNSM's six-facet star-catalogue drum and LOG's SEVEN-FACET
 * TEAR-OFF TAIL -- and a curved carrier is handled the only way a CSS3D overlay
 * can handle one anyway: as N flat facets, each its own DOM element and its own
 * plane.  Six facets plus a module's other readouts does not fit in four.  The
 * per-fragment cost of the extra slots is measured in design/TEXT_OCCLUSION.md;
 * the loop breaks at uPlaneN, so unused slots cost one comparison.
 *
 * If a module genuinely needs more than 12, RAISE THIS NUMBER rather than
 * inventing a second mechanism -- but measure first: 7 planes was already
 * unmeasurable above run-to-run variance. */
export const MAX_PLANES = 12;

/* Shared uniform objects.  Spliced into every material with
 * attachForeground(); the SAME object identities are handed to both
 * renderers' programs, so flipping uOccMode between the two render() calls
 * steers both passes from one place.  (Each renderer keeps its own uniform
 * cache, and we always set the value immediately before its own render, so
 * the caches never disagree.) */
export const OCC = {
  uOccMode: { value: 0 },        // 0 = draw all, 1 = background half, 2 = front half
  uPlaneN: { value: 0 },
  uPlaneO: { value: mk() },      // view-space origin
  uPlaneU: { value: mk() },      // view-space unit u
  uPlaneV: { value: mk() },
  uPlaneNrm: { value: mk() },
  uPlaneHalf: { value: Array.from({ length: MAX_PLANES }, () => new THREE.Vector2(1, 1)) },
};
function mk() { return Array.from({ length: MAX_PLANES }, () => new THREE.Vector3(0, 0, 1)); }

/* The GLSL is shared by the lit materials and by the baked-plate quad, so the
 * two can never drift apart.  `P` is the fragment's VIEW-space position. */
export const OCC_GLSL = `
uniform int  uOccMode;
uniform int  uPlaneN;
uniform vec3 uPlaneO[${MAX_PLANES}];
uniform vec3 uPlaneU[${MAX_PLANES}];
uniform vec3 uPlaneV[${MAX_PLANES}];
uniform vec3 uPlaneNrm[${MAX_PLANES}];
uniform vec2 uPlaneHalf[${MAX_PLANES}];

bool occInFrontOfText(vec3 P) {
  for (int i = 0; i < ${MAX_PLANES}; i++) {
    if (i >= uPlaneN) break;
    float den = dot(P, uPlaneNrm[i]);
    /* den >= 0 means the plane's front face is turned AWAY from the camera --
     * a facet going round the back of a drum.  Its text is not visible, so
     * nothing can be "in front of" it.  Without this, the far side of a curved
     * carrier punches holes in the near side. */
    if (den > -1e-6) continue;
    float s = dot(uPlaneO[i], uPlaneNrm[i]) / den;
    if (s <= 1.0001) continue;            // plane is at or nearer than P
    vec3 d = P * s - uPlaneO[i];
    if (abs(dot(d, uPlaneU[i])) > uPlaneHalf[i].x) continue;
    if (abs(dot(d, uPlaneV[i])) > uPlaneHalf[i].y) continue;
    return true;
  }
  return false;
}

void occCull(vec3 P) {
  if (uOccMode == 0) return;
  bool f = occInFrontOfText(P);
  if (uOccMode == 1 &&  f) discard;       // background half: drop the front
  if (uOccMode == 2 && !f) discard;       // front half: drop everything else
}
`;

/* Set on every material that has been through attachForeground(), so
 * OcclusionSplit.auditScene() can find the ones that have not.  A material
 * that is NOT attached draws in BOTH passes and double-blends; that is the
 * single easiest way to get this wrong, and it looks like "the edges got
 * slightly darker", not like an error.  See CONVERSION_BRIEF.md trap 3. */
export const OCC_FLAG = '__occForeground';

/* Splice the partition into a three.js material.  Chains onto whatever
 * onBeforeCompile the material already had (app.js's depth composite), so the
 * baked-depth discard and this one coexist.
 *
 * ORDER MATTERS ONE WAY ONLY: attachDepthTest() in app.js ASSIGNS
 * onBeforeCompile, this one CHAINS.  Call the depth test first, then this.
 * Calling this twice on one material is a no-op, not a double splice. */
export function attachForeground(mat) {
  if (mat[OCC_FLAG]) return mat;
  mat[OCC_FLAG] = true;
  const prev = mat.onBeforeCompile;
  mat.onBeforeCompile = function (sh, renderer) {
    if (prev) prev.call(this, sh, renderer);
    Object.assign(sh.uniforms, OCC);
    if (!/varying vec3 vOccView/.test(sh.vertexShader)) {
      sh.vertexShader = 'varying vec3 vOccView;\n' + sh.vertexShader.replace(
        '#include <project_vertex>',
        '#include <project_vertex>\n  vOccView = mvPosition.xyz;');
    }
    sh.fragmentShader = 'varying vec3 vOccView;\n' + OCC_GLSL +
      sh.fragmentShader.replace('void main() {', 'void main() {\n  occCull(vOccView);');
  };
  mat.needsUpdate = true;
  return mat;
}

/* The baked plate is static geometry too, and it can also be in front of a
 * readout -- a console rim over a gauge, a raised bezel, PKT's header bar,
 * LOG's window trim, DNSM's aperture face.  That is SEVEN OF THE TEN audit
 * findings, and none of them is a mesh: they are plate pixels, so there is
 * nothing to project and nothing to mask.  Measured on the shipped KVS export:
 * a strip of the same console plane 60 mm above the platen is 31% covered by
 * baked geometry nearer than the plane, holes in the lamp rings included.  So
 * the front pass has to be able to redraw plate pixels as well as live meshes.
 *
 * This is one fullscreen quad that samples plate.png and depth.bin, rebuilds
 * each pixel's view-space position from its baked depth, runs the same
 * occCull, and writes gl_FragDepth so live meshes still sort against it.
 * GLSL3/WebGL2 for gl_FragDepth.
 *
 * NOTE the plate texture must be UNTAGGED (no colorSpace) and flipY = false --
 * see the wiring notes in CONVERSION_BRIEF.md step 6. */
export function makePlateFront({ plateTex, depthTex, W, H, fovYdeg, near, far }) {
  const tanY = Math.tan(fovYdeg * Math.PI / 360);
  const mat = new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    transparent: true,
    depthTest: true,
    depthWrite: true,
    uniforms: Object.assign({
      uPlate: { value: plateTex },
      uDepth: { value: depthTex },
      uRes: { value: new THREE.Vector2(W, H) },
      uTan: { value: new THREE.Vector2(tanY * W / H, tanY) },
      uNearFar: { value: new THREE.Vector2(near, far) },
    }, OCC),
    vertexShader: `
      precision highp float;
      in vec3 position;
      void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: `
      precision highp float;
      uniform sampler2D uPlate;
      uniform sampler2D uDepth;
      uniform vec2 uRes, uTan, uNearFar;
      out vec4 fragColor;
      ${OCC_GLSL}
      void main() {
        vec2 uv = gl_FragCoord.xy / uRes;
        vec2 tuv = vec2(uv.x, 1.0 - uv.y);          // depth.bin is top-down
        float d = texture(uDepth, tuv).r;
        if (d > 1e6) discard;                        // background
        vec2 ndc = uv * 2.0 - 1.0;
        vec3 P = vec3(ndc.x * uTan.x, ndc.y * uTan.y, -1.0) * d;
        if (uOccMode == 2 && !occInFrontOfText(P)) discard;
        if (uOccMode == 1 &&  occInFrontOfText(P)) discard;
        vec4 c = texture(uPlate, tuv);
        if (c.a < 0.5) discard;
        float n = uNearFar.x, f = uNearFar.y;
        float zc = (-(f + n) / (f - n)) * (-d) + (-2.0 * f * n / (f - n));
        gl_FragDepth = 0.5 * (zc / d) + 0.5;
        fragColor = c;
      }`,
  });
  const m = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat);
  m.frustumCulled = false;
  m.renderOrder = -1;
  /* gl_FragCoord is in DRAWING BUFFER pixels, not stage pixels: uRes has to
   * track renderer.setPixelRatio() or every screen-space lookup shears.  This
   * is the Retina bug (README section 16.5) in its second incarnation; see
   * OcclusionSplit.setPixelRatio. */
  m.userData.uRes = mat.uniforms.uRes;
  m[OCC_FLAG] = true;      // it carries occCull inline, not via onBeforeCompile
  mat[OCC_FLAG] = true;
  return m;
}

/* A text plane in world coordinates, exactly the frame the exporter already
 * writes as scene.json -> text_plane (origin / u / v / n / half_w / half_h).
 *
 * MOVING PLANES: mutate `o` / `u` / `v` / `n` in place from your animation
 * code and nothing else has to change -- the uniforms are re-uploaded from
 * these objects EVERY FRAME.  OTA's cartridge version, DNSM's courier card and
 * LOG's whole ribbon are moving planes; see CONVERSION_BRIEF.md step 5b. */
export class TextPlane {
  constructor(tp) {
    this.o = new THREE.Vector3().fromArray(tp.origin);
    this.u = new THREE.Vector3().fromArray(tp.u).normalize();
    this.v = new THREE.Vector3().fromArray(tp.v).normalize();
    this.n = new THREE.Vector3().fromArray(tp.n).normalize();
    this.half = new THREE.Vector2(tp.half_w, tp.half_h);
    this.enabled = true;
  }
  /** Re-seat the frame from a parent object's world matrix.  For a readout
   *  parented to a control pivot: keep the rest-pose frame, and each frame
   *  push it through the pivot's matrixWorld.  `rest` is a plain
   *  {origin,u,v,n} in the pivot's REST world space. */
  followRest(rest, matrixWorld) {
    this.o.fromArray(rest.origin).applyMatrix4(matrixWorld);
    this.u.fromArray(rest.u).transformDirection(matrixWorld);
    this.v.fromArray(rest.v).transformDirection(matrixWorld);
    this.n.fromArray(rest.n).transformDirection(matrixWorld);
    return this;
  }
}

export class OcclusionSplit {
  /**
   * @param {HTMLCanvasElement} canvas the FRONT canvas (z above the DOM text)
   * @param {THREE.Scene} scene the same scene the back canvas draws
   */
  constructor({ canvas, scene, camera, W, H, exposure }) {
    this.scene = scene; this.camera = camera; this.W = W; this.H = H;
    /* premultipliedAlpha: TRUE, which is three's own default and is what its
     * blending actually writes.  three's NormalBlending for a material with
     * `premultipliedAlpha` false is SRC_ALPHA / ONE_MINUS_SRC_ALPHA for rgb and
     * ONE / ONE_MINUS_SRC_ALPHA for alpha, so a transparent fragment drawn over
     * an EMPTY region of the canvas leaves `a*rgb` in the buffer -- premultiplied
     * -- and telling the browser to composite it as straight multiplies by alpha
     * a second time.  Measured by LOG (NOTES 8.1) on the shipped page at buffer
     * pixel (600,340), its magnifier glass over the ribbon: front (38,40,38,a49)
     * over back (212,206,197,a255); the page showed 178 and the split-OFF page
     * 210, and `38 + (1 - 49/255)*212 = 209.3` -- reading the buffer as
     * PREMULTIPLIED -- reproduces the right answer to one level.  It cost LOG
     * 16.6 of live-set rms and 0.08 of its fitted light_gain, because the gain
     * was being asked to cancel it.
     *
     * FOR A FULLY OPAQUE FRAGMENT THE TWO ARE IDENTICAL, so this moves nothing
     * on a module with no transparent live geometry -- except on the front
     * pass's own ANTIALIASED EDGE, where alpha is 64 or 128 and the old flag
     * made those pixels too dark.
     *
     * THE BACK RENDERER MUST MATCH.  It is created in each module's own
     * module.js (and in app.js and modules/_TEMPLATE/module.js); all of those
     * are the same one word.  A page whose two renderers disagree composites
     * the same antialiased silhouette two different ways across the split
     * boundary.
     *
     * AND THIS FLAG SILENTLY RE-ENCODES EVERY CAPTURED PNG.  `toDataURL` --
     * which is what `__occ.shotBoth()` uses, and therefore what every check in
     * this project scores -- writes DIFFERENT BYTES for the two flags, because
     * the browser un-premultiplies on the way out only when it has been told
     * the buffer is premultiplied.  Measured on a bare WebGL2 context drawing
     * rgb(255,0,0) at alpha 0.2 with three's own NormalBlending factors:
     *
     *     readPixels                        (51,0,0,51)   both flags
     *     toDataURL, premultipliedAlpha:false (50,0,0,51)  PNG is PREMULTIPLIED
     *     toDataURL, premultipliedAlpha:true  (255,0,0,51) PNG is STRAIGHT
     *
     * So a capture taken before this change and one taken after are in
     * DIFFERENT ALPHA CONVENTIONS, and a checker that composites them the same
     * way is comparing two encodings -- which is precisely how a correct fix
     * looks like a regression.  `shoot_occlusion.mjs` therefore records
     * `info.premultiplied = {back, front}` with every capture, and
     * `check_occlusion.py`'s `px_over()` and `compare.py`'s `over()` pick the
     * convention per canvas from it.  Any new tool that reads a canvas grab
     * must do the same. */
    this.renderer = new THREE.WebGLRenderer({
      canvas, alpha: true, antialias: true, premultipliedAlpha: true,
      preserveDrawingBuffer: true,
    });
    this.renderer.setClearAlpha(0);
    this.renderer.setSize(W, H, false);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.AgXToneMapping;
    /* THE TWO RENDERERS MUST AGREE ON EXPOSURE.  They draw the SAME materials
     * into the two halves of ONE partition, so a module with a non-unit
     * exposure -- `scene.json -> colour.exposure`, which is -0.20 stops on FMM
     * because build.py's close_grade() puts a view transform on the close
     * camera -- would otherwise render the same surface at two different
     * exposures across the split boundary, on any pixel where live geometry
     * crosses a readout.  This was hardcoded to 1.0 while the back renderer
     * took the module's; FMM kept them in step from its own module.js and
     * reported it as belonging here.  FMM NOTES 8.1.
     *
     * Set once from the caller, and re-synced from the BACK renderer on every
     * renderFrame() so a module that changes exposure at runtime (a grade
     * hook, an exposure sweep) cannot drift the two apart either. */
    this.renderer.toneMappingExposure =
      (typeof exposure === 'number') ? exposure : 1.0;
    this.renderer.autoClear = false;
    this.planes = [];
    this.plateScene = new THREE.Scene();
    this.enabled = true;
    /* Objects the FRONT pass must not draw.  In-scene text (an SDF mesh, a
     * canvas-texture quad) sits AT its plane, not in front of it, so occCull
     * would drop it anyway -- but debug wireframes with depthTest off and no
     * occCull spliced in WOULD double-draw. */
    this.hideInFront = [];
  }

  addPlane(tp) { const p = new TextPlane(tp); this.planes.push(p); return p; }

  /** plateFront must be built by makePlateFront(); it is drawn in the FRONT
   *  half only, which is why it is kept in its own scene: the back canvas has
   *  the plate as a plain <img> underneath it already. */
  setPlateFront(mesh) { this.plateScene.add(mesh); }

  _upload() {
    const vm = this.camera.matrixWorldInverse;
    const act = this.planes.filter(p => p.enabled).slice(0, MAX_PLANES);
    OCC.uPlaneN.value = act.length;
    act.forEach((p, i) => {
      OCC.uPlaneO.value[i].copy(p.o).applyMatrix4(vm);
      OCC.uPlaneU.value[i].copy(p.u).transformDirection(vm);
      OCC.uPlaneV.value[i].copy(p.v).transformDirection(vm);
      OCC.uPlaneNrm.value[i].copy(p.n).transformDirection(vm);
      OCC.uPlaneHalf.value[i].copy(p.half);
    });
  }

  /** call BEFORE the back renderer's render() */
  beginBack() {
    this.camera.updateMatrixWorld();
    this._upload();
    OCC.uOccMode.value = this.enabled ? 1 : 0;
  }

  /** call AFTER the back renderer's render() (and after the CSS3D layer, which
   *  does not care either way) */
  renderFront() {
    if (!this.enabled) {
      this.renderer.clear();
      OCC.uOccMode.value = 0;
      return;
    }
    const hid = [];
    for (const o of this.hideInFront) {
      if (!o) continue;
      hid.push([o, o.visible]);
      o.visible = false;
    }
    OCC.uOccMode.value = 2;
    this.renderer.clear();
    if (this.plateScene.children.length)
      this.renderer.render(this.plateScene, this.camera);
    this.renderer.render(this.scene, this.camera);
    OCC.uOccMode.value = 0;
    for (const [o, v] of hid) o.visible = v;
  }

  /** The whole frame, in the one order that is correct.  Prefer this over
   *  calling beginBack/renderFront by hand -- getting the order wrong is
   *  silent (the front pass reads last frame's plane uniforms). */
  renderFrame(backRenderer, css3d) {
    /* one partition, one exposure -- see the constructor */
    this.renderer.toneMappingExposure = backRenderer.toneMappingExposure;
    this.beginBack();
    backRenderer.render(this.scene, this.camera);
    if (css3d) css3d.render(this.camera);
    this.renderFront();
  }

  /** Sets the front renderer's pixel ratio AND every screen-space uniform that
   *  depends on the drawing-buffer size.  gl_FragCoord.xy is in drawing-buffer
   *  pixels; dividing it by the STAGE size (1280x720) instead is a silent
   *  shear of (pixelRatio - 1) across the frame -- 20 px at mid-screen for the
   *  1.03 ratio the page picks at its default window size, and the composite
   *  fails outright at 2.  README section 16.5.  Pass the back renderer's
   *  screen-space uniforms in `extraRes` so there is ONE call site for both. */
  setPixelRatio(r, extraRes = []) {
    this.renderer.setPixelRatio(r);
    this.renderer.setSize(this.W, this.H, false);
    const v = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    for (const m of this.plateScene.children)
      if (m.userData.uRes) m.userData.uRes.value.copy(v);
    for (const u of extraRes) u.value.copy(v);
    return v;
  }

  /** Every mesh in the scene whose material has NOT been through
   *  attachForeground().  Such a material draws in BOTH passes and
   *  double-blends its antialiased edges.  Run this once after everything is
   *  loaded; the expected answer is an empty array.  Objects listed in
   *  hideInFront are excused, because they never reach the front pass. */
  auditScene() {
    const excused = new Set();
    for (const root of this.hideInFront)
      if (root) root.traverse(o => excused.add(o));
    const bad = [];
    this.scene.traverse(o => {
      if (!o.isMesh && !o.isLine && !o.isPoints && !o.isSprite) return;
      if (excused.has(o)) return;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats)
        if (m && !m[OCC_FLAG]) bad.push(o.name || '(unnamed ' + o.type + ')');
    });
    return bad;
  }

  /** Re-derive each enabled plane's four corners in STAGE pixels from the live
   *  camera, so a module can check its declared frame against the exporter's
   *  own text_plane.corners_px.  Agreement to ~1e-3 px means the projection
   *  under the plane test is the projection the pipeline used; a big number
   *  means the plane, the camera or the Z-up->Y-up map is wrong.
   *
   *  IT IS ONLY DEFINED AT THE EXPORT POSE.  `corners_px` is a constant the
   *  exporter measured with the plane where Blender had it; a MOVING plane is
   *  somewhere else the rest of the time, so the difference is the motion and
   *  not an error.  Measured: DNSM reads 3.6e-04 px at its export pose and
   *  201.6 px mid-rotation, with seven moving planes (six drum facets and the
   *  courier card); OTA reproduced the same thing on its cartridge (OTA NOTES
   *  7.2, DNSM NOTES 9.3).  Call it after pose() -- which is what
   *  shoot_occlusion.mjs does before it reads `plane_corner_err_px`, and why
   *  the harness's number is a health metric and a mid-animation one is not.
   *  For a moving plane use it as a POSE-TIME assertion, never as a monitor. */
  cornersPx(plane) {
    const out = [];
    for (const [a, b] of [[-1, 1], [1, 1], [1, -1], [-1, -1]]) {
      const p = plane.o.clone()
        .addScaledVector(plane.u, a * plane.half.x)
        .addScaledVector(plane.v, b * plane.half.y)
        .project(this.camera);
      out.push([(p.x * 0.5 + 0.5) * this.W, (0.5 - p.y * 0.5) * this.H]);
    }
    return out;   // tl, tr, br, bl
  }
}
