import React, { useState, useEffect, useRef } from 'react'
import {
  LineChart, Line, ResponsiveContainer
} from 'recharts'
import * as d3 from 'd3'
import * as THREE from 'three'
import { authFetch } from '../utils/authFetch'
import { RosViewer } from '../components/RosViewer'
import { getRos, getStatus, onStatusChange, reconnect as rosReconnect } from '../utils/rosConnection'
import { NavContext } from '../contexts/NavContext'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'

var e = React.createElement;

// =========================================================================
// PAGE: ROBOT COCKPIT
// =========================================================================

// SVG Arc Gauge component for joint display
function JointArcGauge(props) {
  var value = props.value || 0;
  var min = props.min || -3.14;
  var max = props.max || 3.14;
  var label = props.label || '';
  var size = props.size || 80;
  var r = (size - 8) / 2;
  var cx = size / 2;
  var cy = size / 2;

  var range = max - min;
  var normalized = Math.max(0, Math.min(1, (value - min) / range));
  var startAngle = -135 * (Math.PI / 180);
  var endAngle = 135 * (Math.PI / 180);
  var sweep = endAngle - startAngle;
  var angle = startAngle + normalized * sweep;

  // Track arc
  var trackD = describeArc(cx, cy, r, startAngle, endAngle);
  // Value arc
  var valueD = describeArc(cx, cy, r, startAngle, angle);
  // Needle endpoint
  var nx = cx + (r - 6) * Math.cos(angle);
  var ny = cy + (r - 6) * Math.sin(angle);

  var pct = normalized * 100;
  var color = pct > 85 ? 'var(--danger)' : pct > 60 ? 'var(--warning)' : 'var(--accent)';
  var degValue = (value * 180 / Math.PI).toFixed(1);

  return e('div', { className: 'joint-gauge' },
    e('div', { className: 'joint-gauge__label' }, label),
    e('svg', { width: size, height: size * 0.75, viewBox: '0 0 ' + size + ' ' + (size * 0.75) },
      e('path', { d: trackD, fill: 'none', stroke: 'var(--border)', strokeWidth: 4, strokeLinecap: 'round' }),
      e('path', { d: valueD, fill: 'none', stroke: color, strokeWidth: 4, strokeLinecap: 'round' }),
      e('circle', { cx: nx, cy: ny, r: 3, fill: color }),
      e('text', { x: cx, y: cy + 2, textAnchor: 'middle', fill: 'var(--text)', fontSize: '12', fontFamily: 'var(--font-mono)', fontWeight: 700 }, degValue + '\u00B0')
    ),
    e('div', { className: 'joint-gauge__sub' },
      (min * 180 / Math.PI).toFixed(0) + '\u00B0 / ' + (max * 180 / Math.PI).toFixed(0) + '\u00B0'
    )
  );
}

function describeArc(cx, cy, r, startAngle, endAngle) {
  var x1 = cx + r * Math.cos(startAngle);
  var y1 = cy + r * Math.sin(startAngle);
  var x2 = cx + r * Math.cos(endAngle);
  var y2 = cy + r * Math.sin(endAngle);
  var largeArc = (endAngle - startAngle > Math.PI) ? 1 : 0;
  return 'M ' + x1 + ' ' + y1 + ' A ' + r + ' ' + r + ' 0 ' + largeArc + ' 1 ' + x2 + ' ' + y2;
}

