/**
 * RosViewer — 3D robot viewer using Three.js + roslibjs
 *
 * Loads URDF from backend API, renders meshes, subscribes to
 * /joint_states via rosbridge for live joint animation.
 *
 * Props:
 *   ros          — ROSLIB.Ros instance (from rosConnection.js)
 *   rosStatus    — 'connected' | 'disconnected' | 'error'
 *   fixedFrame   — TF fixed frame (default 'base_link')
 *   robotId      — robot ID for URDF API (default 'dobot_cr10')
 *   topics       — object enabling visualization layers:
 *     { urdf: true, jointStates: '/joint_states' }
 *   onReconnect  — callback when user clicks reconnect button
 */
import React, { useState, useEffect, useRef, useCallback } from 'react'
import * as THREE from 'three'
import ROSLIB from '../utils/roslib-browser.js'
import { authFetch } from '../utils/authFetch'

var e = React.createElement

// Simple OBJ loader for robot meshes (Three.js 0.128 compatible)
function parseOBJ(text) {
  var vertices = []
  var normals = []
  var uvs = []
  var faces = []
  var lines = text.split('\n')
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim()
    if (line.length === 0 || line[0] === '#') continue
    var parts = line.split(/\s+/)
    if (parts[0] === 'v') {
      vertices.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]))
    } else if (parts[0] === 'vn') {
      normals.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]))
    } else if (parts[0] === 'vt') {
      uvs.push(parseFloat(parts[1]), parseFloat(parts[2]))
    } else if (parts[0] === 'f') {
      // Triangulate faces with > 3 vertices
      var faceVerts = []
      for (var j = 1; j < parts.length; j++) {
        var indices = parts[j].split('/')
        faceVerts.push({
          v: parseInt(indices[0]) - 1,
          vt: indices[1] ? parseInt(indices[1]) - 1 : -1,
          vn: indices[2] ? parseInt(indices[2]) - 1 : -1
        })
      }
      for (var k = 1; k < faceVerts.length - 1; k++) {
        faces.push(faceVerts[0], faceVerts[k], faceVerts[k + 1])
      }
    }
  }

  var geometry = new THREE.BufferGeometry()
  var pos = new Float32Array(faces.length * 3)
  var norm = normals.length > 0 ? new Float32Array(faces.length * 3) : null

  for (var fi = 0; fi < faces.length; fi++) {
    var face = faces[fi]
    pos[fi * 3] = vertices[face.v * 3]
    pos[fi * 3 + 1] = vertices[face.v * 3 + 1]
    pos[fi * 3 + 2] = vertices[face.v * 3 + 2]
    if (norm && face.vn >= 0) {
      norm[fi * 3] = normals[face.vn * 3]
      norm[fi * 3 + 1] = normals[face.vn * 3 + 1]
      norm[fi * 3 + 2] = normals[face.vn * 3 + 2]
    }
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  if (norm) geometry.setAttribute('normal', new THREE.BufferAttribute(norm, 3))
  else geometry.computeVertexNormals()

  return geometry
}

