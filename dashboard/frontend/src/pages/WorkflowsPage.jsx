import React, { useState, useEffect, useCallback } from 'react'
import { authFetch } from '../utils/authFetch'
import { fmtDuration, fmtDate, statusVariant } from '../utils/fmt'

var e = React.createElement;

function WorkflowsPage() {
  var tabState = useState('graphs');
  var tab = tabState[0], setTab = tabState[1];
  var graphsState = useState([]);
  var graphs = graphsState[0], setGraphs = graphsState[1];
  var runsState = useState([]);
  var runs = runsState[0], setRuns = runsState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];
  var expandedState = useState(null);
  var expanded = expandedState[0], setExpanded = expandedState[1];
  var jsonViewState = useState(null);
  var jsonView = jsonViewState[0], setJsonView = jsonViewState[1];
  var filterGraph = useState('');
  var graphFilter = filterGraph[0], setGraphFilter = filterGraph[1];
  var filterStatus = useState('');
  var statusFilter = filterStatus[0], setStatusFilter = filterStatus[1];

  useEffect(function() {
    setLoading(true);
    if (tab === 'graphs') {
      authFetch('/mc/api/workflows/graphs')
        .then(function(r) { return r.json(); })
        .then(function(d) { setGraphs(d.items || d); setLoading(false); })
        .catch(function() { setLoading(false); });
    } else {
      var params = '?limit=50';
      if (graphFilter) params += '&graph_id=' + encodeURIComponent(graphFilter);
      if (statusFilter) params += '&status=' + encodeURIComponent(statusFilter);
      authFetch('/mc/api/workflows/runs' + params)
        .then(function(r) { return r.json(); })
        .then(function(d) { setRuns(d.items || d); setLoading(false); })
        .catch(function() { setLoading(false); });
    }
  }, [tab, graphFilter, statusFilter]);

  function startRun(graphId, graphName) {
    authFetch('/mc/api/workflows/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ graph_id: graphId, graph_name: graphName || 'unnamed' })
    }).then(function() {
      setTab('runs');
    }).catch(function() {});
  }

  function fetchRunLogs(runId) {
    return authFetch('/mc/api/workflows/runs/' + runId + '/logs')
      .then(function(r) { return r.json(); });
  }

  return e('div', null,
    e('div', { className: 'glass-page-header' },
      e('h1', null, 'Workflows'),
      e('p', null, 'Pipeline workflow graphs and execution runs')
    ),

    // Tabs
    e('div', { className: 'glass-tabs' },
      e('button', {
        className: 'glass-tab' + (tab === 'graphs' ? ' glass-tab--active' : ''),
        onClick: function() { setTab('graphs'); }
      }, 'Graphs'),
      e('button', {
        className: 'glass-tab' + (tab === 'runs' ? ' glass-tab--active' : ''),
        onClick: function() { setTab('runs'); }
      }, 'Runs')
    ),

    loading
      ? e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...')
      : tab === 'graphs'
        ? e('div', null,
            graphs.length === 0
              ? e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'No workflow graphs defined')
              : e('div', { className: 'glass-card-grid' },
                  graphs.map(function(g) {
                    var showJson = jsonView === (g.graph_id || g.id);
                    return e('div', { key: g.graph_id || g.id, className: 'glass-card' },
                      e('div', { className: 'glass-card__header' },
                        e('div', null,
                          e('div', { className: 'glass-card__title' }, g.name || 'Graph ' + (g.graph_id || g.id)),
                          e('div', { className: 'glass-card__sub' }, g.description || (g.node_count || 0) + ' nodes · v' + (g.version || '1'))
                        ),
                        e('span', { className: 'glass-pill glass-pill--accent' }, 'v' + (g.version || '1'))
                      ),
                      e('div', { className: 'glass-card__actions' },
                        e('button', { className: 'glass-btn', onClick: function() { startRun(g.graph_id || g.id, g.name); } }, 'New Run'),
                        e('button', { className: 'glass-btn glass-btn--ghost', onClick: function() { setJsonView(showJson ? null : g.graph_id || g.id); } },
                          showJson ? 'Hide JSON' : 'View JSON')
                      ),
                      showJson ? e('div', { className: 'glass-log', style: { marginTop: '8px' } },
                        e('pre', null, JSON.stringify(g.graph_json || g, null, 2))
                      ) : null
                    );
                  })
                )
          )
        : e('div', null,
            // Run filters
            e('div', { className: 'glass-filter-row' },
              e('select', { value: graphFilter, onChange: function(ev) { setGraphFilter(ev.target.value); } },
                e('option', { value: '' }, 'All graphs'),
                graphs.map(function(g) { return e('option', { key: g.graph_id || g.id, value: g.graph_id || g.id }, g.name || 'Graph ' + (g.graph_id || g.id)); })
              ),
              e('select', { value: statusFilter, onChange: function(ev) { setStatusFilter(ev.target.value); } },
                e('option', { value: '' }, 'All statuses'),
                e('option', { value: 'pending' }, 'Pending'),
                e('option', { value: 'running' }, 'Running'),
                e('option', { value: 'completed' }, 'Completed'),
                e('option', { value: 'failed' }, 'Failed')
              )
            ),

            e('table', { className: 'glass-table' },
              e('thead', null,
                e('tr', null,
                  e('th', null, 'Run ID'),
                  e('th', null, 'Graph'),
                  e('th', null, 'Status'),
                  e('th', null, 'Duration'),
                  e('th', null, 'Started')
                )
              ),
              e('tbody', null,
                runs.length === 0
                  ? e('tr', null, e('td', { colSpan: 5, style: { textAlign: 'center', color: 'var(--text-dim)', padding: '30px' } }, 'No workflow runs'))
                  : runs.map(function(r) {
                      var isExp = expanded === (r.run_id || r.id);
                      return e(React.Fragment, { key: r.run_id || r.id },
                        e('tr', {
                          className: isExp ? 'glass-table__row--expanded' : '',
                          onClick: function() { setExpanded(isExp ? null : (r.run_id || r.id)); },
                          style: { cursor: 'pointer' }
                        },
                          e('td', { className: 'mono' }, String(r.run_id || r.id).slice(0, 8)),
                          e('td', null, r.graph_name || r.graph_id || '—'),
                          e('td', null, e('span', { className: 'glass-pill glass-pill--' + statusVariant(r.status) }, r.status)),
                          e('td', { className: 'mono' }, fmtDuration(r.duration_s)),
                          e('td', null, fmtDate(r.started_at || r.created_at))
                        ),
                        isExp ? e('tr', { className: 'glass-table__detail-row' },
                          e('td', { colSpan: 5 },
                            r.node_results ? e('div', { className: 'glass-log' },
                              e('strong', null, 'Node Results:'),
                              e('pre', null, typeof r.node_results === 'string' ? r.node_results : JSON.stringify(r.node_results, null, 2))
                            ) : null,
                            e(RunLogs, { runId: r.run_id || r.id })
                          )
                        ) : null
                      );
                    })
              )
            )
          )
  );
}