// Payload Configuration Panel
function PayloadConfigPanel(props) {
  var onPayloadChange = props.onPayloadChange || function() {};
  var camerasState = useState(null);
  var cameras = camerasState[0]; var setCameras = camerasState[1];
  var lensesState = useState(null);
  var lenses = lensesState[0]; var setLenses = lensesState[1];
  var accsState = useState(null);
  var accs = accsState[0]; var setAccs = accsState[1];
  var camState = useState('alexa_mini');
  var selCam = camState[0]; var setSelCam = camState[1];
  var lensState = useState('zeiss_mp_35');
  var selLens = lensState[0]; var setSelLens = lensState[1];
  var accState = useState(['preston_mdr4']);
  var selAccs = accState[0]; var setSelAccs = accState[1];
  var resultState = useState(null);
  var result = resultState[0]; var setResult = resultState[1];
  var presetsState = useState([]);
  var presets = presetsState[0]; var setPresets = presetsState[1];
  var presetState = useState(null);
  var activePreset = presetState[0]; var setActivePreset = presetState[1];
  var saveState = useState(false);
  var showSave = saveState[0]; var setShowSave = saveState[1];
  var nameState = useState('');
  var saveName = nameState[0]; var setSaveName = nameState[1];
  var appliedState = useState('');
  var appliedMsg = appliedState[0]; var setAppliedMsg = appliedState[1];

  // Fetch data on mount
  useEffect(function() {
    authFetch('/api/cameras').then(function(r) { return r.json(); }).then(setCameras).catch(function() {});
    authFetch('/api/lenses').then(function(r) { return r.json(); }).then(setLenses).catch(function() {});
    authFetch('/api/accessories').then(function(r) { return r.json(); }).then(setAccs).catch(function() {});
    authFetch('/api/payload/presets').then(function(r) { return r.json(); }).then(setPresets).catch(function() {});
  }, []);

  // Recalculate payload when selection changes
  useEffect(function() {
    authFetch('/api/payload/calculate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_id: selCam, lens_id: selLens, accessory_ids: selAccs })
    }).then(function(r) { return r.json(); }).then(function(d) {
      setResult(d);
      if (cameras && lenses) {
        var cam = cameras[selCam];
        var lens = lenses[selLens];
        if (cam && lens) {
          onPayloadChange({
            camera_name: cam.name, lens_name: lens.name,
            dims_mm: cam.dims_mm, lens_length_mm: lens.length_mm,
            lens_diameter_mm: lens.diameter_mm || 95, total_mass: d.total_mass_kg
          });
        }
      }
    }).catch(function() {});
  }, [selCam, selLens, selAccs, cameras, lenses]);

  function toggleAcc(id) {
    setSelAccs(function(prev) {
      return prev.indexOf(id) >= 0 ? prev.filter(function(a) { return a !== id; }) : prev.concat([id]);
    });
  }

  function loadPreset(name) {
    var p = presets.find(function(pr) { return pr.name === name; });
    if (p) {
      setSelCam(p.camera_id); setSelLens(p.lens_id); setSelAccs(p.accessory_ids);
      setActivePreset(name);
    }
  }

  function savePreset() {
    if (!saveName) return;
    authFetch('/api/payload/presets', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: saveName, camera_id: selCam, lens_id: selLens, accessory_ids: selAccs })
    }).then(function(r) { return r.json(); }).then(function() {
      authFetch('/api/payload/presets').then(function(r) { return r.json(); }).then(setPresets);
      setSaveName(''); setShowSave(false); setActivePreset(saveName);
    }).catch(function() {});
  }

  function applyPayload() {
    authFetch('/api/payload/apply', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_id: selCam, lens_id: selLens, accessory_ids: selAccs })
    }).then(function() {
      setAppliedMsg('Applied \u2713');
      setTimeout(function() { setAppliedMsg(''); }, 2000);
    }).catch(function() {});
  }

  if (!cameras || !lenses || !accs) {
    return e('div', { style: { background: '#141414', border: '1px solid #2a2a2a', borderLeft: '3px solid #E8A020', borderRadius: '8px', padding: '16px', color: '#808080', fontSize: '12px' } }, 'Loading payload data...');
  }

  // Group items by manufacturer
  function groupByMfr(items) {
    var groups = {};
    Object.keys(items).forEach(function(id) {
      var mfr = items[id].manufacturer || 'Other';
      if (!groups[mfr]) groups[mfr] = [];
      groups[mfr].push({ id: id, data: items[id] });
    });
    return groups;
  }

  var camGroups = groupByMfr(cameras);
  var lensGroups = groupByMfr(lenses);

  var ss = { label: { fontSize: '10px', textTransform: 'uppercase', letterSpacing: '1px', color: '#808080', marginBottom: '6px', display: 'block' } };
  var selectStyle = { width: '100%', padding: '8px 12px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#e0e0e0', fontSize: '13px', outline: 'none' };

  var massPct = result ? (result.total_mass_kg / 10) * 100 : 0;
  var barColor = massPct < 80 ? '#4CAF50' : massPct < 95 ? '#E8A020' : '#f44336';

  return e('div', { style: { background: '#141414', border: '1px solid #2a2a2a', borderLeft: '3px solid #E8A020', borderRadius: '8px', padding: '16px', overflow: 'auto', maxHeight: '100%' } },
    e('div', { style: { fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', color: '#E8A020', marginBottom: '16px' } }, 'PAYLOAD CONFIGURATION'),

    // Camera selector
    e('div', { style: { marginBottom: '12px' } },
      e('label', { style: ss.label }, 'CAMERA BODY'),
      e('select', { value: selCam, onChange: function(ev) { setSelCam(ev.target.value); setActivePreset(null); }, style: selectStyle },
        Object.keys(camGroups).map(function(mfr) {
          return e('optgroup', { key: mfr, label: mfr },
            camGroups[mfr].map(function(item) {
              return e('option', { key: item.id, value: item.id }, item.data.name + ' (' + item.data.mass_kg + 'kg)');
            })
          );
        })
      )
    ),

    // Lens selector
    e('div', { style: { marginBottom: '12px' } },
      e('label', { style: ss.label }, 'LENS'),
      e('select', { value: selLens, onChange: function(ev) { setSelLens(ev.target.value); setActivePreset(null); }, style: selectStyle },
        Object.keys(lensGroups).map(function(mfr) {
          return e('optgroup', { key: mfr, label: mfr },
            lensGroups[mfr].map(function(item) {
              return e('option', { key: item.id, value: item.id }, item.data.name + ' (' + item.data.mass_kg + 'kg)');
            })
          );
        })
      )
    ),

    // Accessories
    e('div', { style: { marginBottom: '12px' } },
      e('label', { style: ss.label }, 'ACCESSORIES'),
      Object.keys(accs).map(function(id) {
        var a = accs[id];
        return e('label', { key: id, style: { fontSize: '12px', color: '#b0b0b0', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', cursor: 'pointer' } },
          e('input', { type: 'checkbox', checked: selAccs.indexOf(id) >= 0, onChange: function() { toggleAcc(id); }, style: { accentColor: '#E8A020' } }),
          a.name + ' (' + a.mass_kg + 'kg)'
        );
      })
    ),

    // Payload summary
    result ? e('div', { style: { marginBottom: '12px', padding: '10px', background: '#0f0f0f', borderRadius: '4px' } },
      e('label', { style: ss.label }, 'PAYLOAD SUMMARY'),
      e('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#e0e0e0', marginBottom: '4px' } },
        e('span', null, 'Total Mass: ' + result.total_mass_kg.toFixed(1) + ' kg'),
        e('span', { style: { color: '#808080' } }, 'Limit: 10.0 kg')
      ),
      e('div', { style: { height: '6px', background: '#1a1a1a', borderRadius: '3px', overflow: 'hidden', marginBottom: '8px' } },
        e('div', { style: { height: '100%', width: Math.min(massPct, 100) + '%', background: barColor, borderRadius: '3px', transition: 'width 300ms' } })
      ),
      e('div', { style: { fontSize: '12px', color: '#b0b0b0' } },
        e('div', null, 'CoM Offset: X: ' + (result.com_offset_mm.x || 0).toFixed(1) + 'mm  Y: ' + (result.com_offset_mm.y || 0).toFixed(1) + 'mm  Z: ' + (result.com_offset_mm.z || 0).toFixed(1) + 'mm'),
        e('div', { style: { marginTop: '4px', color: result.within_limits ? '#4CAF50' : '#f44336' } },
          result.within_limits ? '\u2713 Within limits' : '\u2717 Exceeds limits')
      )
    ) : null,

    // Joint torque margins
    result && result.joint_torque_margins ? e('div', { style: { marginBottom: '12px' } },
      e('label', { style: ss.label }, 'JOINT TORQUE MARGINS'),
      ['J1', 'J2', 'J3', 'J4', 'J5', 'J6'].map(function(jn) {
        var pct = result.joint_torque_margins[jn] || 0;
        var jColor = pct < 80 ? '#4CAF50' : pct < 95 ? '#E8A020' : '#f44336';
        var icon = pct < 80 ? '\u2713' : pct < 95 ? '\u26A0' : '\u2717';
        return e('div', { key: jn, style: { display: 'flex', alignItems: 'center', marginBottom: '3px', fontSize: '11px' } },
          e('span', { style: { width: '22px', color: '#808080' } }, jn),
          e('div', { style: { flex: 1, height: '4px', background: '#1a1a1a', borderRadius: '2px', overflow: 'hidden', margin: '0 6px' } },
            e('div', { style: { height: '100%', width: Math.min(pct, 100) + '%', background: jColor, borderRadius: '2px' } })
          ),
          e('span', { style: { width: '36px', textAlign: 'right', color: '#b0b0b0' } }, pct.toFixed(0) + '%'),
          e('span', { style: { width: '16px', textAlign: 'center', color: jColor, marginLeft: '4px' } }, icon)
        );
      })
    ) : null,

    // Warnings
    result && result.warnings && result.warnings.length > 0 ? e('div', { style: { marginBottom: '12px' } },
      result.warnings.map(function(w, i) {
        return e('div', { key: i, style: { fontSize: '11px', color: '#E8A020', marginBottom: '2px' } }, '\u26A0 ' + w);
      })
    ) : null,

    // Presets
    e('div', { style: { marginBottom: '12px' } },
      e('label', { style: ss.label }, 'PRESETS'),
      e('select', { value: activePreset || '', onChange: function(ev) { if (ev.target.value) loadPreset(ev.target.value); }, style: selectStyle },
        e('option', { value: '' }, '-- Load Preset --'),
        presets.map(function(p) {
          return e('option', { key: p.name, value: p.name }, p.name);
        })
      ),
      activePreset ? e('div', { style: { fontSize: '11px', color: '#E8A020', marginTop: '4px' } }, 'Active: ' + activePreset) : null,
      e('div', { style: { display: 'flex', gap: '8px', marginTop: '8px' } },
        e('button', { onClick: function() { setShowSave(!showSave); }, style: { flex: 1, padding: '6px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#b0b0b0', fontSize: '11px', cursor: 'pointer' } }, 'Save as Preset')
      ),
      showSave ? e('div', { style: { display: 'flex', gap: '6px', marginTop: '8px' } },
        e('input', { type: 'text', value: saveName, onChange: function(ev) { setSaveName(ev.target.value); }, placeholder: 'Preset name', style: { flex: 1, padding: '6px', background: '#1a1a1a', border: '1px solid #333', borderRadius: '4px', color: '#e0e0e0', fontSize: '12px', outline: 'none' } }),
        e('button', { onClick: savePreset, style: { padding: '6px 12px', background: '#E8A020', color: '#0a0a0a', border: 'none', borderRadius: '4px', fontSize: '11px', fontWeight: 700, cursor: 'pointer' } }, 'Save'),
        e('button', { onClick: function() { setShowSave(false); }, style: { padding: '6px 8px', background: '#333', color: '#b0b0b0', border: 'none', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' } }, '\u2717')
      ) : null
    ),

    // Apply button
    e('button', { onClick: applyPayload, style: { width: '100%', padding: '10px', background: '#E8A020', color: '#0a0a0a', border: 'none', borderRadius: '4px', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase', cursor: 'pointer', marginTop: '4px' } }, 'Apply to Simulation'),
    appliedMsg ? e('div', { style: { textAlign: 'center', color: '#4CAF50', fontSize: '12px', marginTop: '6px' } }, appliedMsg) : null
  );
}

// Joint States Card with 6 arc gauges
function JointStatesCard(props) {
  var joints = props.joints || [];
  var urdfChain = props.urdfChain || [];

  return e('div', { className: 'cockpit-card' },
    e('div', { className: 'cockpit-card__title' }, 'Joint States'),
    e('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px' } },
      [0,1,2,3,4,5].map(function(i) {
        var j = joints[i] || {};
        var chain = urdfChain[i] || {};
        var lim = chain.limit || {};
        return e(JointArcGauge, {
          key: i,
          label: 'J' + (i + 1),
          value: j.position || 0,
          min: lim.lower || -3.14,
          max: lim.upper || 3.14,
          size: 80
        });
      })
    )
  );
}

// Robot Mode Card
function RobotModeCard(props) {
  var mode = props.mode || 'unknown';
  var online = props.online;
  var modeColor = mode === 'idle' ? 'var(--success)' : mode === 'running' ? 'var(--accent)' : mode === 'error' ? 'var(--danger)' : 'var(--text-dim)';

  return e('div', { className: 'cockpit-card' },
    e('div', { className: 'cockpit-card__title' }, 'Robot Mode'),
    e('div', { style: { textAlign: 'center', padding: '16px 0' } },
      e('div', { style: { fontSize: '32px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: modeColor, textTransform: 'uppercase' } },
        online ? mode : 'OFFLINE'
      ),
      e('div', { style: { marginTop: '8px' } },
        e(StatusDot, { status: online ? 'online' : 'offline', large: true })
      )
    )
  );
}

// End Effector Card
function EndEffectorCard(props) {
  var pose = props.pose;
  if (!pose) {
    return e('div', { className: 'cockpit-card' },
      e('div', { className: 'cockpit-card__title' }, 'End Effector'),
      e('div', { style: { textAlign: 'center', padding: '20px', color: 'var(--text-dim)', fontSize: '12px' } }, 'No pose data')
    );
  }
  var fields = [
    { label: 'X', value: pose.x, unit: 'm' },
    { label: 'Y', value: pose.y, unit: 'm' },
    { label: 'Z', value: pose.z, unit: 'm' },
    { label: 'Rx', value: pose.rx, unit: '\u00B0' },
    { label: 'Ry', value: pose.ry, unit: '\u00B0' },
    { label: 'Rz', value: pose.rz, unit: '\u00B0' },
  ];
  return e('div', { className: 'cockpit-card' },
    e('div', { className: 'cockpit-card__title' }, 'End Effector Pose'),
    e('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' } },
      fields.map(function(f) {
        return e('div', { key: f.label, style: { textAlign: 'center', padding: '6px 0' } },
          e('div', { style: { fontSize: '10px', color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '4px' } }, f.label),
          e('div', { style: { fontFamily: 'var(--font-mono)', fontSize: '14px', fontWeight: 700 } },
            (typeof f.value === 'number' ? f.value.toFixed(4) : '--') + ' ' + f.unit
          )
        );
      })
    )
  );
}

// Topics Card
function CockpitTopicsCard(props) {
  var topics = props.topics || [];
  return e('div', { className: 'cockpit-card' },
    e('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' } },
      e('div', { className: 'cockpit-card__title', style: { marginBottom: 0 } }, 'Topics'),
      e(Badge, { variant: topics.length > 0 ? 'success' : 'neutral' }, topics.length + ' active')
    ),
    e('div', { className: 'topic-monitor' },
      topics.length === 0
        ? e('div', { style: { textAlign: 'center', padding: '20px', color: 'var(--text-dim)', fontSize: '12px' } }, 'No topics detected')
        : topics.slice(0, 30).map(function(t) {
            return e('div', { key: t.name, className: 'topic-monitor__item' },
              e('span', { className: 'topic-monitor__name' }, t.name),
              e('span', { className: 'topic-monitor__type' }, t.type || '')
            );
          })
    )
  );
}

// Controllers Card
function CockpitControllersCard(props) {
  var controllers = props.controllers || [];
  return e('div', { className: 'cockpit-card' },
    e('div', { className: 'cockpit-card__title' }, 'Controllers'),
    controllers.length === 0
      ? e('div', { style: { textAlign: 'center', padding: '20px', color: 'var(--text-dim)', fontSize: '12px' } }, 'No controllers detected')
      : controllers.map(function(c) {
          var stateColor = c.state === 'active' ? 'var(--success)' : c.state === 'inactive' ? 'var(--text-dim)' : 'var(--warning)';
          return e('div', { key: c.name, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 0', borderBottom: '1px solid var(--border)' } },
            e('span', { style: { width: '8px', height: '8px', borderRadius: '50%', background: stateColor, flexShrink: 0 } }),
            e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', flex: 1 } }, c.name),
            e(Badge, { variant: c.state === 'active' ? 'success' : 'neutral' }, c.state)
          );
        })
  );
}

// Diagnostics Card
function CockpitDiagnosticsCard(props) {
  var diagnostics = props.diagnostics || [];
  return e('div', { className: 'cockpit-card' },
    e('div', { className: 'cockpit-card__title' }, 'Diagnostics'),
    diagnostics.length === 0
      ? e('div', { style: { textAlign: 'center', padding: '20px', color: 'var(--text-dim)', fontSize: '12px' } }, 'No diagnostics')
      : diagnostics.map(function(d, i) {
          var lvl = d.level === 0 ? 'success' : d.level === 1 ? 'warning' : 'danger';
          return e('div', { key: i, style: { display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 0', borderBottom: '1px solid var(--border)' } },
            e(Badge, { variant: lvl }, d.level === 0 ? 'OK' : d.level === 1 ? 'WARN' : 'ERR'),
            e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', flex: 1 } }, d.name),
            e('span', { style: { fontSize: '10px', color: 'var(--text-dim)' } }, d.message)
          );
        })
  );
}

// Three.js 3D Robot Viewer — loads actual CR10 STL meshes with FK chain
function ThreeJSViewer(props) {
  var containerRef = useRef(null);
  var sceneRef = useRef(null);
  var rendererRef = useRef(null);
  var jointGroupsRef = useRef([]);
  var targetAnglesRef = useRef([0, 0, 0, 0, 0, 0]);
  var frameRef = useRef(null);
  var workspaceRef = useRef(null);
  var axesRef = useRef(null);
  var cameraPayloadRef = useRef(null);

  var loadState = useState(true);
  var loading = loadState[0];
  var setLoading = loadState[1];
  var loadMsgState = useState('Loading CR10 meshes...');
  var loadMsg = loadMsgState[0];
  var setLoadMsg = loadMsgState[1];
  var viewState = useState('home');
  var currentView = viewState[0];
  var setCurrentView = viewState[1];
  var wsState = useState(true);
  var showWorkspace = wsState[0];
  var setShowWorkspace = wsState[1];
  var axState = useState(true);
  var showAxesToggle = axState[0];
  var setShowAxesToggle = axState[1];

  var online = props.online;
  var joints = props.joints || [];
  var cameraPayload = props.cameraPayload;

  // CR10 URDF joint configs
  var JOINTS = [
    { origin: [0, 0, 0.1765], axis: 'z' },   // J1 base rotation
    { origin: [0, 0.0055, 0], axis: 'y' },    // J2 shoulder
    { origin: [0, 0, 0.607], axis: 'y' },     // J3 elbow
    { origin: [0, 0, 0.568], axis: 'x' },     // J4 wrist 1
    { origin: [0, 0, 0.191], axis: 'y' },     // J5 wrist 2
    { origin: [0, 0, 0.125], axis: 'x' },     // J6 flange
  ];

  // Binary STL parser
  function parseSTLBinary(buffer) {
    var dv = new DataView(buffer);
    var offset = 80;
    var triCount = dv.getUint32(offset, true);
    offset += 4;
    var positions = new Float32Array(triCount * 9);
    var normals = new Float32Array(triCount * 9);
    for (var i = 0; i < triCount; i++) {
      var nx = dv.getFloat32(offset, true);
      var ny = dv.getFloat32(offset + 4, true);
      var nz = dv.getFloat32(offset + 8, true);
      offset += 12;
      for (var j = 0; j < 3; j++) {
        var idx = i * 9 + j * 3;
        positions[idx] = dv.getFloat32(offset, true);
        positions[idx + 1] = dv.getFloat32(offset + 4, true);
        positions[idx + 2] = dv.getFloat32(offset + 8, true);
        normals[idx] = nx; normals[idx + 1] = ny; normals[idx + 2] = nz;
        offset += 12;
      }
      offset += 2;
    }
    var geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
    return geom;
  }

  // Initialize scene once
  useEffect(function() {
    if (!containerRef.current || typeof THREE === 'undefined') return;
    var container = containerRef.current;
    var w = container.clientWidth;
    var h = container.clientHeight;

    try {
      var tc = document.createElement('canvas');
      var gl = tc.getContext('webgl') || tc.getContext('experimental-webgl');
      if (!gl) throw new Error('No WebGL');
    } catch(ex) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#808080;">3D requires WebGL</div>';
      return;
    }

    try {

    // Scene
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0F0F0F);
    scene.fog = new THREE.Fog(0x0F0F0F, 5, 12);
    sceneRef.current = scene;

    // Camera
    var camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);

    // Renderer
    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lights
    scene.add(new THREE.AmbientLight(0x404040, 0.5));
    var dirLight = new THREE.DirectionalLight(0xFFFFFF, 0.8);
    dirLight.position.set(5, 10, 5);
    dirLight.castShadow = true;
    scene.add(dirLight);
    var rimLight = new THREE.DirectionalLight(0xE8A020, 0.3);
    rimLight.position.set(-2, 3, -2);
    scene.add(rimLight);

    // Grid & Axes
    scene.add(new THREE.GridHelper(4, 20, 0x2E2E2E, 0x1A1A1A));
    var axesHelper = new THREE.AxesHelper(0.3);
    axesHelper.position.set(-1.5, 0, -1.5);
    scene.add(axesHelper);
    axesRef.current = axesHelper;

    // Workspace sphere at J1 height
    var wsSphereGeom = new THREE.SphereGeometry(1.3, 32, 16);
    var wsSphereMat = new THREE.MeshBasicMaterial({ color: 0xE8A020, wireframe: true, transparent: true, opacity: 0.05 });
    var wsSphere = new THREE.Mesh(wsSphereGeom, wsSphereMat);
    wsSphere.position.set(0, 0.1765, 0);
    scene.add(wsSphere);
    workspaceRef.current = wsSphere;

    // Materials
    var linkMat = new THREE.MeshPhongMaterial({ color: 0x2A2A2A, specular: 0x444444, shininess: 30 });
    var baseMat = new THREE.MeshPhongMaterial({ color: 0xE8A020, emissive: 0x4A3000, shininess: 60 });
    var eeMat = new THREE.MeshPhongMaterial({ color: 0xE8A020, emissive: 0x6A4000, shininess: 80 });
    var matMap = [baseMat, linkMat, linkMat, linkMat, linkMat, linkMat, eeMat];

    // Root group: convert URDF Z-up to Three.js Y-up
    var rootGroup = new THREE.Group();
    rootGroup.rotation.x = -Math.PI / 2;
    scene.add(rootGroup);

    var jointGroups = [];

    // Fallback: cylinder primitives if STL loading fails
    function buildFallbackRobot() {
      var linkDefs = [
        { h: 0.08, r: 0.12 },
        { h: 0.10, r: 0.055 }, { h: 0.607, r: 0.045 },
        { h: 0.568, r: 0.04 }, { h: 0.191, r: 0.035 },
        { h: 0.125, r: 0.03 }, { h: 0.1084, r: 0.025 },
      ];
      // Base cylinder
      var baseGeom = new THREE.CylinderGeometry(0.12, 0.14, 0.08, 32);
      var baseCyl = new THREE.Mesh(baseGeom, baseMat);
      baseCyl.rotation.x = Math.PI / 2;
      baseCyl.position.set(0, 0, 0.04);
      rootGroup.add(baseCyl);

      var parent = rootGroup;
      for (var i = 0; i < JOINTS.length; i++) {
        var jg = new THREE.Group();
        jg.position.set(JOINTS[i].origin[0], JOINTS[i].origin[1], JOINTS[i].origin[2]);
        parent.add(jg);
        jointGroups.push(jg);
        var cyl = new THREE.CylinderGeometry(linkDefs[i + 1].r, linkDefs[i + 1].r, linkDefs[i + 1].h, 16);
        var mesh = new THREE.Mesh(cyl, matMap[i + 1]);
        mesh.rotation.x = Math.PI / 2;
        mesh.position.set(0, 0, linkDefs[i + 1].h / 2);
        jg.add(mesh);
        parent = jg;
      }
      jointGroupsRef.current = jointGroups;
    }

    // Build kinematic chain from loaded STL geometries
    function buildKinematicChain(meshList, geometries) {
      var linkNames = ['base_link', 'link_1', 'link_2', 'link_3', 'link_4', 'link_5', 'link_6'];
      if (geometries.base_link) {
        var bm = new THREE.Mesh(geometries.base_link, matMap[0]);
        rootGroup.add(bm);
      }
      var parent = rootGroup;
      for (var i = 0; i < JOINTS.length; i++) {
        var jg = new THREE.Group();
        jg.position.set(JOINTS[i].origin[0], JOINTS[i].origin[1], JOINTS[i].origin[2]);
        parent.add(jg);
        jointGroups.push(jg);
        var linkName = linkNames[i + 1];
        if (geometries[linkName]) {
          var lm = new THREE.Mesh(geometries[linkName], matMap[i + 1]);
          jg.add(lm);
        }
        parent = jg;
      }
      jointGroupsRef.current = jointGroups;
      // End effector cone
      var eeGeom = new THREE.ConeGeometry(0.015, 0.04, 8);
      var eeCone = new THREE.Mesh(eeGeom, eeMat);
      eeCone.position.set(0, 0, 0.06);
      parent.add(eeCone);
    }

    // Load STL meshes
    (function loadMeshes() {
      authFetch('/api/robot/dobot_cr10/meshes')
        .then(function(r) { return r.json(); })
        .then(function(meshList) {
          setLoadMsg('Loading STL files... 0/' + meshList.length);
          var loaded = 0;
          var meshGeometries = {};
          function loadNext(idx) {
            if (idx >= meshList.length) {
              buildKinematicChain(meshList, meshGeometries);
              setLoading(false);
              return;
            }
            var m = meshList[idx];
            authFetch('/static/meshes/' + m.visual_path)
              .then(function(r) { return r.arrayBuffer(); })
              .then(function(buf) {
                meshGeometries[m.link_name] = parseSTLBinary(buf);
                loaded++;
                setLoadMsg('Loading STL files... ' + loaded + '/' + meshList.length);
                loadNext(idx + 1);
              })
              .catch(function(err) {
                console.error('Failed to load ' + m.visual_path, err);
                loaded++;
                loadNext(idx + 1);
              });
          }
          loadNext(0);
        })
        .catch(function(err) {
          console.error('Mesh metadata fetch failed, using fallback', err);
          setLoadMsg('Using fallback geometry...');
          buildFallbackRobot();
          setLoading(false);
        });
    })();

    // Orbit controls
    var isDragging = false;
    var prevMouse = { x: 0, y: 0 };
    var spherical = { theta: Math.PI / 4, phi: Math.PI / 4, radius: 3 };
    function updateCam() {
      camera.position.x = spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.position.y = spherical.radius * Math.cos(spherical.phi);
      camera.position.z = spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.lookAt(0, 0.5, 0);
    }
    updateCam();
    container._spherical = spherical;
    container._updateCamera = updateCam;

    function onDown(ev) { isDragging = true; prevMouse = { x: ev.clientX, y: ev.clientY }; }
    function onUp() { isDragging = false; }
    function onMove(ev) {
      if (!isDragging) return;
      var dx = ev.clientX - prevMouse.x;
      var dy = ev.clientY - prevMouse.y;
      spherical.theta -= dx * 0.005;
      spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi + dy * 0.005));
      updateCam();
      prevMouse = { x: ev.clientX, y: ev.clientY };
    }
    function onWheel(ev) {
      ev.preventDefault();
      spherical.radius = Math.max(0.3, Math.min(5, spherical.radius + ev.deltaY * 0.003));
      updateCam();
    }
    renderer.domElement.addEventListener('mousedown', onDown);
    renderer.domElement.addEventListener('mouseup', onUp);
    renderer.domElement.addEventListener('mousemove', onMove);
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false });

    // Render loop (30fps cap)
    var lastTime = 0;
    function animate(time) {
      frameRef.current = requestAnimationFrame(animate);
      if (document.hidden) return;
      if (time - lastTime < 33) return;
      lastTime = time;
      // Lerp joint angles
      var jgs = jointGroupsRef.current;
      var targets = targetAnglesRef.current;
      for (var j = 0; j < jgs.length; j++) {
        var target = (targets[j] || 0) * Math.PI / 180;
        var ax = JOINTS[j].axis;
        if (ax === 'z') { jgs[j].rotation.z += (target - jgs[j].rotation.z) * 0.15; }
        else if (ax === 'y') { jgs[j].rotation.y += (target - jgs[j].rotation.y) * 0.15; }
        else if (ax === 'x') { jgs[j].rotation.x += (target - jgs[j].rotation.x) * 0.15; }
      }
      renderer.render(scene, camera);
    }
    animate(0);

    // Resize
    function onResize() {
      var nw = container.clientWidth;
      var nh = container.clientHeight;
      if (nw === 0 || nh === 0) return;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    }
    window.addEventListener('resize', onResize);

    return function() {
      window.removeEventListener('resize', onResize);
      renderer.domElement.removeEventListener('mousedown', onDown);
      renderer.domElement.removeEventListener('mouseup', onUp);
      renderer.domElement.removeEventListener('mousemove', onMove);
      renderer.domElement.removeEventListener('wheel', onWheel);
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      if (renderer.domElement.parentNode) container.removeChild(renderer.domElement);
      scene.traverse(function(obj) {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach(function(m) { m.dispose(); });
          else obj.material.dispose();
        }
      });
      renderer.dispose();
    };

    } catch(_webglErr) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#808080;font-size:12px;text-align:center;padding:20px;">3D Error<br><span style="font-size:10px;color:#555;">' + _webglErr.message + '</span></div>';
      return;
    }
  }, []);

  // Update target joint angles from props
  useEffect(function() {
    if (!joints.length) return;
    var angles = [];
    for (var i = 0; i < 6; i++) {
      angles.push(joints[i] ? (joints[i].position || 0) : 0);
    }
    targetAnglesRef.current = angles;
  }, [joints]);

  // Toggle workspace visibility
  useEffect(function() {
    if (workspaceRef.current) workspaceRef.current.visible = showWorkspace;
  }, [showWorkspace]);

  // Toggle axes visibility
  useEffect(function() {
    if (axesRef.current) axesRef.current.visible = showAxesToggle;
  }, [showAxesToggle]);

  // Camera payload visualization at end effector
  useEffect(function() {
    if (cameraPayloadRef.current) {
      var old = cameraPayloadRef.current;
      if (old.parent) old.parent.remove(old);
      old.traverse(function(c) { if (c.geometry) c.geometry.dispose(); if (c.material) c.material.dispose(); });
      cameraPayloadRef.current = null;
    }
    if (!cameraPayload || !jointGroupsRef.current.length) return;
    var eeGroup = jointGroupsRef.current[jointGroupsRef.current.length - 1];
    var payloadGroup = new THREE.Group();
    payloadGroup.position.set(0, 0, 0.11);
    // Camera body
    var cw = (cameraPayload.dims_mm ? cameraPayload.dims_mm.w : 114) / 1000;
    var ch = (cameraPayload.dims_mm ? cameraPayload.dims_mm.h : 58) / 1000;
    var cl = (cameraPayload.dims_mm ? cameraPayload.dims_mm.l : 130) / 1000;
    var camGeom = new THREE.BoxGeometry(cw, ch, cl);
    var camMat = new THREE.MeshPhongMaterial({ color: 0x1A3A5A, specular: 0x333366, shininess: 40 });
    var camMesh = new THREE.Mesh(camGeom, camMat);
    camMesh.position.set(0, 0, cl / 2);
    payloadGroup.add(camMesh);
    // Lens
    var ll = (cameraPayload.lens_length_mm || 128) / 1000;
    var ld = (cameraPayload.lens_diameter_mm || 95) / 1000;
    var lensGeom = new THREE.CylinderGeometry(ld / 2, ld / 2, ll, 16);
    var lensMat = new THREE.MeshPhongMaterial({ color: 0x2A2A2A, specular: 0x333333, shininess: 30 });
    var lensMesh = new THREE.Mesh(lensGeom, lensMat);
    lensMesh.rotation.x = Math.PI / 2;
    lensMesh.position.set(0, 0, cl + ll / 2);
    payloadGroup.add(lensMesh);
    eeGroup.add(payloadGroup);
    cameraPayloadRef.current = payloadGroup;
  }, [cameraPayload]);

  function setView(name) {
    setCurrentView(name);
    var sp = containerRef.current && containerRef.current._spherical;
    var upd = containerRef.current && containerRef.current._updateCamera;
    if (!sp || !upd) return;
    if (name === 'home') { sp.theta = Math.PI / 4; sp.phi = Math.PI / 4; sp.radius = 3; }
    else if (name === 'front') { sp.theta = 0; sp.phi = Math.PI / 3; sp.radius = 3; }
    else if (name === 'side') { sp.theta = Math.PI / 2; sp.phi = Math.PI / 3; sp.radius = 3; }
    else if (name === 'top') { sp.theta = 0; sp.phi = 0.15; sp.radius = 3.5; }
    else if (name === 'iso') { sp.theta = Math.PI / 5; sp.phi = Math.PI / 5; sp.radius = 2.5; }
    upd();
  }

  return e('div', { className: 'threejs-viewer', ref: containerRef },
    !online ? e('div', { className: 'threejs-viewer__offline' },
      e('div', { className: 'threejs-viewer__offline-text' }, 'ROBOT OFFLINE')
    ) : null,
    loading ? e('div', { style: { position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', color: '#E8A020', textAlign: 'center', zIndex: 10 } },
      e('div', { style: { fontSize: '32px', animation: 'pulse 2s infinite' } }, '\u03B1'),
      e('div', { style: { fontSize: '12px', color: '#808080', marginTop: '8px' } }, loadMsg)
    ) : null,
    e('div', { className: 'threejs-viewer__overlay' },
      ['home', 'front', 'side', 'top', 'iso'].map(function(v) {
        return e('button', {
          key: v,
          className: 'threejs-viewer__btn' + (currentView === v ? ' threejs-viewer__btn--active' : ''),
          onClick: function() { setView(v); }
        }, v === 'home' ? '\u2299' : v.toUpperCase());
      })
    ),
    e('div', { style: { position: 'absolute', bottom: '8px', right: '8px', display: 'flex', flexDirection: 'column', gap: '4px', zIndex: 10 } },
      e('label', { style: { fontSize: '10px', color: '#808080', cursor: 'pointer', display: 'flex', alignItems: 'center' } },
        e('input', { type: 'checkbox', checked: showWorkspace, onChange: function() { setShowWorkspace(function(p) { return !p; }); }, style: { marginRight: '4px' } }), 'Workspace'),
      e('label', { style: { fontSize: '10px', color: '#808080', cursor: 'pointer', display: 'flex', alignItems: 'center' } },
        e('input', { type: 'checkbox', checked: showAxesToggle, onChange: function() { setShowAxesToggle(function(p) { return !p; }); }, style: { marginRight: '4px' } }), 'Axes')
    )
  );
}

// Simulation Mode Panel
function SimulationModePanel() {
  var stState = useState({ running: false, mode: 'STANDALONE', uptime: 0, pid: null });
  var simStatus = stState[0]; var setSimStatus = stState[1];

  function fetchStatus() {
    authFetch('/api/simulation/status')
      .then(function(r) { return r.json(); })
      .then(setSimStatus)
      .catch(function() {});
  }

  useEffect(function() {
    fetchStatus();
    var iv = setInterval(fetchStatus, 3000);
    return function() { clearInterval(iv); };
  }, []);

  function changeMode(mode) {
    authFetch('/api/robot/dobot_cr10/twin/mode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: mode })
    }).then(function() { fetchStatus(); }).catch(function() {});
  }

  function toggleSim() {
    var endpoint = simStatus.running ? '/api/simulation/stop' : '/api/simulation/start';
    authFetch(endpoint, { method: 'POST' }).then(function() { fetchStatus(); }).catch(function() {});
  }

  var modeDescs = {
    STANDALONE: 'Simulation running independently',
    MIRROR: 'Mirroring real robot joint states',
    SHADOW: 'Predicting motion 500ms ahead',
    COMMAND: 'Simulation commanding real robot'
  };

  var upStr = '';
  if (simStatus.running && simStatus.uptime) {
    var m = Math.floor(simStatus.uptime / 60);
    var s = Math.floor(simStatus.uptime % 60);
    upStr = m + 'm ' + s + 's';
  }

  var ss = { label: { fontSize: '10px', textTransform: 'uppercase', letterSpacing: '1px', color: '#808080' } };

  return e('div', { style: { background: '#141414', border: '1px solid #2a2a2a', borderLeft: '3px solid #E8A020', borderRadius: '8px', padding: '16px' } },
    e('div', { style: { fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', color: '#E8A020', marginBottom: '12px' } }, 'SIMULATION MODE'),

    // Mode buttons
    e('div', { style: { display: 'flex', gap: '6px', marginBottom: '8px' } },
      ['STANDALONE', 'MIRROR', 'SHADOW', 'COMMAND'].map(function(mode) {
        var active = simStatus.mode === mode;
        return e('button', {
          key: mode, onClick: function() { changeMode(mode); },
          style: { flex: 1, padding: '8px 4px', borderRadius: '4px', fontSize: '10px', fontWeight: 700,
            textTransform: 'uppercase', cursor: 'pointer', border: active ? 'none' : '1px solid #333',
            background: active ? '#E8A020' : '#1a1a1a', color: active ? '#0a0a0a' : '#808080', transition: 'all 150ms' }
        }, mode);
      })
    ),

    // Mode description
    e('div', { style: { fontSize: '11px', color: '#808080', marginBottom: '12px' } }, modeDescs[simStatus.mode] || ''),

    // Status indicators
    e('div', { style: { display: 'flex', gap: '16px', marginBottom: '12px', fontSize: '11px' } },
      e('div', { style: { display: 'flex', alignItems: 'center', gap: '4px' } },
        e('span', { style: { display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: simStatus.running ? '#4CAF50' : '#555' } }),
        e('span', { style: { color: simStatus.running ? '#4CAF50' : '#808080' } }, simStatus.running ? 'RUNNING' : 'STOPPED')
      ),
      e('div', { style: { display: 'flex', alignItems: 'center', gap: '4px' } },
        e('span', { style: { display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: '#555' } }),
        e('span', { style: { color: '#808080' } }, 'OFFLINE')
      ),
      upStr ? e('div', { style: { color: '#b0b0b0' } }, 'Uptime: ' + upStr) : null
    ),

    // Start/Stop button
    e('button', {
      onClick: toggleSim,
      style: { width: '100%', padding: '10px', fontWeight: 700, fontSize: '12px', textTransform: 'uppercase',
        border: 'none', borderRadius: '4px', cursor: 'pointer',
        background: simStatus.running ? '#f44336' : '#E8A020',
        color: simStatus.running ? '#fff' : '#0a0a0a' }
    }, simStatus.running ? '\u25A0 Stop Simulation' : '\u25B6 Start Simulation')
  );
}

// =========================================================================
// D3 Node Graph helpers (duplicated from RobotROS2Tab for independence)
// =========================================================================
var KEY_TOPICS = ['/joint_states', '/tf', '/tf_static', '/robot_description', '/diagnostics'];
var NODE_ICONS = {
  'robot_state_publisher': '\uD83E\uDD16',
  'joint_state_publisher': '\u2699\uFE0F',
  'controller_manager': '\uD83C\uDFAE',
  'ros2_control_node': '\uD83D\uDD27',
  'rviz': '\uD83D\uDC41\uFE0F'
};

function getNodeIcon(nodeId) {
  var name = nodeId.replace(/^\//, '');
  for (var key in NODE_ICONS) {
    if (name.indexOf(key) >= 0) return NODE_ICONS[key];
  }
  return '\u25CF';
}

function isKeyTopic(topicId) {
  return KEY_TOPICS.indexOf(topicId) >= 0;
}

function renderD3Graph(svgEl, data, opts) {
  var svg = d3.select(svgEl);
  svg.selectAll('*').remove();

  var width = svgEl.clientWidth || 800;
  var height = svgEl.clientHeight || 500;

  // Build visible node/edge lists
  var visibleNodes = data.nodes.slice();
  var visibleEdges = data.edges.slice();

  if (opts.showTopics) {
    visibleNodes = visibleNodes.concat(data.topics.map(function(t) { return Object.assign({}, t); }));
  }
  if (opts.showServices) {
    visibleNodes = visibleNodes.concat(data.services.map(function(s) { return Object.assign({}, s); }));
  }

  // Filter by text
  if (opts.filterText) {
    var ft = opts.filterText.toLowerCase();
    var matchIds = {};
    visibleNodes.forEach(function(n) {
      if (n.id.toLowerCase().indexOf(ft) >= 0) matchIds[n.id] = true;
    });
    // Also include nodes connected to matched nodes
    visibleEdges.forEach(function(ed) {
      if (matchIds[ed.source] || matchIds[ed.target]) {
        matchIds[ed.source] = true;
        matchIds[ed.target] = true;
      }
    });
    visibleNodes = visibleNodes.filter(function(n) { return matchIds[n.id]; });
  }

  // Only edges with both endpoints visible
  var nodeIdSet = {};
  visibleNodes.forEach(function(n) { nodeIdSet[n.id] = true; });
  visibleEdges = visibleEdges.filter(function(ed) {
    return nodeIdSet[ed.source] && nodeIdSet[ed.target];
  });

  if (visibleNodes.length === 0) return;

  // Defs: arrow markers
  var defs = svg.append('defs');
  var markerColors = { publishes: '#E8A020', subscribes: '#26A69A', serves: '#AB47BC' };
  Object.keys(markerColors).forEach(function(type) {
    defs.append('marker')
      .attr('id', 'arrow-' + type)
      .attr('viewBox', '0 0 10 6').attr('refX', 10).attr('refY', 3)
      .attr('markerWidth', 8).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,3 L0,6 Z').attr('fill', markerColors[type]);
  });

  // Zoom
  var g = svg.append('g').attr('class', 'zoom-group');
  var zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', function(event) {
      g.attr('transform', event.transform);
      opts.transformRef.current = event.transform;
      updateMinimap();
    });
  svg.call(zoom);

  // Restore previous transform
  if (opts.transformRef.current) {
    svg.call(zoom.transform, opts.transformRef.current);
  }

  // Force simulation
  var simNodes = visibleNodes.map(function(n) { return Object.assign({}, n); });
  var simEdges = visibleEdges.map(function(ed) { return { source: ed.source, target: ed.target, type: ed.type }; });

  var simulation = d3.forceSimulation(simNodes)
    .force('link', d3.forceLink(simEdges).id(function(d) { return d.id; }).distance(140))
    .force('charge', d3.forceManyBody().strength(-350))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(50))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05));

  opts.simRef.current = simulation;

  // Pre-tick for stable layout
  simulation.alpha(1);
  for (var i = 0; i < 300; i++) simulation.tick();
  simulation.alpha(0).stop();

  // Edges
  var edgeGroup = g.append('g').attr('class', 'edges');
  var links = edgeGroup.selectAll('path')
    .data(simEdges).enter().append('path')
    .attr('stroke', function(d) { return markerColors[d.type] || '#555'; })
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .attr('opacity', 0.5)
    .attr('marker-end', function(d) { return 'url(#arrow-' + d.type + ')'; });

  // Nodes
  var nodeGroup = g.append('g').attr('class', 'nodes');
  var nodeGs = nodeGroup.selectAll('g')
    .data(simNodes).enter().append('g')
    .attr('cursor', 'pointer')
    .call(d3.drag()
      .on('start', function(event, d) { d.fx = d.x; d.fy = d.y; })
      .on('drag', function(event, d) { d.fx = event.x; d.fy = event.y; updatePositions(); })
      .on('end', function(event, d) { d.fx = null; d.fy = null; })
    );

  // Draw shapes per type
  nodeGs.each(function(d) {
    var el = d3.select(this);
    if (d.type === 'node') {
      // Rounded rect with left accent bar
      el.append('rect')
        .attr('rx', 6).attr('ry', 6)
        .attr('width', 160).attr('height', 36)
        .attr('x', -80).attr('y', -18)
        .attr('fill', '#242424').attr('stroke', '#2E2E2E').attr('stroke-width', 1);
      // Left accent bar
      el.append('rect')
        .attr('width', 3).attr('height', 28)
        .attr('x', -80).attr('y', -14)
        .attr('rx', 1.5).attr('fill', '#E8A020');
      // Icon
      el.append('text')
        .attr('x', -68).attr('dy', '0.35em')
        .attr('font-size', '12px')
        .text(getNodeIcon(d.id));
      // Label
      el.append('text')
        .attr('x', -54).attr('dy', '0.35em')
        .attr('fill', '#E0E0E0').attr('font-size', '11px').attr('font-family', 'Inter, sans-serif')
        .text(d.id.length > 18 ? d.id.slice(0, 17) + '\u2026' : d.id);
    } else if (d.type === 'topic') {
      var isKey = isKeyTopic(d.id);
      el.append('rect')
        .attr('rx', 12).attr('ry', 12)
        .attr('width', 140).attr('height', 28)
        .attr('x', -70).attr('y', -14)
        .attr('fill', isKey ? 'rgba(232,160,32,0.08)' : '#1A2A1A')
        .attr('stroke', isKey ? '#E8A020' : '#2E4A2E').attr('stroke-width', 1);
      el.append('text')
        .attr('text-anchor', 'middle').attr('dy', '0.35em')
        .attr('fill', isKey ? '#E8A020' : '#80C080')
        .attr('font-size', '10px').attr('font-family', 'JetBrains Mono, monospace')
        .text(d.id.length > 18 ? d.id.slice(0, 17) + '\u2026' : d.id);
    } else if (d.type === 'service') {
      el.append('rect')
        .attr('rx', 12).attr('ry', 12)
        .attr('width', 120).attr('height', 24)
        .attr('x', -60).attr('y', -12)
        .attr('fill', 'rgba(171,71,188,0.08)')
        .attr('stroke', '#7B1FA2').attr('stroke-width', 1);
      el.append('text')
        .attr('text-anchor', 'middle').attr('dy', '0.35em')
        .attr('fill', '#CE93D8')
        .attr('font-size', '9px').attr('font-family', 'JetBrains Mono, monospace')
        .text(d.id.length > 16 ? d.id.slice(0, 15) + '\u2026' : d.id);
    }
  });

  // Hover: highlight connected, fade others
  nodeGs.on('mouseover', function(event, d) {
    var connectedIds = {};
    connectedIds[d.id] = true;
    simEdges.forEach(function(ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source;
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target;
      if (sid === d.id) connectedIds[tid] = true;
      if (tid === d.id) connectedIds[sid] = true;
    });
    nodeGs.transition().duration(150).attr('opacity', function(n) { return connectedIds[n.id] ? 1 : 0.15; });
    links.transition().duration(150).attr('opacity', function(ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source;
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target;
      return (sid === d.id || tid === d.id) ? 0.9 : 0.04;
    }).attr('stroke-width', function(ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source;
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target;
      return (sid === d.id || tid === d.id) ? 2.5 : 1.5;
    });

    // Tooltip
    var tooltip = d3.select(svgEl.parentNode.parentNode).select('.ros2-graph-tooltip');
    if (!tooltip.empty()) {
      var info = '';
      if (d.type === 'node') {
        var pubs = 0, subs = 0, srvs = 0;
        simEdges.forEach(function(ed) {
          var sid = typeof ed.source === 'object' ? ed.source.id : ed.source;
          var tid = typeof ed.target === 'object' ? ed.target.id : ed.target;
          if (sid === d.id && ed.type === 'publishes') pubs++;
          if (tid === d.id && ed.type === 'subscribes') subs++;
          if (sid === d.id && ed.type === 'serves') srvs++;
        });
        info = 'Publishers: ' + pubs + ' | Subscribers: ' + subs + ' | Services: ' + srvs;
      } else if (d.type === 'topic') {
        info = 'Type: ' + (d.msg_type || 'unknown');
      } else {
        info = 'Type: ' + (d.srv_type || 'unknown');
      }
      tooltip.style('display', 'block')
        .style('left', (event.offsetX + 12) + 'px')
        .style('top', (event.offsetY - 10) + 'px');
      tooltip.select('.ros2-graph-tooltip__name').text(d.id);
      tooltip.select('.ros2-graph-tooltip__row').text(info);
    }
  }).on('mouseout', function() {
    nodeGs.transition().duration(150).attr('opacity', 1);
    links.transition().duration(150).attr('opacity', 0.5).attr('stroke-width', 1.5);
    d3.select(svgEl.parentNode.parentNode).select('.ros2-graph-tooltip').style('display', 'none');
  });

  // Click: detail panel
  nodeGs.on('click', function(event, d) {
    event.stopPropagation();
    var detail = { id: d.id, type: d.type, msg_type: d.msg_type || '', srv_type: d.srv_type || '', publishers: [], subscribers: [], services: [] };
    simEdges.forEach(function(ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source;
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target;
      if (ed.type === 'publishes' && sid === d.id) detail.publishers.push(tid);
      if (ed.type === 'publishes' && tid === d.id) detail.publishers.push(sid);
      if (ed.type === 'subscribes' && tid === d.id) detail.subscribers.push(sid);
      if (ed.type === 'subscribes' && sid === d.id) detail.subscribers.push(tid);
      if (ed.type === 'serves' && sid === d.id) detail.services.push(tid);
      if (ed.type === 'serves' && tid === d.id) detail.services.push(sid);
    });
    opts.setSelected(detail);
  });

  // Click background to deselect
  svg.on('click', function() { opts.setSelected(null); });

  // Position update function
  function updatePositions() {
    links.attr('d', function(d) {
      var sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y;
      var dx = tx - sx, dy = ty - sy;
      var dr = Math.sqrt(dx * dx + dy * dy) * 0.6;
      return 'M' + sx + ',' + sy + 'A' + dr + ',' + dr + ' 0 0,1 ' + tx + ',' + ty;
    });
    nodeGs.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
  }

  updatePositions();

  // Minimap
  function updateMinimap() {
    var mm = d3.select(svgEl.parentNode.parentNode).select('.ros2-minimap svg');
    if (mm.empty()) return;
    mm.selectAll('*').remove();
    var ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
    simNodes.forEach(function(n) {
      if (n.x < ext.x0) ext.x0 = n.x;
      if (n.y < ext.y0) ext.y0 = n.y;
      if (n.x > ext.x1) ext.x1 = n.x;
      if (n.y > ext.y1) ext.y1 = n.y;
    });
    var pad = 40;
    ext.x0 -= pad; ext.y0 -= pad; ext.x1 += pad; ext.y1 += pad;
    var gw = ext.x1 - ext.x0 || 1, gh = ext.y1 - ext.y0 || 1;
    var mw = 100, mh = 75;
    var sx = mw / gw, sy = mh / gh, s = Math.min(sx, sy);

    // Draw mini nodes
    simNodes.forEach(function(n) {
      var color = n.type === 'node' ? '#E8A020' : n.type === 'topic' ? '#4CAF50' : '#AB47BC';
      mm.append('circle')
        .attr('cx', (n.x - ext.x0) * s)
        .attr('cy', (n.y - ext.y0) * s)
        .attr('r', 2).attr('fill', color);
    });

    // Draw viewport rect
    var t = opts.transformRef.current || d3.zoomIdentity;
    var vx = -t.x / t.k, vy = -t.y / t.k, vw = width / t.k, vh = height / t.k;
    mm.append('rect')
      .attr('x', (vx - ext.x0) * s).attr('y', (vy - ext.y0) * s)
      .attr('width', vw * s).attr('height', vh * s)
      .attr('fill', 'none').attr('stroke', '#E8A020').attr('stroke-width', 1).attr('opacity', 0.7);
  }
  updateMinimap();

  // Store fitView function
  opts.fitViewRef.current = function() {
    var ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
    simNodes.forEach(function(n) {
      if (n.x < ext.x0) ext.x0 = n.x;
      if (n.y < ext.y0) ext.y0 = n.y;
      if (n.x > ext.x1) ext.x1 = n.x;
      if (n.y > ext.y1) ext.y1 = n.y;
    });
    var pad = 60;
    var gw = (ext.x1 - ext.x0 + pad * 2) || 1;
    var gh = (ext.y1 - ext.y0 + pad * 2) || 1;
    var scale = Math.min(width / gw, height / gh, 2);
    var cx = (ext.x0 + ext.x1) / 2, cy = (ext.y0 + ext.y1) / 2;
    var t = d3.zoomIdentity.translate(width / 2 - cx * scale, height / 2 - cy * scale).scale(scale);
    svg.transition().duration(500).call(zoom.transform, t);
  };

  opts.resetZoomRef.current = function() {
    svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
  };
}

