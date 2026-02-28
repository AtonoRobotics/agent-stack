import React, { useState, useEffect, useRef } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { authFetch } from '../utils/authFetch'
import { parseCSV, computeVelocity } from '../utils/parseCSV'
import { Icon } from '../components/Icon'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'
import { MetricCard } from '../components/MetricCard'

var e = React.createElement;

function DemoPrereqBar(props) {
  var prereqs = props.prerequisites || {};
  return e('div', { className: 'demo-prereq-bar' },
    e('div', { className: 'demo-prereq-bar__item' },
      e('div', { className: 'demo-prereq-bar__dot demo-prereq-bar__dot--' + (prereqs.docker_available ? 'ok' : 'fail') }),
      e('span', null, prereqs.docker_available ? 'Docker ready' : 'Docker unavailable')
    ),
    e('div', { className: 'demo-prereq-bar__item' },
      e('div', { className: 'demo-prereq-bar__dot demo-prereq-bar__dot--' + (prereqs.gpu_available ? 'ok' : 'fail') }),
      e('span', null, prereqs.gpu_available ? 'GPU available' : 'GPU unavailable')
    ),
    prereqs.gpu_available ? e('div', { className: 'demo-prereq-bar__item', style: { fontFamily: 'var(--font-mono)', color: 'var(--accent)' } },
      'VRAM: ' + (prereqs.vram_free_mb || 0) + ' MB free'
    ) : null,
    props.runningDemo ? e('div', { className: 'demo-prereq-bar__item' },
      e(StatusDot, { status: 'busy' }),
      e('span', { style: { color: 'var(--info)' } }, 'Running: ' + props.runningDemo)
    ) : null
  );
}

function DemoMetric(props) {
  return e('div', { className: 'demo-card__metric' },
    e('div', { className: 'demo-card__metric-label' }, props.label),
    e('div', { className: 'demo-card__metric-value', style: props.color ? { color: props.color } : null }, props.value)
  );
}

