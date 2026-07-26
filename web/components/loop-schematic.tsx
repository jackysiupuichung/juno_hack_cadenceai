import * as React from "react"

const d = (delay: string) => ({ "--d": delay }) as React.CSSProperties

/**
 * The caretaker-loop schematic. Draw-in animations are gated on an enclosing
 * `<Reveal>` (`.reveal.is-visible`), so wrap it in one.
 */
export function LoopSchematic() {
  return (
    <div className="loop-schematic overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
      <div className="overflow-x-auto">
        <svg
          className="block h-auto w-full min-w-[1000px] lg:min-w-0"
          viewBox="0 0 1440 736"
          role="img"
          aria-label="The caretaker loop: a consultation grounded in a clinical knowledge base (CKS / NICE) becomes a patient-owned record, a plan, and voice check-ins across the gap between visits. Red flags return early; everything else loops back until the brief opens visit two."
        >
          <defs>
            <marker id="ls-m-line" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="oklch(0.72 0.018 225)" />
            </marker>
            <marker id="ls-m-dim" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="oklch(0.91 0.012 218)" />
            </marker>
            <marker id="ls-m-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="oklch(0.52 0.09 212)" />
            </marker>
            <marker id="ls-m-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="oklch(0.62 0.19 33)" />
            </marker>
            <marker id="ls-m-warn" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" fill="oklch(0.75 0.15 72)" />
            </marker>
          </defs>

          {/* the gap : band + watermark */}
          <rect className="ls-fade" style={d(".1s")} x="500" y="0" width="706" height="736" fill="oklch(0.75 0.15 72 / 0.05)" />
          <text className="ls-gapmark ls-fade" style={d(".25s")} x="853" y="262" textAnchor="middle">
            the gap
          </text>

          {/* phases */}
          <g className="ls-fade" style={d(".05s")}>
            <text className="ls-phase" x="40" y="52">VISIT 1</text>
            <text className="ls-phase" x="1222" y="52">VISIT 2</text>
            <path d="M500 34 V702" stroke="var(--border)" strokeDasharray="2 8" fill="none" />
            <path d="M1206 34 V702" stroke="var(--border)" strokeDasharray="2 8" fill="none" />
          </g>

          {/* dimension line across the gap */}
          <g className="ls-fade" style={d(".3s")}>
            <path d="M510 36 V60" stroke="var(--warning)" fill="none" />
            <path d="M1196 36 V60" stroke="var(--warning)" fill="none" />
            <path d="M756 48 H510" stroke="var(--warning)" fill="none" markerEnd="url(#ls-m-warn)" />
            <path d="M950 48 H1196" stroke="var(--warning)" fill="none" markerEnd="url(#ls-m-warn)" />
            <text className="ls-gap-lab" x="853" y="52" textAnchor="middle">THE GAP · WEEKS</text>
          </g>

          {/* knowledge base rail → inputs */}
          <path className="ls-draw ls-dim" style={d(".3s")} pathLength={1} d="M60 168 V442" />
          <path className="ls-draw ls-dim" style={d(".4s")} pathLength={1} d="M60 298 H82" markerEnd="url(#ls-m-dim)" />
          <path className="ls-draw ls-dim" style={d(".45s")} pathLength={1} d="M60 370 H82" markerEnd="url(#ls-m-dim)" />
          <path className="ls-draw ls-dim" style={d(".5s")} pathLength={1} d="M60 442 H82" markerEnd="url(#ls-m-dim)" />

          {/* inputs → context */}
          <path className="ls-draw" style={d(".55s")} pathLength={1} d="M240 298 L280 330" markerEnd="url(#ls-m-line)" />
          <path className="ls-draw" style={d(".6s")} pathLength={1} d="M240 370 L280 360" markerEnd="url(#ls-m-line)" />
          <path className="ls-draw" style={d(".65s")} pathLength={1} d="M240 442 L280 390" markerEnd="url(#ls-m-line)" />

          {/* context ⇄ supabase */}
          <path className="ls-draw ls-dim" style={d(".8s")} pathLength={1} d="M370 164 V294" strokeDasharray="3 6" markerStart="url(#ls-m-dim)" markerEnd="url(#ls-m-dim)" />

          {/* main chain */}
          <path className="ls-draw" style={d(".9s")} pathLength={1} d="M460 360 H554" markerEnd="url(#ls-m-line)" />
          <path className="ls-draw" style={d("1.05s")} pathLength={1} d="M770 360 H814" markerEnd="url(#ls-m-line)" />
          <path className="ls-draw" style={d("1.15s")} pathLength={1} d="M950 360 H984" markerEnd="url(#ls-m-line)" />

          {/* check-in → triage */}
          <path className="ls-draw" style={d("1.25s")} pathLength={1} d="M1090 402 V446" markerEnd="url(#ls-m-line)" />

          {/* triage: no → monitor */}
          <path className="ls-draw" style={d("1.4s")} pathLength={1} d="M1054 488 H965 V554" markerEnd="url(#ls-m-line)" />
          <text className="ls-tag ls-fade" style={d("1.45s")} x="1042" y="480" textAnchor="end" fill="var(--muted-foreground)">no</text>

          {/* triage: yes → early return */}
          <path className="ls-draw ls-red" style={d("1.55s")} pathLength={1} d="M1126 488 H1322 V614" markerEnd="url(#ls-m-red)" />
          <text className="ls-tag ls-fade" style={d("1.6s")} x="1146" y="480" fill="var(--destructive)">yes</text>

          {/* monitor → context : the loop */}
          <path className="ls-draw ls-teal" style={d("1.7s")} pathLength={1} d="M880 592 H350 V426" markerEnd="url(#ls-m-teal)" />
          <path className="ls-flow" style={d("1.95s")} d="M880 592 H350 V426" />
          <text className="ls-tag ls-fade" style={d("1.95s")} x="615" y="580" textAnchor="middle" fill="var(--primary)">
            interval data writes back
          </text>

          {/* context → the brief (interval end) */}
          <path className="ls-draw ls-teal" style={d("2.1s")} pathLength={1} d="M440 300 C620 150, 950 130, 1216 220" markerEnd="url(#ls-m-teal)" opacity=".65" />
          <text className="ls-tag ls-fade" style={d("2.35s")} x="800" y="158" textAnchor="middle" fill="var(--primary)" opacity=".8">
            at interval end
          </text>

          {/* medical knowledge base. A plain label, not the NICE wordmark:
              this node is our grounding source, not their brand. */}
          <g className="ls-node" style={d(".08s")}>
            <title>Knowledge base (CKS / NICE) grounds every input</title>
            <rect className="ls-box" x="24" y="98" width="150" height="64" rx="14" />
            <text className="ls-lab" x="99" y="126" textAnchor="middle" fontSize="11.5">KNOWLEDGE BASE</text>
            <text className="ls-sub" x="99" y="145" textAnchor="middle">CKS / NICE</text>
          </g>

          {/* inputs */}
          <g className="ls-node" style={d(".14s")}>
            <title>Visit transcript, captured by ElevenLabs Scribe</title>
            <rect className="ls-box" x="90" y="272" width="150" height="52" rx="14" />
            <text className="ls-lab" x="165" y="302" textAnchor="middle">CONSULTATION</text>
            <circle cx="240" cy="272" r="10" fill="var(--card)" stroke="var(--border)" strokeWidth="1.5" />
            <text x="240" y="276.5" textAnchor="middle" fontSize="11" fill="var(--primary)">∞</text>
          </g>
          <g className="ls-node" style={d(".2s")}>
            <title>Condition primer from the knowledge base (CKS / NICE)</title>
            <rect className="ls-box" x="90" y="344" width="150" height="52" rx="14" />
            <text className="ls-lab" x="165" y="374" textAnchor="middle">DISEASE</text>
          </g>
          <g className="ls-node" style={d(".26s")}>
            <title>Medication reference from the knowledge base (CKS / NICE)</title>
            <rect className="ls-box" x="90" y="416" width="150" height="52" rx="14" />
            <text className="ls-lab" x="165" y="446" textAnchor="middle">DRUG</text>
            <circle cx="240" cy="416" r="10" fill="var(--card)" stroke="var(--border)" strokeWidth="1.5" />
            <text x="240" y="420.5" textAnchor="middle" fontSize="11" fill="var(--primary)">∞</text>
          </g>

          {/* context */}
          <g className="ls-node" style={d(".7s")}>
            <title>The longitudinal record</title>
            <rect className="ls-box" x="280" y="300" width="180" height="120" rx="16" stroke="var(--primary)" strokeOpacity=".45" />
            <text className="ls-lab ls-lab-lg" x="370" y="356" textAnchor="middle">CONTEXT</text>
            <text className="ls-sub" x="370" y="380" textAnchor="middle">patient-owned record</text>
          </g>

          {/* supabase */}
          <g className="ls-node" style={d(".75s")}>
            <title>Supabase — Postgres, pgvector, row-level security</title>
            <rect className="ls-box" x="285" y="98" width="170" height="64" rx="14" />
            <svg x="303" y="112" width="134" height="26" viewBox="0 0 581 113" fill="none" style={{ color: "var(--foreground)" }}>
              <path d="M151.397 66.7608C151.996 72.3621 157.091 81.9642 171.877 81.9642C184.764 81.9642 190.959 73.7624 190.959 65.7607C190.959 58.559 186.063 52.6577 176.373 50.6571L169.379 49.1569C166.682 48.6568 164.884 47.1565 164.884 44.7559C164.884 41.9552 167.681 39.8549 171.178 39.8549C176.772 39.8549 178.87 43.5556 179.27 46.4564L190.359 43.9558C189.76 38.6546 185.064 29.7527 171.078 29.7527C160.488 29.7527 152.696 37.0543 152.696 45.8561C152.696 52.7576 156.991 58.4591 166.482 60.5594L172.976 62.0598C176.772 62.8599 178.271 64.6605 178.271 66.8609C178.271 69.4615 176.173 71.762 171.777 71.762C165.983 71.762 163.085 68.1611 162.786 64.2602L151.397 66.7608Z" fill="currentColor" />
              <path d="M233.421 80.4639H246.109C245.909 78.7635 245.609 75.3628 245.609 71.5618V31.2529H232.321V59.8592C232.321 65.5606 228.925 69.5614 223.031 69.5614C216.837 69.5614 214.039 65.1604 214.039 59.6592V31.2529H200.752V62.3599C200.752 73.0622 207.545 81.7642 219.434 81.7642C224.628 81.7642 230.325 79.7638 233.022 75.1627C233.022 77.1631 233.221 79.4636 233.421 80.4639Z" fill="currentColor" />
              <path d="M273.076 99.4682V75.663C275.473 78.9636 280.469 81.6644 287.263 81.6644C301.149 81.6644 310.439 70.6617 310.439 55.7584C310.439 41.1553 302.148 30.1528 287.762 30.1528C280.37 30.1528 274.875 33.4534 272.677 37.2544V31.253H259.79V99.4682H273.076ZM297.352 55.8585C297.352 64.6606 291.958 69.7616 285.164 69.7616C278.372 69.7616 272.877 64.5605 272.877 55.8585C272.877 47.1566 278.372 42.0554 285.164 42.0554C291.958 42.0554 297.352 47.1566 297.352 55.8585Z" fill="currentColor" />
              <path d="M317.964 67.0609C317.964 74.7627 324.357 81.8643 334.848 81.8643C342.139 81.8643 346.835 78.4634 349.332 74.5625C349.332 76.463 349.532 79.1635 349.832 80.4639H362.02C361.72 78.7635 361.422 75.2627 361.422 72.6622V48.4567C361.422 38.5545 355.627 29.7527 340.043 29.7527C326.855 29.7527 319.761 38.2544 318.963 45.9562L330.751 48.4567C331.151 44.1558 334.348 40.455 340.141 40.455C345.737 40.455 348.434 43.3556 348.434 46.8564C348.434 48.5568 347.536 49.9572 344.738 50.3572L332.65 52.1576C324.458 53.3579 317.964 58.2589 317.964 67.0609ZM337.644 71.962C333.349 71.962 331.25 69.1614 331.25 66.2608C331.25 62.4599 333.947 60.5594 337.345 60.0594L348.434 58.359V60.5594C348.434 69.2615 343.239 71.962 337.644 71.962Z" fill="currentColor" />
              <path d="M387.703 80.4641V74.4627C390.299 78.6637 395.494 81.6644 402.288 81.6644C416.276 81.6644 425.467 70.5618 425.467 55.6585C425.467 41.0552 417.174 29.9528 402.788 29.9528C395.494 29.9528 390.1 33.1535 387.902 36.6541V8.04785H374.815V80.4641H387.703ZM412.178 55.7584C412.178 64.7605 406.784 69.7616 399.99 69.7616C393.297 69.7616 387.703 64.6606 387.703 55.7584C387.703 46.7564 393.297 41.8554 399.99 41.8554C406.784 41.8554 412.178 46.7564 412.178 55.7584Z" fill="currentColor" />
              <path d="M432.99 67.0609C432.99 74.7627 439.383 81.8643 449.873 81.8643C457.165 81.8643 461.862 78.4634 464.358 74.5625C464.358 76.463 464.559 79.1635 464.858 80.4639H477.046C476.748 78.7635 476.448 75.2627 476.448 72.6622V48.4567C476.448 38.5545 470.653 29.7527 455.068 29.7527C441.881 29.7527 434.788 38.2544 433.989 45.9562L445.776 48.4567C446.177 44.1558 449.374 40.455 455.167 40.455C460.763 40.455 463.46 43.3556 463.46 46.8564C463.46 48.5568 462.561 49.9572 459.763 50.3572L447.676 52.1576C439.484 53.3579 432.99 58.2589 432.99 67.0609ZM452.671 71.962C448.375 71.962 446.276 69.1614 446.276 66.2608C446.276 62.4599 448.973 60.5594 452.371 60.0594L463.46 58.359V60.5594C463.46 69.2615 458.265 71.962 452.671 71.962Z" fill="currentColor" />
              <path d="M485.645 66.7608C486.243 72.3621 491.339 81.9642 506.124 81.9642C519.012 81.9642 525.205 73.7624 525.205 65.7607C525.205 58.559 520.311 52.6577 510.62 50.6571L503.626 49.1569C500.929 48.6568 499.132 47.1565 499.132 44.7559C499.132 41.9552 501.928 39.8549 505.425 39.8549C511.021 39.8549 513.118 43.5556 513.519 46.4564L524.607 43.9558C524.007 38.6546 519.312 29.7527 505.326 29.7527C494.735 29.7527 486.944 37.0543 486.944 45.8561C486.944 52.7576 491.238 58.4591 500.73 60.5594L507.224 62.0598C511.021 62.8599 512.519 64.6605 512.519 66.8609C512.519 69.4615 510.421 71.762 506.025 71.762C500.23 71.762 497.334 68.1611 497.034 64.2602L485.645 66.7608Z" fill="currentColor" />
              <path d="M545.385 50.2571C545.685 45.7562 549.482 40.5549 556.375 40.5549C563.967 40.5549 567.165 45.3561 567.365 50.2571H545.385ZM568.664 63.0601C567.065 67.4609 563.668 70.5617 557.474 70.5617C550.88 70.5617 545.385 65.8606 545.087 59.3593H580.252C580.252 59.159 580.451 57.1587 580.451 55.2582C580.451 39.4547 571.361 29.7527 556.175 29.7527C543.588 29.7527 531.998 39.9548 531.998 55.6584C531.998 72.262 543.886 81.9642 557.374 81.9642C569.462 81.9642 577.255 74.8626 579.753 66.3607L568.664 63.0601Z" fill="currentColor" />
              <path d="M63.7076 110.284C60.8481 113.885 55.0502 111.912 54.9813 107.314L53.9738 40.0627L99.1935 40.0627C107.384 40.0627 111.952 49.5228 106.859 55.9374L63.7076 110.284Z" fill="url(#ls_sb_g0)" />
              <path d="M63.7076 110.284C60.8481 113.885 55.0502 111.912 54.9813 107.314L53.9738 40.0627L99.1935 40.0627C107.384 40.0627 111.952 49.5228 106.859 55.9374L63.7076 110.284Z" fill="url(#ls_sb_g1)" fillOpacity="0.2" />
              <path d="M45.317 2.07103C48.1765 -1.53037 53.9745 0.442937 54.0434 5.041L54.4849 72.2922H9.83113C1.64038 72.2922 -2.92775 62.8321 2.1655 56.4175L45.317 2.07103Z" fill="#3ECF8E" />
              <defs>
                <linearGradient id="ls_sb_g0" x1="53.9738" y1="54.974" x2="94.1635" y2="71.8295" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#249361" />
                  <stop offset="1" stopColor="#3ECF8E" />
                </linearGradient>
                <linearGradient id="ls_sb_g1" x1="36.1558" y1="30.578" x2="54.4844" y2="65.0806" gradientUnits="userSpaceOnUse">
                  <stop />
                  <stop offset="1" stopOpacity="0" />
                </linearGradient>
              </defs>
            </svg>
          </g>

          {/* caretaker llm */}
          <g className="ls-node" style={d("1s")}>
            <title>Claude reads the record and plans the interval</title>
            <rect className="ls-box" x="560" y="318" width="210" height="84" rx="16" />
            <text className="ls-lab" x="665" y="350" textAnchor="middle">CARETAKER LLM</text>
            <g transform="translate(629,360) scale(0.72)">
              <path fill="#D97757" d="m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z" />
            </g>
            <text className="ls-serif" x="652" y="376" fontSize="16">Claude</text>
          </g>

          {/* plan */}
          <g className="ls-node" style={d("1.1s")}>
            <title>Extracted commitments and check-in cadence</title>
            <rect className="ls-box" x="820" y="326" width="130" height="68" rx="16" />
            <text className="ls-lab" x="885" y="365" textAnchor="middle">PLAN</text>
          </g>

          {/* basic questions */}
          <g className="ls-node" style={d("1.2s")}>
            <title>Voice check-in call — ElevenLabs agent</title>
            <rect className="ls-box" x="990" y="318" width="200" height="84" rx="16" />
            <text className="ls-lab" x="1090" y="350" textAnchor="middle">BASIC QUESTIONS</text>
            <g transform="translate(1049,360) scale(0.5)">
              <path fill="var(--foreground)" d="M4.6035 0v24h4.9317V0zm9.8613 0v24h4.9317V0z" />
            </g>
            <text x="1064" y="371" fontSize="12.5" fontWeight="700" fill="var(--foreground)">ElevenLabs</text>
          </g>

          {/* triage diamond */}
          <g className="ls-node" style={d("1.35s")}>
            <title>Any red-flag answers?</title>
            <path className="ls-shape" d="M1090 450 L1128 488 L1090 526 L1052 488 Z" />
            <text className="ls-tag" x="1090" y="484" textAnchor="middle" fill="var(--destructive)" fontSize="9">RED</text>
            <text className="ls-tag" x="1090" y="496" textAnchor="middle" fill="var(--destructive)" fontSize="9">FLAG?</text>
          </g>

          {/* monitor */}
          <g className="ls-node" style={d("1.55s")}>
            <title>Monitoring across the interval</title>
            <rect className="ls-box" x="880" y="560" width="170" height="64" rx="16" />
            <text className="ls-lab" x="965" y="598" textAnchor="middle">MONITOR</text>
          </g>

          {/* the brief */}
          <g className="ls-node ls-hero" style={d("2.45s")}>
            <title>The next-visit brief — visit two starts warm</title>
            <rect className="ls-box" x="1222" y="170" width="200" height="110" rx="18" />
            <text className="ls-serif" x="1322" y="218" textAnchor="middle" fontSize="21" fill="#ffffff">The Brief</text>
            <text x="1322" y="244" textAnchor="middle" fontSize="10" fill="#ffffff" opacity=".85" letterSpacing=".03em">
              agreed · done · happened · changed
            </text>
          </g>

          {/* early return */}
          <g className="ls-node ls-alarm" style={d("1.8s")}>
            <title>Red flag — return to the clinic early</title>
            <rect className="ls-box" x="1222" y="620" width="200" height="72" rx="16" />
            <text className="ls-lab" x="1322" y="661" textAnchor="middle">EARLY RETURN</text>
          </g>
        </svg>
      </div>

      <style>{`
        .loop-schematic text{fill:var(--foreground);letter-spacing:.02em}
        .loop-schematic .ls-phase{font-size:11px;font-weight:600;letter-spacing:.22em;fill:var(--muted-foreground)}
        .loop-schematic .ls-lab{font-weight:600;letter-spacing:.08em;font-size:12.5px}
        .loop-schematic .ls-lab-lg{font-size:15px}
        .loop-schematic .ls-sub{font-size:10.5px;fill:var(--muted-foreground)}
        .loop-schematic .ls-tag{font-size:10px;font-weight:600;letter-spacing:.06em}
        .loop-schematic .ls-gapmark{font-family:var(--font-display),serif;font-style:italic;font-size:118px;fill:oklch(0.75 0.15 72 / 0.13)}
        .loop-schematic .ls-gap-lab{font-size:12px;font-weight:700;letter-spacing:.26em;fill:var(--warning-foreground)}
        .loop-schematic .ls-serif{font-family:var(--font-display),serif;font-weight:600}

        .loop-schematic .ls-node{opacity:0;transform-box:fill-box;transform-origin:center;transition:filter .3s var(--ease-out)}
        .loop-schematic .ls-node:hover{filter:drop-shadow(0 6px 14px oklch(0.3 0.02 235 / 0.14))}
        .loop-schematic .ls-node rect.ls-box,.loop-schematic .ls-node path.ls-shape{fill:var(--card);stroke:var(--border);stroke-width:1.5}
        .loop-schematic .ls-hero rect.ls-box{fill:var(--primary);stroke:none;filter:drop-shadow(0 10px 22px oklch(0.52 0.09 212 / 0.35))}
        .loop-schematic .ls-alarm rect.ls-box{stroke:var(--destructive)}
        .loop-schematic .ls-alarm .ls-lab{fill:var(--destructive)}

        .loop-schematic .ls-draw{fill:none;stroke:oklch(0.72 0.018 225);stroke-width:1.5;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:1;opacity:0}
        .loop-schematic .ls-dim{stroke:var(--border)}
        .loop-schematic .ls-teal{stroke:var(--primary);stroke-width:2}
        .loop-schematic .ls-red{stroke:var(--destructive);stroke-width:1.8}
        .loop-schematic .ls-flow{fill:none;stroke:var(--primary);stroke-width:2.6;stroke-linecap:round;stroke-dasharray:1 16;opacity:0}
        .loop-schematic .ls-fade{opacity:0}

        .reveal.is-visible .loop-schematic .ls-node{animation:ls-rise .64s var(--ease-out) both;animation-delay:var(--d,0s)}
        .reveal.is-visible .loop-schematic .ls-draw{animation:ls-drawin .7s var(--ease-out) both;animation-delay:var(--d,0s)}
        .reveal.is-visible .loop-schematic .ls-fade{animation:ls-appear .6s var(--ease-out) both;animation-delay:var(--d,0s)}
        .reveal.is-visible .loop-schematic .ls-flow{animation:ls-appear .6s ease both,ls-flowmove 1.9s linear infinite;animation-delay:var(--d,0s),0s}

        @keyframes ls-drawin{to{stroke-dashoffset:0;opacity:1}}
        @keyframes ls-flowmove{to{stroke-dashoffset:-17}}
        @keyframes ls-appear{to{opacity:1}}
        @keyframes ls-rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}

        @media (prefers-reduced-motion:reduce){
          .loop-schematic .ls-node,.loop-schematic .ls-fade{opacity:1;animation:none!important}
          .loop-schematic .ls-draw{opacity:1;stroke-dashoffset:0;animation:none!important}
          .loop-schematic .ls-flow{display:none}
        }
      `}</style>
    </div>
  )
}
