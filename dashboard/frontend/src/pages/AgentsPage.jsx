import React from 'react'
import { authFetch } from '../utils/authFetch'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'
import { MetricCard } from '../components/MetricCard'
import { DataTable } from '../components/DataTable'
import { Icon } from '../components/Icon'

var e = React.createElement;

var AGENT_META = {
  code_generation: { display: 'Code Generation', model: 'qwen2.5-coder:32b', icon: 'cpu' },
  research:        { display: 'Research',         model: 'qwen2.5:72b',       icon: 'chart' },
  sysadmin:        { display: 'System Admin',     model: 'qwen2.5:72b',       icon: 'server' },
  monitoring:      { display: 'Monitoring',       model: 'qwen2.5:7b',        icon: 'activity' },
  simulation:      { display: 'Simulation',       model: 'qwen2.5:72b',       icon: 'play' },
  training:        { display: 'Training',         model: 'qwen2.5:72b',       icon: 'brain' },
  cosmos:          { display: 'Cosmos',            model: 'qwen2.5:72b',       icon: 'play' },
  resource_mgr:    { display: 'Resource Manager',  model: 'qwen2.5:7b',        icon: 'chart' },
  git:             { display: 'Git',              model: 'qwen2.5-coder:32b', icon: 'git' },
  docs:            { display: 'Documentation',    model: 'qwen2.5:72b',       icon: 'docs' }
};

function formatName(s) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}

function formatDuration(started, completed) {
  if (!started || !completed) return '—';
  var ms = new Date(completed) - new Date(started);
  if (ms < 0) return '—';
  var s = Math.floor(ms / 1000);
  if (s < 60) return s + 's';
  var m = Math.floor(s / 60);
  s = s % 60;
  if (m < 60) return m + 'm ' + s + 's';
  var h = Math.floor(m / 60);
  m = m % 60;
  return h + 'h ' + m + 'm';
}

function timeAgo(dateStr) {
  if (!dateStr) return '—';
  var diff = Date.now() - new Date(dateStr).getTime();
  if (diff < 0) return 'just now';
  var mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  var hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  var days = Math.floor(hrs / 24);
  return days + 'd ago';
}

function formatTime(dateStr) {
  if (!dateStr) return '—';
  var d = new Date(dateStr);
  var mo = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return mo[d.getMonth()] + ' ' + d.getDate() + ' ' +
    String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}

function truncateTask(text, max) {
  if (!text) return '—';
  return text.length > max ? text.substring(0, max) + '...' : text;
}

function priorityLabel(p) {
  if (p <= 0) return { text: 'CRITICAL', variant: 'danger' };
  if (p <= 10) return { text: 'HIGH', variant: 'danger' };
  if (p <= 50) return { text: 'NORMAL', variant: 'neutral' };
  return { text: 'LOW', variant: 'info' };
}

function eventStatusVariant(status) {
  if (status === 'completed') return 'success';
  if (status === 'failed' || status === 'timeout') return 'danger';
  if (status === 'processing') return 'accent';
  return 'neutral';
}

