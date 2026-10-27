/* Starfield — lifted from style/starfield-realistic.html (the owner's own
   work). Classic script, no module: it must run behind the cockpit plate,
   whose window is an alpha hole. Draws into #stars.

   The bottom-row Performance button opens a dialog. It does not itself
   toggle a setting. Dynamic stars is the old shader switch: off does not
   create a WebGL context, program, or buffer, and does not keep an
   animation loop. The window shows a still SVG star field, which is not a
   frozen frame of this shader. That choice is remembered in
   localStorage['cockpit.stars.shader'] ('off' / 'on'). Missing means on.

   Pre-load modules on hover is remembered in
   localStorage['cockpit.modules.hover'] the same way. This file only
   stores it. app.js reads it and skips warm() on hover when it is off.

   prefers-reduced-motion is not the star setting. When dynamic stars are
   on, that OS setting still builds the program and draws one frame, then
   rests. */
(function () {
  "use strict";

  const STORAGE_KEY = "cockpit.stars.shader";
  const HOVER_KEY = "cockpit.modules.hover";
  let canvas = document.getElementById("stars");
  let stopLive = null;
  let stillUrl = "";
  let perfOpen = false;

  function shaderOff() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "off";
    } catch (e) {
      return false;
    }
  }

  function remember(off) {
    try {
      localStorage.setItem(STORAGE_KEY, off ? "off" : "on");
    } catch (e) {
      /* storage denied: the flip still applies to this page */
    }
  }

  /* One still image. Not the live star program: no GL, no per-frame draw. */
  function stillFieldUrl() {
    if (stillUrl) return stillUrl;
    let seed = 0x5a17c0;
    function rnd() {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    }
    const parts = [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">',
      '<rect width="1280" height="720" fill="#02030a"/>',
      '<ellipse cx="640" cy="380" rx="640" ry="78" fill="#142038" opacity="0.55"/>',
    ];
    for (let i = 0; i < 160; i++) {
      const x = (rnd() * 1280).toFixed(1);
      const y = (rnd() * 720).toFixed(1);
      const r = (0.35 + rnd() * rnd() * 1.7).toFixed(2);
      const pick = rnd();
      const fill = pick < 0.72 ? "#d7e6ff" : pick < 0.9 ? "#fff4e4" : "#ffc99a";
      const opacity = (0.4 + rnd() * 0.6).toFixed(2);
      parts.push(
        '<circle cx="' + x + '" cy="' + y + '" r="' + r +
        '" fill="' + fill + '" opacity="' + opacity + '"/>',
      );
    }
    parts.push("</svg>");
    stillUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(parts.join(""));
    return stillUrl;
  }

  function showStill() {
    if (!canvas) return;
    canvas.setAttribute("data-stars", "still");
    canvas.style.backgroundColor = "#02030a";
    canvas.style.backgroundImage = 'url("' + stillFieldUrl() + '")';
    canvas.style.backgroundSize = "cover";
    canvas.style.backgroundPosition = "center";
    canvas.style.backgroundRepeat = "no-repeat";
  }

  function clearStill() {
    if (!canvas) return;
    canvas.style.backgroundColor = "";
    canvas.style.backgroundImage = "";
    canvas.style.backgroundSize = "";
    canvas.style.backgroundPosition = "";
    canvas.style.backgroundRepeat = "";
  }

  function hoverOff() {
    try {
      return localStorage.getItem(HOVER_KEY) === "off";
    } catch (e) {
      return false;
    }
  }

  function rememberHover(off) {
    try {
      localStorage.setItem(HOVER_KEY, off ? "off" : "on");
    } catch (e) {
      /* storage denied: the next hover on this page still reads the old value */
    }
  }

  function paintSetting(btn, on) {
    if (!btn) return;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-checked", on ? "true" : "false");
    btn.textContent = on ? "On" : "Off";
  }

  function paintSettings() {
    paintSetting(document.getElementById("perfStars"), !shaderOff());
    paintSetting(document.getElementById("perfHover"), !hoverOff());
    const opener = document.getElementById("bPerf");
    if (opener) opener.setAttribute("aria-expanded", perfOpen ? "true" : "false");
  }

  function setShaderOff(off) {
    remember(off);
    if (off) haltLive();
    else startLive();
    paintSettings();
  }

  function setHoverOff(off) {
    rememberHover(off);
    paintSettings();
  }

  function setPerfOpen(open) {
    perfOpen = open;
    const shade = document.getElementById("perfShade");
    const dialog = document.getElementById("perfDialog");
    if (shade) shade.hidden = !open;
    if (dialog) dialog.hidden = !open;
    paintSettings();
    if (open && dialog) {
      const close = dialog.querySelector(".perf-x");
      if (close) close.focus();
    } else {
      const opener = document.getElementById("bPerf");
      if (opener) opener.focus();
    }
  }

  function ensurePerfStyle() {
    if (document.getElementById("perfStyle")) return;
    const style = document.createElement("style");
    style.id = "perfStyle";
    style.textContent =
      "#bPerf{text-transform:none;letter-spacing:.04em}" +
      "#bPerf[aria-expanded=true]{border-color:#f2d67a;color:#f2d67a}" +
      "#perfShade{position:fixed;inset:0;z-index:28;background:rgba(2,6,14,.62)}" +
      "#perfShade[hidden],#perfDialog[hidden]{display:none}" +
      "#perfDialog{position:fixed;z-index:29;left:50%;top:50%;transform:translate(-50%,-50%);" +
      "width:min(440px,calc(100vw - 32px));padding:16px 18px 14px;" +
      "background:rgba(4,8,16,.97);border:1px solid #3d6a96;border-radius:4px;" +
      "color:#d8e8fa;text-align:left;text-transform:none;letter-spacing:.02em;" +
      "box-shadow:0 18px 60px rgba(0,0,0,.65)}" +
      "#perfDialog h2{margin:0;flex:1;font-size:13px;font-weight:400;letter-spacing:.12em;" +
      "text-transform:uppercase;color:#f2d67a}" +
      "#perfDialog .perf-head{display:flex;align-items:center;gap:12px}" +
      "#perfDialog .perf-x{text-transform:none;letter-spacing:.04em}" +
      "#perfDialog .perf-row{display:flex;align-items:center;justify-content:space-between;" +
      "gap:12px;margin-top:14px}" +
      "#perfDialog .perf-name{text-transform:none;letter-spacing:.02em;color:#d8e8fa}" +
      "#perfDialog .perf-note{margin:4px 0 0;color:#5f7590;font-size:10.5px}" +
      "#perfDialog button{text-transform:none;letter-spacing:.04em}";
    document.head.appendChild(style);
  }

  function settingRow(id, name, note) {
    const row = document.createElement("div");
    row.className = "perf-row";
    const label = document.createElement("span");
    label.className = "perf-name";
    label.id = id + "Label";
    label.textContent = name;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = id;
    btn.setAttribute("role", "switch");
    btn.setAttribute("aria-labelledby", label.id);
    row.appendChild(label);
    row.appendChild(btn);
    const hint = document.createElement("p");
    hint.className = "perf-note";
    hint.textContent = note;
    return { row: row, hint: hint, btn: btn };
  }

  function mountPerformance() {
    const btn = document.getElementById("bPerf");
    if (!btn || document.getElementById("perfDialog")) {
      paintSettings();
      return;
    }
    ensurePerfStyle();
    btn.addEventListener("click", function () {
      setPerfOpen(!perfOpen);
    });

    const shade = document.createElement("div");
    shade.id = "perfShade";
    shade.hidden = true;
    shade.addEventListener("click", function () { setPerfOpen(false); });

    const dialog = document.createElement("div");
    dialog.id = "perfDialog";
    dialog.hidden = true;
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "perfTitle");
    const head = document.createElement("div");
    head.className = "perf-head";
    const title = document.createElement("h2");
    title.id = "perfTitle";
    title.textContent = "Performance";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "perf-x";
    close.textContent = "Close";
    close.addEventListener("click", function () { setPerfOpen(false); });
    head.appendChild(title);
    head.appendChild(close);
    dialog.appendChild(head);

    const stars = settingRow(
      "perfStars",
      "Dynamic stars",
      "On is the moving star shader. Off leaves a still star field and does not run that shader.",
    );
    stars.btn.addEventListener("click", function () {
      setShaderOff(!shaderOff());
    });
    dialog.appendChild(stars.row);
    dialog.appendChild(stars.hint);

    const hover = settingRow(
      "perfHover",
      "Pre-load modules on hover",
      "On starts a module loading when the pointer enters it. Off waits for the click.",
    );
    hover.btn.addEventListener("click", function () {
      setHoverOff(!hoverOff());
    });
    dialog.appendChild(hover.row);
    dialog.appendChild(hover.hint);

    document.body.appendChild(shade);
    document.body.appendChild(dialog);
    paintSettings();
  }

  function replaceCanvas(old) {
    const next = document.createElement("canvas");
    next.id = "stars";
    if (old && old.parentNode) old.replaceWith(next);
    return next;
  }

  /* Today's shader. Only called when the switch is on. */
  function mountLive(target) {
    const gl = target.getContext("webgl", {
      antialias: true,
      alpha: false,
    });
    if (!gl) return null;

    const prefersReducedMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function compileShader(type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      return shader;
    }
    function linkProgram(vertexSource, fragmentSource) {
      const shaderProgram = gl.createProgram();
      const vertexShader = compileShader(gl.VERTEX_SHADER, vertexSource);
      const fragmentShader = compileShader(gl.FRAGMENT_SHADER, fragmentSource);
      gl.attachShader(shaderProgram, vertexShader);
      gl.attachShader(shaderProgram, fragmentShader);
      gl.linkProgram(shaderProgram);
      return { program: shaderProgram, vertexShader: vertexShader, fragmentShader: fragmentShader };
    }

    const vertexShaderSource = `
    precision highp float;
    attribute vec3 a_position;   // star direction * shell radius
    attribute vec3 a_color;      // temperature tint
    attribute vec3 a_params;     // x: point size, y: twinkle phase, z: twinkle speed
    uniform mat3  u_rotation;    // view rotation (yaw, pitch, roll)
    uniform vec3  u_camera;      // camera position (drives parallax)
    uniform vec2  u_resolution;
    uniform float u_time;
    uniform float u_fov;
    varying vec3  v_color;
    varying float v_brightness;
    void main() {
      vec3 viewPos = u_rotation * (a_position - u_camera);
      if (viewPos.z <= 0.05) { gl_Position = vec4(2.0); gl_PointSize = 0.0; return; }
      vec2 ndc = vec2(u_fov * viewPos.x / viewPos.z, u_fov * viewPos.y / viewPos.z);
      ndc.x /= (u_resolution.x / u_resolution.y);
      gl_Position = vec4(ndc, 0.0, 1.0);
      float twinkle = 0.72 + 0.28 * sin(u_time * a_params.z + a_params.y);
      float depthScale = clamp(6.0 / viewPos.z, 0.25, 1.6);
      gl_PointSize = a_params.x * depthScale * (0.8 + 0.5 * twinkle) * (u_resolution.y / 900.0 + 0.35);
      v_color = a_color;
      v_brightness = twinkle * depthScale;
    }`;

    const fragmentShaderSource = `
    precision highp float;
    varying vec3  v_color;
    varying float v_brightness;
    void main() {
      float distFromCenter = length(gl_PointCoord - vec2(0.5)) * 2.0;
      float core = smoothstep(1.0, 0.0, distFromCenter);
      float alpha = pow(core, 2.7) * clamp(v_brightness * 1.3, 0.0, 1.8);
      gl_FragColor = vec4(v_color * (0.85 + v_brightness), alpha);
    }`;

    const linked = linkProgram(vertexShaderSource, fragmentShaderSource);
    const starProgram = linked.program;

    const STAR_COUNT = 18000;
    const positionData = new Float32Array(STAR_COUNT * 3);
    const colorData = new Float32Array(STAR_COUNT * 3);
    const paramData = new Float32Array(STAR_COUNT * 3);

    function temperatureToColor(temperature) {
      if (temperature < 0.5) {
        const blend = temperature / 0.5;
        return [0.7 + 0.3 * blend, 0.8 + 0.18 * blend, 1.0];
      }
      const blend = (temperature - 0.5) / 0.5;
      return [1.0, 0.98 - 0.36 * blend, 0.92 - 0.52 * blend];
    }

    for (let i = 0; i < STAR_COUNT; i++) {
      const unitY = Math.random() * 2 - 1;
      const azimuth = Math.random() * Math.PI * 2;
      const ringRadius = Math.sqrt(1 - unitY * unitY);
      let dirX = ringRadius * Math.cos(azimuth);
      let dirY = unitY;
      let dirZ = ringRadius * Math.sin(azimuth);

      if (Math.random() < 0.45) {
        dirY *= 0.28;
        const magnitude = Math.hypot(dirX, dirY, dirZ);
        dirX /= magnitude;
        dirY /= magnitude;
        dirZ /= magnitude;
      }

      const shellRadius = 7 + Math.pow(Math.random(), 0.6) * 26;
      positionData[i * 3] = dirX * shellRadius;
      positionData[i * 3 + 1] = dirY * shellRadius;
      positionData[i * 3 + 2] = dirZ * shellRadius;

      const pointSize = 1.1 + Math.pow(Math.random(), 3.0) * 6.5;
      let temperature = Math.random();
      temperature =
        temperature < 0.72
          ? temperature * 0.5
          : 0.5 + ((temperature - 0.72) / 0.28) * 0.5;
      const color = temperatureToColor(temperature);
      colorData[i * 3] = color[0];
      colorData[i * 3 + 1] = color[1];
      colorData[i * 3 + 2] = color[2];

      paramData[i * 3] = pointSize;
      paramData[i * 3 + 1] = Math.random() * Math.PI * 2;
      paramData[i * 3 + 2] = prefersReducedMotion
        ? 0.0
        : 0.6 + Math.random() * 2.4;
    }

    function createBuffer(data) {
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      return buffer;
    }
    const positionBuffer = createBuffer(positionData);
    const colorBuffer = createBuffer(colorData);
    const paramBuffer = createBuffer(paramData);

    function bindAttribute(name, buffer, componentsPerVertex) {
      const location = gl.getAttribLocation(starProgram, name);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, componentsPerVertex, gl.FLOAT, false, 0, 0);
    }

    const rotationLoc = gl.getUniformLocation(starProgram, "u_rotation");
    const cameraLoc = gl.getUniformLocation(starProgram, "u_camera");
    const resolutionLoc = gl.getUniformLocation(starProgram, "u_resolution");
    const timeLoc = gl.getUniformLocation(starProgram, "u_time");
    const fovLoc = gl.getUniformLocation(starProgram, "u_fov");

    let viewportWidth = 0,
      viewportHeight = 0;
    function resize() {
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      viewportWidth = Math.floor(window.innerWidth * pixelRatio);
      viewportHeight = Math.floor(window.innerHeight * pixelRatio);
      target.width = viewportWidth;
      target.height = viewportHeight;
      gl.viewport(0, 0, viewportWidth, viewportHeight);
    }
    window.addEventListener("resize", resize);
    resize();

    let isRunning = false;
    let alive = true;
    let rafId = 0;
    let animationTime = 0;
    let lastFrameMs = 0;
    function startRenderLoop() {
      if (!alive || isRunning) return;
      isRunning = true;
      lastFrameMs = performance.now();
      rafId = requestAnimationFrame(renderFrame);
    }
    function onVisibility() {
      if (!alive) return;
      if (document.hidden) isRunning = false;
      else startRenderLoop();
    }
    document.addEventListener("visibilitychange", onVisibility);

    function renderFrame(nowMs) {
      if (!alive || !isRunning) return;
      const deltaSeconds = Math.min(0.05, (nowMs - lastFrameMs) / 1000);
      lastFrameMs = nowMs;
      if (!prefersReducedMotion) animationTime += deltaSeconds;
      const time = animationTime;

      const yaw = time * 0.02;
      const pitch = Math.sin(time * 0.045) * 0.12;
      const roll = Math.sin(time * 0.035) * 0.08;
      const cosYaw = Math.cos(yaw),
        sinYaw = Math.sin(yaw);
      const cosPitch = Math.cos(pitch),
        sinPitch = Math.sin(pitch);
      const cosRoll = Math.cos(roll),
        sinRoll = Math.sin(roll);

      const rotationMatrix = new Float32Array([
        cosRoll * cosYaw,
        sinRoll * cosYaw,
        -sinYaw,

        -cosRoll * sinYaw * sinPitch - sinRoll * cosPitch,
        -sinRoll * sinYaw * sinPitch + cosRoll * cosPitch,
        -cosYaw * sinPitch,

        cosRoll * sinYaw * cosPitch - sinRoll * sinPitch,
        sinRoll * sinYaw * cosPitch + cosRoll * sinPitch,
        cosYaw * cosPitch,
      ]);

      const cameraPosition = prefersReducedMotion
        ? [0, 0, 0]
        : [
            Math.sin(time * 0.06) * 0.9,
            Math.sin(time * 0.045) * 0.5,
            Math.cos(time * 0.05) * 0.9,
          ];

      gl.clearColor(0.008, 0.012, 0.039, 1.0);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.useProgram(starProgram);
      bindAttribute("a_position", positionBuffer, 3);
      bindAttribute("a_color", colorBuffer, 3);
      bindAttribute("a_params", paramBuffer, 3);
      gl.uniformMatrix3fv(rotationLoc, false, rotationMatrix);
      gl.uniform3f(cameraLoc, cameraPosition[0], cameraPosition[1], cameraPosition[2]);
      gl.uniform2f(resolutionLoc, viewportWidth, viewportHeight);
      gl.uniform1f(timeLoc, time);
      gl.uniform1f(fovLoc, 1.2);

      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
      gl.drawArrays(gl.POINTS, 0, STAR_COUNT);
      gl.disable(gl.BLEND);

      if (prefersReducedMotion) {
        isRunning = false;
        return;
      }
      rafId = requestAnimationFrame(renderFrame);
    }
    startRenderLoop();

    return function stop() {
      alive = false;
      isRunning = false;
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      gl.deleteProgram(starProgram);
      gl.deleteShader(linked.vertexShader);
      gl.deleteShader(linked.fragmentShader);
      gl.deleteBuffer(positionBuffer);
      gl.deleteBuffer(colorBuffer);
      gl.deleteBuffer(paramBuffer);
      const lose = gl.getExtension("WEBGL_lose_context");
      if (lose) lose.loseContext();
      return replaceCanvas(target);
    };
  }

  function startLive() {
    if (stopLive || !canvas) return;
    clearStill();
    canvas.setAttribute("data-stars", "live");
    stopLive = mountLive(canvas);
    if (!stopLive) canvas.setAttribute("data-stars", "unavailable");
  }

  function haltLive() {
    if (stopLive) {
      const next = stopLive();
      stopLive = null;
      if (next) canvas = next;
    }
    showStill();
  }

  if (canvas) {
    if (shaderOff()) showStill();
    else startLive();
  }

  document.addEventListener("keydown", function (e) {
    if (!perfOpen || e.key !== "Escape") return;
    setPerfOpen(false);
    e.preventDefault();
    e.stopPropagation();
  }, true);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountPerformance);
  } else {
    mountPerformance();
  }
})();
