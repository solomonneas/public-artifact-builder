from __future__ import annotations

from html import escape

from .models import ArtifactMap


def render_preview_html(artifact_map: ArtifactMap, markdown_outputs: dict[str, str]) -> str:
    stack = "".join(
        f"<li><span>{escape(item.name)}</span><small>{escape(item.category)} - {item.confidence:.2f}</small></li>"
        for item in artifact_map.detected_stack
    ) or "<li><span>Manual stack review needed</span></li>"
    claims = "".join(f"<li>{escape(claim.claim)}</li>" for claim in artifact_map.public_safe_claims)
    components = "".join(
        f"<li><span>{escape(item.name)}</span><small>{escape(item.kind)}</small></li>"
        for item in [*artifact_map.components, *artifact_map.services, *artifact_map.data_stores]
    ) or "<li><span>No components detected</span></li>"
    risks = "".join(
        f"<li><span>{escape(risk.name)}</span><small>{escape(risk.severity)}</small></li>"
        for risk in artifact_map.risks
    ) or "<li><span>No structural risks detected</span></li>"
    markdown_cards = "".join(
        _markdown_card(name, content) for name, content in markdown_outputs.items()
    )
    privacy_class = "ok" if artifact_map.privacy.status == "pass" else "blocked"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(artifact_map.project_name)} artifact preview</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #18212f;
      --muted: #5e6a7b;
      --line: #d9dee7;
      --accent: #176b87;
      --ok: #18794e;
      --blocked: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 32px max(24px, calc((100vw - 1120px) / 2)) 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      gap: 18px;
    }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 32px; line-height: 1.15; }}
    h2 {{ font-size: 18px; }}
    h3 {{ font-size: 15px; }}
    p {{ max-width: 860px; color: var(--muted); }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: #fafdff;
      color: var(--muted);
      font-size: 13px;
    }}
    .pill.ok {{ color: var(--ok); border-color: #b8dec9; }}
    .pill.blocked {{ color: var(--blocked); border-color: #f2b8b5; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      min-width: 0;
    }}
    ul {{ padding-left: 18px; margin: 12px 0 0; }}
    li {{ margin: 6px 0; }}
    li small {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    pre {{
      margin: 12px 0 0;
      padding: 14px;
      overflow: auto;
      background: #101820;
      color: #e9eef5;
      border-radius: 6px;
      font-size: 12px;
      white-space: pre-wrap;
    }}
    .markdown {{
      display: grid;
      gap: 18px;
    }}
    @media (max-width: 760px) {{
      header {{ padding: 24px; }}
      h1 {{ font-size: 26px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(artifact_map.project_name)}</h1>
    <p>{escape(artifact_map.summary)}</p>
    <div class="meta">
      <span class="pill">Audience: {escape(artifact_map.audience)}</span>
      <span class="pill {privacy_class}">Privacy: {escape(artifact_map.privacy.status)}</span>
      <span class="pill">Findings: {len(artifact_map.privacy.findings)}</span>
      <span class="pill">High risk: {artifact_map.privacy.high_risk_count}</span>
    </div>
  </header>
  <main>
    <div class="grid">
      <section>
        <h2>Stack</h2>
        <ul>{stack}</ul>
      </section>
      <section>
        <h2>Public-Safe Claims</h2>
        <ul>{claims}</ul>
      </section>
      <section>
        <h2>Architecture Signals</h2>
        <ul>{components}</ul>
      </section>
      <section>
        <h2>Review Notes</h2>
        <ul>{risks}</ul>
      </section>
    </div>
    <section>
      <h2>Markdown Outputs</h2>
      <div class="markdown">{markdown_cards}</div>
    </section>
  </main>
</body>
</html>
"""


def _markdown_card(name: str, content: str) -> str:
    excerpt = "\n".join(content.splitlines()[:18])
    return f"""<article>
  <h3>{escape(name)}</h3>
  <pre>{escape(excerpt)}</pre>
</article>"""
