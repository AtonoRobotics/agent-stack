import React, { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer
} from 'recharts'
import { authFetch } from '../utils/authFetch'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'
import { ProgressBar } from '../components/ProgressBar'
import { DataTable } from '../components/DataTable'

var e = React.createElement;

function TrainingPage() {
  var runsState = useState([]);
  var runs = runsState[0];
  var setRuns = runsState[1];
  var loadingState = useState(true);
  var loading = loadingState[0];
  var setLoading = loadingState[1];

  useEffect(function() {
    authFetch('/api/training?limit=50')
      .then(function(r) { return r.json(); })
      .then(function(data) { setRuns(data); setLoading(false); })
      .catch(function() { setLoading(false); });
  }, []);

  var activeRuns = runs.filter(function(t) { return t.status === 'running'; });
  var completedRuns = runs.filter(function(t) { return t.status !== 'running'; });

  // Build loss curve from completed runs with loss data
  var lossData = completedRuns.filter(function(r) { return r.final_loss != null; }).map(function(r, i) {
    return { run: i + 1, trainLoss: r.final_loss, valLoss: r.val_loss };
  });

  if (loading) {
    return e('div', null,
      e('div', { className: 'page-header' },
        e('h1', { className: 'page-header__title' }, 'Training'),
        e('p', { className: 'page-header__sub' }, 'Loading training runs...')
      )
    );
  }

  return e('div', null,
    e('div', { className: 'page-header' },
      e('h1', { className: 'page-header__title' }, 'Training'),
      e('p', { className: 'page-header__sub' }, 'Active and historical training runs')
    ),

    runs.length === 0
      ? e('div', { style: { padding: '48px 24px', textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' } },
          e('div', { style: { fontSize: '14px', fontWeight: 600, color: 'var(--text)', marginBottom: '6px' } }, 'No training runs recorded'),
          e('div', { style: { fontSize: '12px', color: 'var(--text-secondary)' } }, 'Training runs will appear here when you start a training job.')
        )
      : null,

    activeRuns.length > 0 ? e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Active Runs'),
        e(Badge, { variant: 'info' }, activeRuns.length + ' running')
      ),
      activeRuns.map(function(run) {
        var pct = run.epochs ? Math.round((run.epochs / (run.dataset_size || run.epochs)) * 100) : 0;
        return e('div', { key: run.id, style: { padding: '14px 0', borderBottom: '1px solid var(--border)' } },
          e('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' } },
            e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } },
              e(StatusDot, { status: 'busy' }),
              e('span', { style: { fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '13px' } }, 'TR-' + String(run.id).padStart(3, '0')),
              e('span', { style: { fontSize: '12px', color: 'var(--text-secondary)' } }, (run.robot || '') + ' \u2022 ' + (run.policy_name || ''))
            ),
            e('div', { style: { display: 'flex', gap: '16px', fontSize: '11px' } },
              run.final_loss != null ? e('span', { style: { color: 'var(--text-secondary)' } }, 'Loss: ', e('span', { style: { fontFamily: 'var(--font-mono)', color: 'var(--accent)' } }, run.final_loss.toFixed(4))) : null
            )
          ),
          run.epochs ? e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } },
            e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-dim)', minWidth: '70px' } }, 'Epoch ' + run.epochs),
            e('div', { style: { flex: 1 } },
              e(ProgressBar, { value: Math.min(pct, 100) })
            )
          ) : null
        );
      })
    ) : null,

    lossData.length > 1 ? e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Loss History')
      ),
      e(ResponsiveContainer, { width: '100%', height: 300 },
        e(LineChart, { data: lossData, margin: { top: 10, right: 30, left: 10, bottom: 10 } },
          e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#2E2E2E' }),
          e(XAxis, { dataKey: 'run', tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' }, label: { value: 'Run', position: 'bottom', fill: '#808080', fontSize: 11 } }),
          e(YAxis, { tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' }, label: { value: 'Loss', angle: -90, position: 'insideLeft', fill: '#808080', fontSize: 11 } }),
          e(Tooltip, { contentStyle: { background: '#242424', border: '1px solid #2E2E2E', borderRadius: '6px', fontSize: '12px', fontFamily: 'JetBrains Mono' } }),
          e(Legend, { wrapperStyle: { fontSize: '11px' } }),
          e(Line, { type: 'monotone', dataKey: 'trainLoss', stroke: '#E8A020', strokeWidth: 2, dot: true, name: 'Train Loss' }),
          e(Line, { type: 'monotone', dataKey: 'valLoss', stroke: '#26A69A', strokeWidth: 2, dot: true, name: 'Val Loss' })
        )
      )
    ) : null,

    completedRuns.length > 0 ? e('div', { className: 'card' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Historical Runs')
      ),
      e(DataTable, { columns: [
        { key: 'id', label: 'ID', mono: true },
        { key: 'robot', label: 'Robot' },
        { key: 'policy_name', label: 'Policy', mono: true },
        { key: 'status', label: 'Status', render: function(row) {
          var v = row.status === 'completed' ? 'success' : row.status === 'running' ? 'info' : 'danger';
          return e(Badge, { variant: v }, row.status || 'unknown');
        }},
        { key: 'epochs', label: 'Epochs', mono: true },
        { key: 'final_loss', label: 'Final Loss', mono: true, render: function(row) {
          return row.final_loss != null ? row.final_loss.toFixed(4) : '\u2014';
        }},
        { key: 'started', label: 'Started', render: function(row) {
          return row.started ? row.started.slice(0, 16) : '\u2014';
        }}
      ], data: completedRuns })
    ) : null
  );
}

export { TrainingPage }
