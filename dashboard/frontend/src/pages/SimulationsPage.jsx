import React, { useState, useEffect } from 'react'
import { authFetch } from '../utils/authFetch'
import { Badge } from '../components/Badge'
import { MetricCard } from '../components/MetricCard'
import { DataTable } from '../components/DataTable'

var e = React.createElement;

function SimulationsPage() {
  var filterState = useState({ robot: 'all', result: 'all' });
  var filters = filterState[0];
  var setFilters = filterState[1];

  var simsState = useState([]);
  var sims = simsState[0];
  var setSims = simsState[1];

  var robotsState = useState([]);
  var robots = robotsState[0];
  var setRobots = robotsState[1];

  useEffect(function() {
    authFetch('/api/simulations?limit=100')
      .then(function(r) { return r.json(); })
      .then(setSims)
      .catch(function() {});
    authFetch('/api/robots')
      .then(function(r) { return r.json(); })
      .then(setRobots)
      .catch(function() {});
  }, []);

  var filtered = sims.filter(function(s) {
    if (filters.robot !== 'all' && s.robot !== filters.robot) return false;
    if (filters.result !== 'all' && s.result !== filters.result) return false;
    return true;
  });

  var totalSims = sims.length;
  var passCount = sims.filter(function(s) { return s.result === 'pass' || s.safety_pass === 1; }).length;
  var avgScore = totalSims > 0
    ? (sims.reduce(function(a, s) { return a + (s.path_error || 0); }, 0) / totalSims).toFixed(3)
    : '0';
  var totalEpisodes = sims.length;

  var columns = [
    { key: 'id', label: 'ID', mono: true },
    { key: 'robot', label: 'Robot' },
    { key: 'scene', label: 'Scene' },
    { key: 'result', label: 'Result', render: function(row) {
      var passed = row.safety_pass === 1 || row.result === 'pass';
      return e(Badge, { variant: passed ? 'success' : 'danger' }, passed ? 'pass' : 'fail');
    }},
    { key: 'path_error', label: 'Path Error', mono: true, render: function(row) {
      return row.path_error != null ? row.path_error.toFixed(3) : '\u2014';
    }},
    { key: 'cycle_time', label: 'Cycle Time', mono: true, render: function(row) {
      return row.cycle_time ? row.cycle_time.toFixed(2) + 's' : '\u2014';
    }},
    { key: 'timestamp', label: 'Date', mono: true, render: function(row) {
      return row.timestamp ? row.timestamp.slice(0, 16) : '\u2014';
    }}
  ];

  return e('div', null,
    e('div', { className: 'page-header' },
      e('h1', { className: 'page-header__title' }, 'Simulations'),
      e('p', { className: 'page-header__sub' }, 'Simulation runs and results')
    ),

    e('div', { className: 'grid-4 mb-20' },
      e(MetricCard, { label: 'Total Simulations', value: String(totalSims), borderColor: 'var(--accent)' }),
      e(MetricCard, { label: 'Pass Rate', value: totalSims > 0 ? Math.round(passCount / totalSims * 100) + '%' : '\u2014', sub: passCount + '/' + totalSims + ' passed', borderColor: 'var(--success)' }),
      e(MetricCard, { label: 'Avg Path Error', value: avgScore, borderColor: 'var(--info)' }),
      e(MetricCard, { label: 'Total Runs', value: String(totalEpisodes), borderColor: 'var(--accent)' })
    ),

    e('div', { className: 'filter-row' },
      e('select', { value: filters.robot, onChange: function(ev) { setFilters(Object.assign({}, filters, { robot: ev.target.value })); } },
        e('option', { value: 'all' }, 'All Robots'),
        robots.map(function(r) { return e('option', { key: r.id, value: r.id }, r.name || r.id); })
      ),
      e('select', { value: filters.result, onChange: function(ev) { setFilters(Object.assign({}, filters, { result: ev.target.value })); } },
        e('option', { value: 'all' }, 'All Results'),
        e('option', { value: 'pass' }, 'Pass'),
        e('option', { value: 'fail' }, 'Fail')
      )
    ),

    sims.length === 0
      ? e('div', { style: { padding: '48px 24px', textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' } },
          e('div', { style: { fontSize: '14px', fontWeight: 600, color: 'var(--text)', marginBottom: '6px' } }, 'No simulation runs recorded'),
          e('div', { style: { fontSize: '12px', color: 'var(--text-secondary)' } }, 'Run a simulation from the Demos page to see results here.')
        )
      : e('div', { className: 'card' },
          e(DataTable, { columns: columns, data: filtered })
        )
  );
}

export { SimulationsPage }
