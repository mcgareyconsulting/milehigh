/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Job Log — D6 design preview. Renders REAL job-log data in the new D6 spreadsheet design
 *   (dense table, row numbers, real banana code). Each column header is a fully-clickable
 *   filter/sort dropdown (reuses the production ColumnHeaderFilter). Read-only preview at /job-log-v2;
 *   the production /job-log page is untouched.
 * exports: default JobLogV2
 * imports_from: [react, ../hooks/useJobsDataFetching, ../hooks/useJobsFilters, ../components/v2/D6Shell,
 *   ../components/ColumnHeaderFilter, ../components/StageIconRow, ../utils/formatters]
 * imported_by: [src/App.jsx]
 */
import React, { useMemo } from 'react';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { StageIconRow } from '../components/StageIconRow';
import { formatDateShort } from '../utils/formatters';
import {
    D6Layout, D6Header, D6PageBar, D6FilterRow,
    D6Table, D6HeaderRow, D6Th, D6Td, D6Row, D6StagePill, useDensity,
} from '../components/v2/D6Shell';

// Columns that get the Excel-style header dropdown (matches the production Job Log).
const FILTERABLE = new Set(['Job #', 'Release #', 'Job', 'Stage', 'Paint color', 'PM', 'BY']);

const num = (v) => {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n.toFixed(2) : (v == null || v === '' ? '—' : String(v));
};
const txt = (v) => (v == null || v === '' ? '—' : String(v));

