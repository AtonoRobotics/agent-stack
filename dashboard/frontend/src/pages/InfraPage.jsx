import React, { useState, useEffect } from 'react'
import { authFetch } from '../utils/authFetch'
import { statusVariant } from '../utils/fmt'

var e = React.createElement;

function InfraPage() {
  var tabState = useState('containers');
  var tab = tabState[0], setTab = tabState[1];

  return e('div', null,
    e('div', { className: 'glass-page-header' },
      e('h1', null, 'Infrastructure'),
      e('p', null, 'Containers, ROS2 network, and simulation status')
    ),
    e('div', { className: 'glass-tabs' },
      ['containers', 'ros2', 'isaac'].map(function(t) {
        var labels = { containers: 'Containers', ros2: 'ROS2', isaac: 'Isaac Sim' };
        return e('button', {
          key: t, className: 'glass-tab' + (tab === t ? ' glass-tab--active' : ''),
          onClick: function() { setTab(t); }
        }, labels[t]);
      })
    ),
    tab === 'containers' ? e(ContainersTab) : null,
    tab === 'ros2' ? e(Ros2Tab) : null,
    tab === 'isaac' ? e(IsaacTab) : null
  );
}

function ContainersTab() {
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];

  function fetchContainers() {
    authFetch('/mc/api/containers')
      .then(function(r) { return r.json(); })
      .then(function(d) { setData(d.items || d); setLoading(false); })
      .catch(function() { setLoading(false); });
  }

  useEffect(function() {
    fetchContainers();
    var iv = setInterval(fetchContainers, 15000);
    return function() { clearInterval(iv); };
  }, []);

  if (loading) return e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...');

  return data.length === 0
    ? e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'No containers defined or Docker daemon unavailable')
    : e('div', { className: 'container-grid' },
        data.map(function(c) {
          var st = (c.status || c.state || 'unknown').toLowerCase();
          var variant = st === 'running' ? 'success' : st === 'exited' ? 'neutral' : st === 'error' ? 'danger' : 'warning';
          return e('div', { key: c.name || c.id, className: 'container-tile' },
            e('div', { className: 'container-tile__header' },
              e('div', { className: 'container-tile__dot container-tile__dot--' + variant }),
              e('div', { className: 'container-tile__name' }, c.name || c.id)
            ),
            e('div', { className: 'container-tile__status' },
              e('span', { className: 'glass-pill glass-pill--' + variant }, st)
            ),
            c.image ? e('div', { className: 'container-tile__detail' }, c.image) : null,
            c.ports ? e('div', { className: 'container-tile__detail' }, 'Ports: ' + (typeof c.ports === 'string' ? c.ports : JSON.stringify(c.ports))) : null
          );
        })
      );
}

function Ros2Tab() {
  var statusState = useState(null);
  var rosStatus = statusState[0], setRosStatus = statusState[1];
  var topicsState = useState([]);
  var topics = topicsState[0], setTopics = topicsState[1];
  var nodesState = useState([]);
  var nodes = nodesState[0], setNodes = nodesState[1];
  var loadingState = useState(true);
  var loading = loadingState[0], setLoading = loadingState[1];

  useEffect(function() {
    Promise.all([
      authFetch('/mc/api/ros2/status').then(function(r) { return r.json(); }),
      authFetch('/mc/api/ros2/topics').then(function(r) { return r.json(); }).catch(function() { return []; }),
      authFetch('/mc/api/ros2/nodes').then(function(r) { return r.json(); }).catch(function() { return []; })
    ]).then(function(results) {
      setRosStatus(results[0]);
      var t = results[1]; setTopics(Array.isArray(t) ? t : t.topics || t.items || []);
      var n = results[2]; setNodes(Array.isArray(n) ? n : n.nodes || n.items || []);
      setLoading(false);
    }).catch(function() { setLoading(false); });
  }, []);

  if (loading) return e('div', { className: 'glass-card', style: { padding: '40px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading...');

  var connected = rosStatus && rosStatus.connected;

  return e('div', null,
    // Connection status
    e('div', { className: 'glass-card', style: { marginBottom: '12px' } },
      e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } },
        e('div', { className: 'status-dot' + (connected ? ' status-dot--online' : ' status-dot--offline') }),
        e('div', null,
          e('div', { style: { fontSize: '12px', fontWeight: 600, color: 'var(--text-bright)' } },
            connected ? 'ROS2 Bridge Connected' : 'ROS2 Bridge Disconnected'),
          rosStatus && rosStatus.url ? e('div', { style: { fontSize: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', marginTop: '2px' } }, rosStatus.url) : null
        )
      )
    ),

    // Topics
    e('div', { className: 'glass-card', style: { marginBottom: '12px' } },
      e('div', { style: { fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' } },
        'Topics (' + topics.length + ')'),
      topics.length === 0
        ? e('div', { style: { color: 'var(--text-dim)', fontSize: '11px' } }, 'No topics available')
        : e('table', { className: 'glass-table' },
            e('thead', null, e('tr', null, e('th', null, 'Topic'), e('th', null, 'Type'))),
            e('tbody', null,
              topics.map(function(t, i) {
                return e('tr', { key: i },
                  e('td', { className: 'mono' }, t.name || t.topic || t),
                  e('td', { style: { fontSize: '10px', color: 'var(--text-dim)' } }, t.type || t.msg_type || '—')
                );
              })
            )
          )
    ),

    // Nodes
    e('div', { className: 'glass-card' },
      e('div', { style: { fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' } },
        'Nodes (' + nodes.length + ')'),
      nodes.length === 0
        ? e('div', { style: { color: 'var(--text-dim)', fontSize: '11px' } }, 'No nodes available')
        : e('div', null,
            nodes.map(function(n, i) {
              return e('div', { key: i, style: { fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--accent)', padding: '2px 0' } },
                typeof n === 'string' ? n : n.name || n.node || JSON.stringify(n)
              );
            })
          )
    )
  );
}

function IsaacTab() {
  var statusState = useState(null);
  var isaacStatus = statusState[0], setIsaacStatus = statusState[1];

  useEffect(function() {
    authFetch('/mc/api/isaac/status')
      .then(function(r) { return r.json(); })
      .then(setIsaacStatus)
      .catch(function() {});
  }, []);

  return e('div', { className: 'glass-card' },
    e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' } },
      e('div', { className: 'status-dot status-dot--' + (isaacStatus && isaacStatus.running ? 'online' : 'offline') }),
      e('div', { style: { fontSize: '12px', fontWeight: 600, color: 'var(--text-bright)' } }, 'Isaac Sim')
    ),
    isaacStatus
      ? e('div', { className: 'glass-log' },
          e('pre', null, JSON.stringify(isaacStatus, null, 2))
        )
      : e('div', { style: { color: 'var(--text-dim)', fontSize: '11px' } },
          'Isaac Sim status not available. Check /api/containers for container status.')
  );
}

export { InfraPage }
