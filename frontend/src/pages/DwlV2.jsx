/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Drafting WL — D6 design preview. Renders REAL submittal data in the new D6 spreadsheet design
 *   (Open/Draft tabs, status dots, dense table). Read-only preview at /dwl-v2; production page untouched.
 * exports: default DwlV2
 * imports_from: [react, ../hooks/useDataFetching, ../hooks/useFilters, ../components/v2/D6Shell, ../utils/formatters]
 * imported_by: [src/App.jsx]
 */
import React, { useState } from 'react';
import { useDataFetching } from '../hooks/useDataFetching';
import { useFilters } from '../hooks/useFilters';
import { formatDateShort } from '../utils/formatters';
import {
    D6Layout, D6Header, D6PageBar, D6ViewTabs, D6FilterRow,
    D6Table, D6HeaderRow, D6Th, D6Td, D6Row, D6StatusDot,
} from '../components/v2/D6Shell';

const VIEWS = [
    { id: 'open', label: 'Open' },
    { id: 'draft', label: 'Draft' },
];

const txt = (v) => (v == null || v === '' ? '—' : String(v));
const date = (v) => formatDateShort(v) || txt(v);

export default function DwlV2() {
    const [tab, setTab] = useState('open');
    const { submittals, loading, error, lastUpdated } = useDataFetching(null, tab);
    const { search, setSearch, displayRows, resetFilters } = useFilters(submittals);

    const updated = lastUpdated
        ? new Date(lastUpdated).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        : null;

    const inReview = displayRows.filter((r) => r['COMP. STATUS'] === 'In review').length;

    return (
        <D6Layout>
            <D6Header active="draft" />
            <D6PageBar
                primary="Add project"
                viewMode="table"
                activeView={{ label: VIEWS.find((v) => v.id === tab)?.label, count: displayRows.length }}
            />
            <D6ViewTabs views={VIEWS} active={tab} onChange={setTab} />
            <D6FilterRow
                search={search}
                onSearch={setSearch}
                searchPlaceholder="Project, title, BIC, sub manager…"
                onReset={resetFilters}
                meta={[{ k: 'In review', v: inReview }]}
                total={`${displayRows.length} records`}
                updated={updated}
            />

            {loading ? (
                <Centered>Loading drafting work load…</Centered>
            ) : error ? (
                <Centered tone="error">{String(error)}</Centered>
            ) : (
                <D6Table>
                    <D6HeaderRow>
                        <D6Th w={72} sort first>Order #</D6Th>
                        <D6Th w={64}>Proj #</D6Th>
                        <D6Th w={208} sort>Name</D6Th>
                        <D6Th w={248}>Title</D6Th>
                        <D6Th w={124}>Procore status</D6Th>
                        <D6Th w={60}>BIC</D6Th>
                        <D6Th w={80} sort>Last BIC</D6Th>
                        <D6Th w={100} sort>Type</D6Th>
                        <D6Th w={116}>Comp status</D6Th>
                        <D6Th w={124}>Sub manager</D6Th>
                        <D6Th w={92} sort hi>Due date</D6Th>
                        <D6Th w={74} sort>Lifespan</D6Th>
                        <D6Th w={200}>Notes</D6Th>
                    </D6HeaderRow>

                    {displayRows.map((r, i) => (
                        <D6Row key={r.id ?? i} index={i}>
                            <D6Td w={72} monoCell className="text-[#1e3a8a] dark:text-[#6694ff]">{txt(r['ORDER #'])}</D6Td>
                            <D6Td w={64} monoCell>{txt(r['PROJ. #'])}</D6Td>
                            <D6Td w={208} title={r['NAME']}>{txt(r['NAME'])}</D6Td>
                            <D6Td w={248} title={r['TITLE']}>{txt(r['TITLE'])}</D6Td>
                            <D6Td w={124}><D6StatusDot label={r['PROCORE STATUS']} /></D6Td>
                            <D6Td w={60}>{txt(r['BIC'])}</D6Td>
                            <D6Td w={80} monoCell className="text-[#6a665c] dark:text-[#9d9588]">{txt(r['LAST BIC'])}</D6Td>
                            <D6Td w={100}>{txt(r['TYPE'])}</D6Td>
                            <D6Td w={116}><D6StatusDot label={r['COMP. STATUS']} /></D6Td>
                            <D6Td w={124}>{txt(r['SUB MANAGER'])}</D6Td>
                            <D6Td w={92} monoCell>{date(r['DUE DATE'])}</D6Td>
                            <D6Td w={74} monoCell className="text-[#6a665c] dark:text-[#9d9588]">{txt(r['LIFESPAN'])}</D6Td>
                            <D6Td w={200} className="text-[#6a665c] dark:text-[#9d9588]" title={r['NOTES']}>{txt(r['NOTES'])}</D6Td>
                        </D6Row>
                    ))}
                    {displayRows.length === 0 && <Centered>No records match the current filters.</Centered>}
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
