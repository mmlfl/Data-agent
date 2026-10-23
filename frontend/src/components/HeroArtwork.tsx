export function HeroArtwork() {
  return (
    <div className="hero-art" aria-hidden="true">
      <div className="hero-art__glow" />
      <img
        src="/images/data-analysis-hero.png"
        width="1536"
        height="1024"
        alt=""
        fetchPriority="high"
        decoding="async"
      />
      <div className="hero-art__question">
        <span>
          今年每个月的订单金额
          <br />
          如何变化？
        </span>
        <i>↗</i>
      </div>
    </div>
  );
}