// Node Graph Panel (slide-in)
function CockpitNodeGraphPanel(props) {
  var open = props.open;
  var onClose = props.onClose;

  var tabState = useState('nodes');
  var activeTab = tabState[0];
  var setActiveTab = tabState[1];

  var graphState = useState(null);
  var graphData = graphState[0];
  var setGraphData = graphState[1];

  var svgRef = useRef(null);
  var simRef = useRef(null);
  var transformRef = useRef(null);
  var fitViewRef = useRef(null);
  var resetZoomRef = useRef(null);

  // Fetch graph when opened
  useEffect(function() {
    if (!open) return;
    authFetch('/api/ros2/graph')
      .then(function(r) { return r.json(); })
      .then(setGraphData)
      .catch(function() {});
    var interval = setInterval(function() {
      authFetch('/api/ros2/graph')
        .then(function(r) { return r.json(); })
        .then(setGraphData)
        .catch(function() {});
    }, 5000);
    return function() { clearInterval(interval); };
  }, [open]);

  // Render D3 graph
  useEffect(function() {
    if (!graphData || !graphData.online || !svgRef.current || activeTab !== 'nodes') return;
    renderD3Graph(svgRef.current, graphData, {
      showTopics: true,
      showServices: false,
      filterText: '',
      transformRef: transformRef,
      simRef: simRef,
      fitViewRef: fitViewRef,
      resetZoomRef: resetZoomRef,
      setSelected: function() {}
    });
  }, [graphData, activeTab]);

  // Build TF tree from URDF chain
  function renderTFTree() {
    var urdfChain = props.urdfChain || [];
    if (urdfChain.length === 0) {
      return e('div', { className: 'tf-tree' },
        e('div', { style: { color: 'var(--text-dim)' } }, 'No URDF data loaded')
      );
    }

    var lines = [];
    lines.push(e('div', { key: 'world', className: 'tf-tree__node' },
      e('span', { className: 'tf-tree__name' }, 'world')
    ));
    lines.push(e('div', { key: 'base', className: 'tf-tree__node' },
      e('span', { className: 'tf-tree__indent' }, '\u2514\u2500'),
      e('span', { className: 'tf-tree__name' }, 'base_link')
    ));
    for (var i = 0; i < urdfChain.length; i++) {
      var indent = '';
      for (var d = 0; d < i + 2; d++) { indent += '  '; }
      lines.push(e('div', { key: 'j' + i, className: 'tf-tree__node' },
        e('span', { className: 'tf-tree__indent' }, indent + '\u2514\u2500'),
        e('span', { className: 'tf-tree__arrow' }, urdfChain[i].joint),
        e('span', { className: 'tf-tree__arrow' }, '\u2192'),
        e('span', { className: 'tf-tree__name' }, urdfChain[i].child)
      ));
    }
    return e('div', { className: 'tf-tree' }, lines);
  }

  return e('div', { className: 'node-graph-panel' + (open ? ' node-graph-panel--open' : '') },
    e('div', { className: 'node-graph-panel__header' },
      e('span', { className: 'node-graph-panel__title' }, 'Node Graph'),
      e('span', { className: 'node-graph-panel__close', onClick: onClose }, '\u00D7')
    ),
    e('div', { className: 'node-graph-panel__tabs' },
      e('span', {
        className: 'node-graph-panel__tab' + (activeTab === 'nodes' ? ' node-graph-panel__tab--active' : ''),
        onClick: function() { setActiveTab('nodes'); }
      }, 'NODES'),
      e('span', {
        className: 'node-graph-panel__tab' + (activeTab === 'tf' ? ' node-graph-panel__tab--active' : ''),
        onClick: function() { setActiveTab('tf'); }
      }, 'TF TREE')
    ),
    e('div', { className: 'node-graph-panel__body' },
      activeTab === 'nodes'
        ? e('div', { className: 'node-graph-panel__content' },
            e('div', { className: 'node-graph-panel__svg-wrap' },
              graphData && graphData.online
                ? e('svg', { ref: svgRef })
                : e('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontSize: '12px' } },
                    'ROS2 offline \u2014 no node graph available'
                  )
            )
          )
        : e('div', { className: 'node-graph-panel__content' }, renderTFTree())
    )
  );
}

