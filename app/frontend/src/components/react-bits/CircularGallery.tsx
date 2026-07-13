import { Camera, Mesh, Plane, Program, Renderer, Texture, Transform } from 'ogl';
import { useEffect, useRef } from 'react';
import { arcTransform, lerp, snapTarget, wrapOffset } from './circularGalleryMath.mjs';
import './CircularGallery.css';

export interface CircularGalleryItem { image: string; text: string }
interface CircularGalleryProps {
  items: CircularGalleryItem[];
  bend?: number;
  textColor?: string;
  borderRadius?: number;
  scrollSpeed?: number;
  scrollEase?: number;
  itemScale?: number;
  dpr?: number;
  interactive?: boolean;
  onItemSelect?: (item: CircularGalleryItem, index: number) => void;
}
interface Size { width: number; height: number }
interface ScrollState { ease: number; current: number; target: number; last: number; position: number }
type GL = Renderer['gl'];

const vertex = `
precision highp float;
attribute vec3 position; attribute vec2 uv;
uniform mat4 modelViewMatrix; uniform mat4 projectionMatrix;
uniform float uTime; uniform float uSpeed;
varying vec2 vUv;
void main(){
  vUv=uv; vec3 p=position;
  p.z=(sin(p.x*4.0+uTime)*1.5+cos(p.y*2.0+uTime)*1.5)*(0.1+abs(uSpeed)*0.5);
  gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);
}`;

const fragment = `
precision highp float;
uniform vec2 uImageSizes; uniform vec2 uPlaneSizes;
uniform sampler2D tMap; uniform float uBorderRadius;
varying vec2 vUv;
float roundedBoxSDF(vec2 p,vec2 b,float r){vec2 d=abs(p)-b;return length(max(d,vec2(0.0)))+min(max(d.x,d.y),0.0)-r;}
void main(){
  vec2 ratio=vec2(min((uPlaneSizes.x/uPlaneSizes.y)/(uImageSizes.x/uImageSizes.y),1.0),min((uPlaneSizes.y/uPlaneSizes.x)/(uImageSizes.y/uImageSizes.x),1.0));
  vec2 uv=vec2(vUv.x*ratio.x+(1.0-ratio.x)*0.5,vUv.y*ratio.y+(1.0-ratio.y)*0.5);
  vec4 color=texture2D(tMap,uv);
  float d=roundedBoxSDF(vUv-0.5,vec2(0.5-uBorderRadius),uBorderRadius);
  float alpha=1.0-smoothstep(-0.002,0.002,d);
  gl_FragColor=vec4(color.rgb,alpha);
}`;