function AgentsPage() {
  var stateArr = React.useState(null);
  var data = stateArr[0], setData = stateArr[1];
  var loadArr = React.useState(true);
  var loading = loadArr[0], setLoading = loadArr[1];
  var errArr = React.useState(null);
  var error = errArr[0], setError = errArr[1];

  function fetchData() {
    authFetch('/api/agents').then(function(r) { return r.json(); }).then(function(d) {
      setData(d);
      setLoading(false);
    }).catch(function(err) {
      setError('Failed to load agents: ' + err.message);
      setLoading(false);
    });
  }

  React.useEffect(function() {
    fetchData();
    var interval = setInterval(function() {
      fetchData();
    }, 30000);
    return function() {
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return e('div', { className: 'page-header' },
      e('h1', { className: 'page-header__title' }, 'Agents'),
      e('p', { className: 'page-header__sub' }, 'Loading...')
    );
  }

  if (error || !data) {
    return e('div', null,
      e('div', { className: 'page-header' },
        e('h1', { className: 'page-header__title' }, 'Agents'),
        e('p', { className: 'page-header__sub' }, error || 'No data')
      )
    );
  }

  var tasks = data.tasks || [];
  var stats = data.stats || {};
  var perAgent = data.per_agent || {};
  var orchestrator = data.orchestrator || {};
  var orchStats = orchestrator.stats || {};
  var orchByStatus = orchStats.by_status || {};
  var orchEvents = (orchestrator.events || []).slice(0, 30);
  var orchActive = !!orchestrator.service_active;

  // Group tasks by agent
  var agentTasks = {};
  tasks.forEach(function(t) {
    var a = t.agent || 'unknown';
    if (!agentTasks[a]) agentTasks[a] = [];
    agentTasks[a].push(t);
  });

  var agentNames = Object.keys(perAgent).sort(function(a, b) {
    return (perAgent[b].total || 0) - (perAgent[a].total || 0);
  });

  var recentlyActive = {};
  tasks.forEach(function(t) {
    if (t.completed && (Date.now() - new Date(t.completed).getTime()) < 300000) {
      recentlyActive[t.agent] = true;
    }
  });

  return e('div', null,
    // Page header
    e('div', { className: 'page-header' },
      e('h1', { className: 'page-header__title' }, 'Agents'),
      e('p', { className: 'page-header__sub' }, agentNames.length + ' agents registered')
    ),

    // Orchestrator status banner
    e('div', { className: 'card mb-20', style: { padding: '12px 20px' } },
      e('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' } },
        e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } },
          e(StatusDot, { status: orchActive ? 'online' : 'offline' }),
          e('span', { style: { fontWeight: 600, fontSize: '14px' } },
            orchActive ? 'Orchestrator Running' : 'Orchestrator Stopped'
          )
        ),
        e('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } },
          e(Badge, { variant: 'neutral' }, (orchStats.total || 0) + ' events'),
          e(Badge, { variant: 'success' }, (orchByStatus.completed || 0) + ' completed'),
          e(Badge, { variant: 'danger' }, (orchByStatus.failed || 0) + ' failed'),
          e(Badge, { variant: 'accent' }, (orchByStatus.processing || 0) + ' processing')
        )
      )
    ),

    // Summary stats
    e('div', { className: 'grid-3 mb-20' },
      e(MetricCard, { label: 'Total Tasks', value: String(stats.total || 0), borderColor: 'var(--accent)' }),
      e(MetricCard, { label: 'Success Rate', value: Math.round(stats.success_rate || 0) + '%', borderColor: 'var(--success)' }),
      e(MetricCard, { label: 'Local Inference', value: Math.round(stats.cost_savings_pct || 0) + '%', borderColor: 'var(--info)' }),
      e(MetricCard, { label: 'Agents', value: String(agentNames.length), borderColor: 'var(--warning)' }),
      e(MetricCard, { label: 'Events Processed', value: String(orchStats.total || 0), borderColor: 'var(--accent)' }),
      e(MetricCard, { label: 'Orchestrator', value: orchActive ? 'Active' : 'Stopped', borderColor: orchActive ? 'var(--success)' : 'var(--danger)' })
    ),

    // Agent cards grid
    e('div', { className: 'grid-2 mb-20' },
      agentNames.map(function(agentKey) {
        var meta = AGENT_META[agentKey] || { display: formatName(agentKey), model: 'unknown', icon: 'cpu' };
        var agStats = perAgent[agentKey] || {};
        var agTasks = agentTasks[agentKey] || [];
        var lastTask = agTasks[0] || null;
        var successRate = agStats.total > 0 ? Math.round(agStats.success / agStats.total * 100) : 0;
        var localPct = agStats.total > 0 ? Math.round(agStats.local / agStats.total * 100) : 0;
        var isRecent = !!recentlyActive[agentKey];

        return e('div', {
          key: agentKey,
          className: 'agent-card' + (isRecent ? ' agent-card--recent' : '')
        },
          // Header
          e('div', { className: 'agent-card__header' },
            e('div', { className: 'agent-card__name-row' },
              e('div', { className: 'agent-card__icon' }, Icon(meta.icon)),
              e('span', { className: 'agent-card__name' }, meta.display)
            ),
            e(Badge, { variant: 'neutral' }, meta.model)
          ),

          // Stats row
          e('div', { className: 'agent-card__stats' },
            e('span', null,
              e('strong', null, agStats.total || 0), ' tasks'
            ),
            e('span', null, '\u00b7'),
            e('span', { style: { color: successRate >= 90 ? 'var(--success)' : successRate >= 70 ? 'var(--warning)' : 'var(--danger)' } },
              e('strong', null, successRate + '%'), ' success'
            ),
            e('span', null, '\u00b7'),
            e('span', null, localPct + '% local')
          ),

          // Last task
          lastTask ? e('div', { className: 'agent-card__task' },
            e('div', { className: 'agent-card__task-label' }, 'LAST TASK'),
            e('div', { className: 'agent-card__task-text' }, truncateTask(lastTask.task, 120)),
            e('div', { className: 'agent-card__task-meta' },
              formatTime(lastTask.started),
              ' \u2192 ',
              formatDuration(lastTask.started, lastTask.completed),
              ' \u00b7 ',
              lastTask.success ? e('span', { key: 's', style: { color: 'var(--success)' } }, '\u2713') : e('span', { key: 'f', style: { color: 'var(--danger)' } }, '\u2717'),
              ' \u00b7 ',
              timeAgo(lastTask.completed)
            )
          ) : e('div', { className: 'agent-card__task' },
            e('div', { className: 'agent-card__task-label' }, 'No tasks yet')
          )
        );
      })
    ),

    // Orchestrator events table
    e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Orchestrator Events'),
        e(Badge, { variant: 'accent' }, orchEvents.length + ' events')
      ),
      orchEvents.length > 0
        ? e(DataTable, {
            columns: [
              { key: 'priority', label: 'Priority', render: function(row) {
                var p = priorityLabel(row.priority != null ? row.priority : 50);
                return e(Badge, { variant: p.variant }, p.text);
              }},
              { key: 'source', label: 'Source', render: function(row) {
                return formatName(row.source || 'unknown');
              }},
              { key: 'event_type', label: 'Event Type', render: function(row) {
                return formatName(row.event_type || '—');
              }},
              { key: 'status', label: 'Status', render: function(row) {
                return e(Badge, { variant: eventStatusVariant(row.status) }, row.status || 'unknown');
              }},
              { key: 'assigned_agents', label: 'Agents', render: function(row) {
                var agents = row.assigned_agents || [];
                if (!agents.length) return '—';
                return agents.map(function(a) {
                  var m = AGENT_META[a];
                  return m ? m.display : formatName(a);
                }).join(', ');
              }},
              { key: 'result', label: 'Result', render: function(row) {
                return e('span', { title: row.result || '' }, truncateTask(row.result, 60));
              }},
              { key: 'timestamp', label: 'When', render: function(row) {
                return timeAgo(row.completed_at || row.timestamp);
              }}
            ],
            data: orchEvents
          })
        : e('div', { style: { padding: '20px', textAlign: 'center', color: 'var(--text-dim)' } },
            'No orchestrator events yet'
          )
    ),

    // Recent task history table
    e('div', { className: 'card' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Task History'),
        e(Badge, { variant: 'accent' }, tasks.length + ' records')
      ),
      e(DataTable, {
        columns: [
          { key: 'id', label: 'ID', mono: true },
          { key: 'agent', label: 'Agent', render: function(row) {
            var m = AGENT_META[row.agent];
            return m ? m.display : formatName(row.agent || 'unknown');
          }},
          { key: 'task', label: 'Task', render: function(row) {
            return e('span', { title: row.task }, truncateTask(row.task, 80));
          }},
          { key: 'status', label: 'Status', render: function(row) {
            return e(Badge, { variant: row.success ? 'success' : 'danger' }, row.success ? 'completed' : 'failed');
          }},
          { key: 'duration', label: 'Duration', mono: true, render: function(row) {
            return formatDuration(row.started, row.completed);
          }},
          { key: 'time', label: 'When', render: function(row) {
            return timeAgo(row.completed || row.started);
          }}
        ],
        data: tasks.slice(0, 25)
      })
    )
  );
}

export { AgentsPage }