// Velocity Chart (sparkline for each joint velocity)
function VelocityChart(props) {
  var joints = props.joints || [];
  var historyRef = useRef([]);

  // Accumulate history
  if (joints.length > 0) {
    historyRef.current.push(joints.map(function(j) { return Math.abs(j.velocity || 0); }));
    if (historyRef.current.length > 30) historyRef.current.shift();
  }

  var chartData = historyRef.current.map(function(snapshot, idx) {
    var point = { t: idx };
    for (var i = 0; i < 6; i++) {
      point['j' + (i + 1)] = snapshot[i] || 0;
    }
    return point;
  });

  var COLORS = ['#E8A020', '#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336'];

  return e('div', { className: 'cockpit-card' },
    e('div', { className: 'cockpit-card__title' }, 'Joint Velocities'),
    e('div', { style: { height: '120px' } },
      chartData.length > 1
        ? e(ResponsiveContainer, { width: '100%', height: 120 },
            e(LineChart, { data: chartData, margin: { top: 4, right: 4, left: 4, bottom: 4 } },
              [0,1,2,3,4,5].map(function(i) {
                return e(Line, { key: i, type: 'monotone', dataKey: 'j' + (i + 1), stroke: COLORS[i], strokeWidth: 1.5, dot: false, isAnimationActive: false });
              })
            )
          )
        : e('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontSize: '12px' } }, 'Awaiting data...')
    )
  );
}

// TCP Connection Indicator pill (duplicated from RobotDetailPage)
function TcpConnectionIndicator(props) {
  var tcp = props.tcp || {};
  var allUp = tcp.dashboard && tcp.control && tcp.feedback;
  var anyUp = tcp.dashboard || tcp.control || tcp.feedback;
  var label = allUp ? 'Connected' : anyUp ? 'Partial' : 'Disconnected';
  var color = allUp ? 'var(--success)' : anyUp ? 'var(--warning)' : 'var(--danger)';
  return e('div', {
    style: {
      display: 'inline-flex', alignItems: 'center', gap: '6px',
      padding: '3px 10px', borderRadius: '12px', fontSize: '10px', fontWeight: 600,
      background: color + '18', border: '1px solid ' + color + '44',
      color: color, textTransform: 'uppercase', letterSpacing: '0.5px'
    }
  },
    e('div', { style: { width: '6px', height: '6px', borderRadius: '50%', background: color } }),
    'TCP: ' + label,
    props.host ? e('span', { style: { opacity: 0.7, fontWeight: 400, marginLeft: '4px' } }, props.host) : null
  );
}

// Data Source Badge with click-to-switch (duplicated from RobotDetailPage)
function DataSourceBadge(props) {
  var source = props.source || 'ros2';
  var color = source === 'tcp' ? 'var(--info)' : 'var(--accent)';
  function handleClick() {
    var newSource = source === 'ros2' ? 'tcp' : 'ros2';
    authFetch('/api/robot/' + (props.robotId || 'dobot_cr10') + '/source', {
      method: 'POST',
      body: JSON.stringify({ source: newSource })
    }).then(function() {
      if (props.onChange) props.onChange(newSource);
    }).catch(function() {});
  }
  return e('button', {
    onClick: handleClick,
    title: 'Click to switch data source',
    style: {
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 10px', borderRadius: '12px', fontSize: '10px', fontWeight: 700,
      background: color + '18', border: '1px solid ' + color + '44',
      color: color, textTransform: 'uppercase', letterSpacing: '0.5px',
      cursor: 'pointer', transition: 'all 150ms ease'
    }
  }, source.toUpperCase());
}

// Cockpit Header
function CockpitHeader(props) {
  var nav = React.useContext(NavContext);
  return e('div', { className: 'cockpit-header' },
    e('div', null,
      e('div', { className: 'cockpit-header__title' }, '\u25C9 ROBOT COCKPIT'),
      e('div', { className: 'cockpit-header__meta' },
        e('div', { className: 'cockpit-header__meta-item' },
          e('span', null, 'Robot:'),
          e('span', { className: 'val' }, 'Dobot CR10')
        ),
        e('div', { className: 'cockpit-header__meta-item' },
          e('span', null, 'Status:'),
          e(StatusDot, { status: props.online ? 'online' : 'offline' }),
          e('span', { className: 'val' }, props.online ? 'ONLINE' : 'OFFLINE')
        ),
        e('div', { className: 'cockpit-header__meta-item' },
          e('span', null, 'DOF:'),
          e('span', { className: 'val' }, String(props.dof || 6))
        ),
        e('div', { className: 'cockpit-header__meta-item', style: { marginLeft: '8px' } },
          e(TcpConnectionIndicator, { tcp: props.tcpConnection, host: props.tcpHost })
        ),
        e('div', { className: 'cockpit-header__meta-item' },
          e(DataSourceBadge, { source: props.dataSource, robotId: props.robotId, onChange: props.onSourceChange })
        )
      )
    ),
    e('button', {
      className: 'cockpit-header__back',
      onClick: function() { nav.navigate('robot', { id: props.robotId || 'dobot_cr10' }); }
    }, '\u2190 BACK TO ROBOT')
  );
}

// Main Cockpit Page
function CockpitPage() {
  var nav = React.useContext(NavContext);
  var robotId = (nav.params && nav.params.id) || 'dobot_cr10';

  // State
  var statusState = useState({ online: false, joints: [], mode: 'unknown', pose: null, tcp_connection: {}, data_source: 'ros2' });
  var status = statusState[0];
  var setStatus = statusState[1];

  var urdfState = useState(null);
  var urdfData = urdfState[0];
  var setUrdfData = urdfState[1];

  var topicsState = useState([]);
  var topics = topicsState[0];
  var setTopics = topicsState[1];

  var controllersState = useState([]);
  var controllers = controllersState[0];
  var setControllers = controllersState[1];

  var diagnosticsState = useState([]);
  var diagnostics = diagnosticsState[0];
  var setDiagnostics = diagnosticsState[1];

  var nodePanelState = useState(false);
  var showNodePanel = nodePanelState[0];
  var setShowNodePanel = nodePanelState[1];

  var payloadState = useState(null);
  var cameraPayload = payloadState[0];
  var setCameraPayload = payloadState[1];

  // ROS connection status
  var rosStatusState = useState(getStatus());
  var rosStatus = rosStatusState[0];
  var setRosStatus = rosStatusState[1];
  useEffect(function() { return onStatusChange(setRosStatus); }, []);

  // Fetch URDF once
  useEffect(function() {
    authFetch('/api/robot/' + robotId + '/urdf')
      .then(function(r) { return r.json(); })
      .then(setUrdfData)
      .catch(function() {});
  }, []);

  // WebSocket for robot status at ~10hz (replaces REST polling)
  useEffect(function() {
    var wsToken = localStorage.getItem('mc_token') || '';
    var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = null;
    var reconnectTimer = null;

    function connect() {
      ws = new WebSocket(protocol + '//' + location.host + '/ws/robot/' + robotId + '?token=' + encodeURIComponent(wsToken));
      ws.onmessage = function(evt) {
        try {
          var msg = JSON.parse(evt.data);
          if (msg.type === 'robot_status' && msg.data) {
            setStatus(msg.data);
          }
        } catch(e) {}
      };
      ws.onclose = function() {
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = function() {};
    }
    connect();

    return function() {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) { try { ws.close(); } catch(e) {} }
    };
  }, [robotId]);

  // Poll low-frequency data (topics, controllers, diagnostics) at 5s
  useEffect(function() {
    function fetchSlow() {
      authFetch('/api/robot/' + robotId + '/topics')
        .then(function(r) { return r.json(); })
        .then(function(d) { setTopics(d.topics || []); })
        .catch(function() {});
      authFetch('/api/robot/' + robotId + '/controllers')
        .then(function(r) { return r.json(); })
        .then(function(d) { setControllers(d.controllers || []); })
        .catch(function() {});
      authFetch('/api/robot/' + robotId + '/diagnostics')
        .then(function(r) { return r.json(); })
        .then(function(d) { setDiagnostics(d.diagnostics || []); })
        .catch(function() {});
    }
    fetchSlow();
    var interval = setInterval(fetchSlow, 5000);
    return function() { clearInterval(interval); };
  }, [robotId]);

  var urdfChain = urdfData ? (urdfData.kinematic_chain || []) : [];
  var online = status.online;

  function handleSourceChange(newSource) {
    setStatus(Object.assign({}, status, { data_source: newSource }));
  }

  return e('div', { className: 'cockpit' },
    e(CockpitHeader, {
      online: online, robotId: robotId, dof: urdfData ? urdfData.dof : 6,
      tcpConnection: status.tcp_connection, dataSource: status.data_source,
      onSourceChange: handleSourceChange
    }),

    // Row 1: 3D viewer + Joint gauges
    e('div', { className: 'cockpit-grid', style: { gridTemplateColumns: '1.5fr 1fr' } },
      e('div', { style: { height: '500px' } },
        e(RosViewer, {
          ros: (function() { try { return getRos(); } catch(ex) { return null; } })(),
          rosStatus: rosStatus,
          robotId: robotId,
          fixedFrame: 'base_link',
          topics: { urdf: true, jointStates: '/joint_states' },
          onReconnect: function() { rosReconnect(); }
        })
      ),
      e(JointStatesCard, { joints: status.joints, urdfChain: urdfChain })
    ),

    // Row 1.5: Payload configuration
    e('div', { className: 'cockpit-grid', style: { gridTemplateColumns: '1fr' } },
      e(PayloadConfigPanel, { onPayloadChange: setCameraPayload })
    ),

    // Simulation mode panel
    e('div', { className: 'cockpit-grid', style: { gridTemplateColumns: '1fr' } },
      e(SimulationModePanel, null)
    ),

    // Row 2: Mode + End Effector + Velocity
    e('div', { className: 'cockpit-grid cockpit-grid--3' },
      e(RobotModeCard, { mode: status.mode, online: online }),
      e(EndEffectorCard, { pose: status.pose }),
      e(VelocityChart, { joints: status.joints })
    ),

    // Row 3: Topics + Controllers + Diagnostics
    e('div', { className: 'cockpit-grid cockpit-grid--3' },
      e(CockpitTopicsCard, { topics: topics }),
      e(CockpitControllersCard, { controllers: controllers }),
      e(CockpitDiagnosticsCard, { diagnostics: diagnostics })
    ),

    // Node graph button
    e('div', { style: { marginTop: '16px', textAlign: 'center' } },
      e('button', {
        style: {
          padding: '10px 24px', fontSize: '12px', fontWeight: 700,
          background: 'var(--raised)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)',
          textTransform: 'uppercase', letterSpacing: '0.5px', cursor: 'pointer',
          transition: 'all 150ms ease'
        },
        onClick: function() { setShowNodePanel(true); }
      }, '\u25C9 OPEN NODE GRAPH')
    ),

    // Slide-in node graph panel
    e(CockpitNodeGraphPanel, {
      open: showNodePanel,
      onClose: function() { setShowNodePanel(false); },
      urdfChain: urdfChain
    })
  );
}

export { CockpitPage }
