import React, { useState, useEffect, useRef, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Area, AreaChart
} from 'recharts'
import * as d3 from 'd3'
import { authFetch } from '../utils/authFetch'
import { NavContext } from '../contexts/NavContext'
import { StatusDot } from '../components/StatusDot'
import { Badge } from '../components/Badge'
import { MetricCard } from '../components/MetricCard'
import { TabNav } from '../components/TabNav'
import { DataTable } from '../components/DataTable'
import { RosViewer } from '../components/RosViewer'
import { ROSCamera } from '../components/ROSCamera'
import ROSLIB from '../utils/roslib-browser.js'
import { getRos, getStatus, onStatusChange, reconnect as rosReconnect } from '../utils/rosConnection'

var e = React.createElement

// ── Helper: TCP Connection Indicator ─────────────────────
function TcpConnectionIndicator(props) {
  var tcp = props.tcp || {}
  var allUp = tcp.dashboard && tcp.control && tcp.feedback
  var anyUp = tcp.dashboard || tcp.control || tcp.feedback
  var label = allUp ? 'Connected' : anyUp ? 'Partial' : 'Disconnected'
  var color = allUp ? 'var(--success)' : anyUp ? 'var(--warning)' : 'var(--danger)'
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
  )
}

// Data Source Badge with click-to-switch
function DataSourceBadge(props) {
  var source = props.source || 'ros2'
  var color = source === 'tcp' ? 'var(--info)' : 'var(--accent)'
  function handleClick() {
    var newSource = source === 'ros2' ? 'tcp' : 'ros2'
    authFetch('/api/robot/' + (props.robotId || 'dobot_cr10') + '/source', {
      method: 'POST',
      body: JSON.stringify({ source: newSource })
    }).then(function () {
      if (props.onChange) props.onChange(newSource)
    }).catch(function () {})
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
  }, source.toUpperCase())
}

// ROS2 connection status badge
function RosBridgeBadge(props) {
  var status = props.status || 'disconnected'
  var color = status === 'connected' ? 'var(--success)' : status === 'error' ? 'var(--danger)' : 'var(--text-dim)'
  return e('div', {
    style: {
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 10px', borderRadius: '12px', fontSize: '10px', fontWeight: 600,
      background: color + '18', border: '1px solid ' + color + '44',
      color: color, textTransform: 'uppercase', letterSpacing: '0.5px'
    }
  },
    e('div', { style: { width: '6px', height: '6px', borderRadius: '50%', background: color } }),
    'ROS: ' + status
  )
}

// Empty state component
function EmptyState(props) {
  return e('div', {
    style: {
      padding: '48px 24px', textAlign: 'center',
      background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)'
    }
  },
    e('div', { style: { fontSize: '32px', marginBottom: '12px', opacity: 0.5 } }, props.icon || '\u2205'),
    e('div', { style: { fontSize: '14px', fontWeight: 600, color: 'var(--text)', marginBottom: '6px' } }, props.title || 'No Data'),
    e('div', { style: { fontSize: '12px', color: 'var(--text-secondary)' } }, props.message || '')
  )
}

// =========================================================================
// PAGE: ROBOT DETAIL
// =========================================================================

function RobotDetailPage() {
  var nav = React.useContext(NavContext)
  var robotId = (nav.params && nav.params.id) || 'dobot_cr10'

  var tabState = useState('Overview')
  var activeTab = tabState[0]
  var setActiveTab = tabState[1]

  // Fetch robots list from DB
  var robotsState = useState([])
  var robots = robotsState[0]
  var setRobots = robotsState[1]

  var robotDetailState = useState(null)
  var robotDetail = robotDetailState[0]
  var setRobotDetail = robotDetailState[1]

  // ROS connection status
  var rosState = useState(getStatus())
  var rosStatus = rosState[0]
  var setRosStatus = rosState[1]

  useEffect(function () {
    return onStatusChange(setRosStatus)
  }, [])

  // Fetch robots list
  useEffect(function () {
    authFetch('/api/robots')
      .then(function (r) { return r.json() })
      .then(setRobots)
      .catch(function () {})
  }, [])

  // Fetch robot detail
  useEffect(function () {
    authFetch('/api/robots/' + robotId)
      .then(function (r) { return r.json() })
      .then(setRobotDetail)
      .catch(function () {})
  }, [robotId])

  var robot = robotDetail || {}
  var statusVariant = robot.status === 'active' ? 'success' : robot.status === 'training' ? 'info' : 'neutral'

  return e('div', null,
    // Robot selector
    e('div', { style: { display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' } },
      robots.map(function (r) {
        var isActive = r.id === robotId
        return e('a', {
          key: r.id, href: '#',
          style: {
            padding: '6px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 600,
            background: isActive ? 'var(--accent-dim)' : 'var(--raised)',
            color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
            border: '1px solid ' + (isActive ? 'var(--accent)' : 'var(--border)'),
            textDecoration: 'none'
          },
          onClick: function (ev) { ev.preventDefault(); nav.navigate('robot', { id: r.id }) }
        },
          e('span', null, r.name || r.id),
          r.type ? e('span', { style: { marginLeft: '6px', fontSize: '10px', opacity: 0.6 } }, r.type) : null
        )
      })
    ),

    // Hero
    e('div', { className: 'hero' },
      e('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' } },
        e('div', null,
          e('div', { style: { display: 'flex', alignItems: 'center', gap: '12px' } },
            e('h1', { className: 'hero__name' }, robot.name || robotId),
            e(Badge, { variant: statusVariant }, robot.status || 'unknown')
          )
        ),
        e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } },
          e(StatusDot, { status: robot.status === 'active' ? 'online' : robot.status === 'training' ? 'busy' : 'warning', large: true }),
          e('button', {
            style: {
              padding: '8px 18px', fontSize: '11px', fontWeight: 700,
              background: 'var(--accent)', color: '#000', borderRadius: 'var(--radius-sm)',
              textTransform: 'uppercase', letterSpacing: '0.8px', border: 'none', cursor: 'pointer'
            },
            onClick: function () { nav.navigate('cockpit', { id: robotId }) }
          }, '\u25C9 COCKPIT')
        )
      ),
      e('div', { className: 'hero__meta' },
        e('div', { className: 'hero__meta-item' }, e('span', { className: 'label' }, 'Serial:'), e('span', { className: 'value' }, robot.serial || '\u2014')),
        e('div', { className: 'hero__meta-item' }, e('span', { className: 'label' }, 'DOF:'), e('span', { className: 'value' }, robot.dof || '\u2014')),
        e('div', { className: 'hero__meta-item' }, e('span', { className: 'label' }, 'Payload:'), e('span', { className: 'value' }, robot.max_payload_kg ? robot.max_payload_kg + ' kg' : '\u2014')),
        e('div', { className: 'hero__meta-item' }, e('span', { className: 'label' }, 'Reach:'), e('span', { className: 'value' }, robot.reach_mm ? robot.reach_mm + ' mm' : '\u2014'))
      )
    ),

    // Tabs
    e(TabNav, {
      tabs: ['Overview', 'Telemetry', 'Digital Twin', 'Simulations', 'Training', 'Safety', 'Deployments', 'ROS2'],
      active: activeTab, onChange: setActiveTab
    }),

    // Tab content
    activeTab === 'Overview' ? e(RobotOverviewTab, { robot: robot, robotId: robotId, rosStatus: rosStatus }) : null,
    activeTab === 'Telemetry' ? e(RobotTelemetryTab, { robot: robot, robotId: robotId, rosStatus: rosStatus }) : null,
    activeTab === 'Digital Twin' ? e(RobotDigitalTwinTab, { robot: robot, robotId: robotId, rosStatus: rosStatus }) : null,
    activeTab === 'Simulations' ? e(RobotSimulationsTab, { robot: robot, robotId: robotId }) : null,
    activeTab === 'Training' ? e(RobotTrainingTab, { robot: robot, robotId: robotId }) : null,
    activeTab === 'Safety' ? e(RobotSafetyTab, { robot: robot, robotId: robotId }) : null,
    activeTab === 'Deployments' ? e(RobotDeploymentsTab, { robot: robot, robotId: robotId }) : null,
    activeTab === 'ROS2' ? e(RobotROS2Tab, { robot: robot, rosStatus: rosStatus }) : null
  )
}