function DemoLogViewer(props) {
  var logRef = useRef(null);
  useEffect(function() {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [props.lines]);

  if (!props.lines || props.lines.length === 0) return null;
  return e('div', { className: 'demo-log', ref: logRef },
    props.lines.map(function(line, i) {
      var cls = 'demo-log__line';
      if (/ERROR|FAILED|FAILURE/i.test(line)) cls += ' demo-log__line--error';
      else if (/SUCCESS|PLANNED|COMPLETE|OK/i.test(line)) cls += ' demo-log__line--success';
      return e('div', { key: i, className: cls }, line);
    })
  );
}

function DemoCard(props) {
  var demo = props.demo;
  var isRunning = props.runningDemo === demo.id;
  var canRun = props.canRun && !props.runningDemo;
  var thumbState = useState(null);
  var thumb = thumbState[0]; var setThumb = thumbState[1];

  // Load thumbnail as blob URL
  useEffect(function() {
    if (!demo.has_results || !demo.files) return;
    var imgFile = demo.files.find(function(f) { return f.type === 'image'; });
    if (!imgFile) return;
    authFetch('/api/demos/files/' + imgFile.filename).then(function(r) {
      return r.blob();
    }).then(function(blob) {
      setThumb(URL.createObjectURL(blob));
    }).catch(function() {});
  }, [demo.has_results]);

  var statusVariant = demo.status === 'completed' ? 'success' : demo.status === 'running' ? 'info' : demo.status === 'failed' ? 'danger' : 'neutral';

  // Extract metrics from last run
  var metrics = (demo.last_run && demo.last_run.metrics) || {};

  function renderMetrics() {
    if (demo.id === 'singularity') {
      return e('div', { className: 'demo-card__metrics' },
        e(DemoMetric, { label: 'Kinematic Min Manip', value: metrics.kinematic_min_manip != null ? metrics.kinematic_min_manip.toFixed(5) : '—', color: 'var(--danger)' }),
        e(DemoMetric, { label: 'cuRobo Min Manip', value: metrics.curobo_min_manip != null ? metrics.curobo_min_manip.toFixed(4) : '—', color: 'var(--success)' }),
        e(DemoMetric, { label: 'Singularity Frames', value: metrics.singularity_frames != null ? String(metrics.singularity_frames) : '—' }),
        e(DemoMetric, { label: 'Kinematic Failed', value: metrics.kinematic_failed ? 'YES' : metrics.kinematic_failed === false ? 'NO' : '—', color: metrics.kinematic_failed ? 'var(--danger)' : 'var(--success)' })
      );
    } else if (demo.id === 'velocity') {
      return e('div', { className: 'demo-card__metrics' },
        e(DemoMetric, { label: 'cuRobo Jerk', value: metrics.curobo_jerk_score != null ? metrics.curobo_jerk_score.toFixed(1) : '—', color: 'var(--success)' }),
        e(DemoMetric, { label: 'Kinematic Jerk', value: metrics.kinematic_jerk_score != null ? metrics.kinematic_jerk_score.toFixed(1) : '—', color: 'var(--danger)' }),
        e(DemoMetric, { label: 'cuRobo Path', value: metrics.curobo_path_length != null ? metrics.curobo_path_length.toFixed(3) + ' rad' : '—' }),
        e(DemoMetric, { label: 'Kinematic Path', value: metrics.kinematic_path_length != null ? metrics.kinematic_path_length.toFixed(3) + ' rad' : '—' })
      );
    } else if (demo.id === 'cartesian') {
      return e('div', { className: 'demo-card__metrics' },
        e(DemoMetric, { label: 'cuRobo Max Error', value: metrics.curobo_max_error != null ? (metrics.curobo_max_error * 1000).toFixed(1) + ' mm' : '—', color: 'var(--success)' }),
        e(DemoMetric, { label: 'Kinematic Max Error', value: metrics.kinematic_max_error != null ? (metrics.kinematic_max_error * 1000).toFixed(1) + ' mm' : '—', color: 'var(--danger)' }),
        e(DemoMetric, { label: 'cuRobo Avg Error', value: metrics.curobo_avg_error != null ? (metrics.curobo_avg_error * 1000).toFixed(1) + ' mm' : '—' }),
        e(DemoMetric, { label: 'Kinematic Avg Error', value: metrics.kinematic_avg_error != null ? (metrics.kinematic_avg_error * 1000).toFixed(1) + ' mm' : '—' })
      );
    }
    return null;
  }

  return e('div', { className: 'demo-card' + (isRunning ? ' demo-card--active' : '') },
    e('div', { className: 'demo-card__header' },
      e('span', { className: 'demo-card__title' }, demo.name),
      e('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
        isRunning ? e(DemoElapsedTimer, { startedAt: demo.last_run ? demo.last_run.started : null }) : null,
        e(Badge, { variant: statusVariant }, demo.status || 'idle')
      )
    ),
    e('div', { className: 'demo-card__desc' }, demo.description),
    e('div', { className: 'demo-card__thumb' },
      thumb ? e('img', { src: thumb, alt: demo.name }) : e('div', { className: 'demo-card__thumb--empty' }, isRunning ? 'Running...' : demo.has_results ? 'Loading...' : 'No results yet — run demo')
    ),
    renderMetrics(),
    e('div', { className: 'demo-card__actions' },
      isRunning
        ? e('button', { className: 'demo-btn demo-btn--stop', onClick: function() { props.onStop(demo.id); } }, 'Stop')
        : e('button', { className: 'demo-btn demo-btn--run', disabled: !canRun, onClick: function() { props.onRun(demo.id); } }, 'Run'),
      e('button', { className: 'demo-btn demo-btn--view', disabled: !demo.has_results && !isRunning, onClick: function() { props.onView(demo.id); } }, 'Details'),
      demo.has_csv ? e('button', { className: 'demo-btn demo-btn--download', onClick: function() {
        var csvFile = demo.files.find(function(f) { return f.type === 'csv'; });
        if (csvFile) {
          authFetch('/api/demos/files/' + csvFile.filename).then(function(r) { return r.blob(); }).then(function(blob) {
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a'); a.href = url; a.download = csvFile.filename; a.click();
            URL.revokeObjectURL(url);
          });
        }
      }}, 'CSV') : null
    )
  );
}

function DemoElapsedTimer(props) {
  var elapsedState = useState('');
  var elapsed = elapsedState[0]; var setElapsed = elapsedState[1];

  useEffect(function() {
    if (!props.startedAt) return;
    function tick() {
      var start = new Date(props.startedAt).getTime();
      var diff = Math.floor((Date.now() - start) / 1000);
      var m = Math.floor(diff / 60); var s = diff % 60;
      setElapsed((m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s);
    }
    tick();
    var id = setInterval(tick, 1000);
    return function() { clearInterval(id); };
  }, [props.startedAt]);

  if (!elapsed) return null;
  return e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--accent)', fontWeight: 600 } }, elapsed);
}

function DemoConfirmDialog(props) {
  if (!props.demoId) return null;
  var name = props.demoName || props.demoId;
  return e('div', { style: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center', animation: 'fadeIn 0.2s ease'
  }, onClick: props.onCancel },
    e('div', { style: {
      background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
      padding: '24px', maxWidth: '400px', width: '90%'
    }, onClick: function(ev) { ev.stopPropagation(); } },
      e('h3', { style: { fontSize: '16px', fontWeight: 700, marginBottom: '12px' } }, 'Launch Demo'),
      e('p', { style: { fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '8px' } },
        'Run "' + name + '" in headless mode? This will use GPU resources and may take several minutes.'
      ),
      e('p', { style: { fontSize: '11px', color: 'var(--warning)', marginBottom: '20px' } },
        'Only one demo can run at a time. Ensure no other GPU-heavy processes are active.'
      ),
      e('div', { style: { display: 'flex', gap: '8px', justifyContent: 'flex-end' } },
        e('button', { className: 'demo-btn demo-btn--view', onClick: props.onCancel }, 'Cancel'),
        e('button', { className: 'demo-btn demo-btn--run', onClick: function() { props.onConfirm(props.demoId); } }, 'Launch')
      )
    )
  );
}

