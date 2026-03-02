import React, { useState, useEffect } from 'react'
import { authFetch } from '../utils/authFetch'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'
import { GaugeBar } from '../components/GaugeBar'
import { fmtDate } from '../utils/fmt'

var e = React.createElement;

function FleetPage() {
  var fleetState = useState(null);
  var fleetData = fleetState[0];
  var setFleetData = fleetState[1];
  var loadingState = useState(true);
  var loading = loadingState[0];
  var setLoading = loadingState[1];

  useEffect(function() {
    authFetch('/api/fleet').then(function(r) { return r.json(); }).then(function(d) { setFleetData(d); setLoading(false); }).catch(function() { setLoading(false); });
    var interval = setInterval(function() {
      authFetch('/api/fleet').then(function(r) { return r.json(); }).then(setFleetData).catch(function() {});
    }, 15000);
    return function() { clearInterval(interval); };
  }, []);

  var displayMachines = fleetData ? fleetData.map(function(m) {
    var met = m.metrics || {};
    var hasMetrics = met.ram_total != null && met.ram_total > 0;
    return {
      id: m.name, name: m.name, os: (m.config && m.config.os) || 'N/A', arch: (m.config && m.config.arch) || 'N/A',
      status: met.status === 'online' && hasMetrics ? 'online' : met.status === 'error' ? 'offline' : hasMetrics ? 'warning' : 'offline',
      hasMetrics: hasMetrics,
      gpu: met.gpu_util, gpuTemp: met.temp_c,
      vramUsed: met.gpu_vram_used, vramTotal: met.gpu_vram_total,
      ram: met.ram_total, ramUsed: met.ram_used,
      disk: met.disk_total > 0 ? Math.round(met.disk_used / met.disk_total * 100) : null,
      diskUsed: met.disk_used, diskTotal: met.disk_total,
      gpu_label: (m.config && m.config.gpu) || 'N/A',
      role: (m.config && m.config.role) || '',
      roleDesc: (m.config && m.config.description) || ''
    };
  }) : [];

  if (loading) {
    return e('div', null,
      e('div', { className: 'glass-page-header' },
        e('h1', null, 'Fleet'),
        e('p', null, 'Loading fleet data...')
      )
    );
  }

  var onlineCount = displayMachines.filter(function(m) { return m.hasMetrics; }).length;

  return e('div', null,
    e('div', { className: 'glass-page-header' },
      e('h1', null, 'Fleet'),
      e('p', null, displayMachines.length + ' machines registered \u00b7 ' + onlineCount + ' reporting')
    ),
    displayMachines.length === 0
      ? e('div', { className: 'glass-card', style: { textAlign: 'center', padding: '40px' } },
          e('div', { style: { fontSize: '13px', color: 'var(--text-dim)' } }, 'No machines registered in fleet configuration.')
        )
      : e('div', { className: 'glass-card-grid' },
          displayMachines.map(function(m) {
            var tempColor = m.gpuTemp != null && m.gpuTemp > 75 ? 'var(--danger)' : m.gpuTemp != null && m.gpuTemp > 60 ? 'var(--warning)' : 'var(--success)';

            return e('div', { key: m.id, className: 'glass-card', style: { opacity: m.hasMetrics ? 1 : 0.6 } },
              e('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' } },
                e('div', null,
                  e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' } },
                    e(StatusDot, { status: m.status, large: true }),
                    e('span', { style: { fontSize: '15px', fontWeight: 700 } }, m.name)
                  ),
                  e('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap' } },
                    e(Badge, { variant: 'neutral' }, m.os),
                    e(Badge, { variant: 'accent' }, m.arch),
                    m.role === 'compute_node' ? e(Badge, { variant: 'info' }, 'COMPUTE NODE') : null
                  )
                ),
                m.hasMetrics
                  ? e('div', { style: { textAlign: 'right' } },
                      e('div', { style: { fontFamily: 'var(--font-mono)', fontSize: '22px', fontWeight: 700, color: tempColor } }, Math.round(m.gpuTemp || 0) + '\u00B0'),
                      e('div', { style: { fontSize: '9px', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px' } }, 'GPU Temp')
                    )
                  : e('div', { style: { textAlign: 'right' } },
                      e('div', { style: { fontFamily: 'var(--font-mono)', fontSize: '14px', fontWeight: 500, color: 'var(--text-dim)' } }, 'No data'),
                      e('div', { style: { fontSize: '9px', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px' } }, 'unreachable')
                    )
              ),

              m.hasMetrics
                ? e(React.Fragment, null,
                    e(GaugeBar, { label: 'GPU', value: Math.round(m.gpu || 0), detail: (m.vramUsed || 0).toFixed(1) + '/' + (m.vramTotal || 0).toFixed(1) + 'GB VRAM' }),
                    e(GaugeBar, { label: 'RAM', value: m.ram > 0 ? Math.round((m.ramUsed || 0) / m.ram * 100) : 0, detail: (m.ramUsed || 0).toFixed(1) + '/' + (m.ram || 0).toFixed(1) + 'GB' }),
                    e(GaugeBar, { label: 'Disk', value: m.disk || 0, detail: Math.round(m.diskUsed || 0) + '/' + Math.round(m.diskTotal || 0) + 'GB', color: 'blue' })
                  )
                : e('div', { style: { padding: '16px 0', textAlign: 'center', color: 'var(--text-dim)', fontSize: '12px', borderTop: '1px solid rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.03)' } },
                    'Machine registered but not reporting metrics.',
                    e('br', null),
                    e('span', { style: { fontSize: '10px', color: 'var(--text-dim)' } }, 'Config: ' + m.gpu_label + ' \u00b7 ' + ((m.config && m.config.ram) || m.arch))
                  ),

              m.hasMetrics
                ? e('div', { style: { display: 'flex', justifyContent: 'space-between', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.03)', fontSize: '11px', color: 'var(--text-secondary)' } },
                    e('span', null, m.gpu_label),
                    e('span', null, m.os)
                  )
                : null
            );
          })
        ),

    e(ComputeHistory)
  );
}

function ComputeHistory() {
  var openState = useState(false);
  var open = openState[0], setOpen = openState[1];
  var dataState = useState([]);
  var data = dataState[0], setData = dataState[1];
  var loadedState = useState(false);
  var loaded = loadedState[0], setLoaded = loadedState[1];

  function toggle() {
    if (!open && !loaded) {
      authFetch('/mc/api/compute/snapshots?limit=20')
        .then(function(r) { return r.json(); })
        .then(function(d) { setData(d.items || d); setLoaded(true); })
        .catch(function() { setLoaded(true); });
    }
    setOpen(!open);
  }

  return e('div', { style: { marginTop: '16px' } },
    e('button', {
      className: 'glass-btn',
      onClick: toggle,
      style: { display: 'flex', alignItems: 'center', gap: '6px', marginBottom: open ? '8px' : 0 }
    },
      e('span', { style: { transform: open ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.15s', display: 'inline-block', fontSize: '10px' } }, '\u25BC'),
      'Compute History'
    ),
    open ? e('table', { className: 'glass-table' },
      e('thead', null,
        e('tr', null,
          e('th', null, 'Host'),
          e('th', null, 'Timestamp'),
          e('th', null, 'CPU %'),
          e('th', null, 'RAM'),
          e('th', null, 'Disk')
        )
      ),
      e('tbody', null,
        data.length === 0
          ? e('tr', null, e('td', { colSpan: 5, style: { textAlign: 'center', color: 'var(--text-dim)', padding: '20px' } }, loaded ? 'No snapshots' : 'Loading...'))
          : data.map(function(s, i) {
              return e('tr', { key: i },
                e('td', { className: 'mono' }, s.host || '—'),
                e('td', null, fmtDate(s.created_at || s.timestamp)),
                e('td', { className: 'mono' }, s.cpu_percent != null ? s.cpu_percent.toFixed(1) + '%' : '—'),
                e('td', { className: 'mono' }, s.ram_used_gb != null && s.ram_total_gb != null ? s.ram_used_gb.toFixed(1) + '/' + s.ram_total_gb.toFixed(1) + 'GB' : '—'),
                e('td', { className: 'mono' }, s.disk_used_gb != null && s.disk_total_gb != null ? Math.round(s.disk_used_gb) + '/' + Math.round(s.disk_total_gb) + 'GB' : '—')
              );
            })
      )
    ) : null
  );
}

export { FleetPage }
