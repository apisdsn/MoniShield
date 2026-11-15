"""Analysis Settings page (stage 62): validate and save the settings of one source to analysis.toml (ctx.analysisfile) and use
them at once (analysis.use), so the next page read and the next ingest follow them without a restart.
Reading what Auto picks and counting the rules over a folder is read-side work (infrastructure/queries/analysis.py), called by the router."""
from monishield.application import sources
from monishield.domain import analysis
from monishield.domain.errors import Fail


def _sentence(text): return text[:1].upper() + text[1:] + ('' if text.endswith('.') else '.')


def source_name(name):
    if not sources.valid(name): raise Fail('invalid_parameter', 'source must be s3, kafka or collector.', 400)
    return name


def settings_of(source, body):
    """A settings table as the page sends it -> Settings. A 400 names what is wrong."""
    try: return analysis.settings_from(body if isinstance(body, dict) else {}, source)
    except analysis.AnalysisError as e: raise Fail('invalid_analysis', _sentence(str(e)), 400) from None


def metrics_of(source, items):
    """Rules as the page sends them (a list of dicts) -> (Metric, …), to test them without saving."""
    st = settings_of(source, dict(business=items if isinstance(items, list) else []))
    return st.business


def save(ctx, source, body, admin, ip):
    """Replace the settings of one source, write analysis.toml, use the result at once."""
    parsed = settings_of(source_name(source), body)
    merged = {**analysis.all_current(), source: parsed}
    ctx.analysisfile.write(analysis.dumps(merged))
    analysis.use(merged)
    ctx.auth.audit('analysis.save', admin, f'source={source} {len(parsed.business)} business rules by {admin["username"]}', ip)
    return parsed