function DemoDetailPanel(props) {
  var demo = props.demo;
  var isRunning = props.isRunning;
  var imgState = useState(null);
  var imgUrl = imgState[0]; var setImgUrl = imgState[1];
  var csvState = useState(null);
  var csvData = csvState[0]; var setCsvData = csvState[1];

  // Load full-size image
  useEffect(function() {
    if (!demo || !demo.files) return;
    var imgFile = demo.files.find(function(f) { return f.type === 'image'; });
    if (!imgFile) return;
    authFetch('/api/demos/files/' + imgFile.filename).then(function(r) { return r.blob(); })
      .then(function(blob) { setImgUrl(URL.createObjectURL(blob)); }).catch(function() {});
  }, [demo]);

  // Load CSV for velocity demo
  useEffect(function() {
    if (!demo || demo.id !== 'velocity') return;
    Promise.all([
      authFetch('/api/demos/files/curobo_trajectory.csv').then(function(r) { return r.text(); }),
      authFetch('/api/demos/files/kinematic_trajectory.csv').then(function(r) { return r.text(); }),
    ]).then(function(results) {
      var curobo = parseCSV(results[0]);
      var kinematic = parseCSV(results[1]);
      setCsvData({ curobo: curobo, kinematic: kinematic });
    }).catch(function() {});
  }, [demo]);

  if (!demo) return null;

  var metrics = (demo.last_run && demo.last_run.metrics) || {};

  function renderDemoMetrics() {
    if (demo.id === 'singularity') {
      return e('div', { className: 'demo-card__metrics', style: { marginBottom: '20px' } },
        e(DemoMetric, { label: 'Kinematic Min Manip', value: metrics.kinematic_min_manip != null ? metrics.kinematic_min_manip.toFixed(5) : '—', color: 'var(--danger)' }),
        e(DemoMetric, { label: 'cuRobo Min Manip', value: metrics.curobo_min_manip != null ? metrics.curobo_min_manip.toFixed(4) : '—', color: 'var(--success)' }),
        e(DemoMetric, { label: 'Singularity Frames', value: metrics.singularity_frames != null ? String(metrics.singularity_frames) : '—' }),
        e(DemoMetric, { label: 'Kinematic Failed', value: metrics.kinematic_failed ? 'YES' : metrics.kinematic_failed === false ? 'NO' : '—', color: metrics.kinematic_failed ? 'var(--danger)' : 'var(--success)' })
      );
    } else if (demo.id === 'velocity') {
      return e('div', { className: 'demo-card__metrics', style: { marginBottom: '20px' } },
        e(DemoMetric, { label: 'cuRobo Jerk Score', value: metrics.curobo_jerk_score != null ? metrics.curobo_jerk_score.toFixed(1) : '—', color: 'var(--success)' }),
        e(DemoMetric, { label: 'Kinematic Jerk Score', value: metrics.kinematic_jerk_score != null ? metrics.kinematic_jerk_score.toFixed(1) : '—', color: 'var(--danger)' }),
        e(DemoMetric, { label: 'cuRobo Path Length', value: metrics.curobo_path_length != null ? metrics.curobo_path_length.toFixed(3) + ' rad' : '—' }),
        e(DemoMetric, { label: 'Kinematic Path Length', value: metrics.kinematic_path_length != null ? metrics.kinematic_path_length.toFixed(3) + ' rad' : '—' })
      );
    } else if (demo.id === 'cartesian') {
      return e('div', { className: 'demo-card__metrics', style: { marginBottom: '20px' } },
        e(DemoMetric, { label: 'cuRobo Max Error', value: metrics.curobo_max_error != null ? (metrics.curobo_max_error * 1000).toFixed(1) + ' mm' : '—', color: 'var(--success)' }),
        e(DemoMetric, { label: 'Kinematic Max Error', value: metrics.kinematic_max_error != null ? (metrics.kinematic_max_error * 1000).toFixed(1) + ' mm' : '—', color: 'var(--danger)' }),
        e(DemoMetric, { label: 'cuRobo Avg Error', value: metrics.curobo_avg_error != null ? (metrics.curobo_avg_error * 1000).toFixed(1) + ' mm' : '—' }),
        e(DemoMetric, { label: 'Kinematic Avg Error', value: metrics.kinematic_avg_error != null ? (metrics.kinematic_avg_error * 1000).toFixed(1) + ' mm' : '—' })
      );
    }
    return null;
  }

  function renderVelocityCharts() {
    if (!csvData) return e('div', { style: { color: 'var(--text-secondary)', padding: '20px', textAlign: 'center' } }, 'Loading CSV data...');

    var joints = ['joint1_pos', 'joint2_pos', 'joint3_pos', 'joint4_pos', 'joint5_pos', 'joint6_pos'];
    var jointLabels = ['Joint 1', 'Joint 2', 'Joint 3', 'Joint 4', 'Joint 5', 'Joint 6'];

    return e('div', null,
      e('h3', { style: { fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase' } }, 'Interactive Velocity Profiles'),
      e('div', { className: 'velocity-charts' },
        joints.map(function(jKey, ji) {
          var cVel = computeVelocity(csvData.curobo.data, jKey, 'timestamp');
          var kVel = computeVelocity(csvData.kinematic.data, jKey, 'timestamp');
          var maxLen = Math.max(csvData.curobo.data.length, csvData.kinematic.data.length);
          var chartData = [];
          for (var i = 0; i < maxLen; i++) {
            var row = { idx: i };
            if (i < csvData.curobo.data.length) {
              row.curobo_pos = csvData.curobo.data[i][jKey];
              row.curobo_vel = cVel[i];
              row.time = csvData.curobo.data[i].timestamp;
            }
            if (i < csvData.kinematic.data.length) {
              row.kinematic_pos = csvData.kinematic.data[i][jKey];
              row.kinematic_vel = kVel[i];
            }
            chartData.push(row);
          }

          return e('div', { key: jKey, className: 'card', style: { padding: '12px' } },
            e('div', { style: { fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', marginBottom: '8px', color: 'var(--text-secondary)' } }, jointLabels[ji]),
            e(ResponsiveContainer, { width: '100%', height: 140 },
              e(LineChart, { data: chartData, margin: { top: 4, right: 8, bottom: 4, left: -10 } },
                e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#333' }),
                e(XAxis, { dataKey: 'time', tick: { fontSize: 9, fill: '#666' }, tickFormatter: function(v) { return v != null ? v.toFixed(1) + 's' : ''; } }),
                e(YAxis, { tick: { fontSize: 9, fill: '#666' } }),
                e(Tooltip, { contentStyle: { background: '#1A1A1A', border: '1px solid #333', fontSize: '10px' },
                  formatter: function(v, name) { return [v != null ? v.toFixed(4) : '—', name]; } }),
                e(Line, { type: 'monotone', dataKey: 'curobo_vel', stroke: '#2171B5', strokeWidth: 1.5, dot: false, name: 'cuRobo' }),
                e(Line, { type: 'monotone', dataKey: 'kinematic_vel', stroke: '#CB181D', strokeWidth: 1.5, dot: false, name: 'Kinematic' })
              )
            )
          );
        })
      )
    );
  }

  return e('div', { className: 'demo-detail' },
    e('div', { className: 'demo-detail__header' },
      e('div', null,
        e('span', { className: 'demo-detail__title' }, demo.name),
        isRunning ? e('span', { style: { marginLeft: '12px' } },
          e(Badge, { variant: 'info' }, 'RUNNING'),
          e('span', { style: { marginLeft: '8px' } }, e(DemoElapsedTimer, { startedAt: demo.last_run ? demo.last_run.started : null }))
        ) : demo.last_run ? e('span', { style: { marginLeft: '12px', fontSize: '11px', color: 'var(--text-secondary)' } },
          'Last run: ' + (demo.last_run.started || '').replace('T', ' ').substring(0, 19)
        ) : null
      ),
      e('div', { style: { display: 'flex', gap: '8px' } },
        isRunning
          ? e('button', { className: 'demo-btn demo-btn--stop', onClick: function() { props.onStop(demo.id); } }, 'Stop')
          : props.canRun && !props.runningDemo
            ? e('button', { className: 'demo-btn demo-btn--run', onClick: function() { props.onRun(demo.id); } }, 'Run')
            : null,
        e('button', { className: 'demo-btn demo-btn--view', onClick: props.onClose }, 'Close')
      )
    ),

    // Stats row
    demo.last_run ? e('div', { className: 'demo-detail__stats' },
      e(MetricCard, { label: 'Status', value: demo.last_run.status || '—', borderColor: demo.last_run.status === 'completed' ? 'var(--success)' : demo.last_run.status === 'running' ? 'var(--info)' : 'var(--danger)' }),
      e(MetricCard, { label: 'Mode', value: demo.last_run.mode || 'headless', borderColor: 'var(--info)' }),
      e(MetricCard, { label: 'Exit Code', value: demo.last_run.exit_code != null ? String(demo.last_run.exit_code) : isRunning ? '...' : '—', borderColor: demo.last_run.exit_code === 0 ? 'var(--success)' : 'var(--warning)' }),
      e(MetricCard, { label: 'Launched By', value: demo.last_run.launched_by || '—', borderColor: 'var(--accent)' })
    ) : null,

    // Demo-specific metrics
    Object.keys(metrics).length > 0 ? e('div', null,
      e('h3', { style: { fontSize: '14px', fontWeight: 700, marginBottom: '12px', textTransform: 'uppercase' } }, 'Performance Metrics'),
      renderDemoMetrics()
    ) : null,

    // Full-size result image
    imgUrl ? e('img', { src: imgUrl, alt: demo.name + ' results', className: 'demo-detail__image' }) : null,

    // Interactive charts for velocity demo
    demo.id === 'velocity' && demo.has_results ? renderVelocityCharts() : null,

    // Live log when running (from WebSocket)
    isRunning && props.logLines && props.logLines.length > 0 ? e('div', null,
      e('h3', { style: { fontSize: '14px', fontWeight: 700, marginTop: '20px', marginBottom: '8px', textTransform: 'uppercase' } },
        Icon('activity'), ' Live Output'
      ),
      e(DemoLogViewer, { lines: props.logLines })
    ) : null,

    // Log from last run (static)
    !isRunning && demo.last_run && demo.last_run.log_tail ? e('div', null,
      e('h3', { style: { fontSize: '14px', fontWeight: 700, marginTop: '20px', marginBottom: '8px', textTransform: 'uppercase' } }, 'Execution Log'),
      e(DemoLogViewer, { lines: demo.last_run.log_tail.split('\n') })
    ) : null
  );
}

function DemosPage() {
  var demosState = useState(null);
  var demos = demosState[0]; var setDemos = demosState[1];
  var prereqState = useState({});
  var prereqs = prereqState[0]; var setPrereqs = prereqState[1];
  var runningState = useState(null);
  var runningDemo = runningState[0]; var setRunningDemo = runningState[1];
  var detailState = useState(null);
  var selectedDetail = detailState[0]; var setSelectedDetail = detailState[1];
  var logState = useState([]);
  var logLines = logState[0]; var setLogLines = logState[1];
  var errorState = useState(null);
  var error = errorState[0]; var setError = errorState[1];
  var confirmState = useState(null);
  var confirmDemoId = confirmState[0]; var setConfirmDemoId = confirmState[1];

  function fetchDemos() {
    authFetch('/api/demos').then(function(r) { return r.json(); }).then(function(data) {
      setDemos(data.demos);
      setPrereqs(data.prerequisites);
      var running = data.demos.find(function(d) { return d.status === 'running'; });
      setRunningDemo(running ? running.id : null);
      // Auto-update selected detail panel with fresh data
      setSelectedDetail(function(prev) {
        if (!prev) return null;
        var updated = data.demos.find(function(d) { return d.id === prev.id; });
        return updated || prev;
      });
    }).catch(function(e) { setError('Failed to load demos: ' + e.message); });
  }

  useEffect(function() {
    fetchDemos();
    var interval = setInterval(fetchDemos, 5000);
    return function() { clearInterval(interval); };
  }, []);

  // WebSocket for live log when demo is running
  useEffect(function() {
    if (!runningDemo) return;
    var token = localStorage.getItem('mc_token');
    if (!token) return;
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = proto + '//' + location.host + '/ws/demo/' + runningDemo + '?token=' + token;
    var ws = new WebSocket(wsUrl);
    ws.onmessage = function(ev) {
      try {
        var msg = JSON.parse(ev.data);
        if (msg.type === 'demo_log') {
          setLogLines(function(prev) { return prev.concat([msg.line]).slice(-500); });
        } else if (msg.type === 'demo_status') {
          fetchDemos();
          if (msg.status !== 'running') { setRunningDemo(null); }
        }
      } catch(e) {}
    };
    return function() { ws.close(); };
  }, [runningDemo]);

  function handleRunRequest(demoId) {
    setConfirmDemoId(demoId);
  }

  function handleRunConfirmed(demoId) {
    setConfirmDemoId(null);
    setLogLines([]);
    authFetch('/api/demos/' + demoId + '/run', { method: 'POST' }).then(function(r) {
      if (r.status === 202) {
        setRunningDemo(demoId);
        fetchDemos();
      } else {
        return r.json().then(function(d) { setError(d.detail || 'Failed to start'); });
      }
    }).catch(function(e) { setError(e.message); });
  }

  function handleStop(demoId) {
    authFetch('/api/demos/' + demoId + '/stop', { method: 'DELETE' }).then(function() {
      setRunningDemo(null);
      fetchDemos();
    }).catch(function(e) { setError(e.message); });
  }

  function handleView(demoId) {
    var demo = demos.find(function(d) { return d.id === demoId; });
    setSelectedDetail(demo);
  }

  var canRun = prereqs.docker_available && prereqs.gpu_available;
  var confirmDemoName = confirmDemoId && demos ? (demos.find(function(d) { return d.id === confirmDemoId; }) || {}).name : '';

  return e('div', null,
    // Confirm dialog
    e(DemoConfirmDialog, {
      demoId: confirmDemoId, demoName: confirmDemoName,
      onConfirm: handleRunConfirmed, onCancel: function() { setConfirmDemoId(null); }
    }),

    e('div', { className: 'page-header' },
      e('div', null,
        e('h1', { className: 'page-header__title' }, 'DEMOS'),
        e('p', { className: 'page-header__subtitle' }, 'Isaac Sim demonstrations — cuRobo vs standard kinematics')
      )
    ),

    e(DemoPrereqBar, { prerequisites: prereqs, runningDemo: runningDemo }),

    error ? e('div', { style: { padding: '12px 16px', background: 'rgba(244,67,54,0.1)', border: '1px solid var(--danger)', borderRadius: 'var(--radius)', marginBottom: '16px', fontSize: '12px', color: 'var(--danger)' } },
      error,
      e('button', { style: { marginLeft: '12px', background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', textDecoration: 'underline' }, onClick: function() { setError(null); } }, 'dismiss')
    ) : null,

    // Detail view or card grid
    selectedDetail
      ? e(DemoDetailPanel, {
          demo: selectedDetail,
          isRunning: runningDemo === selectedDetail.id,
          runningDemo: runningDemo,
          canRun: canRun,
          logLines: runningDemo === selectedDetail.id ? logLines : null,
          onRun: handleRunRequest,
          onStop: handleStop,
          onClose: function() { setSelectedDetail(null); }
        })
      : demos ? e('div', { className: 'demo-grid' },
          demos.map(function(demo) {
            return e(DemoCard, {
              key: demo.id, demo: demo, canRun: canRun, runningDemo: runningDemo,
              onRun: handleRunRequest, onStop: handleStop, onView: handleView,
            });
          })
        ) : e('div', { style: { textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' } }, 'Loading demos...'),

    // Live log viewer when running (only show if detail panel is NOT open for the running demo)
    runningDemo && !(selectedDetail && selectedDetail.id === runningDemo) ? e('div', { style: { marginTop: '20px' } },
      e('h3', { style: { fontSize: '14px', fontWeight: 700, marginBottom: '8px', textTransform: 'uppercase' } },
        Icon('activity'), ' Live Output — ' + runningDemo
      ),
      e(DemoLogViewer, { lines: logLines })
    ) : null
  );
}

export { DemosPage }
