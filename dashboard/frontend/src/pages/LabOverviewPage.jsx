import React, { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { authFetch } from '../utils/authFetch'
import { Icon } from '../components/Icon'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'

var e = React.createElement;

function timeAgo(ts) {
  if (!ts) return ''
  var diff = Date.now() - new Date(ts).getTime()
  var mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return mins + 'm ago'
  var hours = Math.floor(mins / 60)
  if (hours < 24) return hours + 'h ago'
  return Math.floor(hours / 24) + 'd ago'
}

function LabOverviewPage() {
  var apiState = useState(null);
  var apiData = apiState[0];
  var setApiData = apiState[1];
  var fleetState = useState(null);
  var fleetData = fleetState[0];
  var setFleetData = fleetState[1];
  var agentsState = useState(null);
  var agentsData = agentsState[0];
  var setAgentsData = agentsState[1];
  var loadingState = useState(true);
  var loading = loadingState[0];
  var setLoading = loadingState[1];

  useEffect(function() {
    function fetchAll() {
      Promise.all([
        authFetch('/api/summary').then(function(r) { return r.json(); }).catch(function() { return null; }),
        authFetch('/api/fleet').then(function(r) { return r.json(); }).catch(function() { return null; }),
        authFetch('/api/agents').then(function(r) { return r.json(); }).catch(function() { return null; })
      ]).then(function(results) {
        if (results[0]) setApiData(results[0]);
        if (results[1]) setFleetData(results[1]);
        if (results[2]) setAgentsData(results[2]);
        setLoading(false);
      });
    }
    fetchAll();
    var interval = setInterval(fetchAll, 10000);
    return function() { clearInterval(interval); };
  }, []);

  var machinesOnline = apiData ? apiData.machines_online : 0;
  var machinesTotal = apiData ? apiData.machines_total : 0;
  var modelsLoaded = apiData ? apiData.models_loaded : 0;
  var activeTasks = apiData ? apiData.active_tasks : 0;
  var openIncidents = apiData ? apiData.open_incidents : 0;

  var displayMachines = fleetData ? fleetData.map(function(m) {
    var met = m.metrics || {};
    var hasMetrics = met.ram_total != null && met.ram_total > 0;
    return {
      id: m.name, name: m.name, os: (m.config && m.config.os) || '', arch: (m.config && m.config.arch) || '',
      status: met.status === 'online' && hasMetrics ? 'online' : met.status === 'error' ? 'offline' : hasMetrics ? 'warning' : 'offline',
      hasMetrics: hasMetrics,
      gpu: met.gpu_util, gpuTemp: met.temp_c,
      ram: met.ram_total, ramUsed: met.ram_used
    };
  }) : [];

  var recentTasks = agentsData && agentsData.tasks ? agentsData.tasks.slice(0, 4) : [];
  var activityFeed = apiData && apiData.recent_activity ? apiData.recent_activity : [];

  return e('div', null,
    e('div', { className: 'glass-page-header' },
      e('h1', null, 'Mission Control'),
      e('p', null, 'Robotics Fleet Intelligence')
    ),

    openIncidents > 0 ? e('div', {
      className: 'glass-card',
      style: { marginBottom: '14px', background: 'rgba(184,84,84,0.1)', border: '1px solid rgba(184,84,84,0.25)', display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 12px' }
    },
      Icon('alert'),
      e('span', { style: { fontSize: '11px', fontWeight: 500, color: '#c87070' } }, openIncidents + ' active alert' + (openIncidents > 1 ? 's' : ''))
    ) : null,

    e('div', { className: 'glass-metric-row' },
      e('div', { className: 'glass-metric' },
        e('div', { className: 'glass-metric__label' }, 'Machines Online'),
        e('div', { className: 'glass-metric__value' }, machinesOnline + '/' + machinesTotal),
        e('div', { className: 'glass-metric__sub' }, (machinesTotal - machinesOnline) + ' offline')
      ),
      e('div', { className: 'glass-metric' },
        e('div', { className: 'glass-metric__label' }, 'Models Loaded'),
        e('div', { className: 'glass-metric__value' }, String(modelsLoaded)),
        e('div', { className: 'glass-metric__sub' }, 'across fleet')
      ),
      e('div', { className: 'glass-metric' },
        e('div', { className: 'glass-metric__label' }, 'Active Tasks'),
        e('div', { className: 'glass-metric__value' }, String(activeTasks)),
        e('div', { className: 'glass-metric__sub' }, activeTasks > 0 ? 'in progress' : 'idle')
      ),
      e('div', { className: 'glass-metric' },
        e('div', { className: 'glass-metric__label' }, 'Open Incidents'),
        e('div', { className: 'glass-metric__value' }, String(openIncidents)),
        e('div', { className: 'glass-metric__sub' }, openIncidents > 0 ? 'Needs attention' : 'All clear')
      )
    ),

    e('div', { className: 'glass-card-grid', style: { marginBottom: '10px' } },
      e('div', { className: 'glass-card' },
        e('div', { className: 'glass-card__header' },
          e('span', { className: 'glass-card__title' }, 'Fleet Health')
        ),
        loading && displayMachines.length === 0
          ? e('div', { style: { padding: '20px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '12px' } }, 'Loading fleet data...')
          : displayMachines.length === 0
            ? e('div', { style: { padding: '20px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '12px' } }, 'No machines registered')
            : displayMachines.map(function(m) {
                var ramPct = m.ram > 0 ? Math.round((m.ramUsed || 0) / m.ram * 100) : null;
                return e('div', { key: m.id, style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: m.hasMetrics ? 1 : 0.5 } },
                  e(StatusDot, { status: m.status }),
                  e('span', { style: { flex: 1, fontSize: '12px', fontWeight: 500 } }, m.name),
                  m.hasMetrics
                    ? e(React.Fragment, null,
                        e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', color: m.gpu > 85 ? 'var(--danger)' : 'var(--text)', minWidth: '60px' } }, 'GPU ' + Math.round(m.gpu || 0) + '%'),
                        e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', color: m.gpuTemp > 75 ? 'var(--danger)' : m.gpuTemp > 60 ? 'var(--warning)' : 'var(--text)', minWidth: '44px' } }, Math.round(m.gpuTemp || 0) + '\u00B0C'),
                        e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', minWidth: '60px' } }, 'RAM ' + ramPct + '%')
                      )
                    : e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-dim)' } }, 'no data')
                );
              })
      ),

      e('div', { className: 'glass-card' },
        e('div', { className: 'glass-card__header' },
          e('span', { className: 'glass-card__title' }, 'GPU Utilization')
        ),
        displayMachines.filter(function(m) { return m.hasMetrics; }).length > 0
          ? e(ResponsiveContainer, { width: '100%', height: 260 },
              e(BarChart, { data: displayMachines.filter(function(m) { return m.hasMetrics; }).map(function(m) { return { name: m.name, gpu: Math.round(m.gpu || 0) }; }), layout: 'vertical', margin: { top: 5, right: 30, left: 80, bottom: 5 } },
                e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#2E2E2E' }),
                e(XAxis, { type: 'number', domain: [0, 100], tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' } }),
                e(YAxis, { type: 'category', dataKey: 'name', tick: { fill: '#E0E0E0', fontSize: 11 }, width: 130 }),
                e(Tooltip, { contentStyle: { background: '#242424', border: '1px solid #2E2E2E', borderRadius: '6px', fontSize: '12px', fontFamily: 'JetBrains Mono' }, labelStyle: { color: '#E0E0E0' } }),
                e(Bar, { dataKey: 'gpu', fill: '#E8A020', radius: [0, 4, 4, 0], barSize: 18 })
              )
            )
          : e('div', { style: { height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: '12px' } }, 'No GPU data available')
      )
    ),

    e('div', { className: 'glass-card-grid', style: { marginBottom: '10px' } },
      e('div', { className: 'glass-card' },
        e('div', { className: 'glass-card__header' },
          e('span', { className: 'glass-card__title' }, 'Recent Tasks')
        ),
        recentTasks.length === 0
          ? e('div', { style: { padding: '20px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '12px' } }, 'No recent tasks')
          : recentTasks.map(function(t) {
              var agentLabel = (t.agent || '').replace(/_/g, ' ');
              agentLabel = agentLabel.charAt(0).toUpperCase() + agentLabel.slice(1);
              return e('div', { key: t.id, style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' } },
                e(StatusDot, { status: t.success ? 'online' : t.completed ? 'offline' : 'busy' }),
                e('div', { style: { flex: 1, minWidth: 0 } },
                  e('div', { style: { fontSize: '12px', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, (t.task || '').substring(0, 60)),
                  e('div', { style: { fontSize: '10px', color: 'var(--text-secondary)', marginTop: '2px' } }, agentLabel + ' \u2022 ' + (t.model_used || ''))
                ),
                e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-dim)', minWidth: '50px', textAlign: 'right' } }, timeAgo(t.completed || t.started))
              );
            })
      ),

      e('div', { className: 'glass-card' },
        e('div', { className: 'glass-card__header' },
          e('span', { className: 'glass-card__title' }, 'Activity Feed')
        ),
        activityFeed.length === 0
          ? e('div', { style: { padding: '20px', textAlign: 'center', color: 'var(--text-dim)', fontSize: '12px' } }, 'No recent activity')
          : e('div', { className: 'glass-timeline' },
              activityFeed.slice(0, 10).map(function(a, i) {
                var cat = a.category || '';
                var dotClass = cat === 'auto_fix' ? 'glass-timeline__dot--success' : cat === 'api_escalation' ? 'glass-timeline__dot--danger' : 'glass-timeline__dot--accent';
                return e('div', { key: a.id || i, className: 'glass-timeline__item' },
                  e('div', { className: 'glass-timeline__dot ' + dotClass }),
                  e('div', { className: 'glass-timeline__content' },
                    e('span', { className: 'glass-timeline__msg' }, (a.message || '').substring(0, 100)),
                    e('span', { className: 'glass-timeline__time' }, timeAgo(a.timestamp))
                  )
                );
              })
            )
      )
    )
  );
}

export { LabOverviewPage }