// Parse STL binary
function parseSTLBinary(buffer) {
  var dv = new DataView(buffer)
  var triangles = dv.getUint32(80, true)
  var geometry = new THREE.BufferGeometry()
  var pos = new Float32Array(triangles * 9)
  var norm = new Float32Array(triangles * 9)

  for (var i = 0; i < triangles; i++) {
    var offset = 84 + i * 50
    var nx = dv.getFloat32(offset, true)
    var ny = dv.getFloat32(offset + 4, true)
    var nz = dv.getFloat32(offset + 8, true)
    for (var j = 0; j < 3; j++) {
      var vOff = offset + 12 + j * 12
      var base = i * 9 + j * 3
      pos[base] = dv.getFloat32(vOff, true)
      pos[base + 1] = dv.getFloat32(vOff + 4, true)
      pos[base + 2] = dv.getFloat32(vOff + 8, true)
      norm[base] = nx
      norm[base + 1] = ny
      norm[base + 2] = nz
    }
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geometry.setAttribute('normal', new THREE.BufferAttribute(norm, 3))
  return geometry
}

// Load mesh by URL (auto-detect STL vs OBJ)
function loadMesh(url) {
  return new Promise(function (resolve, reject) {
    if (url.toLowerCase().endsWith('.stl')) {
      fetch(url).then(function (r) { return r.arrayBuffer() }).then(function (buf) {
        resolve(parseSTLBinary(buf))
      }).catch(reject)
    } else {
      fetch(url).then(function (r) { return r.text() }).then(function (text) {
        resolve(parseOBJ(text))
      }).catch(reject)
    }
  })
}

// DH parameters for Dobot CR10 (matching URDF)
var CR10_JOINTS = [
  { name: 'J1', axis: [0, 0, 1], origin: [0, 0, 0.1765], rpy: [0, 0, 0] },
  { name: 'J2', axis: [0, 0, 1], origin: [0, 0, 0], rpy: [Math.PI / 2, 0, 0] },
  { name: 'J3', axis: [0, 0, 1], origin: [0.607, 0, 0], rpy: [0, 0, 0] },
  { name: 'J4', axis: [0, 0, 1], origin: [0.568, 0, 0], rpy: [-Math.PI / 2, 0, 0] },
  { name: 'J5', axis: [0, 0, 1], origin: [0, 0, 0.191], rpy: [Math.PI / 2, 0, 0] },
  { name: 'J6', axis: [0, 0, 1], origin: [0, 0, 0.125], rpy: [-Math.PI / 2, 0, 0] }
]

var LINK_NAMES = ['base_link', 'Link1', 'Link2', 'Link3', 'Link4', 'Link5', 'Link6']

var LINK_MATERIALS = [
  new THREE.MeshPhongMaterial({ color: 0x3a3a3a, specular: 0x444444, shininess: 60 }),
  new THREE.MeshPhongMaterial({ color: 0xE8A020, specular: 0x666666, shininess: 80 }),
  new THREE.MeshPhongMaterial({ color: 0x4a4a4a, specular: 0x444444, shininess: 60 }),
  new THREE.MeshPhongMaterial({ color: 0xE8A020, specular: 0x666666, shininess: 80 }),
  new THREE.MeshPhongMaterial({ color: 0x4a4a4a, specular: 0x444444, shininess: 60 }),
  new THREE.MeshPhongMaterial({ color: 0xE8A020, specular: 0x666666, shininess: 80 }),
  new THREE.MeshPhongMaterial({ color: 0x3a3a3a, specular: 0x444444, shininess: 60 })
]

function RosViewer(props) {
  var containerRef = useRef(null)
  var sceneRef = useRef(null)
  var rendererRef = useRef(null)
  var cameraRef = useRef(null)
  var jointGroupsRef = useRef([])
  var animFrameRef = useRef(null)
  var rosSubRef = useRef(null)

  var rosStatus = props.rosStatus || 'disconnected'
  var topics = props.topics || {}

  var statusState = useState({ topicHz: 0, activeTopics: 0, frame: props.fixedFrame || 'base_link' })
  var hud = statusState[0]
  var setHud = statusState[1]
  var hzCountRef = useRef(0)
  var lastHzUpdateRef = useRef(Date.now())

  // Initialize Three.js scene
  useEffect(function () {
    var container = containerRef.current
    if (!container) return

    var width = container.clientWidth
    var height = container.clientHeight || 500

    // Scene
    var scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0d1117)
    sceneRef.current = scene

    // Camera
    var camera = new THREE.PerspectiveCamera(45, width / height, 0.01, 100)
    camera.position.set(1.5, 1.0, 1.5)
    camera.lookAt(0, 0.5, 0)
    cameraRef.current = camera

    // Renderer
    var renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    container.appendChild(renderer.domElement)
    rendererRef.current = renderer

    // Lights
    var ambient = new THREE.AmbientLight(0xffffff, 0.4)
    scene.add(ambient)
    var directional = new THREE.DirectionalLight(0xffffff, 0.8)
    directional.position.set(2, 4, 3)
    directional.castShadow = true
    scene.add(directional)
    var fill = new THREE.DirectionalLight(0x6688cc, 0.3)
    fill.position.set(-2, 1, -1)
    scene.add(fill)

    // Grid
    var grid = new THREE.GridHelper(4, 20, 0x1a2a1a, 0x1a1a2a)
    grid.position.y = 0
    scene.add(grid)

    // Axes helper (small)
    var axes = new THREE.AxesHelper(0.15)
    scene.add(axes)

    // Orbit controls (manual implementation — mouse drag to rotate)
    var isDragging = false
    var isRightDrag = false
    var prevMouse = { x: 0, y: 0 }
    var spherical = { theta: Math.PI / 4, phi: Math.PI / 3, radius: 2.5 }
    var target = new THREE.Vector3(0, 0.4, 0)

    function updateCamera() {
      camera.position.x = target.x + spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta)
      camera.position.y = target.y + spherical.radius * Math.cos(spherical.phi)
      camera.position.z = target.z + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta)
      camera.lookAt(target)
    }
    updateCamera()

    function onMouseDown(ev) {
      isDragging = true
      isRightDrag = ev.button === 2
      prevMouse.x = ev.clientX
      prevMouse.y = ev.clientY
    }
    function onMouseMove(ev) {
      if (!isDragging) return
      var dx = ev.clientX - prevMouse.x
      var dy = ev.clientY - prevMouse.y
      prevMouse.x = ev.clientX
      prevMouse.y = ev.clientY

      if (isRightDrag) {
        // Pan
        var panSpeed = 0.002 * spherical.radius
        var right = new THREE.Vector3()
        right.crossVectors(camera.up, new THREE.Vector3().subVectors(camera.position, target)).normalize()
        var up = camera.up.clone()
        target.add(right.multiplyScalar(dx * panSpeed))
        target.add(up.multiplyScalar(-dy * panSpeed))
      } else {
        // Rotate
        spherical.theta -= dx * 0.005
        spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi + dy * 0.005))
      }
      updateCamera()
    }
    function onMouseUp() { isDragging = false; isRightDrag = false }
    function onWheel(ev) {
      ev.preventDefault()
      spherical.radius = Math.max(0.5, Math.min(10, spherical.radius + ev.deltaY * 0.002))
      updateCamera()
    }
    function onContextMenu(ev) { ev.preventDefault() }

    renderer.domElement.addEventListener('mousedown', onMouseDown)
    renderer.domElement.addEventListener('mousemove', onMouseMove)
    renderer.domElement.addEventListener('mouseup', onMouseUp)
    renderer.domElement.addEventListener('mouseleave', onMouseUp)
    renderer.domElement.addEventListener('wheel', onWheel, { passive: false })
    renderer.domElement.addEventListener('contextmenu', onContextMenu)

    // Load robot meshes
    var robotGroup = new THREE.Group()
    scene.add(robotGroup)

    var jointGroups = []
    jointGroupsRef.current = jointGroups

    // Build kinematic chain
    var parentGroup = robotGroup

    // Base link (no joint)
    var baseGroup = new THREE.Group()
    parentGroup.add(baseGroup)

    loadMesh('/static/meshes/visual/base_link.STL').then(function (geo) {
      var mesh = new THREE.Mesh(geo, LINK_MATERIALS[0])
      mesh.receiveShadow = true
      baseGroup.add(mesh)
    }).catch(function () {
      // Fallback: cylinder for base
      var geo = new THREE.CylinderGeometry(0.08, 0.1, 0.05, 32)
      baseGroup.add(new THREE.Mesh(geo, LINK_MATERIALS[0]))
    })

    parentGroup = baseGroup

    // Joints + links
    for (var i = 0; i < CR10_JOINTS.length; i++) {
      (function (idx) {
        var joint = CR10_JOINTS[idx]
        var linkName = LINK_NAMES[idx + 1]

        // Create joint group at the joint origin
        var jointGroup = new THREE.Group()
        jointGroup.position.set(joint.origin[0], joint.origin[1], joint.origin[2])

        // Apply RPY rotation
        if (joint.rpy[0] !== 0 || joint.rpy[1] !== 0 || joint.rpy[2] !== 0) {
          var euler = new THREE.Euler(joint.rpy[0], joint.rpy[1], joint.rpy[2], 'XYZ')
          jointGroup.setRotationFromEuler(euler)
        }

        parentGroup.add(jointGroup)

        // The rotation group (this is what gets animated)
        var rotGroup = new THREE.Group()
        jointGroup.add(rotGroup)
        jointGroups.push({ group: rotGroup, axis: joint.axis })

        // Load mesh for this link
        loadMesh('/static/meshes/visual/' + linkName + '.STL').then(function (geo) {
          var mesh = new THREE.Mesh(geo, LINK_MATERIALS[idx + 1])
          mesh.castShadow = true
          rotGroup.add(mesh)
        }).catch(function () {
          // Fallback: simple box
          var geo = new THREE.BoxGeometry(0.05, 0.05, 0.15)
          rotGroup.add(new THREE.Mesh(geo, LINK_MATERIALS[idx + 1]))
        })

        parentGroup = rotGroup
      })(i)
    }

    // Animation loop
    function animate() {
      animFrameRef.current = requestAnimationFrame(animate)
      renderer.render(scene, camera)
    }
    animate()

    // Resize observer
    var ro = new ResizeObserver(function (entries) {
      var entry = entries[0]
      if (!entry) return
      var w = entry.contentRect.width
      var h = entry.contentRect.height
      if (w > 0 && h > 0) {
        camera.aspect = w / h
        camera.updateProjectionMatrix()
        renderer.setSize(w, h)
      }
    })
    ro.observe(container)

    return function () {
      ro.disconnect()
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      renderer.domElement.removeEventListener('mousedown', onMouseDown)
      renderer.domElement.removeEventListener('mousemove', onMouseMove)
      renderer.domElement.removeEventListener('mouseup', onMouseUp)
      renderer.domElement.removeEventListener('mouseleave', onMouseUp)
      renderer.domElement.removeEventListener('wheel', onWheel)
      renderer.domElement.removeEventListener('contextmenu', onContextMenu)
      renderer.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  // Subscribe to /joint_states via rosbridge when connected
  useEffect(function () {
    if (!props.ros || rosStatus !== 'connected') return
    if (!topics.jointStates) return

    var topic = new ROSLIB.Topic({
      ros: props.ros,
      name: topics.jointStates || '/joint_states',
      messageType: 'sensor_msgs/JointState'
    })

    topic.subscribe(function (msg) {
      hzCountRef.current++
      var now = Date.now()
      if (now - lastHzUpdateRef.current >= 1000) {
        setHud(function (prev) {
          return Object.assign({}, prev, { topicHz: hzCountRef.current, activeTopics: 1 })
        })
        hzCountRef.current = 0
        lastHzUpdateRef.current = now
      }

      // Update joint rotations
      var positions = msg.position || []
      var jointGroups = jointGroupsRef.current
      for (var i = 0; i < Math.min(positions.length, jointGroups.length); i++) {
        var jg = jointGroups[i]
        var angle = positions[i]
        // Rotate around the joint axis (all Z for CR10 URDF)
        if (jg.axis[2] === 1) {
          jg.group.rotation.z = angle
        } else if (jg.axis[1] === 1) {
          jg.group.rotation.y = angle
        } else if (jg.axis[0] === 1) {
          jg.group.rotation.x = angle
        }
      }
    })

    rosSubRef.current = topic

    return function () {
      if (rosSubRef.current) {
        rosSubRef.current.unsubscribe()
        rosSubRef.current = null
      }
    }
  }, [props.ros, rosStatus, topics.jointStates])

  // Also support joint updates from dashboard WebSocket (fallback when rosbridge not available)
  useEffect(function () {
    if (rosStatus === 'connected' && topics.jointStates) return // rosbridge takes priority

    var robotId = props.robotId || 'dobot_cr10'
    var wsToken = localStorage.getItem('mc_token') || ''
    var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    var ws = null
    var reconnectTimer = null

    function connect() {
      ws = new WebSocket(protocol + '//' + location.host + '/ws/robot/' + robotId + '?token=' + encodeURIComponent(wsToken))
      ws.onmessage = function (evt) {
        try {
          var msg = JSON.parse(evt.data)
          if (msg.type !== 'robot_status' || !msg.data || !msg.data.joints) return
          var joints = msg.data.joints
          var jointGroups = jointGroupsRef.current
          for (var i = 0; i < Math.min(joints.length, jointGroups.length); i++) {
            var angle = joints[i].position || 0 // radians
            var jg = jointGroups[i]
            if (jg.axis[2] === 1) jg.group.rotation.z = angle
            else if (jg.axis[1] === 1) jg.group.rotation.y = angle
            else if (jg.axis[0] === 1) jg.group.rotation.x = angle
          }
        } catch (ex) { /* ignore */ }
      }
      ws.onclose = function () { reconnectTimer = setTimeout(connect, 3000) }
    }
    connect()

    return function () {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) try { ws.close() } catch (ex) { /* ignore */ }
    }
  }, [props.robotId, rosStatus, topics.jointStates])

  return e('div', { style: { position: 'relative', width: '100%', height: '100%', minHeight: '400px' } },
    // Three.js canvas container
    e('div', {
      ref: containerRef,
      style: { width: '100%', height: '100%', minHeight: '400px', borderRadius: 'var(--radius)', overflow: 'hidden' }
    }),

    // HUD overlay (top-left)
    e('div', {
      style: {
        position: 'absolute', top: '8px', left: '8px',
        background: 'rgba(13,17,23,0.85)', borderRadius: '6px', padding: '6px 10px',
        fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-secondary)',
        display: 'flex', flexDirection: 'column', gap: '2px', pointerEvents: 'none'
      }
    },
      e('div', null, 'Frame: ', e('span', { style: { color: 'var(--accent)' } }, hud.frame)),
      e('div', null, 'ROS: ', e('span', { style: { color: rosStatus === 'connected' ? 'var(--success)' : 'var(--danger)' } }, rosStatus)),
      rosStatus === 'connected' ? e('div', null, 'Hz: ', e('span', { style: { color: 'var(--text)' } }, hud.topicHz)) : null
    ),

    // Offline overlay
    rosStatus !== 'connected' && !topics.jointStates
      ? e('div', {
          style: {
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            background: 'rgba(13,17,23,0.9)', borderRadius: '12px', padding: '24px 32px',
            textAlign: 'center', border: '1px solid var(--border)'
          }
        },
          e('div', { style: { fontSize: '14px', fontWeight: 600, color: 'var(--text)', marginBottom: '8px' } }, 'ROS2 Offline'),
          e('div', { style: { fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' } }, 'Using dashboard WebSocket fallback'),
          props.onReconnect
            ? e('button', {
                onClick: props.onReconnect,
                style: {
                  padding: '6px 16px', borderRadius: '6px', fontSize: '11px', fontWeight: 600,
                  background: 'var(--accent)', color: '#000', border: 'none', cursor: 'pointer'
                }
              }, 'Reconnect rosbridge')
            : null
        )
      : null
  )
}

export { RosViewer }
