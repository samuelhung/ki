import KiNavigationShell from './KiNavigationShell';

export default function DualNavigationDemo() {
  return (
    <KiNavigationShell>
      <section className="cinematic-hero dual-nav-demo__hero" aria-label="今日知几">
        <h1><span className="brand-title">知几</span><span className="line3">其神乎 见微知著</span></h1>
        <p>知几其神乎。真正的洞察，不在声势浩大处，而在一线微光。见微知著，从细小征兆预见趋势，于万象未形时辨其轮廓。世事常起微末，端倪易被忽略，须心神澄明，方能在众声鼎沸前辨认方向。知几者，知其始亦知其势；观微者，于未显时读懂万象将成。</p>
      </section>
    </KiNavigationShell>
  );
}
