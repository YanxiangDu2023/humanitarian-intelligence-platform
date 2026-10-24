import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const AI_GENERATION_ENABLED = import.meta.env.VITE_ENABLE_AI_GENERATION !== "false";

async function fetchJson(path, signal, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { ...options, signal });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || `API returned ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function formatValue(value, unit) {
  if (value === null || value === undefined) return "—";
  if (unit === "people") {
    return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  }
  return new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(value);
}

const sourceLabel = (source) => source === "unicef_education_fls" ? "UNICEF" : "World Bank";
const freshnessLabel = (status) => ({
  current: "Current",
  aging: "Aging",
  stale: "Stale",
  survey_snapshot: "Survey snapshot",
}[status] || status);

function LoadingState() {
  return <div className="state-card"><span className="spinner" /><div>
    <strong>Loading country intelligence</strong><span>Reading the latest values from PostgreSQL.</span>
  </div></div>;
}

function ErrorState({ message, retry }) {
  return <div className="state-card error-state"><span className="state-symbol">!</span><div>
    <strong>We could not reach the data API</strong><span>{message}. Make sure `humanitarian-api` is running.</span>
  </div><button type="button" onClick={retry}>Try again</button></div>;
}

function SummaryCards({ country, indicator, observation, rank, total, coverage, newestYear, sourceCount }) {
  return <section className="summary-grid" aria-label="Selected country summary">
    <article className="summary-card accent-card"><div className="summary-icon">01</div>
      <span>{indicator?.indicator_name}</span><strong>
        {formatValue(observation?.observation_value, observation?.unit)}
        {observation?.unit !== "people" && <small>{observation?.unit}</small>}
      </strong><footer>{country?.country_name} · {observation?.observation_year}</footer></article>
    <article className="summary-card"><div className="summary-icon">#</div>
      <span>Position by reported value</span><strong>#{rank || "—"}<small> / {total}</small></strong>
      <footer>Neutral ranking, not a performance score</footer></article>
    <article className="summary-card"><div className="summary-icon">✓</div>
      <span>Indicator coverage</span><strong>{coverage.loaded}<small> / {coverage.expected}</small></strong>
      <footer>All expected indicators available</footer></article>
    <article className="summary-card"><div className="summary-icon">YR</div>
      <span>Newest observation</span><strong>{newestYear || "—"}</strong>
      <footer>Across {sourceCount} verified public sources</footer></article>
  </section>;
}

function ComparisonChart({ data, countryCode, indicator, loading, error }) {
  const maxValue = Math.max(...data.map((item) => item.observation_value), 1);
  return <article className="panel comparison-panel">
    <header className="panel-header"><div><span className="section-kicker">Cross-country comparison</span>
      <h2>{indicator?.indicator_name}</h2></div><span className="unit-pill">Unit: {indicator?.unit}</span></header>
    {loading ? <div className="chart-status"><span className="spinner" /> Updating comparison…</div>
      : error ? <div className="chart-status error-state">Comparison unavailable: {error}</div>
        : <div className="chart-wrap" role="img" aria-label={`Country comparison for ${indicator?.indicator_name}`}>
      <div className="bar-chart-scale"><span>0</span><span>Reported value</span>
        <span>{formatValue(maxValue, indicator?.unit)}</span></div>
      {data.map((item) => <div
        className={`bar-row ${item.country_iso3 === countryCode ? "selected" : ""}`}
        key={item.country_iso3}
        title={`${item.country_name}: ${formatValue(item.observation_value, item.unit)} ${item.unit} · ${item.observation_year}`}
      >
        <span className="bar-country">{item.country_iso3}</span>
        <span className="bar-track"><span className="bar-fill" style={{ width: `${Math.max(item.observation_value / maxValue * 100, 1.5)}%` }} /></span>
        <span className="bar-value">{formatValue(item.observation_value, item.unit)}</span>
        <span className="bar-year">{item.observation_year}</span>
      </div>)}
    </div>}
    <p className="panel-note"><span className="info-dot">i</span> Values use each country’s latest available
      observation; years can differ. Hover over a bar for the country name and source year.</p>
  </article>;
}

function CountryProfile({ country, countryCode, rows, indicatorCode, selectIndicator }) {
  return <article className="panel profile-panel">
    <header className="panel-header"><div><span className="section-kicker">Country profile</span>
      <h2>{country?.country_name}</h2></div><span className="country-code">{countryCode}</span></header>
    <div className="indicator-list">{rows.map((item) => <button
      type="button" key={item.indicator_code} onClick={() => selectIndicator(item.indicator_code)}
      className={`indicator-row ${item.indicator_code === indicatorCode ? "active" : ""}`}
    >
      <span className="indicator-copy"><strong>{item.indicator_name}</strong>
        <small>{sourceLabel(item.source_name)} · {item.observation_year}</small></span>
      <span className="indicator-value"><strong>{formatValue(item.observation_value, item.unit)}</strong>
        <small>{item.unit}</small></span>
      <span className={`freshness ${item.freshness_status}`}>{freshnessLabel(item.freshness_status)}</span>
    </button>)}</div>
  </article>;
}

function FindingCard({ finding, tone }) {
  return <article className={`finding-card ${tone}`}>
    <div className="finding-heading"><span>{tone === "strength" ? "+" : "!"}</span>
      <h3>{finding.title}</h3></div>
    <p>{finding.analysis}</p>
    <div className="evidence-list">{finding.evidence.map((item) => <div
      className="evidence-item" key={item.indicator_code}
    >
      <span>{item.indicator_name}</span>
      <strong>{formatValue(item.value, item.unit)} {item.unit}</strong>
      <small>{item.year} · {sourceLabel(item.source_name)} · rank {item.value_rank_descending}/{item.cohort_size}</small>
    </div>)}</div>
  </article>;
}

function AIBriefPanel({ country, brief, loading, generating, error, generate, generationEnabled }) {
  const buttonLabel = generating ? "Generating…" : brief ? "Regenerate analysis" : "Generate AI analysis";
  return <section className="panel ai-panel">
    <header className="panel-header ai-header"><div><span className="section-kicker">Grounded AI country brief</span>
      <h2>{country?.country_name || "Country"} evidence synthesis</h2></div>
      {generationEnabled && <button type="button" className="ai-action" disabled={generating || loading} onClick={generate}>
        {generating && <span className="button-spinner" />}{buttonLabel}
      </button>}</header>
    {loading ? <div className="ai-empty"><span className="spinner" /> Loading saved analysis…</div>
      : error ? <div className="ai-message error-state"><strong>AI analysis unavailable</strong><span>{error}</span></div>
        : !brief ? <div className="ai-empty"><div className="ai-orb">AI</div><div>
          <strong>No saved analysis for this country yet.</strong>
          <span>{generationEnabled
            ? "Generate one grounded in the verified indicators below. The result will be saved and reused."
            : "A saved analysis has not been published for this country yet."}</span>
        </div></div>
          : <div className="brief-content">
            <div className="brief-summary"><span>Executive summary</span><p>{brief.executive_summary}</p>
              <small>{brief.cached ? "Saved report" : "New report"} · {brief.model}
                {brief.generated_at && ` · ${new Date(brief.generated_at).toLocaleString()}`}</small></div>
            <div className="brief-columns"><div><h3>Strengths</h3>
              {brief.strengths.length ? brief.strengths.map((finding) => <FindingCard
                key={finding.title} finding={finding} tone="strength" />)
                : <p className="brief-placeholder">No evidence-supported strength was identified.</p>}</div>
              <div><h3>Risks and constraints</h3>
                {brief.risks.length ? brief.risks.map((finding) => <FindingCard
                  key={finding.title} finding={finding} tone="risk" />)
                  : <p className="brief-placeholder">No evidence-supported risk was identified.</p>}</div></div>
            <details className="brief-notes"><summary>Data limitations and methodology</summary>
              <div><ul>{[...new Set(brief.data_limitations)].map((note) => <li key={note}>{note}</li>)}</ul>
                <ul>{brief.methodology_notes.map((note) => <li key={note}>{note}</li>)}</ul></div>
            </details>
          </div>}
  </section>;
}

const TREND_COLORS = ["#168c91", "#ef6c4d", "#526b9a"];
const AVAILABLE_YEARS = Array.from({ length: 8 }, (_, index) => 2018 + index);

function TrendTooltip({ active, payload, label, countries }) {
  if (!active || !payload?.length) return null;
  return <div className="trend-tooltip"><strong>{label}</strong>
    {payload.map((entry) => {
      const country = countries.find((item) => item.country_iso3 === entry.dataKey);
      const metadata = entry.payload[`${entry.dataKey}_metadata`];
      return <div key={entry.dataKey}><span style={{ background: entry.color }} />
        <p><b>{country?.country_name || entry.dataKey}</b>
          <small>{formatValue(entry.value, metadata?.unit)} {metadata?.unit} · {sourceLabel(metadata?.source_name)}</small></p>
      </div>;
    })}
  </div>;
}

function TrendPanel({
  countries,
  indicator,
  selectedCountries,
  toggleCountry,
  startYear,
  setStartYear,
  endYear,
  setEndYear,
  chartData,
  loading,
  error,
}) {
  return <section className="panel trend-panel">
    <header className="panel-header"><div><span className="section-kicker">Historical trends</span>
      <h2>{indicator?.indicator_name}</h2></div><span className="unit-pill">2018–2025 series</span></header>
    <div className="trend-controls">
      <div><span className="control-label">Compare up to 3 countries</span>
        <div className="country-chips">{countries.map((country) => {
          const selected = selectedCountries.includes(country.country_iso3);
          const disabled = !selected && selectedCountries.length >= 3;
          return <button type="button" key={country.country_iso3} disabled={disabled}
            className={selected ? "selected" : ""} onClick={() => toggleCountry(country.country_iso3)}>
            {country.country_iso3}
          </button>;
        })}</div></div>
      <div className="year-controls"><label><span>From</span><select value={startYear}
        onChange={(event) => setStartYear(Math.min(Number(event.target.value), endYear))}>
        {AVAILABLE_YEARS.map((year) => <option key={year}>{year}</option>)}</select></label>
        <label><span>To</span><select value={endYear}
          onChange={(event) => setEndYear(Math.max(Number(event.target.value), startYear))}>
          {AVAILABLE_YEARS.map((year) => <option key={year}>{year}</option>)}</select></label></div>
    </div>
    <div className="trend-chart">
      {loading ? <div className="trend-status"><span className="spinner" /> Loading historical observations…</div>
        : error ? <div className="trend-status error-state">{error}</div>
          : <ResponsiveContainer width="100%" height={380}>
            <LineChart data={chartData} margin={{ top: 22, right: 22, left: 4, bottom: 4 }}>
              <CartesianGrid stroke="#e5eceb" strokeDasharray="4 5" />
              <XAxis dataKey="year" axisLine={false} tickLine={false} tick={{ fill: "#6b7d86", fontSize: 12 }} />
              <YAxis axisLine={false} tickLine={false} width={54}
                tick={{ fill: "#6b7d86", fontSize: 11 }} tickFormatter={(value) => formatValue(value, indicator?.unit)} />
              <Tooltip content={<TrendTooltip countries={countries} />} />
              <Legend formatter={(code) => countries.find((item) => item.country_iso3 === code)?.country_name || code} />
              {selectedCountries.map((code, index) => <Line key={code} type="monotone" dataKey={code}
                stroke={TREND_COLORS[index]} strokeWidth={3} connectNulls={false}
                dot={{ r: 4, fill: "white", strokeWidth: 3 }} activeDot={{ r: 6 }} />)}
            </LineChart>
          </ResponsiveContainer>}
    </div>
    <p className="panel-note"><span className="info-dot">i</span> Missing years remain blank and lines break at gaps.
      UNICEF learning measures are survey snapshots, so a sparse series is expected and is not treated as zero.</p>
  </section>;
}

function App() {
  const [countries, setCountries] = useState([]);
  const [indicators, setIndicators] = useState([]);
  const [countryCode, setCountryCode] = useState("KEN");
  const [indicatorCode, setIndicatorCode] = useState("ED_SE_LPV_PRIM");
  const [countryData, setCountryData] = useState([]);
  const [comparisonData, setComparisonData] = useState([]);
  const [comparisonLoading, setComparisonLoading] = useState(true);
  const [comparisonError, setComparisonError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [trendCountries, setTrendCountries] = useState(["KEN", "JOR", "ZAF"]);
  const [trendStartYear, setTrendStartYear] = useState(2018);
  const [trendEndYear, setTrendEndYear] = useState(2025);
  const [trendRows, setTrendRows] = useState([]);
  const [trendLoading, setTrendLoading] = useState(true);
  const [trendError, setTrendError] = useState("");
  const [brief, setBrief] = useState(null);
  const [briefLoading, setBriefLoading] = useState(true);
  const [briefGenerating, setBriefGenerating] = useState(false);
  const [briefError, setBriefError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      fetchJson("/api/v1/countries", controller.signal),
      fetchJson("/api/v1/indicators", controller.signal),
      fetchJson(`/api/v1/countries/${countryCode}/indicators`, controller.signal),
    ]).then(([countryRows, indicatorRows, profileRows]) => {
      setCountries(countryRows);
      setIndicators(indicatorRows);
      setCountryData(profileRows);
    }).catch((requestError) => {
      if (requestError.name !== "AbortError") setError(requestError.message);
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [countryCode, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setComparisonLoading(true);
    setComparisonError("");
    fetchJson(`/api/v1/comparisons/${indicatorCode}`, controller.signal)
      .then(setComparisonData)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setComparisonError(requestError.message);
      })
      .finally(() => setComparisonLoading(false));
    return () => controller.abort();
  }, [indicatorCode, reload]);

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ start_year: trendStartYear, end_year: trendEndYear });
    trendCountries.forEach((code) => query.append("country", code));
    setTrendLoading(true);
    setTrendError("");
    fetchJson(`/api/v1/trends/${indicatorCode}?${query}`, controller.signal)
      .then(setTrendRows)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setTrendError(requestError.message);
      })
      .finally(() => setTrendLoading(false));
    return () => controller.abort();
  }, [indicatorCode, trendCountries, trendStartYear, trendEndYear, reload]);

  useEffect(() => {
    const controller = new AbortController();
    setBriefLoading(true);
    setBriefError("");
    fetchJson(`/api/v1/ai/country-brief/${countryCode}`, controller.signal)
      .then(setBrief)
      .catch((requestError) => {
        if (requestError.name === "AbortError") return;
        if (requestError.status === 404) setBrief(null);
        else setBriefError(requestError.message);
      })
      .finally(() => setBriefLoading(false));
    return () => controller.abort();
  }, [countryCode]);

  const country = countries.find((item) => item.country_iso3 === countryCode);
  const indicator = indicators.find((item) => item.indicator_code === indicatorCode);
  const observation = countryData.find((item) => item.indicator_code === indicatorCode);
  const ranked = useMemo(
    () => [...comparisonData].sort((a, b) => b.observation_value - a.observation_value),
    [comparisonData],
  );
  const rank = comparisonLoading
    ? 0
    : ranked.findIndex((item) => item.country_iso3 === countryCode) + 1;
  const newestYear = countryData.length ? Math.max(...countryData.map((item) => item.observation_year)) : null;
  const sourceCount = new Set(countryData.map((item) => item.source_name)).size;
  const trendChartData = useMemo(() => {
    const rowsByYear = new Map();
    for (let year = trendStartYear; year <= trendEndYear; year += 1) {
      rowsByYear.set(year, { year });
    }
    trendRows.forEach((row) => {
      const point = rowsByYear.get(row.observation_year);
      if (!point) return;
      point[row.country_iso3] = row.observation_value;
      point[`${row.country_iso3}_metadata`] = row;
    });
    return [...rowsByYear.values()];
  }, [trendRows, trendStartYear, trendEndYear]);

  function toggleTrendCountry(code) {
    setTrendCountries((selected) => {
      if (selected.includes(code)) return selected.length === 1 ? selected : selected.filter((item) => item !== code);
      return selected.length < 3 ? [...selected, code] : selected;
    });
  }

  async function generateBrief() {
    setBriefGenerating(true);
    setBriefError("");
    try {
      const generated = await fetchJson("/api/v1/ai/country-brief", undefined, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_iso3: countryCode }),
      });
      setBrief(generated);
    } catch (requestError) {
      setBriefError(requestError.message);
    } finally {
      setBriefGenerating(false);
    }
  }

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#top"><span className="brand-mark">HI</span>
      <span><strong>Humanitarian Intelligence</strong><small>Evidence for better decisions</small></span></a>
      <div className="topbar-meta"><span className="live-dot" /><span>Public data pipeline live</span>
        <a href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">API docs ↗</a></div></header>
    <main id="top">
      <section className="hero"><div className="eyebrow"><span>◆</span> Traceable public evidence</div>
        <h1>See the context behind<br /><em>every country indicator.</em></h1>
        <p>Compare education access, learning outcomes, connectivity, spending, and population
          across a verified 17-country cohort.</p>
        <div className="hero-summary"><div><strong>17</strong><span>countries</span></div>
          <div><strong>8</strong><span>indicators</span></div><div><strong>2</strong><span>public sources</span></div></div>
      </section>
      <section className="control-panel"><div className="control-heading"><div>
        <span className="section-kicker">Explore the evidence</span><h2>Country intelligence workspace</h2></div>
        <span className="snapshot"><b>DB</b> PostgreSQL · latest loaded values</span></div>
        <div className="filters"><label><span>Focus country</span><select value={countryCode}
          onChange={(event) => setCountryCode(event.target.value)} disabled={!countries.length}>
          {countries.map((item) => <option key={item.country_iso3} value={item.country_iso3}>
            {item.country_name} ({item.country_iso3})</option>)}</select></label>
          <label><span>Comparison indicator</span><select value={indicatorCode}
            onChange={(event) => setIndicatorCode(event.target.value)} disabled={!indicators.length}>
            {indicators.map((item) => <option key={item.indicator_code} value={item.indicator_code}>
              {item.indicator_name}</option>)}</select></label></div>
      </section>
      {error ? <ErrorState message={error} retry={() => setReload((value) => value + 1)} /> : loading ? <LoadingState /> : <>
        <SummaryCards country={country} indicator={indicator} observation={observation} rank={rank}
          total={ranked.length} coverage={{ loaded: countryData.length, expected: indicators.length }}
          newestYear={newestYear} sourceCount={sourceCount} />
        <AIBriefPanel country={country} brief={brief} loading={briefLoading}
          generating={briefGenerating} error={briefError} generate={generateBrief}
          generationEnabled={AI_GENERATION_ENABLED} />
        <section className="dashboard-grid"><ComparisonChart data={ranked} countryCode={countryCode}
          indicator={indicator} loading={comparisonLoading} error={comparisonError} />
          <CountryProfile country={country} countryCode={countryCode} rows={countryData}
            indicatorCode={indicatorCode} selectIndicator={setIndicatorCode} /></section>
        <TrendPanel countries={countries} indicator={indicator} selectedCountries={trendCountries}
          toggleCountry={toggleTrendCountry} startYear={trendStartYear} setStartYear={setTrendStartYear}
          endYear={trendEndYear} setEndYear={setTrendEndYear} chartData={trendChartData}
          loading={trendLoading} error={trendError} />
        <section className="method-card"><div className="method-icon">DB</div><div>
          <span className="section-kicker">Read the numbers responsibly</span>
          <h2>Comparable does not always mean collected in the same year.</h2>
          <p>UNICEF learning indicators are survey snapshots, while World Bank series may be updated annually.
            The dashboard preserves each observation year and source instead of presenting the values as if they were simultaneous.</p></div>
          <a href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">Inspect source fields ↗</a></section>
      </>}
    </main>
    <footer className="site-footer"><span>Humanitarian Intelligence Platform · Portfolio prototype</span>
      <span>Public data from UNICEF and the World Bank</span></footer>
  </div>;
}

export default App;