// ── Overview Tab ─────────────────────────────────────────
function RobotOverviewTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var rosStatus = props.rosStatus || 'disconnected'

  // Live status from WebSocket
  var liveState = useState({ online: false, joints: [], mode: 'unknown', pose: null, tcp_connection: {}, data_source: 'ros2' })
  var live = liveState[0]
  var setLive = liveState[1]

  useEffect(function () {
    var wsToken = localStorage.getItem('mc_token') || ''
    var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    var ws = null
    var reconnectTimer = null

    function connect() {
      ws = new WebSocket(protocol + '//' + location.host + '/ws/robot/' + robotId + '?token=' + encodeURIComponent(wsToken))
      ws.onmessage = function (evt) {
        try {
          var msg = JSON.parse(evt.data)
          if (msg.type === 'robot_status' && msg.data) setLive(msg.data)
        } catch (ex) {}
      }
      ws.onclose = function () { reconnectTimer = setTimeout(connect, 3000) }
    }
    connect()
    return function () {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) { try { ws.close() } catch (ex) {} }
    }
  }, [robotId])

  // Joint angle summary
  var jointSummary = (live.joints || []).slice(0, 6).map(function (j) {
    return (j.position_deg || 0).toFixed(1) + '\u00B0'
  }).join('  ')

  // End-effector position
  var pose = live.pose
  var poseStr = pose ? 'X:' + pose.x + '  Y:' + pose.y + '  Z:' + pose.z : '--'

  function handleSourceChange(newSource) {
    setLive(Object.assign({}, live, { data_source: newSource }))
  }

  // Fetch real metrics from API
  var metricsState = useState({})
  var realMetrics = metricsState[0]
  var setRealMetrics = metricsState[1]

  useEffect(function () {
    var metricNames = ['safety_score', 'sim_accuracy', 'uptime']
    metricNames.forEach(function (m) {
      authFetch('/api/metrics/' + robotId + '/' + m + '?hours=168')
        .then(function (r) { return r.json() })
        .then(function (data) {
          setRealMetrics(function (prev) {
            var next = Object.assign({}, prev)
            next[m] = data
            return next
          })
        })
        .catch(function () {})
    })
  }, [robotId])

  // Build sparkline data from real metrics
  function buildSparkData(metricData) {
    if (!metricData || !Array.isArray(metricData) || metricData.length === 0) return null
    return metricData.slice(-20).map(function (d) { return { v: d.value } })
  }

  function SparklineCard(cardProps) {
    var data = cardProps.data
    var hasData = data && data.length > 0
    return e('div', { className: 'stat-card' },
      e('div', { className: 'stat-card__label' }, cardProps.label),
      e('div', { className: 'stat-card__value' }, cardProps.value),
      hasData
        ? e('div', { style: { marginTop: '8px', height: '36px' } },
            e(ResponsiveContainer, { width: '100%', height: 36 },
              e(AreaChart, { data: data, margin: { top: 2, right: 2, left: 2, bottom: 2 } },
                e(Area, { type: 'monotone', dataKey: 'v', stroke: cardProps.color || '#E8A020', fill: (cardProps.color || '#E8A020') + '22', strokeWidth: 1.5, dot: false })
              )
            )
          )
        : e('div', { style: { marginTop: '8px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: '10px' } }, 'No history')
    )
  }

  var safetyData = buildSparkData(realMetrics['safety_score'])
  var simData = buildSparkData(realMetrics['sim_accuracy'])
  var uptimeData = buildSparkData(realMetrics['uptime'])

  return e('div', null,
    // Live status cards row
    e('div', { className: 'grid-4 mb-20' },
      e('div', { className: 'stat-card' },
        e('div', { className: 'stat-card__label' }, 'Status'),
        e('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' } },
          e(StatusDot, { status: live.online ? 'online' : 'offline', large: true }),
          e('span', { style: { fontSize: '18px', fontWeight: 700, color: live.online ? 'var(--success)' : 'var(--danger)' } }, live.online ? 'ONLINE' : 'OFFLINE')
        )
      ),
      e('div', { className: 'stat-card' },
        e('div', { className: 'stat-card__label' }, 'Mode'),
        e('div', { className: 'stat-card__value' }, live.mode || 'unknown')
      ),
      e('div', { className: 'stat-card' },
        e('div', { className: 'stat-card__label' }, 'End Effector'),
        e('div', { style: { fontFamily: 'var(--font-mono)', fontSize: '12px', marginTop: '6px', color: 'var(--text)' } }, poseStr)
      ),
      e('div', { className: 'stat-card' },
        e('div', { className: 'stat-card__label' }, 'Joints'),
        e('div', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', marginTop: '6px', color: 'var(--text)' } }, jointSummary || 'No data')
      )
    ),

    // Indicators row
    e('div', { style: { display: 'flex', gap: '10px', marginBottom: '16px', alignItems: 'center' } },
      e(TcpConnectionIndicator, { tcp: live.tcp_connection }),
      e(DataSourceBadge, { source: live.data_source, robotId: robotId, onChange: handleSourceChange }),
      e(RosBridgeBadge, { status: rosStatus })
    ),

    // Metric cards from real API data (or empty states)
    e('div', { className: 'grid-3' },
      e(SparklineCard, { label: 'Sim Accuracy', value: simData ? (simData[simData.length - 1].v).toFixed(1) + '%' : '\u2014', data: simData, color: '#E8A020' }),
      e(SparklineCard, { label: 'Safety Score', value: safetyData ? (safetyData[safetyData.length - 1].v).toFixed(1) + '%' : '\u2014', data: safetyData, color: '#4CAF50' }),
      e(SparklineCard, { label: 'Uptime', value: uptimeData ? (uptimeData[uptimeData.length - 1].v).toFixed(1) + '%' : '\u2014', data: uptimeData, color: '#2196F3' })
    )
  )
}

// ── Telemetry Tab ────────────────────────────────────────
function RobotTelemetryTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var rosStatus = props.rosStatus || 'disconnected'
  var COLORS = ['#E8A020', '#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#F44336']
  var MAX_SAMPLES = 300

  // Ring buffer for 30s of data at 10Hz
  var posBufferRef = useRef([])
  var velBufferRef = useRef([])

  var posState = useState([])
  var posData = posState[0]
  var setPosData = posState[1]

  var velState = useState([])
  var velData = velState[0]
  var setVelData = velState[1]

  var currentState = useState([])
  var currentValues = currentState[0]
  var setCurrentValues = currentState[1]

  var hzState = useState(0)
  var topicHz = hzState[0]
  var setTopicHz = hzState[1]
  var hzCountRef = useRef(0)
  var lastHzRef = useRef(Date.now())

  // Try rosbridge first, fall back to dashboard WebSocket
  useEffect(function () {
    var cleanup = null

    if (rosStatus === 'connected') {
      // Subscribe via rosbridge
      var ros = getRos()
      var topic = new ROSLIB.Topic({
        ros: ros,
        name: '/joint_states',
        messageType: 'sensor_msgs/JointState'
      })
      var frameCount = 0

      topic.subscribe(function (msg) {
        frameCount++
        hzCountRef.current++
        var now = Date.now()
        if (now - lastHzRef.current >= 1000) {
          setTopicHz(hzCountRef.current)
          hzCountRef.current = 0
          lastHzRef.current = now
        }

        var positions = msg.position || []
        var velocities = msg.velocity || []
        var efforts = msg.effort || []
        var names = msg.name || []

        var posPoint = { t: frameCount }
        var velPoint = { t: frameCount }
        var vals = []
        for (var i = 0; i < Math.min(positions.length, 6); i++) {
          var degVal = positions[i] * 180 / Math.PI
          posPoint['j' + (i + 1)] = degVal
          velPoint['j' + (i + 1)] = Math.abs(velocities[i] || 0)
          vals.push({
            name: names[i] || ('J' + (i + 1)),
            position: degVal.toFixed(2),
            velocity: (velocities[i] || 0).toFixed(4),
            effort: (efforts[i] || 0).toFixed(2)
          })
        }

        posBufferRef.current.push(posPoint)
        if (posBufferRef.current.length > MAX_SAMPLES) posBufferRef.current.shift()
        velBufferRef.current.push(velPoint)
        if (velBufferRef.current.length > MAX_SAMPLES) velBufferRef.current.shift()

        if (frameCount % 3 === 0) {
          setPosData(posBufferRef.current.slice())
          setVelData(velBufferRef.current.slice())
          setCurrentValues(vals)
        }
      })

      cleanup = function () { topic.unsubscribe() }
    } else {
      // Fallback: dashboard WebSocket
      var wsToken = localStorage.getItem('mc_token') || ''
      var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      var ws = null
      var reconnectTimer = null
      var frameCount2 = 0

      function connect() {
        ws = new WebSocket(protocol + '//' + location.host + '/ws/robot/' + robotId + '?token=' + encodeURIComponent(wsToken))
        ws.onmessage = function (evt) {
          try {
            var msg = JSON.parse(evt.data)
            if (msg.type !== 'robot_status' || !msg.data || !msg.data.joints) return
            var joints = msg.data.joints
            frameCount2++

            var posPoint = { t: frameCount2 }
            var velPoint = { t: frameCount2 }
            var vals = []
            for (var i = 0; i < Math.min(joints.length, 6); i++) {
              posPoint['j' + (i + 1)] = (joints[i].position_deg || 0)
              velPoint['j' + (i + 1)] = Math.abs(joints[i].velocity || 0)
              vals.push({
                name: joints[i].name || ('J' + (i + 1)),
                position: (joints[i].position_deg || 0).toFixed(2),
                velocity: (joints[i].velocity || 0).toFixed(4),
                effort: (joints[i].effort || 0).toFixed(2)
              })
            }

            posBufferRef.current.push(posPoint)
            if (posBufferRef.current.length > MAX_SAMPLES) posBufferRef.current.shift()
            velBufferRef.current.push(velPoint)
            if (velBufferRef.current.length > MAX_SAMPLES) velBufferRef.current.shift()

            if (frameCount2 % 3 === 0) {
              setPosData(posBufferRef.current.slice())
              setVelData(velBufferRef.current.slice())
              setCurrentValues(vals)
            }
          } catch (ex) {}
        }
        ws.onclose = function () { reconnectTimer = setTimeout(connect, 3000) }
      }
      connect()

      cleanup = function () {
        if (reconnectTimer) clearTimeout(reconnectTimer)
        if (ws) try { ws.close() } catch (ex) {}
      }
    }

    return cleanup
  }, [robotId, rosStatus])

  var chartMargin = { top: 10, right: 20, left: 10, bottom: 10 }
  var tooltipStyle = { background: '#242424', border: '1px solid #2E2E2E', borderRadius: '6px', fontSize: '11px', fontFamily: 'JetBrains Mono' }

  return e('div', null,
    // Data source indicator
    e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' } },
      e(RosBridgeBadge, { status: rosStatus }),
      e('span', { style: { fontSize: '11px', color: 'var(--text-secondary)' } },
        rosStatus === 'connected'
          ? 'Streaming from rosbridge /joint_states @ ' + topicHz + ' Hz'
          : 'Streaming from dashboard WebSocket'
      )
    ),

    // Joint Positions chart
    e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Joint Positions (\u00B0)')
      ),
      e('div', { style: { height: '240px' } },
        posData.length > 1
          ? e(ResponsiveContainer, { width: '100%', height: 240 },
              e(LineChart, { data: posData, margin: chartMargin },
                e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#2E2E2E' }),
                e(XAxis, { dataKey: 't', tick: false }),
                e(YAxis, { tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' }, domain: ['auto', 'auto'] }),
                e(Tooltip, { contentStyle: tooltipStyle }),
                e(Legend, { wrapperStyle: { fontSize: '11px' } }),
                [0, 1, 2, 3, 4, 5].map(function (i) {
                  return e(Line, { key: 'pos' + i, type: 'monotone', dataKey: 'j' + (i + 1), stroke: COLORS[i], strokeWidth: 1.5, dot: false, isAnimationActive: false, name: 'J' + (i + 1) })
                })
              )
            )
          : e('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontSize: '12px' } }, 'Awaiting telemetry data...')
      )
    ),

    // Joint Velocities chart
    e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Joint Velocities (rad/s)')
      ),
      e('div', { style: { height: '240px' } },
        velData.length > 1
          ? e(ResponsiveContainer, { width: '100%', height: 240 },
              e(LineChart, { data: velData, margin: chartMargin },
                e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#2E2E2E' }),
                e(XAxis, { dataKey: 't', tick: false }),
                e(YAxis, { tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' }, domain: [0, 'auto'] }),
                e(Tooltip, { contentStyle: tooltipStyle }),
                e(Legend, { wrapperStyle: { fontSize: '11px' } }),
                [0, 1, 2, 3, 4, 5].map(function (i) {
                  return e(Line, { key: 'vel' + i, type: 'monotone', dataKey: 'j' + (i + 1), stroke: COLORS[i], strokeWidth: 1.5, dot: false, isAnimationActive: false, name: 'J' + (i + 1) })
                })
              )
            )
          : e('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontSize: '12px' } }, 'Awaiting telemetry data...')
      )
    ),

    // Current values table
    e('div', { className: 'card' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Current Joint Values')
      ),
      e('table', { style: { width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: '12px' } },
        e('thead', null,
          e('tr', { style: { borderBottom: '1px solid var(--border)' } },
            e('th', { style: { padding: '8px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' } }, 'Joint'),
            e('th', { style: { padding: '8px 12px', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' } }, 'Position (\u00B0)'),
            e('th', { style: { padding: '8px 12px', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' } }, 'Velocity (rad/s)'),
            e('th', { style: { padding: '8px 12px', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.5px' } }, 'Effort')
          )
        ),
        e('tbody', null,
          currentValues.length > 0
            ? currentValues.map(function (v, idx) {
                return e('tr', { key: idx, style: { borderBottom: '1px solid var(--border)' } },
                  e('td', { style: { padding: '8px 12px', color: COLORS[idx] || 'var(--text)', fontWeight: 600 } }, v.name),
                  e('td', { style: { padding: '8px 12px', textAlign: 'right' } }, v.position),
                  e('td', { style: { padding: '8px 12px', textAlign: 'right' } }, v.velocity),
                  e('td', { style: { padding: '8px 12px', textAlign: 'right' } }, v.effort)
                )
              })
            : e('tr', null, e('td', { colSpan: 4, style: { padding: '20px', textAlign: 'center', color: 'var(--text-dim)' } }, 'No joint data'))
        )
      )
    )
  )
}

// ── Simulations Tab — real API ───────────────────────────
function RobotSimulationsTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var dataState = useState([])
  var sims = dataState[0]
  var setSims = dataState[1]
  var loadingState = useState(true)
  var loading = loadingState[0]
  var setLoading = loadingState[1]

  useEffect(function () {
    authFetch('/api/simulations?robot=' + robotId)
      .then(function (r) { return r.json() })
      .then(function (data) { setSims(data); setLoading(false) })
      .catch(function () { setLoading(false) })
  }, [robotId])

  if (loading) return e('div', { style: { padding: '24px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading simulations...')

  if (sims.length === 0) {
    return e(EmptyState, {
      icon: '\uD83C\uDFAC',
      title: 'No Simulation Runs',
      message: 'No simulation runs recorded for this robot. Run a simulation from the Demos page.'
    })
  }

  var cols = [
    { key: 'id', label: 'ID', mono: true },
    { key: 'scene', label: 'Scene' },
    { key: 'result', label: 'Result', render: function (row) {
      var passed = row.safety_pass === 1 || row.result === 'pass'
      return e(Badge, { variant: passed ? 'success' : 'danger' }, passed ? 'pass' : 'fail')
    }},
    { key: 'path_error', label: 'Path Error', mono: true, render: function (row) {
      var val = row.path_error
      if (val == null) return '\u2014'
      return e('span', { className: 'mono' }, val.toFixed(3))
    }},
    { key: 'cycle_time', label: 'Cycle Time', mono: true, render: function (row) {
      return row.cycle_time ? row.cycle_time.toFixed(2) + 's' : '\u2014'
    }},
    { key: 'timestamp', label: 'Date', mono: true, render: function (row) {
      return row.timestamp ? row.timestamp.slice(0, 16) : '\u2014'
    }}
  ]

  return e('div', { className: 'card' },
    e(DataTable, { columns: cols, data: sims })
  )
}

// ── Training Tab — real API ─────────────────────────────
function RobotTrainingTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var dataState = useState([])
  var runs = dataState[0]
  var setRuns = dataState[1]
  var loadingState = useState(true)
  var loading = loadingState[0]
  var setLoading = loadingState[1]

  useEffect(function () {
    authFetch('/api/training?robot=' + robotId)
      .then(function (r) { return r.json() })
      .then(function (data) { setRuns(data); setLoading(false) })
      .catch(function () { setLoading(false) })
  }, [robotId])

  if (loading) return e('div', { style: { padding: '24px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading training runs...')

  if (runs.length === 0) {
    return e(EmptyState, {
      icon: '\uD83E\uDDE0',
      title: 'No Training Runs',
      message: 'No training runs recorded for this robot.'
    })
  }

  // Build loss curve from completed runs that have loss data
  var completedRuns = runs.filter(function (r) { return r.final_loss != null })
  var hasCurve = completedRuns.length > 0

  var cols = [
    { key: 'id', label: 'ID', mono: true },
    { key: 'policy_name', label: 'Policy', mono: true },
    { key: 'status', label: 'Status', render: function (row) {
      var v = row.status === 'completed' ? 'success' : row.status === 'running' ? 'info' : 'danger'
      return e(Badge, { variant: v }, row.status || 'unknown')
    }},
    { key: 'epochs', label: 'Epochs', mono: true },
    { key: 'final_loss', label: 'Loss', mono: true, render: function (row) {
      return row.final_loss != null ? row.final_loss.toFixed(4) : '\u2014'
    }},
    { key: 'started', label: 'Started', mono: true, render: function (row) {
      return row.started ? row.started.slice(0, 16) : '\u2014'
    }}
  ]

  return e('div', null,
    // Loss curve from real training data
    hasCurve ? e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Training Loss History')
      ),
      e(ResponsiveContainer, { width: '100%', height: 200 },
        e(LineChart, { data: completedRuns.map(function (r, i) {
          return { run: i + 1, loss: r.final_loss, valLoss: r.val_loss }
        }), margin: { top: 10, right: 30, left: 10, bottom: 10 } },
          e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#2E2E2E' }),
          e(XAxis, { dataKey: 'run', tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' } }),
          e(YAxis, { tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' } }),
          e(Tooltip, { contentStyle: { background: '#242424', border: '1px solid #2E2E2E', borderRadius: '6px', fontSize: '12px', fontFamily: 'JetBrains Mono' } }),
          e(Legend, { wrapperStyle: { fontSize: '11px' } }),
          e(Line, { type: 'monotone', dataKey: 'loss', stroke: '#E8A020', strokeWidth: 2, dot: true, name: 'Train Loss' }),
          e(Line, { type: 'monotone', dataKey: 'valLoss', stroke: '#26A69A', strokeWidth: 2, dot: true, name: 'Val Loss' })
        )
      )
    ) : null,

    // Runs table
    e('div', { className: 'card' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Training Runs')
      ),
      e(DataTable, { columns: cols, data: runs })
    )
  )
}

// ── Safety Tab — real API ───────────────────────────────
function RobotSafetyTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var diagState = useState([])
  var diagnostics = diagState[0]
  var setDiagnostics = diagState[1]
  var metricsState = useState([])
  var safetyMetrics = metricsState[0]
  var setSafetyMetrics = metricsState[1]
  var loadingState = useState(true)
  var loading = loadingState[0]
  var setLoading = loadingState[1]

  useEffect(function () {
    Promise.all([
      authFetch('/api/robot/' + robotId + '/diagnostics').then(function (r) { return r.json() }).catch(function () { return [] }),
      authFetch('/api/metrics/' + robotId + '/safety_score?hours=720').then(function (r) { return r.json() }).catch(function () { return [] })
    ]).then(function (results) {
      setDiagnostics(results[0] || [])
      setSafetyMetrics(results[1] || [])
      setLoading(false)
    })
  }, [robotId])

  if (loading) return e('div', { style: { padding: '24px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading safety data...')

  var hasDiagnostics = diagnostics.length > 0
  var hasMetrics = safetyMetrics.length > 0

  if (!hasDiagnostics && !hasMetrics) {
    return e(EmptyState, {
      icon: '\uD83D\uDEE1\uFE0F',
      title: 'No Safety Data',
      message: 'Safety diagnostics will appear when the robot stack is running.'
    })
  }

  return e('div', null,
    // Diagnostics from ROS2
    hasDiagnostics ? e('div', { className: 'card mb-20' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'ROS2 Diagnostics'),
        e(Badge, { variant: 'accent' }, diagnostics.length + ' messages')
      ),
      diagnostics.map(function (d, i) {
        var levelColor = d.level === 'OK' ? 'var(--success)' : d.level === 'WARN' ? 'var(--warning)' : 'var(--danger)'
        return e('div', { key: i, style: { display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 0', borderBottom: '1px solid var(--border)' } },
          e(StatusDot, { status: d.level === 'OK' ? 'online' : d.level === 'WARN' ? 'warning' : 'offline' }),
          e('span', { style: { flex: 1, fontSize: '13px' } }, d.name || 'Unknown'),
          e('span', { style: { fontFamily: 'var(--font-mono)', fontSize: '11px', color: levelColor } }, d.message || d.level)
        )
      })
    ) : null,

    // Safety score history from metrics
    hasMetrics ? e('div', { className: 'card' },
      e('div', { className: 'card__header' },
        e('span', { className: 'card__title' }, 'Safety Score History')
      ),
      e(ResponsiveContainer, { width: '100%', height: 200 },
        e(AreaChart, { data: safetyMetrics.map(function (d) {
          return { time: d.timestamp ? d.timestamp.slice(5, 16) : '', score: d.value }
        }), margin: { top: 10, right: 30, left: 10, bottom: 10 } },
          e(CartesianGrid, { strokeDasharray: '3 3', stroke: '#2E2E2E' }),
          e(XAxis, { dataKey: 'time', tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' } }),
          e(YAxis, { domain: ['auto', 'auto'], tick: { fill: '#808080', fontSize: 10, fontFamily: 'JetBrains Mono' } }),
          e(Tooltip, { contentStyle: { background: '#242424', border: '1px solid #2E2E2E', borderRadius: '6px', fontSize: '12px', fontFamily: 'JetBrains Mono' } }),
          e(Area, { type: 'monotone', dataKey: 'score', stroke: '#4CAF50', fill: 'rgba(76,175,80,0.15)', strokeWidth: 2 })
        )
      )
    ) : null
  )
}

// ── Deployments Tab — real API ──────────────────────────
function RobotDeploymentsTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var robot = props.robot || {}

  // Use deployments from robot detail API
  var deploysState = useState([])
  var deploys = deploysState[0]
  var setDeploys = deploysState[1]
  var loadingState = useState(true)
  var loading = loadingState[0]
  var setLoading = loadingState[1]

  useEffect(function () {
    authFetch('/api/robots/' + robotId)
      .then(function (r) { return r.json() })
      .then(function (data) {
        setDeploys(data.deployments || [])
        setLoading(false)
      })
      .catch(function () { setLoading(false) })
  }, [robotId])

  if (loading) return e('div', { style: { padding: '24px', textAlign: 'center', color: 'var(--text-dim)' } }, 'Loading deployments...')

  if (deploys.length === 0) {
    return e(EmptyState, {
      icon: '\uD83D\uDE80',
      title: 'No Deployments',
      message: 'No deployment records for this robot.'
    })
  }

  return e('div', { className: 'card' },
    e('div', { className: 'card__header' },
      e('span', { className: 'card__title' }, 'Deployment Timeline')
    ),
    deploys.map(function (d, i) {
      var statusVar = d.status === 'active' ? 'success' : d.status === 'superseded' ? 'neutral' : 'danger'
      return e('div', { key: d.id || i, className: 'timeline-item' },
        e('div', { className: 'timeline-item__marker' + (d.status === 'active' ? ' timeline-item__marker--filled' : '') }),
        e('div', { className: 'timeline-item__content' },
          e('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' } },
            e('span', { className: 'timeline-item__title' }, d.policy_version || d.version || '\u2014'),
            e(Badge, { variant: statusVar }, d.status || 'unknown'),
            d.machine ? e(Badge, { variant: 'neutral' }, d.machine) : null
          ),
          e('div', { className: 'timeline-item__detail' }, 'Deployed by ' + (d.deployed_by || 'unknown'))
        ),
        e('div', { className: 'timeline-item__time' }, d.deployed_at || d.date || '\u2014')
      )
    })
  )
}

// =========================================================================
// TAB: ROS2 GRAPH
// =========================================================================
var KEY_TOPICS = ['/joint_states', '/tf', '/tf_static', '/robot_description', '/diagnostics']
var NODE_ICONS = {
  'robot_state_publisher': '\uD83E\uDD16',
  'joint_state_publisher': '\u2699\uFE0F',
  'controller_manager': '\uD83C\uDFAE',
  'ros2_control_node': '\uD83D\uDD27',
  'rviz': '\uD83D\uDC41\uFE0F'
}

function getNodeIcon(nodeId) {
  var name = nodeId.replace(/^\//, '')
  for (var key in NODE_ICONS) {
    if (name.indexOf(key) >= 0) return NODE_ICONS[key]
  }
  return '\u25CF'
}

function isKeyTopic(topicId) {
  return KEY_TOPICS.indexOf(topicId) >= 0
}

function renderD3Graph(svgEl, data, opts) {
  var svg = d3.select(svgEl)
  svg.selectAll('*').remove()

  var width = svgEl.clientWidth || 800
  var height = svgEl.clientHeight || 500

  var visibleNodes = data.nodes.slice()
  var visibleEdges = data.edges.slice()

  if (opts.showTopics) {
    visibleNodes = visibleNodes.concat(data.topics.map(function (t) { return Object.assign({}, t) }))
  }
  if (opts.showServices) {
    visibleNodes = visibleNodes.concat(data.services.map(function (s) { return Object.assign({}, s) }))
  }

  if (opts.filterText) {
    var ft = opts.filterText.toLowerCase()
    var matchIds = {}
    visibleNodes.forEach(function (n) {
      if (n.id.toLowerCase().indexOf(ft) >= 0) matchIds[n.id] = true
    })
    visibleEdges.forEach(function (ed) {
      if (matchIds[ed.source] || matchIds[ed.target]) {
        matchIds[ed.source] = true
        matchIds[ed.target] = true
      }
    })
    visibleNodes = visibleNodes.filter(function (n) { return matchIds[n.id] })
  }

  var nodeIdSet = {}
  visibleNodes.forEach(function (n) { nodeIdSet[n.id] = true })
  visibleEdges = visibleEdges.filter(function (ed) {
    return nodeIdSet[ed.source] && nodeIdSet[ed.target]
  })

  if (visibleNodes.length === 0) return

  var defs = svg.append('defs')
  var markerColors = { publishes: '#E8A020', subscribes: '#26A69A', serves: '#AB47BC' }
  Object.keys(markerColors).forEach(function (type) {
    defs.append('marker')
      .attr('id', 'arrow-' + type)
      .attr('viewBox', '0 0 10 6').attr('refX', 10).attr('refY', 3)
      .attr('markerWidth', 8).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,3 L0,6 Z').attr('fill', markerColors[type])
  })

  var g = svg.append('g').attr('class', 'zoom-group')
  var zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', function (event) {
      g.attr('transform', event.transform)
      opts.transformRef.current = event.transform
      updateMinimap()
    })
  svg.call(zoom)

  if (opts.transformRef.current) {
    svg.call(zoom.transform, opts.transformRef.current)
  }

  var simNodes = visibleNodes.map(function (n) { return Object.assign({}, n) })
  var simEdges = visibleEdges.map(function (ed) { return { source: ed.source, target: ed.target, type: ed.type } })

  var simulation = d3.forceSimulation(simNodes)
    .force('link', d3.forceLink(simEdges).id(function (d) { return d.id }).distance(140))
    .force('charge', d3.forceManyBody().strength(-350))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(50))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05))

  opts.simRef.current = simulation

  simulation.alpha(1)
  for (var i = 0; i < 300; i++) simulation.tick()
  simulation.alpha(0).stop()

  var edgeGroup = g.append('g').attr('class', 'edges')
  var links = edgeGroup.selectAll('path')
    .data(simEdges).enter().append('path')
    .attr('stroke', function (d) { return markerColors[d.type] || '#555' })
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .attr('opacity', 0.5)
    .attr('marker-end', function (d) { return 'url(#arrow-' + d.type + ')' })

  var nodeGroup = g.append('g').attr('class', 'nodes')
  var nodeGs = nodeGroup.selectAll('g')
    .data(simNodes).enter().append('g')
    .attr('cursor', 'pointer')
    .call(d3.drag()
      .on('start', function (event, d) { d.fx = d.x; d.fy = d.y })
      .on('drag', function (event, d) { d.fx = event.x; d.fy = event.y; updatePositions() })
      .on('end', function (event, d) { d.fx = null; d.fy = null })
    )

  nodeGs.each(function (d) {
    var el = d3.select(this)
    if (d.type === 'node') {
      el.append('rect').attr('rx', 6).attr('ry', 6).attr('width', 160).attr('height', 36).attr('x', -80).attr('y', -18).attr('fill', '#242424').attr('stroke', '#2E2E2E').attr('stroke-width', 1)
      el.append('rect').attr('width', 3).attr('height', 28).attr('x', -80).attr('y', -14).attr('rx', 1.5).attr('fill', '#E8A020')
      el.append('text').attr('x', -68).attr('dy', '0.35em').attr('font-size', '12px').text(getNodeIcon(d.id))
      el.append('text').attr('x', -54).attr('dy', '0.35em').attr('fill', '#E0E0E0').attr('font-size', '11px').attr('font-family', 'Inter, sans-serif').text(d.id.length > 18 ? d.id.slice(0, 17) + '\u2026' : d.id)
    } else if (d.type === 'topic') {
      var isKey = isKeyTopic(d.id)
      el.append('rect').attr('rx', 12).attr('ry', 12).attr('width', 140).attr('height', 28).attr('x', -70).attr('y', -14).attr('fill', isKey ? 'rgba(232,160,32,0.08)' : '#1A2A1A').attr('stroke', isKey ? '#E8A020' : '#2E4A2E').attr('stroke-width', 1)
      el.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').attr('fill', isKey ? '#E8A020' : '#80C080').attr('font-size', '10px').attr('font-family', 'JetBrains Mono, monospace').text(d.id.length > 18 ? d.id.slice(0, 17) + '\u2026' : d.id)
    } else if (d.type === 'service') {
      el.append('rect').attr('rx', 12).attr('ry', 12).attr('width', 120).attr('height', 24).attr('x', -60).attr('y', -12).attr('fill', 'rgba(171,71,188,0.08)').attr('stroke', '#7B1FA2').attr('stroke-width', 1)
      el.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').attr('fill', '#CE93D8').attr('font-size', '9px').attr('font-family', 'JetBrains Mono, monospace').text(d.id.length > 16 ? d.id.slice(0, 15) + '\u2026' : d.id)
    }
  })

  nodeGs.on('mouseover', function (event, d) {
    var connectedIds = {}
    connectedIds[d.id] = true
    simEdges.forEach(function (ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target
      if (sid === d.id) connectedIds[tid] = true
      if (tid === d.id) connectedIds[sid] = true
    })
    nodeGs.transition().duration(150).attr('opacity', function (n) { return connectedIds[n.id] ? 1 : 0.15 })
    links.transition().duration(150).attr('opacity', function (ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target
      return (sid === d.id || tid === d.id) ? 0.9 : 0.04
    }).attr('stroke-width', function (ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target
      return (sid === d.id || tid === d.id) ? 2.5 : 1.5
    })

    var tooltip = d3.select(svgEl.parentNode.parentNode).select('.ros2-graph-tooltip')
    if (!tooltip.empty()) {
      var info = ''
      if (d.type === 'node') {
        var pubs = 0, subs = 0, srvs = 0
        simEdges.forEach(function (ed) {
          var sid = typeof ed.source === 'object' ? ed.source.id : ed.source
          var tid = typeof ed.target === 'object' ? ed.target.id : ed.target
          if (sid === d.id && ed.type === 'publishes') pubs++
          if (tid === d.id && ed.type === 'subscribes') subs++
          if (sid === d.id && ed.type === 'serves') srvs++
        })
        info = 'Publishers: ' + pubs + ' | Subscribers: ' + subs + ' | Services: ' + srvs
      } else if (d.type === 'topic') {
        info = 'Type: ' + (d.msg_type || 'unknown')
      } else {
        info = 'Type: ' + (d.srv_type || 'unknown')
      }
      tooltip.style('display', 'block')
        .style('left', (event.offsetX + 12) + 'px')
        .style('top', (event.offsetY - 10) + 'px')
      tooltip.select('.ros2-graph-tooltip__name').text(d.id)
      tooltip.select('.ros2-graph-tooltip__row').text(info)
    }
  }).on('mouseout', function () {
    nodeGs.transition().duration(150).attr('opacity', 1)
    links.transition().duration(150).attr('opacity', 0.5).attr('stroke-width', 1.5)
    d3.select(svgEl.parentNode.parentNode).select('.ros2-graph-tooltip').style('display', 'none')
  })

  nodeGs.on('click', function (event, d) {
    event.stopPropagation()
    var detail = { id: d.id, type: d.type, msg_type: d.msg_type || '', srv_type: d.srv_type || '', publishers: [], subscribers: [], services: [] }
    simEdges.forEach(function (ed) {
      var sid = typeof ed.source === 'object' ? ed.source.id : ed.source
      var tid = typeof ed.target === 'object' ? ed.target.id : ed.target
      if (ed.type === 'publishes' && sid === d.id) detail.publishers.push(tid)
      if (ed.type === 'publishes' && tid === d.id) detail.publishers.push(sid)
      if (ed.type === 'subscribes' && tid === d.id) detail.subscribers.push(sid)
      if (ed.type === 'subscribes' && sid === d.id) detail.subscribers.push(tid)
      if (ed.type === 'serves' && sid === d.id) detail.services.push(tid)
      if (ed.type === 'serves' && tid === d.id) detail.services.push(sid)
    })
    opts.setSelected(detail)
  })

  svg.on('click', function () { opts.setSelected(null) })

  function updatePositions() {
    links.attr('d', function (d) {
      var sx = d.source.x, sy = d.source.y, tx = d.target.x, ty = d.target.y
      var dx = tx - sx, dy = ty - sy
      var dr = Math.sqrt(dx * dx + dy * dy) * 0.6
      return 'M' + sx + ',' + sy + 'A' + dr + ',' + dr + ' 0 0,1 ' + tx + ',' + ty
    })
    nodeGs.attr('transform', function (d) { return 'translate(' + d.x + ',' + d.y + ')' })
  }

  updatePositions()

  function updateMinimap() {
    var mm = d3.select(svgEl.parentNode.parentNode).select('.ros2-minimap svg')
    if (mm.empty()) return
    mm.selectAll('*').remove()
    var ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity }
    simNodes.forEach(function (n) {
      if (n.x < ext.x0) ext.x0 = n.x
      if (n.y < ext.y0) ext.y0 = n.y
      if (n.x > ext.x1) ext.x1 = n.x
      if (n.y > ext.y1) ext.y1 = n.y
    })
    var pad = 40
    ext.x0 -= pad; ext.y0 -= pad; ext.x1 += pad; ext.y1 += pad
    var gw = ext.x1 - ext.x0 || 1, gh = ext.y1 - ext.y0 || 1
    var mw = 100, mh = 75
    var sx = mw / gw, sy = mh / gh, s = Math.min(sx, sy)

    simNodes.forEach(function (n) {
      var color = n.type === 'node' ? '#E8A020' : n.type === 'topic' ? '#4CAF50' : '#AB47BC'
      mm.append('circle')
        .attr('cx', (n.x - ext.x0) * s)
        .attr('cy', (n.y - ext.y0) * s)
        .attr('r', 2).attr('fill', color)
    })

    var t = opts.transformRef.current || d3.zoomIdentity
    var vx = -t.x / t.k, vy = -t.y / t.k, vw = width / t.k, vh = height / t.k
    mm.append('rect')
      .attr('x', (vx - ext.x0) * s).attr('y', (vy - ext.y0) * s)
      .attr('width', vw * s).attr('height', vh * s)
      .attr('fill', 'none').attr('stroke', '#E8A020').attr('stroke-width', 1).attr('opacity', 0.7)
  }
  updateMinimap()

  opts.fitViewRef.current = function () {
    var ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity }
    simNodes.forEach(function (n) {
      if (n.x < ext.x0) ext.x0 = n.x
      if (n.y < ext.y0) ext.y0 = n.y
      if (n.x > ext.x1) ext.x1 = n.x
      if (n.y > ext.y1) ext.y1 = n.y
    })
    var pad = 60
    var gw = (ext.x1 - ext.x0 + pad * 2) || 1
    var gh = (ext.y1 - ext.y0 + pad * 2) || 1
    var scale = Math.min(width / gw, height / gh, 2)
    var cx = (ext.x0 + ext.x1) / 2, cy = (ext.y0 + ext.y1) / 2
    var t = d3.zoomIdentity.translate(width / 2 - cx * scale, height / 2 - cy * scale).scale(scale)
    svg.transition().duration(500).call(zoom.transform, t)
  }

  opts.resetZoomRef.current = function () {
    svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity)
  }
}

function RobotROS2Tab(props) {
  var rosStatus = props.rosStatus || 'disconnected'

  var graphState = useState(null)
  var graphData = graphState[0]
  var setGraphData = graphState[1]

  var selectedState = useState(null)
  var selected = selectedState[0]
  var setSelected = selectedState[1]

  var filterState = useState('')
  var filterText = filterState[0]
  var setFilterText = filterState[1]

  var showTopicsState = useState(true)
  var showTopics = showTopicsState[0]
  var setShowTopics = showTopicsState[1]

  var showServicesState = useState(false)
  var showServices = showServicesState[0]
  var setShowServices = showServicesState[1]

  var lastUpdatedState = useState(null)
  var lastUpdated = lastUpdatedState[0]
  var setLastUpdated = lastUpdatedState[1]

  var svgRef = useRef(null)
  var simRef = useRef(null)
  var transformRef = useRef(null)
  var fitViewRef = useRef(null)
  var resetZoomRef = useRef(null)

  useEffect(function () {
    function fetchGraph() {
      authFetch('/api/ros2/graph')
        .then(function (r) { return r.json() })
        .then(function (d) {
          setGraphData(d)
          setLastUpdated(new Date().toLocaleTimeString())
        })
        .catch(function () {})
    }
    fetchGraph()
    var interval = setInterval(fetchGraph, 5000)
    return function () { clearInterval(interval) }
  }, [])

  useEffect(function () {
    if (!graphData || !graphData.online || !svgRef.current) return
    renderD3Graph(svgRef.current, graphData, {
      showTopics: showTopics,
      showServices: showServices,
      filterText: filterText,
      transformRef: transformRef,
      simRef: simRef,
      fitViewRef: fitViewRef,
      resetZoomRef: resetZoomRef,
      setSelected: setSelected
    })
  }, [graphData, showTopics, showServices, filterText])

  if (graphData && !graphData.online) {
    return e('div', { className: 'ros2-offline' },
      e('div', { className: 'ros2-offline__box' },
        e('div', { className: 'ros2-offline__dot' }),
        e('div', { className: 'ros2-offline__title' }, 'ROS2 OFFLINE'),
        e('div', { className: 'ros2-offline__sub' }, 'Start robot stack to visualize node graph'),
        e('a', { className: 'ros2-offline__link', href: '#' }, 'View Documentation')
      )
    )
  }

  if (!graphData) {
    return e('div', { className: 'ros2-offline' },
      e('div', { style: { color: 'var(--text-dim)', fontSize: '12px' } }, 'Loading ROS2 graph...')
    )
  }

  var nodeCount = graphData.nodes ? graphData.nodes.length : 0
  var topicCount = graphData.topics ? graphData.topics.length : 0

  function renderDetailPanel() {
    if (!selected) return null
    var sections = []

    if (selected.type === 'node') {
      if (selected.publishers.length > 0) {
        sections.push(e('div', { key: 'pub', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Publishes to'),
          selected.publishers.map(function (p, i) { return e('div', { key: i, className: 'ros2-detail-panel__item' }, p) })
        ))
      }
      if (selected.subscribers.length > 0) {
        sections.push(e('div', { key: 'sub', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Subscribes to'),
          selected.subscribers.map(function (s, i) { return e('div', { key: i, className: 'ros2-detail-panel__item' }, s) })
        ))
      }
      if (selected.services.length > 0) {
        sections.push(e('div', { key: 'srv', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Services'),
          selected.services.map(function (s, i) { return e('div', { key: i, className: 'ros2-detail-panel__item' }, s) })
        ))
      }
    } else if (selected.type === 'topic') {
      if (selected.msg_type) {
        sections.push(e('div', { key: 'type', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Message Type'),
          e('div', { className: 'ros2-detail-panel__item' }, selected.msg_type)
        ))
      }
      if (selected.publishers.length > 0) {
        sections.push(e('div', { key: 'pub', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Publisher Nodes'),
          selected.publishers.map(function (p, i) { return e('div', { key: i, className: 'ros2-detail-panel__item' }, p) })
        ))
      }
      if (selected.subscribers.length > 0) {
        sections.push(e('div', { key: 'sub', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Subscriber Nodes'),
          selected.subscribers.map(function (s, i) { return e('div', { key: i, className: 'ros2-detail-panel__item' }, s) })
        ))
      }
    } else if (selected.type === 'service') {
      if (selected.srv_type) {
        sections.push(e('div', { key: 'type', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Service Type'),
          e('div', { className: 'ros2-detail-panel__item' }, selected.srv_type)
        ))
      }
      if (selected.services.length > 0) {
        sections.push(e('div', { key: 'srv', className: 'ros2-detail-panel__section' },
          e('div', { className: 'ros2-detail-panel__label' }, 'Server Nodes'),
          selected.services.map(function (s, i) { return e('div', { key: i, className: 'ros2-detail-panel__item' }, s) })
        ))
      }
    }

    return e('div', { className: 'ros2-detail-panel' },
      e('div', {
        className: 'ros2-detail-panel__close',
        onClick: function (ev) { ev.stopPropagation(); setSelected(null) }
      }, '\u00D7'),
      e('div', { className: 'ros2-detail-panel__title' }, selected.id),
      e('div', { className: 'ros2-detail-panel__section' },
        e('div', { className: 'ros2-detail-panel__label' }, 'Type'),
        e('div', { className: 'ros2-detail-panel__item' },
          e(Badge, { variant: selected.type === 'node' ? 'accent' : selected.type === 'topic' ? 'success' : 'info' }, selected.type.toUpperCase())
        )
      ),
      sections
    )
  }

  return e('div', null,
    // Rosbridge status
    e('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' } },
      e(RosBridgeBadge, { status: rosStatus }),
      e('span', { style: { fontSize: '11px', color: 'var(--text-secondary)' } },
        rosStatus === 'connected' ? 'rosbridge connected — live topic subscriptions available' : 'ROS2 graph from backend subprocess'
      )
    ),

    // Controls bar
    e('div', { className: 'ros2-controls' },
      e('button', { onClick: function () {
        authFetch('/api/ros2/graph').then(function (r) { return r.json() }).then(function (d) {
          setGraphData(d)
          setLastUpdated(new Date().toLocaleTimeString())
        }).catch(function () {})
      } }, 'Refresh'),
      e('button', { onClick: function () { if (fitViewRef.current) fitViewRef.current() } }, 'Fit View'),
      e('button', { onClick: function () { if (resetZoomRef.current) resetZoomRef.current() } }, 'Reset Zoom'),
      e('div', { className: 'ros2-controls__sep' }),
      e('button', {
        className: showTopics ? 'active' : '',
        onClick: function () { setShowTopics(!showTopics) }
      }, '\u25CF Topics'),
      e('button', {
        className: showServices ? 'active' : '',
        onClick: function () { setShowServices(!showServices) }
      }, '\u25CF Services'),
      e('div', { className: 'ros2-controls__sep' }),
      e('input', {
        placeholder: 'Filter nodes...',
        value: filterText,
        onChange: function (ev) { setFilterText(ev.target.value) }
      }),
      e('span', { className: 'ros2-controls__count' },
        nodeCount + ' nodes \u00B7 ' + topicCount + ' topics' +
        (lastUpdated ? ' \u00B7 ' + lastUpdated : '')
      )
    ),

    // Graph container
    e('div', { className: 'ros2-graph-wrap' },
      e('div', { className: 'ros2-graph-container' },
        e('svg', { ref: svgRef })
      ),
      e('div', { className: 'ros2-graph-tooltip', style: { display: 'none' } },
        e('div', { className: 'ros2-graph-tooltip__name' }),
        e('div', { className: 'ros2-graph-tooltip__row' })
      ),
      renderDetailPanel(),
      e('div', { className: 'ros2-minimap' },
        e('svg', null)
      )
    ),

    // Node and topic lists
    e('div', { className: 'grid-2' },
      e('div', { className: 'card' },
        e('div', { className: 'card__header' },
          e('span', { className: 'card__title' }, 'ROS2 Nodes'),
          e(Badge, { variant: 'accent' }, nodeCount + ' active')
        ),
        graphData.nodes.map(function (n) {
          return e('div', { key: n.id, style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 0', borderBottom: '1px solid var(--border)' } },
            e(StatusDot, { status: 'online' }),
            e('span', { style: { flex: 1, fontFamily: 'var(--font-mono)', fontSize: '11px' } }, n.id),
            e('span', { style: { fontSize: '10px', color: 'var(--text-dim)' } },
              (n.publishers ? n.publishers.length : 0) + ' pub \u00B7 ' + (n.subscribers ? n.subscribers.length : 0) + ' sub'
            )
          )
        })
      ),
      e('div', { className: 'card' },
        e('div', { className: 'card__header' },
          e('span', { className: 'card__title' }, 'Topics'),
          e(Badge, { variant: 'success' }, topicCount + ' active')
        ),
        graphData.topics.map(function (t) {
          return e('div', { key: t.id, style: { display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 0', borderBottom: '1px solid var(--border)' } },
            e('span', { style: { width: '8px', height: '8px', borderRadius: '50%', background: isKeyTopic(t.id) ? 'var(--accent)' : 'var(--success)', flexShrink: 0 } }),
            e('span', { style: { flex: 1, fontFamily: 'var(--font-mono)', fontSize: '11px', color: isKeyTopic(t.id) ? 'var(--accent)' : 'var(--text)' } }, t.id),
            e('span', { style: { fontSize: '10px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' } }, t.msg_type || '')
          )
        })
      )
    )
  )
}

// ── Digital Twin Tab ─────────────────────────────────────
function RobotDigitalTwinTab(props) {
  var robotId = props.robotId || 'dobot_cr10'
  var rosStatus = props.rosStatus || 'disconnected'

  var simStatusState = useState({ running: false, mode: 'STANDALONE', uptime: 0 })
  var simStatus = simStatusState[0]; var setSimStatus = simStatusState[1]
  var twinModeState = useState('STANDALONE')
  var twinMode = twinModeState[0]; var setTwinMode = twinModeState[1]
  var loadingState = useState(false)
  var loading = loadingState[0]; var setLoading = loadingState[1]
  var msgState = useState('')
  var msg = msgState[0]; var setMsg = msgState[1]
  var meshState = useState(null)
  var meshes = meshState[0]; var setMeshes = meshState[1]

  // Camera/Lens/Payload state
  var camerasState = useState([])
  var cameras = camerasState[0]; var setCameras = camerasState[1]
  var lensesState = useState([])
  var lenses = lensesState[0]; var setLenses = lensesState[1]
  var accessoriesState = useState([])
  var accessories = accessoriesState[0]; var setAccessories = accessoriesState[1]
  var selectedCameraState = useState('')
  var selectedCamera = selectedCameraState[0]; var setSelectedCamera = selectedCameraState[1]
  var selectedLensState = useState('')
  var selectedLens = selectedLensState[0]; var setSelectedLens = selectedLensState[1]
  var selectedAccessoriesState = useState([])
  var selectedAccessories = selectedAccessoriesState[0]; var setSelectedAccessories = selectedAccessoriesState[1]
  var payloadResultState = useState(null)
  var payloadResult = payloadResultState[0]; var setPayloadResult = payloadResultState[1]

  // Get the ROS instance
  var ros = null
  try { ros = getRos() } catch (ex) {}

  // Poll simulation status
  useEffect(function () {
    function fetchStatus() {
      authFetch('/api/simulation/status').then(function (r) { return r.json() }).then(setSimStatus).catch(function () {})
    }
    fetchStatus()
    var interval = setInterval(fetchStatus, 3000)
    return function () { clearInterval(interval) }
  }, [])

  // Fetch mesh info
  useEffect(function () {
    authFetch('/api/robot/' + robotId + '/meshes').then(function (r) { return r.json() }).then(setMeshes).catch(function () {})
  }, [])

  // Fetch camera/lens/accessories
  useEffect(function () {
    authFetch('/api/cameras').then(function (r) { return r.json() }).then(setCameras).catch(function () {})
    authFetch('/api/lenses').then(function (r) { return r.json() }).then(setLenses).catch(function () {})
    authFetch('/api/accessories').then(function (r) { return r.json() }).then(setAccessories).catch(function () {})
  }, [])

  function startSim() {
    setLoading(true)
    authFetch('/api/simulation/start', { method: 'POST' })
      .then(function (r) { return r.json() })
      .then(function () { setMsg('Simulation started'); setLoading(false) })
      .catch(function () { setMsg('Failed to start'); setLoading(false) })
  }

  function stopSim() {
    setLoading(true)
    authFetch('/api/simulation/stop', { method: 'POST' })
      .then(function (r) { return r.json() })
      .then(function () { setMsg('Simulation stopped'); setLoading(false) })
      .catch(function () { setMsg('Failed to stop'); setLoading(false) })
  }

  function changeTwinMode(newMode) {
    setTwinMode(newMode)
    authFetch('/api/robot/' + robotId + '/twin/mode', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: newMode })
    }).then(function (r) { return r.json() }).then(function (d) {
      setMsg('Mode: ' + d.mode)
      setTimeout(function () { setMsg('') }, 2000)
    }).catch(function () {})
  }

  function calculatePayload() {
    if (!selectedCamera || !selectedLens) return
    authFetch('/api/payload/calculate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_id: selectedCamera, lens_id: selectedLens, accessory_ids: selectedAccessories })
    }).then(function (r) { return r.json() }).then(setPayloadResult).catch(function () {})
  }

  function formatUptime(s) {
    if (s < 60) return Math.round(s) + 's'
    if (s < 3600) return Math.floor(s / 60) + 'm ' + Math.round(s % 60) + 's'
    return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm'
  }

  var modes = ['STANDALONE', 'MIRROR', 'SHADOW', 'COMMAND']
  var modeDescriptions = {
    STANDALONE: 'Free simulation \u2014 no real robot connection',
    MIRROR: 'Real robot drives the digital twin (read-only)',
    SHADOW: 'Twin follows real robot with configurable delay',
    COMMAND: 'Twin generates motion commands for real robot'
  }

  var cardStyle = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '16px' }
  var headerStyle = { fontSize: '13px', fontWeight: 600, color: 'var(--accent)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }
  var labelStyle = { fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }
  var valueStyle = { fontSize: '14px', fontFamily: 'var(--font-mono)', fontWeight: 500 }
  var btnBase = { padding: '8px 16px', borderRadius: 'var(--radius-sm)', fontSize: '12px', fontWeight: 600, cursor: 'pointer', border: 'none', textTransform: 'uppercase' }

  return e('div', { style: { display: 'flex', flexDirection: 'column', gap: '16px' } },

    // ── 3D Viewer ──
    e('div', { style: Object.assign({}, cardStyle, { height: '500px', padding: 0, overflow: 'hidden' }) },
      e(RosViewer, {
        ros: ros,
        rosStatus: rosStatus,
        robotId: robotId,
        fixedFrame: 'base_link',
        topics: { urdf: true, jointStates: '/joint_states' },
        onReconnect: function () { rosReconnect() }
      })
    ),

    // ── Camera/Payload Selector ──
    e('div', { style: cardStyle },
      e('div', { style: headerStyle }, 'Camera Payload Configuration'),
      e('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '12px' } },
        e('div', null,
          e('div', { style: labelStyle }, 'Camera Body'),
          e('select', {
            value: selectedCamera,
            onChange: function (ev) { setSelectedCamera(ev.target.value) },
            style: { width: '100%', padding: '6px 8px', borderRadius: '4px', border: '1px solid var(--border)', background: 'var(--raised)', color: 'var(--text)', fontSize: '12px' }
          },
            e('option', { value: '' }, '-- Select camera --'),
            cameras.map(function (c) {
              return e('option', { key: c.id, value: c.id }, c.name + ' (' + c.mass_kg + ' kg)')
            })
          )
        ),
        e('div', null,
          e('div', { style: labelStyle }, 'Lens'),
          e('select', {
            value: selectedLens,
            onChange: function (ev) { setSelectedLens(ev.target.value) },
            style: { width: '100%', padding: '6px 8px', borderRadius: '4px', border: '1px solid var(--border)', background: 'var(--raised)', color: 'var(--text)', fontSize: '12px' }
          },
            e('option', { value: '' }, '-- Select lens --'),
            lenses.map(function (l) {
              return e('option', { key: l.id, value: l.id }, l.name + ' (' + l.mass_kg + ' kg)')
            })
          )
        ),
        e('div', null,
          e('div', { style: labelStyle }, 'Payload Action'),
          e('button', {
            onClick: calculatePayload,
            disabled: !selectedCamera || !selectedLens,
            style: Object.assign({}, btnBase, {
              width: '100%', marginTop: '0',
              background: selectedCamera && selectedLens ? 'var(--accent)' : 'var(--raised)',
              color: selectedCamera && selectedLens ? '#000' : 'var(--text-dim)'
            })
          }, 'Calculate Payload')
        )
      ),

      // Payload result
      payloadResult ? e('div', { style: { background: 'var(--raised)', borderRadius: 'var(--radius-sm)', padding: '12px', marginTop: '4px' } },
        e('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '12px' } },
          e('div', null,
            e('div', { style: labelStyle }, 'Total Mass'),
            e('div', { style: Object.assign({}, valueStyle, { color: payloadResult.within_limits ? 'var(--success)' : 'var(--danger)' }) },
              payloadResult.total_mass_kg.toFixed(2) + ' kg')
          ),
          e('div', null,
            e('div', { style: labelStyle }, 'CoM Offset'),
            e('div', { style: valueStyle },
              payloadResult.com_offset_mm ? payloadResult.com_offset_mm.x.toFixed(1) + ', ' + payloadResult.com_offset_mm.y.toFixed(1) + ', ' + payloadResult.com_offset_mm.z.toFixed(1) + ' mm' : '\u2014')
          ),
          e('div', null,
            e('div', { style: labelStyle }, 'Within Limits'),
            e('div', { style: { display: 'flex', alignItems: 'center', gap: '6px' } },
              e(StatusDot, { status: payloadResult.within_limits ? 'online' : 'offline' }),
              e('span', { style: Object.assign({}, valueStyle, { color: payloadResult.within_limits ? 'var(--success)' : 'var(--danger)' }) },
                payloadResult.within_limits ? 'YES' : 'EXCEEDS')
            )
          ),
          e('div', null,
            e('div', { style: labelStyle }, 'Safety'),
            e('div', { style: valueStyle },
              payloadResult.warnings && payloadResult.warnings.length > 0
                ? e('span', { style: { color: 'var(--warning)', fontSize: '11px' } }, payloadResult.warnings[0])
                : e('span', { style: { color: 'var(--success)' } }, 'OK'))
          )
        )
      ) : null
    ),

    // ── Simulation Control Card ──
    e('div', { style: cardStyle },
      e('div', { style: headerStyle }, 'Isaac Sim Control'),
      e('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '16px', marginBottom: '16px' } },
        e('div', null,
          e('div', { style: labelStyle }, 'Status'),
          e('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
            e(StatusDot, { status: simStatus.running ? 'online' : 'offline' }),
            e('span', { style: valueStyle }, simStatus.running ? 'Running' : 'Stopped')
          )
        ),
        e('div', null,
          e('div', { style: labelStyle }, 'Mode'),
          e('div', { style: valueStyle }, simStatus.mode || 'N/A')
        ),
        e('div', null,
          e('div', { style: labelStyle }, 'Uptime'),
          e('div', { style: valueStyle }, simStatus.running ? formatUptime(simStatus.uptime) : '\u2014')
        ),
        e('div', null,
          e('div', { style: labelStyle }, 'PID'),
          e('div', { style: Object.assign({}, valueStyle, { fontSize: '12px' }) }, simStatus.pid || '\u2014')
        )
      ),
      e('div', { style: { display: 'flex', gap: '8px', alignItems: 'center' } },
        !simStatus.running
          ? e('button', {
              onClick: startSim, disabled: loading,
              style: Object.assign({}, btnBase, { background: 'var(--success)', color: '#fff' })
            }, loading ? 'Starting...' : 'Start Simulation')
          : e('button', {
              onClick: stopSim, disabled: loading,
              style: Object.assign({}, btnBase, { background: 'var(--danger)', color: '#fff' })
            }, loading ? 'Stopping...' : 'Stop Simulation'),
        msg ? e('span', { style: { fontSize: '12px', color: 'var(--success)', marginLeft: '8px' } }, msg) : null
      )
    ),

    // ── Twin Mode Selector ──
    e('div', { style: cardStyle },
      e('div', { style: headerStyle }, 'Digital Twin Mode'),
      e('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px' } },
        modes.map(function (m) {
          var isActive = (simStatus.mode || twinMode) === m
          return e('button', {
            key: m,
            onClick: function () { changeTwinMode(m) },
            style: Object.assign({}, btnBase, {
              padding: '12px 8px',
              background: isActive ? 'var(--accent)' : 'var(--raised)',
              color: isActive ? '#0a0a0a' : 'var(--text)',
              border: '1px solid ' + (isActive ? 'var(--accent)' : 'var(--border)'),
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px'
            })
          },
            e('span', { style: { fontSize: '12px', fontWeight: 700 } }, m),
            e('span', { style: { fontSize: '10px', fontWeight: 400, opacity: 0.7, textTransform: 'none' } }, modeDescriptions[m])
          )
        })
      )
    ),

    // ── Mesh Info Card ──
    meshes ? e('div', { style: cardStyle },
      e('div', { style: headerStyle }, 'Robot Meshes (' + meshes.length + ' links)'),
      e('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '8px' } },
        meshes.map(function (m) {
          return e('div', { key: m.link_name, style: { background: 'var(--raised)', borderRadius: 'var(--radius-sm)', padding: '10px' } },
            e('div', { style: { fontSize: '12px', fontWeight: 600, color: 'var(--accent)', marginBottom: '4px' } }, m.link_name),
            e('div', { style: { fontSize: '10px', color: 'var(--text-secondary)' } }, 'Faces: ' + m.visual_face_count.toLocaleString() + ' visual / ' + m.collision_face_count + ' collision'),
            e('div', { style: { fontSize: '10px', color: 'var(--text-secondary)' } },
              'BBox: ' + (m.bounding_box.x * 1000).toFixed(0) + ' \u00D7 ' + (m.bounding_box.y * 1000).toFixed(0) + ' \u00D7 ' + (m.bounding_box.z * 1000).toFixed(0) + ' mm'),
            e('div', { style: { fontSize: '10px', color: 'var(--text-secondary)' } }, 'Mass: ' + m.estimated_mass_kg.toFixed(1) + ' kg')
          )
        })
      )
    ) : null,

    // ── Quick Actions Card ──
    e('div', { style: cardStyle },
      e('div', { style: headerStyle }, 'Quick Actions'),
      e('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
        e('button', { style: Object.assign({}, btnBase, { background: 'var(--raised)', border: '1px solid var(--border)' }),
          onClick: function () {
            authFetch('/api/simulation/start', { method: 'POST' }).catch(function () {})
            setMsg('Launching full stack...')
          }
        }, 'Launch Full Stack'),
        e('button', { style: Object.assign({}, btnBase, { background: 'var(--raised)', border: '1px solid var(--border)' }),
          onClick: function () { changeTwinMode('MIRROR') }
        }, 'Start Mirror Mode'),
        e('button', { style: Object.assign({}, btnBase, { background: 'var(--raised)', border: '1px solid var(--border)' }),
          onClick: function () { changeTwinMode('STANDALONE') }
        }, 'Disconnect Twin'),
        e('button', { style: Object.assign({}, btnBase, { background: 'var(--raised)', border: '1px solid var(--danger)' }),
          onClick: stopSim
        }, 'Emergency Stop Sim')
      )
    )
  )
}

export { RobotDetailPage }