function RunLogs(props) {
  var logsState = useState(null);
  var logs = logsState[0], setLogs = logsState[1];

  useEffect(function() {
    authFetch('/mc/api/workflows/runs/' + props.runId + '/logs')
      .then(function(r) { return r.json(); })
      .then(function(d) { setLogs(d.items || d); })
      .catch(function() { setLogs([]); });
  }, [props.runId]);

  if (!logs) return e('div', { style: { padding: '8px', color: 'var(--text-dim)', fontSize: '10px' } }, 'Loading logs...');
  if (logs.length === 0) return e('div', { style: { padding: '8px', color: 'var(--text-dim)', fontSize: '10px' } }, 'No logs for this run');

  return e('div', { className: 'glass-timeline', style: { marginTop: '8px' } },
    e('div', { style: { fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' } }, 'Run Timeline'),
    logs.map(function(log, i) {
      return e('div', { key: i, className: 'glass-timeline__item' },
        e('div', { className: 'glass-timeline__dot glass-timeline__dot--' + statusVariant(log.status || log.level) }),
        e('div', { className: 'glass-timeline__content' },
          e('span', { className: 'glass-timeline__node' }, log.node_name || log.step || ''),
          e('span', { className: 'glass-timeline__msg' }, log.message || log.detail || ''),
          e('span', { className: 'glass-timeline__time' }, fmtDate(log.created_at || log.timestamp))
        )
      );
    })
  );
}

export { WorkflowsPage }
