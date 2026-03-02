import React, { useState, useEffect, useCallback } from 'react'
import { authFetch } from '../utils/authFetch'
import { fmtDuration, fmtDate, statusVariant } from '../utils/fmt'

var e = React.createElement;

function MCAgentsPage() {
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var summaryState = useState([]);
  var summary = summaryState[0], setSummary = summaryState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];
  var filterAgent = useState('');
  var agent = filterAgent[0], setAgent = filterAgent[1];
  var filterStatus = useState('');
  var status = filterStatus[0], setStatus = filterStatus[1];
  var pageState = useState(0);
  var page = pageState[0], setPage = pageState[1];
  var totalState = useState(0);
  var total = totalState[0], setTotal = totalState[1];
  var expandedState = useState(null);
  var expanded = expandedState[0], setExpanded = expandedState[1];
  var limit = 20;

  var fetchData = useCallback(function() {
    var params = '?limit=' + limit + '&offset=' + (page * limit);
    if (agent) params += '&agent_name=' + encodeURIComponent(agent);
    if (status) params += '&status=' + encodeURIComponent(status);
    authFetch('/mc/api/agents/logs' + params)
      .then(function(r) { return r.json(); })
      .then(function(d) {
        setData(d.items || d);
        setTotal(d.total || (Array.isArray(d.items || d) ? (d.items || d).length : 0));
        setLoading(false);
      })
      .catch(function() { setLoading(false); });
  }, [page, agent, status]);

  useEffect(function() {
    authFetch('/mc/api/agents/summary')
      .then(function(r) { return r.json(); })
      .then(setSummary)
      .catch(function() {});
  }, []);

  useEffect(function() {
    fetchData();
    var iv = setInterval(fetchData, 30000);
    return function() { clearInterval(iv); };
  }, [fetchData]);

  var agentNames = summary.map ? summary.map(function(s) { return s.agent_name; }) : [];

  return e('div', null,
    e('div', { className: 'glass-page-header' },
      e('h1', null, 'Pipeline Agents'),
      e('p', null, 'Agent execution logs and performance')
    ),

    // Summary tiles
    e('div', { className: 'glass-metric-row' },
      summary.map ? summary.map(function(s) {
        return e('div', { key: s.agent_name, className: 'glass-metric' },
          e('div', { className: 'glass-metric__label' }, s.agent_name),
          e('div', { className: 'glass-metric__value' }, s.total_runs || 0),
          e('div', { className: 'glass-metric__sub' },
            (s.success_rate != null ? (s.success_rate * 100).toFixed(0) + '% success' : '—') +
            ' · ' + fmtDuration(s.avg_duration)
          )
        );
      }) : null
    ),

    // Filters
    e('div', { className: 'glass-filter-row' },
      e('select', { value: agent, onChange: function(ev) { setAgent(ev.target.value); setPage(0); } },
        e('option', { value: '' }, 'All agents'),
        agentNames.map(function(n) { return e('option', { key: n, value: n }, n); })
      ),
      e('select', { value: status, onChange: function(ev) { setStatus(ev.target.value); setPage(0); } },
        e('option', { value: '' }, 'All statuses'),
        e('option', { value: 'success' }, 'Success'),
        e('option', { value: 'failed' }, 'Failed'),
        e('option', { value: 'in_progress' }, 'In Progress')
      ),
      e('span', { className: 'glass-filter-row__count' }, total + ' results')
    ),

    // Table
    loading
      ? e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...')
      : e('table', { className: 'glass-table' },
          e('thead', null,
            e('tr', null,
              e('th', null, 'Agent'),
              e('th', null, 'Type'),
              e('th', null, 'Status'),
              e('th', null, 'Duration'),
              e('th', null, 'Build'),
              e('th', null, 'Created')
            )
          ),
          e('tbody', null,
            data.length === 0
              ? e('tr', null, e('td', { colSpan: 6, style: { textAlign: 'center', color: 'var(--text-dim)', padding: '30px' } }, 'No agent logs found'))
              : data.map(function(row, i) {
                  var isExp = expanded === (row.log_id || row.id);
                  return e(React.Fragment, { key: row.log_id || row.id || i },
                    e('tr', {
                      className: isExp ? 'glass-table__row--expanded' : '',
                      onClick: function() { setExpanded(isExp ? null : (row.log_id || row.id)); },
                      style: { cursor: 'pointer' }
                    },
                      e('td', { className: 'mono' }, row.agent_name),
                      e('td', null, row.agent_type || '—'),
                      e('td', null, e('span', { className: 'glass-pill glass-pill--' + statusVariant(row.status) }, row.status)),
                      e('td', { className: 'mono' }, fmtDuration(row.duration_s)),
                      e('td', { className: 'mono' }, row.build_id ? String(row.build_id).slice(0, 8) : '—'),
                      e('td', null, fmtDate(row.created_at))
                    ),
                    isExp ? e('tr', { className: 'glass-table__detail-row' },
                      e('td', { colSpan: 6 },
                        e('div', { className: 'glass-log' },
                          row.input_params ? e('div', null,
                            e('strong', null, 'Input: '),
                            e('pre', null, typeof row.input_params === 'string' ? row.input_params : JSON.stringify(row.input_params, null, 2))
                          ) : null,
                          row.output ? e('div', { style: { marginTop: '8px' } },
                            e('strong', null, 'Output: '),
                            e('pre', null, typeof row.output === 'string' ? row.output : JSON.stringify(row.output, null, 2))
                          ) : null
                        )
                      )
                    ) : null
                  );
                })
          )
        ),

    // Pagination
    total > limit ? e('div', { className: 'glass-pagination' },
      e('button', {
        className: 'glass-btn', disabled: page === 0,
        onClick: function() { setPage(page - 1); }
      }, 'Prev'),
      e('span', null, 'Page ' + (page + 1) + ' of ' + Math.ceil(total / limit)),
      e('button', {
        className: 'glass-btn', disabled: (page + 1) * limit >= total,
        onClick: function() { setPage(page + 1); }
      }, 'Next')
    ) : null
  );
}

export { MCAgentsPage }