const labelVertex = `attribute vec3 position;attribute vec2 uv;uniform mat4 modelViewMatrix;uniform mat4 projectionMatrix;varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
const labelFragment = `precision highp float;uniform sampler2D tMap;varying vec2 vUv;void main(){vec4 c=texture2D(tMap,vUv);if(c.a<0.08)discard;gl_FragColor=c;}`;

function createCanvasTexture(gl: GL, text: string, color = '#f5f3ff') {
  const canvas = document.createElement('canvas'); const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D unavailable');
  context.font = '600 34px Inter, system-ui, sans-serif'; const width = Math.ceil(context.measureText(text).width) + 32;
  canvas.width = width; canvas.height = 64; context.font = '600 34px Inter, system-ui, sans-serif'; context.fillStyle = color; context.textAlign = 'center'; context.textBaseline = 'middle'; context.fillText(text, width / 2, 32);
  const texture = new Texture(gl, { generateMipmaps: false }); texture.image = canvas;
  return { texture, aspect: width / 64 };
}

function createFallbackTexture(gl: GL, text: string) {
  const canvas = document.createElement('canvas'); canvas.width = 800; canvas.height = 600; const context = canvas.getContext('2d');
  if (!context) return null;
  const hue = [...text].reduce((sum, char) => sum + char.charCodeAt(0), 0) % 360;
  const gradient = context.createLinearGradient(0, 0, 800, 600); gradient.addColorStop(0, `hsl(${hue} 28% 16%)`); gradient.addColorStop(1, `hsl(${(hue + 55) % 360} 34% 7%)`);
  context.fillStyle = gradient; context.fillRect(0, 0, 800, 600); context.strokeStyle = 'rgba(255,255,255,.14)'; context.lineWidth = 2;
  for (let index = 0; index < 9; index += 1) { context.beginPath(); context.arc(400, 300, 50 + index * 38, 0, Math.PI * 2); context.stroke(); }
  const texture = new Texture(gl, { generateMipmaps: true }); texture.image = canvas; return texture;
}

class GalleryMedia {
  plane: Mesh; label: Mesh; program: Program; extra = 0; width = 0; widthTotal = 0; x = 0;
  constructor(private gl: GL, geometry: Plane, private item: CircularGalleryItem, private index: number, private length: number, private scene: Transform, private screen: Size, private viewport: Size, private bend: number, borderRadius: number, textColor: string, private itemScale: number, requestRender: () => void) {
    const texture = createFallbackTexture(gl, item.text) || new Texture(gl); const image = new Image(); image.crossOrigin = 'anonymous'; image.src = item.image;
    const uniforms = { tMap: { value: texture }, uPlaneSizes: { value: [1, 1] }, uImageSizes: { value: [800, 600] }, uSpeed: { value: 0 }, uTime: { value: Math.random() * 100 }, uBorderRadius: { value: borderRadius } };
    this.program = new Program(gl, { vertex, fragment, uniforms, transparent: true, depthTest: false, depthWrite: false });
    image.onload = () => { texture.image = image; uniforms.uImageSizes.value = [image.naturalWidth, image.naturalHeight]; requestRender(); };
    this.plane = new Mesh(gl, { geometry, program: this.program }); this.plane.setParent(scene);
    const labelData = createCanvasTexture(gl, item.text, textColor); const labelProgram = new Program(gl, { vertex: labelVertex, fragment: labelFragment, uniforms: { tMap: { value: labelData.texture } }, transparent: true, depthTest: false, depthWrite: false });
    this.label = new Mesh(gl, { geometry: new Plane(gl), program: labelProgram }); this.label.setParent(scene); (this.label as any)._aspect = labelData.aspect;
    this.resize(screen, viewport);
  }
  resize(screen: Size, viewport: Size) {
    this.screen = screen; this.viewport = viewport; const scale = screen.height / 1500;
    this.plane.scale.y = ((viewport.height * (900 * scale)) / screen.height) * this.itemScale; this.plane.scale.x = ((viewport.width * (700 * scale)) / screen.width) * this.itemScale;
    this.program.uniforms.uPlaneSizes.value = [this.plane.scale.x, this.plane.scale.y];
    const labelHeight = this.plane.scale.y * .12; this.label.scale.set(labelHeight * (this.label as any)._aspect, labelHeight, 1);
    this.width = this.plane.scale.x + 2 * this.itemScale; this.widthTotal = this.width * this.length; this.x = this.width * this.index;
  }
  update(scroll: ScrollState, direction: 'right' | 'left', wrap = true) {
    this.plane.position.x = this.x - scroll.current - this.extra; const arc = arcTransform(this.plane.position.x, this.viewport.width, this.bend);
    this.plane.position.y = arc.y; this.plane.rotation.z = arc.rotation;
    this.label.position.x = this.plane.position.x; this.label.position.y = arc.y - this.plane.scale.y * .5 - this.label.scale.y * .75; this.label.rotation.z = arc.rotation;
    const speed = scroll.current - scroll.last;
    this.program.uniforms.uTime.value += Math.min(.04, .012 + Math.abs(speed) * .04); this.program.uniforms.uSpeed.value = speed;
    if (wrap) {
      const shift = wrapOffset(this.plane.position.x, this.plane.scale.x / 2, this.viewport.width / 2, this.widthTotal, direction);
      if (shift) this.extra += shift;
    }
  }
}

class GalleryApp {
  renderer: Renderer; gl: GL; camera: Camera; scene = new Transform(); geometry: Plane; medias: GalleryMedia[] = []; screen = { width: 1, height: 1 }; viewport = { width: 1, height: 1 };
  scroll: ScrollState; raf = 0; isDown = false; start = 0; resizeObserver: ResizeObserver; snapTimer = 0; visible = true; destroyed = false;
  constructor(private container: HTMLElement, items: CircularGalleryItem[], private bend: number, textColor: string, borderRadius: number, private scrollSpeed: number, scrollEase: number, itemScale: number, dpr: number, private interactive: boolean) {
    this.scroll = { ease: scrollEase, current: 0, target: 0, last: 0, position: 0 };
    this.renderer = new Renderer({ alpha: true, antialias: true, dpr: Math.min(window.devicePixelRatio || 1, dpr) }); this.gl = this.renderer.gl; this.gl.clearColor(0, 0, 0, 0); container.appendChild(this.gl.canvas as HTMLCanvasElement);
    this.camera = new Camera(this.gl); this.camera.fov = 45; this.camera.position.z = 20; this.geometry = new Plane(this.gl, { heightSegments: interactive ? 50 : 24, widthSegments: interactive ? 100 : 48 });
    this.resize(); const sourceItems = interactive ? [...items, ...items] : items; this.medias = sourceItems.map((item, index) => new GalleryMedia(this.gl, this.geometry, item, index, sourceItems.length, this.scene, this.screen, this.viewport, bend, borderRadius, textColor, itemScale, this.requestRender));
    const initialOffset = this.medias[0].width * (interactive ? items.length : (items.length - 1) / 2); this.scroll.current = initialOffset; this.scroll.target = initialOffset; this.scroll.last = initialOffset;
    this.resizeObserver = new ResizeObserver(this.resize); this.resizeObserver.observe(container); if (this.interactive) this.addEvents();
    if (this.interactive) this.update(); else this.renderFrame();
  }
  resize = () => { this.screen = { width: Math.max(1, this.container.clientWidth), height: Math.max(1, this.container.clientHeight) }; this.renderer.setSize(this.screen.width, this.screen.height); this.camera.perspective({ aspect: this.screen.width / this.screen.height }); const fov = this.camera.fov * Math.PI / 180; const height = 2 * Math.tan(fov / 2) * this.camera.position.z; this.viewport = { width: height * this.camera.aspect, height }; this.medias.forEach(media => media.resize(this.screen, this.viewport)); if (!this.interactive && this.medias[0]) { const staticOffset = this.medias[0].width * (this.medias.length - 1) / 2; this.scroll.current = staticOffset; this.scroll.target = staticOffset; this.scroll.last = staticOffset; this.renderFrame(); } };
  requestRender = () => { if (!this.interactive && !this.destroyed) this.renderFrame(); };
  snap = () => { if (this.medias[0]) this.scroll.target = snapTarget(this.scroll.target, this.medias[0].width); };
  queueSnap = () => { window.clearTimeout(this.snapTimer); this.snapTimer = window.setTimeout(this.snap, 180); };
  onWheel = (event: WheelEvent) => { if (!this.interactive) return; event.preventDefault(); const delta = event.deltaY || event.deltaX; this.scroll.target += (delta > 0 ? this.scrollSpeed : -this.scrollSpeed) * .2; this.queueSnap(); };
  onPointerDown = (event: PointerEvent) => { if (!this.interactive) return; this.isDown = true; this.scroll.position = this.scroll.current; this.start = event.clientX; this.container.setPointerCapture?.(event.pointerId); };
  onPointerMove = (event: PointerEvent) => { if (!this.interactive || !this.isDown) return; this.scroll.target = this.scroll.position + (this.start - event.clientX) * (this.scrollSpeed * .025); };
  onPointerUp = () => { if (!this.interactive || !this.isDown) return; this.isDown = false; this.snap(); };
  onKeyDown = (event: KeyboardEvent) => { if (!this.interactive || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return; event.preventDefault(); this.scroll.target += (event.key === 'ArrowRight' ? 1 : -1) * this.scrollSpeed * 5; this.queueSnap(); };
  onVisibility = () => { this.visible = !document.hidden; if (this.visible && !this.raf) this.update(); else if (!this.visible && this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; } };
  addEvents() { this.container.addEventListener('wheel', this.onWheel, { passive: false }); this.container.addEventListener('pointerdown', this.onPointerDown); this.container.addEventListener('pointermove', this.onPointerMove); this.container.addEventListener('pointerup', this.onPointerUp); this.container.addEventListener('pointercancel', this.onPointerUp); this.container.addEventListener('keydown', this.onKeyDown); document.addEventListener('visibilitychange', this.onVisibility); }
  renderFrame = () => { const direction = this.scroll.current > this.scroll.last ? 'right' : 'left'; this.medias.forEach(media => media.update(this.scroll, direction, this.interactive)); this.renderer.render({ scene: this.scene, camera: this.camera }); this.scroll.last = this.scroll.current; };
  update = () => { if (!this.visible) { this.raf = 0; return; } this.scroll.current = lerp(this.scroll.current, this.scroll.target, this.scroll.ease); this.renderFrame(); this.raf = requestAnimationFrame(this.update); };
  destroy() { this.destroyed = true; cancelAnimationFrame(this.raf); clearTimeout(this.snapTimer); this.resizeObserver.disconnect(); this.container.removeEventListener('wheel', this.onWheel); this.container.removeEventListener('pointerdown', this.onPointerDown); this.container.removeEventListener('pointermove', this.onPointerMove); this.container.removeEventListener('pointerup', this.onPointerUp); this.container.removeEventListener('pointercancel', this.onPointerUp); this.container.removeEventListener('keydown', this.onKeyDown); document.removeEventListener('visibilitychange', this.onVisibility); const canvas = this.gl.canvas as HTMLCanvasElement; canvas.remove(); this.gl.getExtension('WEBGL_lose_context')?.loseContext(); }
}

export default function CircularGallery({ items, bend = 3, textColor = '#ffffff', borderRadius = .05, scrollSpeed = 2, scrollEase = .05, itemScale = 1, dpr = 2, interactive = true, onItemSelect }: CircularGalleryProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!containerRef.current || !items.length) return; const app = new GalleryApp(containerRef.current, items, bend, textColor, borderRadius, scrollSpeed, scrollEase, itemScale, dpr, interactive); return () => app.destroy(); }, [items, bend, textColor, borderRadius, scrollSpeed, scrollEase, itemScale, dpr, interactive]);
  return (
    <div ref={containerRef} className={`circular-gallery${interactive ? '' : ' is-static'}`} tabIndex={interactive ? 0 : -1} role="region" aria-label={interactive ? '循环图片画廊，可使用滚轮、拖拽或方向键浏览' : '静态循环图片画廊'}>
      {onItemSelect && (
        <div className="circular-gallery__actions">
          {items.map((item, index) => {
            const offset = index - (items.length - 1) / 2;
            return (
              <button
                key={`${item.text}-${index}`}
                type="button"
                aria-label={item.text}
                title={item.text}
                style={{ left: `calc(50% + ${offset * 4.25}%)`, top: `${50 + Math.abs(offset) * 1.15}%`, transform: `translate(-50%, -50%) rotate(${-offset * 2.2}deg)` }}
                onClick={() => onItemSelect(item, index)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