export default function JobLogV2() {
    const den = useDensity();
    const { jobs, loading, error, lastUpdated } = useJobsDataFetching();
    const {
        search, setSearch, displayJobs, totalFabHrs, totalInstallHrs, resetFilters,
        columnFilters, columnSort, setColumnFilter, setColumnSort, matchesFilters, matchesSearch,
    } = useJobsFilters(jobs);

    // Per-column reachable values (Excel-style narrowing), mirroring the production Job Log.
    const valuesByColumn = useMemo(() => {
        const out = {};
        FILTERABLE.forEach((col) => {
            const set = new Set();
            let hasBlanks = false;
            for (const job of jobs) {
                if (!matchesFilters(job) || !matchesSearch(job, search)) continue;
                let ok = true;
                for (const k in columnFilters) {
                    if (k === col) continue;
                    const allowed = columnFilters[k];
                    if (!allowed || allowed.length === 0) continue;
                    const v = job[k];
                    const blank = v == null || String(v).trim() === '';
                    if (blank ? !allowed.includes('(Blanks)') : !allowed.includes(String(v).trim())) { ok = false; break; }
                }
                if (!ok) continue;
                const v = job[col];
                if (v == null || String(v).trim() === '') hasBlanks = true;
                else set.add(String(v).trim());
            }
            out[col] = {
                values: [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })),
                hasBlanks,
            };
        });
        return out;
    }, [jobs, columnFilters, matchesFilters, matchesSearch, search]);

    // Build the props a ColumnHeaderFilter needs for a given real column key.
    const filterProps = (column) => {
        const info = valuesByColumn[column];
        const selected = columnFilters[column] ?? [];
        return {
            column,
            values: info?.values ?? [],
            hasBlanks: info?.hasBlanks ?? false,
            selected: new Set(selected),
            onChange: (next) => setColumnFilter(column, [...next]),
            sort: columnSort,
            onSort: (dir) => setColumnSort(column, dir),
            isActive: selected.length > 0,
        };
    };

    // A header cell: clickable filter dropdown when the column is filterable, else a plain label.
    const Head = ({ label, column, w, hi, first, align = 'left', fixed }) => {
        if (column && FILTERABLE.has(column)) {
            const justify = align === 'center' ? 'justify-center' : align === 'right' ? 'justify-end' : 'justify-start';
            return (
                <D6Th w={w} hi={hi} first={first} align={align} interactive>
                    <ColumnHeaderFilter {...filterProps(column)} triggerClassName={`w-full h-full ${justify} px-2`}>
                        {label}
                    </ColumnHeaderFilter>
                </D6Th>
            );
        }
        return <D6Th w={w} hi={hi} first={first} align={align} fixed={fixed}>{label}</D6Th>;
    };

    const updated = lastUpdated
        ? new Date(lastUpdated).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        : null;
    const bananaW = Math.max(150, den.banana * 7 + 24);

    return (
        <D6Layout>
            <D6Header active="job" />
            <D6PageBar primary="New release" viewMode="table" />
            <D6FilterRow
                search={search}
                onSearch={setSearch}
                searchPlaceholder="Job #, release, name, description…"
                onReset={resetFilters}
                meta={[{ k: 'Fab hrs', v: num(totalFabHrs) }, { k: 'Install hrs', v: num(totalInstallHrs) }]}
                total={`${displayJobs.length} records`}
                updated={updated}
            />

            {loading ? (
                <Centered>Loading job log…</Centered>
            ) : error ? (
                <Centered tone="error">{String(error)}</Centered>
            ) : (
                <D6Table>
                    <D6HeaderRow>
                        <Head label="Job" column="Job #" w={42} first />
                        <Head label="Rel" column="Release #" w={48} />
                        <Head label="Job name" column="Job" w={148} />
                        <Head label="Description" w={120} />
                        <Head label="Fab" w={46} align="right" />
                        <Head label="Inst" w={46} align="right" />
                        <Head label="Paint" column="Paint color" w={92} />
                        <Head label="PM" column="PM" w={36} align="center" />
                        <Head label="By" column="BY" w={40} />
                        <Head label="Released" w={74} />
                        <Head label="Banana code" w={bananaW} align="center" fixed />
                        <Head label="Stage" column="Stage" w={90} />
                        <Head label="Start inst." w={78} hi />
                        <Head label="Comp ETA" w={74} />
                        <Head label="Install Prog" w={70} align="center" />
                        <Head label="Invoiced" w={64} align="center" />
                        <Head label="Notes" w={120} />
                    </D6HeaderRow>

                    {displayJobs.map((r, i) => {
                        const isAsap = r['start_install_asap'] === true;
                        const isHard = !isAsap && r['start_install_formulaTF'] === false && r['Start install'];
                        return (
                            <D6Row key={r.id ?? i} index={i} hi={isAsap}>
                                <D6Td w={42} monoCell>{txt(r['Job #'])}</D6Td>
                                <D6Td w={48} monoCell className="text-[#1e3a8a] dark:text-[#6694ff]">{txt(r['Release #'])}</D6Td>
                                <D6Td w={148} title={r['Job']}>{txt(r['Job'])}</D6Td>
                                <D6Td w={120} title={r['Description']}>{txt(r['Description'])}</D6Td>
                                <D6Td w={46} align="right" monoCell>{num(r['Fab Hrs'])}</D6Td>
                                <D6Td w={46} align="right" monoCell>{num(r['Install HRS'])}</D6Td>
                                <D6Td w={92} title={r['Paint color']}>{txt(r['Paint color'])}</D6Td>
                                <D6Td w={36} align="center">{txt(r['PM'])}</D6Td>
                                <D6Td w={40}>{txt(r['BY'])}</D6Td>
                                <D6Td w={74} monoCell>{formatDateShort(r['Released']) || '—'}</D6Td>
                                <D6Td w={bananaW} align="center" fixed>
                                    <StageIconRow stage={r['Stage']} iconSize={den.banana} />
                                </D6Td>
                                <D6Td w={90}><D6StagePill>{txt(r['Stage'])}</D6StagePill></D6Td>
                                <D6Td w={78} monoCell>
                                    {isAsap ? (
                                        <span className="px-1.5 py-0.5 rounded bg-[#dc2626] text-white font-semibold text-[11px]">ASAP</span>
                                    ) : isHard ? (
                                        <span className="px-1.5 py-0.5 rounded bg-[#ffd270] text-[#3a2400] dark:bg-[#d97706] dark:text-white font-semibold">{formatDateShort(r['Start install'])}</span>
                                    ) : (formatDateShort(r['Start install']) || '—')}
                                </D6Td>
                                <D6Td w={74} monoCell>{formatDateShort(r['Comp. ETA']) || '—'}</D6Td>
                                <D6Td w={70} align="center">{txt(r['Job Comp'])}</D6Td>
                                <D6Td w={64} align="center">{txt(r['Invoiced'])}</D6Td>
                                <D6Td w={120} className="text-[#6a665c] dark:text-[#9d9588]" title={r['Notes']}>{txt(r['Notes'])}</D6Td>
                            </D6Row>
                        );
                    })}
                    {displayJobs.length === 0 && <Centered>No records match the current filters.</Centered>}
                </D6Table>
            )}
        </D6Layout>
    );
}

function Centered({ children, tone }) {
    return (
        <div className={`flex-1 grid place-items-center text-sm font-medium ${tone === 'error' ? 'text-red-600' : 'text-[#6a665c] dark:text-[#9d9588]'}`}>
            {children}
        </div>
    );
}
