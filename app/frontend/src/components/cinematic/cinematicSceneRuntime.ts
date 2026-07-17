import * as THREE from 'three';
import type { CinematicSceneProfile } from './cinematicSceneProfile';
import { resolveShaderOctaves } from './cinematicAdaptiveQuality';

export interface CinematicPointer {
  x: number;
  y: number;
}

export interface CinematicSceneRuntime {
  readonly key: string;
  readonly maxFps: number;
  readonly pixelRatioScale: number;
  setQualityScale(scale: number): void;
  resize(width: number, height: number): void;
  update(deltaSeconds: number, elapsedSeconds: number, pointer: CinematicPointer, focus: number): void;
  render(renderer: THREE.WebGLRenderer): void;
  resetClock(): void;
  dispose(): void;
}

function makeLine(points: THREE.Vector3[], color: number, opacity: number) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  return new THREE.Line(geometry, material);
}

function disposeMaterial(material: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) material.forEach((item) => item.dispose());
  else material.dispose();
}

export function createCinematicSceneRuntime(
  key: string,
  config: CinematicSceneProfile,
  size: { width: number; height: number },
): CinematicSceneRuntime {
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x050302, 0.023);

  const camera = new THREE.PerspectiveCamera(50, size.width / size.height, 0.1, 100);
  camera.position.set(0, 0, 7.5);

  const group = new THREE.Group();
  scene.add(group);

  const bgMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    defines: { CINEMATIC_OCTAVES: 6 },
    uniforms: {
      t: { value: 0 },
      m: { value: new THREE.Vector2() },
      intensity: { value: config.bgIntensity },
    },
    vertexShader: `varying vec2 v;void main(){v=uv;gl_Position=vec4(position,1.);}`,
    fragmentShader: `
      precision highp float;
      varying vec2 v;
      uniform float t;
      uniform float intensity;
      uniform vec2 m;
      float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5);}
      float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
      float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<CINEMATIC_OCTAVES;i++){v+=a*n(p);p*=2.03;a*=.5;}return v;}
      void main(){
        vec2 p=v-.5;p.x*=1.78;p+=m*.055;
        float q=fbm(p*2.8+vec2(t*.035,-t*.025));
        float q2=fbm(p*8.5-vec2(t*.05,t*.03));
        float orb=smoothstep(.62,.02,length(p-vec2(.04,-.02)));
        float grain=step(.982,n(v*vec2(420.,240.)+t*.4));
        vec3 warm=vec3(1.,.62,.16);
        vec3 cold=vec3(.32,.54,1.);
        vec3 col=warm*(orb*.18+q2*.045+grain*.18)+cold*(q*.018);
        float a=(orb*.20+q*.045+q2*.035+grain*.16)*smoothstep(1.05,.12,length(p));
        gl_FragColor=vec4(col,a*intensity);
      }`,
  });
  scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMaterial));

  const earth = new THREE.Group();
  earth.position.set(config.earthPosition[0], config.earthPosition[1], config.earthPosition[2]);
  earth.rotation.set(0.22, 0, 0.56);
  earth.scale.setScalar(config.earthScale);
  group.add(earth);

  const globe = new THREE.Group();
  globe.rotation.y = -0.48;
  earth.add(globe);

  const coreMaterial = new THREE.MeshBasicMaterial({
    color: 0xffc46d,
    transparent: true,
    opacity: 0.185 * config.globeIntensity,
    wireframe: true,
    blending: THREE.AdditiveBlending,
  });
  const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1.82, 5), coreMaterial);
  core.position.set(0, 0, -0.1);
  globe.add(core);

  const innerCore = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.22, 3),
    new THREE.MeshBasicMaterial({
      color: 0xffdf9a,
      transparent: true,
      opacity: 0.092 * config.globeIntensity,
      wireframe: true,
      blending: THREE.AdditiveBlending,
    }),
  );
  innerCore.position.set(0, 0, -0.1);
  globe.add(innerCore);

  const scanGroup = new THREE.Group();
  globe.add(scanGroup);
  const scanRings: THREE.Line[] = [];
  for (let i = 0; i < 3; i += 1) {
    const points = new THREE.EllipseCurve(0, 0, 2.12 + i * 0.18, 2.12 + i * 0.18).getPoints(260)
      .map((point) => new THREE.Vector3(point.x, point.y, -0.1));
    const ring = makeLine(points, i === 1 ? 0xa78bfa : 0xffe0a0, 0.06 + i * 0.02);
    ring.rotation.x = 0.62 + i * 0.36;
    ring.rotation.y = i * 0.72;
    ring.userData.baseOpacity = (0.06 + i * 0.02) * config.globeIntensity;
    scanGroup.add(ring);
    scanRings.push(ring);
  }

  const ringGroup = new THREE.Group();
  globe.add(ringGroup);
  const orbitLines: THREE.Line[] = [];
  for (let i = 0; i < 14; i += 1) {
    const points = new THREE.EllipseCurve(0, 0, 1.52 + i * 0.15, 0.36 + i * 0.05).getPoints(260)
      .map((point) => new THREE.Vector3(point.x, 0, point.y - 0.1));
    const strong = i === 3 || i === 8 || i === 12;
    const line = makeLine(points, strong ? 0xffedc6 : i % 2 ? 0xd7ae65 : 0xffe8bc, (strong ? 0.155 : 0.105) + i * 0.01);
    line.rotation.x = 0.7 + i * 0.052;
    line.rotation.y = i * 0.22;
    line.rotation.z = i * 0.018;
    line.userData.baseOpacity = (line.material as THREE.LineBasicMaterial).opacity * config.globeIntensity;
    (line.material as THREE.LineBasicMaterial).opacity = line.userData.baseOpacity;
    line.userData.strong = strong;
    ringGroup.add(line);
    orbitLines.push(line);
  }

  for (let i = 0; i < 8; i += 1) {
    const points = new THREE.EllipseCurve(0, 0, 1.94, 0.66).getPoints(220)
      .map((point) => new THREE.Vector3(point.x, 0, point.y - 0.1));
    const line = makeLine(points, 0xffe5a8, 0.088 + i * 0.007);
    line.rotation.x = Math.PI / 2;
    line.rotation.y = i * Math.PI / 8;
    line.userData.baseOpacity = (line.material as THREE.LineBasicMaterial).opacity * config.globeIntensity;
    (line.material as THREE.LineBasicMaterial).opacity = line.userData.baseOpacity;
    line.userData.strong = i === 1 || i === 5;
    ringGroup.add(line);
    orbitLines.push(line);
  }

  const nodeGeometry = new THREE.BufferGeometry();
  const nodePositions: number[] = [];
  for (let i = 0; i < 520; i += 1) {
    const angle = Math.random() * Math.PI * 2;
    const latitude = -0.95 + Math.random() * 1.9;
    const radius = 1.84 + Math.random() * 0.24;
    nodePositions.push(
      Math.cos(latitude) * Math.cos(angle) * radius,
      Math.sin(latitude) * radius,
      Math.cos(latitude) * Math.sin(angle) * radius - 0.1,
    );
  }
  nodeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(nodePositions, 3));
  const nodeMaterial = new THREE.PointsMaterial({
    color: 0xffda92,
    size: 0.041,
    transparent: true,
    opacity: 0.5 * config.globeIntensity,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  globe.add(new THREE.Points(nodeGeometry, nodeMaterial));

  const arcLines: THREE.Line[] = [];
  const addArc = (a1: number, a2: number, radius = 2.05) => {
    const p1 = new THREE.Vector3(Math.cos(a1) * radius, Math.sin(a1 * 0.7) * 0.9, Math.sin(a1) * radius - 0.1);
    const p2 = new THREE.Vector3(Math.cos(a2) * radius, Math.sin(a2 * 0.7) * 0.9, Math.sin(a2) * radius - 0.1);
    const mid = p1.clone().add(p2).normalize().multiplyScalar(2.65);
    const line = makeLine(new THREE.QuadraticBezierCurve3(p1, mid, p2).getPoints(90), 0xffdfa2, 0.25);
    (line.material as THREE.LineBasicMaterial).opacity *= config.globeIntensity;
    globe.add(line);
    arcLines.push(line);
  };
  addArc(0.25, 2.2);
  addArc(1.7, 4.15);
  addArc(3.2, 5.4);

  const anchorDefs = [
    { a: 0.18, lat: 0.38 }, { a: 0.72, lat: 0.04 }, { a: 1.22, lat: -0.24 },
    { a: 1.78, lat: -0.48 }, { a: 2.42, lat: 0.12 }, { a: 3.14, lat: 0.3 },
    { a: 4.1, lat: -0.18 }, { a: 5.18, lat: 0.22 },
  ];
  const anchorItems: Array<{ dot: THREE.Mesh; halo: THREE.Mesh; index: number }> = [];
  const anchorGeometry = new THREE.SphereGeometry(0.045, 16, 10);
  const haloGeometry = new THREE.TorusGeometry(0.087, 0.004, 8, 36);
  anchorDefs.forEach((definition, index) => {
    const radius = 1.98;
    const point = new THREE.Vector3(
      Math.cos(definition.lat) * Math.cos(definition.a) * radius,
      Math.sin(definition.lat) * radius,
      Math.cos(definition.lat) * Math.sin(definition.a) * radius - 0.1,
    );
    const dot = new THREE.Mesh(anchorGeometry, new THREE.MeshBasicMaterial({
      color: index % 2 ? 0xa78bfa : 0xffd481,
      transparent: true,
      opacity: 0.28 * config.globeIntensity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }));
    dot.position.copy(point);
    globe.add(dot);
    const halo = new THREE.Mesh(haloGeometry, new THREE.MeshBasicMaterial({
      color: 0xffe6aa,
      transparent: true,
      opacity: 0.18 * config.globeIntensity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }));
    halo.position.copy(point);
    halo.lookAt(0, 0, -0.1);
    globe.add(halo);
    anchorItems.push({ dot, halo, index: index + 1 });
  });

  const pulseItems: Array<{ line: THREE.Line; index: number; base: number }> = [];
  anchorDefs.slice(0, 5).forEach((definition, index) => {
    const radius = 2.02;
    const p1 = new THREE.Vector3(
      Math.cos(definition.lat) * Math.cos(definition.a) * radius,
      Math.sin(definition.lat) * radius,
      Math.cos(definition.lat) * Math.sin(definition.a) * radius - 0.1,
    );
    const p2 = p1.clone().multiplyScalar(1.38);
    p2.x += 0.56 + index * 0.06;
    p2.y += (index - 2) * 0.08;
    const mid = p1.clone().add(p2).multiplyScalar(0.5).normalize().multiplyScalar(2.78);
    const line = makeLine(new THREE.QuadraticBezierCurve3(p1, mid, p2).getPoints(80), index === 1 ? 0xa78bfa : 0xffd481, 0.045);
    globe.add(line);
    pulseItems.push({ line, index: index + 1, base: 0.045 * config.globeIntensity });
    (line.material as THREE.LineBasicMaterial).opacity = 0.045 * config.globeIntensity;
  });

  const terrain = new THREE.Group();
  group.add(terrain);
  for (let row = 0; row < 34; row += 1) {
    const points: THREE.Vector3[] = [];
    const z = -16 + row * 0.42;
    const width = 15.5 + Math.abs(z) * 0.1;
    for (let column = 0; column < 132; column += 1) {
      const x = -width / 2 + (width * column) / 131 + row * 0.035;
      const y = -2.12 + Math.sin(column * 0.16 + row * 0.36) * 0.055 + Math.cos(column * 0.055) * 0.035;
      points.push(new THREE.Vector3(x, y, z));
    }
    terrain.add(makeLine(points, 0xf0b85a, (0.035 + row * 0.0038) * config.terrainIntensity));
  }
  terrain.rotation.x = -0.075;
  terrain.rotation.z = 0.015;
  terrain.position.set(1.15, -0.08, 3.9);

  const signalMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    defines: { CINEMATIC_OCTAVES: 5 },
    uniforms: { uTime: { value: 0 }, intensity: { value: config.signalIntensity } },
    vertexShader: `varying vec2 v;void main(){v=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
    fragmentShader: `
      precision highp float;
      varying vec2 v;
      uniform float uTime;
      uniform float intensity;
      float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5);}
      float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
      float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<CINEMATIC_OCTAVES;i++){v+=a*n(p);p*=2.04;a*=.5;}return v;}
      void main(){
        vec2 p=v-.5;p.x*=1.75;
        float t=uTime*.10;
        float q=fbm(p*3.0+vec2(t,-t*.7));
        float core=smoothstep(.62,.05,length(p-vec2(.12,-.08)));
        float horizon=smoothstep(.42,.035,abs(p.y+.22+sin(p.x*4.8+uTime*.22)*.018));
        float dust=step(.975,n(v*vec2(380.,220.)+uTime*.45));
        vec3 gold=vec3(1.,.66,.20);
        float a=(q*.10+core*.18+horizon*.045+dust*.12)*smoothstep(.02,.26,v.y)*smoothstep(1.,.52,v.y);
        gl_FragColor=vec4(gold,a*intensity);
      }`,
  });
  const signalPlane = new THREE.Mesh(new THREE.PlaneGeometry(22, 12.5), signalMaterial);
  signalPlane.position.set(1.45, 0.06, -3.15);
  scene.add(signalPlane);

  const particleGeometry = new THREE.BufferGeometry();
  const positions = new Float32Array(config.particleCount * 3);
  const colors = new Float32Array(config.particleCount * 3);
  const sizes = new Float32Array(config.particleCount);
  for (let index = 0; index < config.particleCount; index += 1) {
    const angle = Math.random() * Math.PI * 2;
    const radius = Math.pow(Math.random(), 0.48) * 9.2;
    positions[index * 3] = Math.cos(angle) * radius;
    positions[index * 3 + 1] = (Math.random() - 0.5) * 5.6;
    positions[index * 3 + 2] = Math.sin(angle) * radius - 3.2;
    const warm = Math.random() < 0.76;
    colors[index * 3] = warm ? 1 : 0.72;
    colors[index * 3 + 1] = warm ? 0.62 : 0.78;
    colors[index * 3 + 2] = warm ? 0.15 : 1;
    sizes[index] = 0.022 + Math.random() * 0.074 + Math.pow(Math.random(), 6) * 0.13;
  }
  particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  particleGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  particleGeometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
  const particleMaterial = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    vertexColors: true,
    blending: THREE.AdditiveBlending,
    uniforms: { t: { value: 0 }, m: { value: new THREE.Vector2() }, intensity: { value: config.particleIntensity } },
    vertexShader: `
      attribute float aSize;
      varying vec3 c;
      uniform float t;
      uniform vec2 m;
      void main(){
        c=color;
        vec3 p=position;
        p.x+=sin(t*.18+p.z*.18)*.13+m.x*.20;
        p.y+=cos(t*.16+p.x*.2)*.08+m.y*.10;
        vec4 mv=modelViewMatrix*vec4(p,1.);
        gl_PointSize=aSize*560./-mv.z;
        gl_Position=projectionMatrix*mv;
      }`,
    fragmentShader: `
      varying vec3 c;
      uniform float intensity;
      void main(){
        float d=length(gl_PointCoord-.5);
        float a=smoothstep(.5,.035,d);
        gl_FragColor=vec4(c,a*.34*intensity);
      }`,
  });
  group.add(new THREE.Points(particleGeometry, particleMaterial));

  let focusValue = 0;
  let disposed = false;

  return {
    key,
    maxFps: config.maxFps,
    pixelRatioScale: config.pixelRatioScale,
    setQualityScale(scale: number) {
      const octaves = resolveShaderOctaves(scale);
      if (bgMaterial.defines.CINEMATIC_OCTAVES !== octaves.background) {
        bgMaterial.defines.CINEMATIC_OCTAVES = octaves.background;
        bgMaterial.needsUpdate = true;
      }
      if (signalMaterial.defines.CINEMATIC_OCTAVES !== octaves.signal) {
        signalMaterial.defines.CINEMATIC_OCTAVES = octaves.signal;
        signalMaterial.needsUpdate = true;
      }
    },
    resize(width, height) {
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
    },
    update(_deltaSeconds, time, pointer, manualFocus) {
      if (disposed) return;
      const autoValue = manualFocus ? 1 : 0.46 + 0.18 * Math.sin(time * 0.72);
      focusValue += (autoValue - focusValue) * 0.065;
      bgMaterial.uniforms.t.value = time;
      bgMaterial.uniforms.m.value.set(pointer.x, pointer.y);
      particleMaterial.uniforms.t.value = time;
      particleMaterial.uniforms.m.value.set(pointer.x, pointer.y);
      signalMaterial.uniforms.uTime.value = time;
      terrain.position.z = 3.6 + Math.sin(time * 0.2 * config.motion) * 0.18;
      terrain.rotation.y = Math.sin(time * 0.13 * config.motion) * 0.018;
      globe.rotation.y = -0.48 + time * (0.04 + focusValue * 0.02) * config.motion;
      core.rotation.x = time * (0.05 + focusValue * 0.024) * config.motion;
      core.rotation.y = time * (0.07 + focusValue * 0.032) * config.motion;
      coreMaterial.opacity = (0.165 + focusValue * 0.06 + Math.sin(time * 2.4) * 0.012) * config.globeIntensity;
      (innerCore.material as THREE.MeshBasicMaterial).opacity = (0.084 + focusValue * 0.04 + Math.max(0, Math.sin(time * 1.7)) * 0.01) * config.globeIntensity;
      nodeMaterial.opacity = (0.46 + focusValue * 0.18) * config.globeIntensity;
      nodeMaterial.size = 0.04 + focusValue * 0.01;
      scanGroup.rotation.y = -time * 0.105 * config.motion;
      scanGroup.rotation.x = 0.18 + Math.sin(time * 0.22 * config.motion) * 0.12;
      scanRings.forEach((ring, index) => {
        const wave = 0.5 + 0.5 * Math.sin(time * 1.9 + index * 1.35);
        (ring.material as THREE.LineBasicMaterial).opacity = ring.userData.baseOpacity + (wave * 0.105 + focusValue * 0.025) * config.globeIntensity;
        ring.scale.setScalar(1 + wave * 0.024);
      });
      orbitLines.forEach((line, index) => {
        const pulse = Math.max(0, Math.sin(time * 1.9 + index * 0.62)) * (line.userData.strong ? 0.052 : 0.034);
        (line.material as THREE.LineBasicMaterial).opacity = (line.userData.baseOpacity || 0.075) + (pulse + focusValue * (line.userData.strong ? 0.065 : 0.045)) * config.globeIntensity;
      });
      arcLines.forEach((line, index) => {
        (line.material as THREE.LineBasicMaterial).opacity = (0.22 + Math.max(0, Math.sin(time * 2.2 + index * 1.4)) * 0.18 + focusValue * 0.05) * config.globeIntensity;
      });
      const activeFocus = manualFocus || Math.floor(time / 3.2) % 6 + 1;
      anchorItems.forEach((item) => {
        const active = activeFocus === item.index || activeFocus > 5;
        const flicker = 0.5 + 0.5 * Math.sin(time * 3.2 + item.index);
        (item.dot.material as THREE.MeshBasicMaterial).opacity = (0.34 + (active ? 0.64 : 0) + focusValue * 0.1 + flicker * 0.08) * config.globeIntensity;
        item.dot.scale.setScalar(1.08 + (active ? 0.86 : 0) + flicker * 0.22);
        (item.halo.material as THREE.MeshBasicMaterial).opacity = (0.17 + (active ? 0.48 : 0) + flicker * 0.1) * config.globeIntensity;
        item.halo.scale.setScalar(1.08 + (active ? 0.62 : 0) + Math.sin(time * 2.2 + item.index) * 0.14);
      });
      pulseItems.forEach((item) => {
        const active = activeFocus === item.index;
        const wave = Math.max(0, Math.sin(time * 2.7 + item.index * 0.85));
        (item.line.material as THREE.LineBasicMaterial).opacity = item.base + (focusValue * 0.065 + (active ? 0.46 : 0.1) * wave) * config.globeIntensity;
        item.line.scale.setScalar(1 + (active ? wave * 0.03 : wave * 0.008));
      });
      ringGroup.rotation.y = time * (0.06 + focusValue * 0.034) * config.motion;
      ringGroup.rotation.x = 0.05 + Math.sin(time * 0.18 * config.motion) * 0.034 + focusValue * 0.022;
      earth.rotation.x = 0.22 + Math.sin(time * 0.12 * config.motion) * 0.012;
      group.rotation.y += (pointer.x * 0.045 * config.pointer + focusValue * 0.012 - group.rotation.y) * 0.025;
      camera.position.x += (pointer.x * 0.35 * config.pointer - camera.position.x) * 0.03;
      camera.position.y += (-pointer.y * 0.24 * config.pointer - camera.position.y) * 0.03;
      camera.lookAt(0, 0, -1.5);
    },
    render(renderer) {
      if (!disposed) renderer.render(scene, camera);
    },
    resetClock() {
      // Elapsed time is owned by the persistent renderer host.
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      const geometries = new Set<THREE.BufferGeometry>();
      const materials = new Set<THREE.Material>();
      scene.traverse((object) => {
        const renderable = object as THREE.Mesh;
        if (renderable.geometry) geometries.add(renderable.geometry);
        const material = renderable.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(material)) material.forEach((item) => materials.add(item));
        else if (material) materials.add(material);
      });
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((material) => disposeMaterial(material));
      scene.clear();
    },
  };
}

export class CinematicSceneRuntimeCache {
  private readonly runtimes = new Map<string, CinematicSceneRuntime>();

  getOrCreate(key: string, factory: () => CinematicSceneRuntime) {
    const existing = this.runtimes.get(key);
    if (existing) return existing;
    const runtime = factory();
    this.runtimes.set(key, runtime);
    return runtime;
  }

  get size() {
    return this.runtimes.size;
  }

  dispose() {
    this.runtimes.forEach((runtime) => runtime.dispose());
    this.runtimes.clear();
  }
}
