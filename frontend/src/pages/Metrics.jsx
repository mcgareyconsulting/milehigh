/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin system-usage dashboard — AI spend/tokens, content volume, human activity, and health,
 *   with a day/week/month selector. Renders from the /brain/metrics JSON contract (same data agents read).
 * exports:
 *   Metrics: Page component (admin-gated).
 * imports_from: [react, recharts, ../services/metricsApi, ../utils/auth, ../context/ThemeContext, ../components/shared/Stat]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Chart hues follow the validated categorical palette (slots 1-4) in fixed order; theme via useTheme().isDark.
 */
import { useState, useEffect, useCallback } from 'react';
import {
    ResponsiveContainer, LineChart, Line, BarChart, Bar,
    XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from 'recharts';
import {
    getSummary, getAi, getContent, getActivity, getSystem, getDigest,
} from '../services/metricsApi';
import { checkAuth } from '../utils/auth';
import { useTheme } from '../context/ThemeContext';
import Stat from '../components/shared/Stat';

const PERIODS = [
    { key: 'day', label: 'Day' },
    { key: 'week', label: 'Week' },
    { key: 'month', label: 'Month' },
];

// Validated categorical palette (slots 1-4), fixed order. Feature identity is
// stable across renders so a filter never repaints the survivors.
const FEATURE_HUES = {
    light: ['#2a78d6', '#1baf7a', '#eda100', '#008300', '#4a3aa7'],
    dark: ['#3987e5', '#199e70', '#c98500', '#008300', '#9085e9'],
};
const CONTENT_HUES = FEATURE_HUES; // same fixed-order categorical ramp

const usd = (n) => `$${(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const num = (n) => (n || 0).toLocaleString();
const shortDay = (iso) => (iso || '').slice(5); // MM-DD

function SectionTitle({ children, note }) {
    return (
        <div className="flex items-baseline gap-2 mt-6 mb-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">{children}</h2>
            {note && <span className="text-[11px] text-gray-400 dark:text-slate-500">{note}</span>}
        </div>
    );
}

function ChartCard({ title, children, height = 220 }) {
    return (
        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3">
            <div className="text-xs font-medium text-gray-600 dark:text-slate-300 mb-2">{title}</div>
            <div style={{ width: '100%', height }}>
                <ResponsiveContainer>{children}</ResponsiveContainer>
            </div>
        </div>
    );
}

function Leaderboard({ title, rows, valueKey, format = num }) {
    return (
        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3">
            <div className="text-xs font-medium text-gray-600 dark:text-slate-300 mb-2">{title}</div>
            {rows.length === 0 ? (
                <div className="text-xs text-gray-400 dark:text-slate-500 py-2">No activity in this window.</div>
            ) : (
                <table className="w-full text-sm">
                    <tbody>
                        {rows.slice(0, 8).map((r, i) => (
                            <tr key={r.user_id ?? r.feature ?? r.model ?? r.action ?? i} className="border-t border-gray-100 dark:border-slate-700/60 first:border-0">
                                <td className="py-1 text-gray-700 dark:text-slate-200 truncate">
                                    {r.username || r.feature || r.model || r.action || `User ${r.user_id ?? '—'}`}
                                </td>
                                <td className="py-1 text-right font-semibold tabular-nums text-gray-900 dark:text-slate-100">
                                    {format(r[valueKey])}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function Metrics() {
    const { isDark } = useTheme();
    const [authorized, setAuthorized] = useState(null);
    const [period, setPeriod] = useState('week');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [data, setData] = useState(null); // { summary, ai, content, activity, system, digest }

    const hues = isDark ? FEATURE_HUES.dark : FEATURE_HUES.light;
    const contentHues = isDark ? CONTENT_HUES.dark : CONTENT_HUES.light;
    const gridColor = isDark ? '#2c2c2a' : '#e1e0d9';
    const axisColor = '#898781';
    const lineColor = isDark ? '#3987e5' : '#2a78d6';

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(!!(user && user.is_admin)));
    }, []);

    const load = useCallback(async (p) => {
        setLoading(true);
        setError(null);
        try {
            const [summary, ai, content, activity, system, digest] = await Promise.all([
                getSummary(p), getAi(p), getContent(p), getActivity(p), getSystem(p), getDigest(p),
            ]);
            setData({ summary, ai, content, activity, system, digest });
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load metrics');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (authorized) load(period);
    }, [authorized, period, load]);

    if (authorized === null) {
        return <div className="p-6 text-gray-500 dark:text-slate-400">Loading…</div>;
    }
    if (!authorized) {
        return <div className="p-6 text-gray-600 dark:text-slate-300">Metrics are available to admins only.</div>;
    }

    const tooltipStyle = {
        contentStyle: {
            background: isDark ? '#1a1a19' : '#ffffff',
            border: `1px solid ${gridColor}`,
            borderRadius: 8,
            fontSize: 12,
            color: isDark ? '#fff' : '#0b0b0b',
        },
        labelStyle: { color: axisColor },
    };
    const axisProps = { stroke: axisColor, tick: { fill: axisColor, fontSize: 11 } };

    const s = data?.summary;
    const ai = data?.ai;
    const content = data?.content;
    const activity = data?.activity;
    const system = data?.system;

    // Content counts → bar rows (fixed order).
    const contentOrder = [
        ['release_photos', 'Release photos'], ['board_photos', 'Board photos'],
        ['drawing_versions', 'Drawings'], ['board_comments', 'Board comments'],
        ['drawing_comments', 'Drawing comments'], ['bb_reviews', 'BB reviews'],
        ['review_feedback', 'Review feedback'], ['mentions', 'Mentions'],
    ];
    const contentBars = content
        ? contentOrder.map(([k, label]) => ({ key: k, label, count: content.totals?.[k] || 0 }))
        : [];

    return (
        <div className="w-full max-w-[1400px] mx-auto p-4">
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">System Metrics</h1>
                <div className="inline-flex rounded-lg border border-gray-200 dark:border-slate-700 overflow-hidden">
                    {PERIODS.map((p) => (
                        <button
                            key={p.key}
                            type="button"
                            onClick={() => setPeriod(p.key)}
                            className={`px-3 py-1.5 text-sm font-medium transition-colors ${period === p.key
                                ? 'bg-accent-500 text-white'
                                : 'bg-white dark:bg-slate-800 text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700'}`}
                        >
                            {p.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Digest line — the same text an agent would ingest */}
            {data?.digest?.text && (
                <div className="mt-3 rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 px-3 py-2 text-sm text-gray-600 dark:text-slate-300">
                    {data.digest.text}
                </div>
            )}

            {error && <div className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</div>}
            {loading && <div className="mt-3 text-xs text-gray-400 dark:text-slate-500">Refreshing…</div>}

            {s && (
                <>
                    {/* Summary tiles */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 mt-4">
                        <Stat label="AI calls" value={num(s.ai.calls)} />
                        <Stat label="AI cost" value={usd(s.ai.cost_usd)} tone="orange" />
                        <Stat label="Tokens in / out" value={`${num(s.ai.input_tokens)} / ${num(s.ai.output_tokens)}`} />
                        <Stat label="Photos" value={num(s.content.photos)} />
                        <Stat label="Drawings" value={num(s.content.drawings)} />
                        <Stat label="Comments" value={num(s.content.comments)} />
                        <Stat label="BB reviews" value={num(s.content.reviews)} />
                        <Stat label="Mentions" value={num(s.content.mentions)} />
                        <Stat label="Human actions" value={num(s.activity.human_actions)} />
                        <Stat label="Sync ops" value={num(s.system.sync_ops)} />
                        <Stat label="Webhooks" value={num(s.system.webhooks)} />
                        <Stat label="Errors" value={num(s.system.errors)} tone={s.system.errors ? 'red' : 'green'} />
                    </div>

                    {/* AI usage */}
                    <SectionTitle note="unified ai_usage ledger — all LLM calls metered">AI Usage</SectionTitle>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <ChartCard title="Cost per day (USD)">
                            <LineChart data={ai?.by_day || []} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                                <CartesianGrid stroke={gridColor} vertical={false} />
                                <XAxis dataKey="date" tickFormatter={shortDay} {...axisProps} />
                                <YAxis {...axisProps} width={48} tickFormatter={(v) => `$${v}`} />
                                <Tooltip {...tooltipStyle} formatter={(v) => usd(v)} labelFormatter={shortDay} />
                                <Line type="monotone" dataKey="cost_usd" name="Cost" stroke={lineColor} strokeWidth={2} dot={false} />
                            </LineChart>
                        </ChartCard>
                        <ChartCard title="Cost by feature (USD)">
                            <BarChart data={ai?.by_feature || []} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                                <CartesianGrid stroke={gridColor} vertical={false} />
                                <XAxis dataKey="feature" {...axisProps} />
                                <YAxis {...axisProps} width={48} tickFormatter={(v) => `$${v}`} />
                                <Tooltip {...tooltipStyle} formatter={(v) => usd(v)} cursor={{ fill: 'transparent' }} />
                                <Bar dataKey="cost_usd" name="Cost" radius={[4, 4, 0, 0]}>
                                    {(ai?.by_feature || []).map((row, i) => (
                                        <Cell key={row.feature} fill={hues[i % hues.length]} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ChartCard>
                        <Leaderboard title="Cost by user" rows={ai?.by_user || []} valueKey="cost_usd" format={usd} />
                        <Leaderboard title="Cost by model" rows={ai?.by_model || []} valueKey="cost_usd" format={usd} />
                    </div>

                    {/* Content */}
                    <SectionTitle>Content</SectionTitle>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <ChartCard title="Artifacts created by type">
                            <BarChart data={contentBars} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                                <CartesianGrid stroke={gridColor} horizontal={false} />
                                <XAxis type="number" {...axisProps} allowDecimals={false} />
                                <YAxis type="category" dataKey="label" {...axisProps} width={120} />
                                <Tooltip {...tooltipStyle} cursor={{ fill: 'transparent' }} />
                                <Bar dataKey="count" name="Count" radius={[0, 4, 4, 0]}>
                                    {contentBars.map((row, i) => (
                                        <Cell key={row.key} fill={contentHues[i % contentHues.length]} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ChartCard>
                        <Leaderboard
                            title="Top photo uploaders"
                            rows={content?.by_type?.release_photos?.by_user || []}
                            valueKey="count"
                        />
                    </div>

                    {/* Activity */}
                    <SectionTitle note="human actions only — system echoes excluded">Activity</SectionTitle>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        <ChartCard title="Human actions per day">
                            <LineChart data={activity?.by_day || []} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                                <CartesianGrid stroke={gridColor} vertical={false} />
                                <XAxis dataKey="date" tickFormatter={shortDay} {...axisProps} />
                                <YAxis {...axisProps} width={36} allowDecimals={false} />
                                <Tooltip {...tooltipStyle} labelFormatter={shortDay} />
                                <Line type="monotone" dataKey="count" name="Actions" stroke={lineColor} strokeWidth={2} dot={false} />
                            </LineChart>
                        </ChartCard>
                        <Leaderboard title="Actions by type" rows={activity?.by_action || []} valueKey="count" />
                        <Leaderboard title="Actions by user" rows={activity?.by_user || []} valueKey="count" />
                    </div>

                    {/* System health */}
                    <SectionTitle>System Health</SectionTitle>
                    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
                        <Stat label="Errors" value={num(system?.errors)} tone={system?.errors ? 'red' : 'green'} />
                        <Stat label="Webhooks" value={num(system?.webhooks_received)} />
                        <Stat
                            label="Avg sync (s)"
                            value={system?.sync_operations?.avg_duration_seconds ?? '—'}
                        />
                        {Object.entries(system?.sync_operations?.by_status || {}).map(([st, n]) => (
                            <Stat key={st} label={`Sync: ${st}`} value={num(n)} tone={st === 'failed' ? 'red' : 'slate'} />
                        ))}
                        {Object.entries(system?.logs_by_level || {}).map(([lvl, n]) => (
                            <Stat key={lvl} label={`Log: ${lvl}`} value={num(n)} tone={lvl === 'ERROR' ? 'red' : lvl === 'WARNING' ? 'amber' : 'slate'} />
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}

export default Metrics;
